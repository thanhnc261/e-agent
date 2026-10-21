"""Run continuation state shared by the coordinator mixins (Phase 1 split of coordinator.py).

ContinuationMixin is the base of every coordinator mixin. It declares the
attributes RunCoordinator.__init__ sets and, for type checking only, the
methods one mixin calls on another (tests/unit/kernel/test_structure.py keeps
each stub matched to its one real method). It implements continuation load,
persist and snapshot, and the budgeted `_timed` call wrapper.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from datetime import datetime, timedelta
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from e_agent.contracts.action import ActionRecord, ActionState
from e_agent.contracts.approval import ApprovalRecord
from e_agent.contracts.capability import CapabilityBinding
from e_agent.contracts.common import new_id
from e_agent.contracts.context import Budgets, TaskContext
from e_agent.contracts.context_pack import ContextRoute
from e_agent.contracts.conversation import CarriedRun
from e_agent.contracts.events import RunEventType
from e_agent.contracts.evidence import Completeness
from e_agent.contracts.features import FeatureMode, RunModes
from e_agent.contracts.grounding import ProposalRationale
from e_agent.contracts.plan import ActionPlan, ActionProposal
from e_agent.contracts.receipt import ExecutionReceipt
from e_agent.contracts.run import (
    ReasonCode,
    RunRecord,
    RunState,
)
from e_agent.contracts.step import StepRecord
from e_agent.contracts.task import TaskDefinition
from e_agent.contracts.validation import Finding, ValidationResult
from e_agent.sdk.auth import CredentialVersionProvider
from e_agent.sdk.errors import DriverStateMismatch, KnownNoEffectError
from e_agent.sdk.ports import (
    AgentDriver,
    DriverInput,
    Observation,
    PolicyEvaluator,
    ReadRequest,
)
from e_agent.sdk.store import EventBatch, RunStore
from e_agent.sdk.tasks import supervised_task
from pydantic import (
    BaseModel,
    Field,
    PrivateAttr,
    SerializerFunctionWrapHandler,
    model_serializer,
)

from .connections import ConnectionCatalog
from .errors import ErrorCode, KernelError
from .registry import PluginRegistry

LOG = logging.getLogger("e_agent.kernel.coordinator")


CONTINUATION_SCHEMA = "kernel-continuation-v1"

KNOWN_RENDERINGS = frozenset({"pack"})
"""The driver snapshot ``rendering`` markers the kernel knows (ADR 0032 §6, §8)."""


class NextStep(StrEnum):
    """What a call may do once a multi-step plan's step is verified with steps left: its own
    authority, passed down the call chain, never state another call can see (Codex C-1,
    C2-1)."""

    START = "start"
    """The approval call or a fenced resume claim: start the next step."""
    QUEUE = "queue"
    """Reconciliation or startup recovery: queue the fenced resume, never send a write."""
    STOP = "stop"
    """Recovery after a failed resume claim: queue nothing; the plan fails closed."""


class _PlanState(BaseModel):
    """The multi-step plan a run is executing (Task 2c.7, ADR 0025); persisted with the
    continuation, so the approved inputs and the verified values survive a restart. Which
    steps started, and which are verified, is read from the durable actions (Codex C-2),
    never from this snapshot."""

    plan_id: str
    step_ids: tuple[str, ...]
    inputs: tuple[dict[str, Any], ...]
    """Each step's approved digest input (`plan_digest_input`), in step-index order: what
    revalidation compares a step against before its reservation."""
    current: int = 0
    """The index of the step in flight."""
    approval_id: str | None = None
    verified: dict[str, dict[str, Any]] = Field(default_factory=dict)
    """Step id to the values its verifier read back (`OutcomeReport.verified_values`), set
    only when that step's outcome is VERIFIED: the one source lineage copies from."""


class BlockedRevision(BaseModel):
    """A write proposal `_handle_proposal` blocked on validation, kept for ``KERNEL-REPEAT``
    (ADR 0031 §5) in a run pinned ``kernel_repeat`` ``shadow`` or ``on``: the action, its
    approval digest, the rule bundle version that digest bound, and the findings."""

    action_id: str
    digest: str
    rule_bundle_version: str
    findings: tuple[Finding, ...] = ()


class _Continuation(BaseModel):
    """Kernel-side run continuation, persisted through the RunStore at every state
    change so a restarted process can resume (ADR 0003/0004). Contains only
    authorized observations and records; never secrets or model reasoning."""

    ctx: TaskContext
    reads: dict[str, ReadRequest] = Field(default_factory=dict)
    observations: dict[str, Observation] = Field(default_factory=dict)
    findings: tuple[Finding, ...] = ()
    turns: int = 0
    read_calls: int = 0
    read_errors: dict[str, str] = Field(default_factory=dict)
    repairs: int = 0
    writes: int = 0
    pending_action_id: str | None = None
    last_action_id: str | None = None  # repairs link to the action they supersede
    canonical_proposal: dict[str, Any] = Field(default_factory=dict)
    last_validation: ValidationResult | None = None
    approval_requested_at: datetime | None = None
    active_seconds: float = 0
    surface_digest: str = ""  # tool surface at run start; resume is blocked if it changed
    task: TaskDefinition | None = None
    """The definition admitted for an execution IR ``on`` run: its tool set, budgets, TTL and
    acceptance for the whole run, whatever the registry later holds (ADR 0028, Codex C-1)."""
    plan: _PlanState | None = None
    """The multi-step plan in flight (execution IR ``on``, Task 2c.7); None otherwise."""
    modes: RunModes | None = None
    """The modes pinned when the run was prepared, the Phase 3 ones and ``conversations``
    (ADR 0032 §8, ADR 0023 §9); None, and left out of the stored continuation, when every mode
    is ``off``."""
    context_boundary: ContextRoute | None = None
    """For a run pinned ``context_assembler: on``, the loosest route boundary any model call
    of it has used (set by the first call, review D3-41): its driver history may hold values
    only that route may see, so a call on a stricter one is refused. None, and left out of
    the stored continuation, for every other run."""
    blocked: tuple[BlockedRevision, ...] = ()
    """The run's validation-blocked write proposals, kept only when ``kernel_repeat`` is not
    pinned ``off`` (ADR 0031 §5), and left out of the stored continuation when empty."""
    rationale: ProposalRationale | None = None
    """The checked rationale of the run's latest write proposal or plan, kept for the
    approval card in a run pinned ``grounded_answers`` ``shadow`` or ``on`` (ADR 0033 §4):
    the one place its text lives, never an event (owner G2). Left out when None."""
    step_rationales: dict[str, ProposalRationale] = Field(default_factory=dict)
    """That plan's step rationales by step id, as ``rationale``; left out when empty."""
    carried: tuple[CarriedRun, ...] = ()
    """Facts carried from earlier runs of the conversation, fixed at admission (ADR 0023 §6):
    never in ``observations`` or ``reads``. Left out when empty."""
    _stored_driver_state: dict[str, Any] | None = PrivateAttr(default=None)
    """The stored driver state this entry was loaded with, whatever the current driver
    supports, kept until the driver's ``advance`` is about to run (`_timed` with
    ``driver_turn``, reviews D3-60, D3-70, D3-80): never serialized, and written back
    verbatim by `_snapshot` meanwhile, so a kernel-only save, and a turn stopped by a
    pre-turn check (a budget, the route, the unbound check, assembly), leave it as it was."""
    _restored: bool = PrivateAttr(default=False)
    """Whether `_restore_for_turn` restored this load's driver state: at most once per load."""

    @model_serializer(mode="wrap")
    def _omit_unbound_task(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        """Leave ``task``, ``plan``, ``modes``, ``context_boundary`` and ``rationale`` out when
        unset, and ``blocked``, ``step_rationales`` and ``carried`` when empty, so an ``off``
        continuation is stored as before Task 2c.6, 3b.2, 3d.6, 3e.3 and 4d.2. A run pinned
        ``kernel_repeat`` ``shadow`` or ``on`` keeps a non-empty ``blocked`` once a proposal is
        blocked."""
        data: dict[str, Any] = handler(self)
        for name in ("task", "plan", "modes", "context_boundary", "rationale"):
            if getattr(self, name) is None:
                data.pop(name, None)
        for name in ("blocked", "step_rationales", "carried"):
            if not getattr(self, name):
                data.pop(name, None)
        return data


def rendering_mismatch(cont: _Continuation, driver_state: Mapping[str, Any]) -> bool:
    """The restore check (ADR 0032 §8): a ``rendering`` marker on a run not pinned
    ``context_assembler: on``, or a marker the kernel does not know. A pinned-``on`` run
    without the marker is valid (no pack turn yet, or every turn so far fell back)."""
    marker = driver_state.get("rendering")
    if marker is None:
        return False
    pinned_on = cont.modes is not None and cont.modes.context_assembler is FeatureMode.ON
    return marker not in KNOWN_RENDERINGS or not pinned_on


class _GatewayReader:
    """ScopedReader handed to verifiers: authorized, recorded reads only."""

    def __init__(self, coordinator: ContinuationMixin, cont: _Continuation, connection_id: str):
        self._coordinator = coordinator
        self._cont = cont
        self._connection_id = connection_id

    async def read(self, contract_id: str, arguments: Mapping[str, Any]) -> Observation:
        request = ReadRequest(
            request_id=new_id("vread"),
            contract_id=contract_id,
            connection_id=self._connection_id,
            arguments=dict(arguments),
        )
        observation = await self._coordinator._gateway_read(self._cont, request, count_budget=True)
        if observation.evidence.completeness is not Completeness.COMPLETE:
            raise KernelError(ErrorCode.DEPENDENCY_UNAVAILABLE, "verification read is incomplete")
        return observation


class ContinuationMixin:
    _store: RunStore
    _registry: PluginRegistry
    _connections: ConnectionCatalog
    _policy: PolicyEvaluator
    _credentials: CredentialVersionProvider | None
    _driver: AgentDriver
    _clock: Callable[[], datetime]
    _approval_ttl: timedelta
    _allow_self_approval: bool
    _budgets: Budgets
    _runs: dict[str, _Continuation]
    _active_calls: dict[str, asyncio.Task[Any]]

    if TYPE_CHECKING:

        async def _gateway_read(
            self, cont: _Continuation, request: ReadRequest, *, count_budget: bool
        ) -> Observation:
            raise NotImplementedError

        async def _handle_proposal(
            self,
            run: RunRecord,
            cont: _Continuation,
            proposal: ActionProposal,
            *,
            rationales: Sequence[tuple[str | None, ProposalRationale]] | None = None,
        ) -> RunRecord | DriverInput:
            raise NotImplementedError

        async def _handle_plan(
            self, run: RunRecord, cont: _Continuation, plan: ActionPlan
        ) -> RunRecord | DriverInput:
            raise NotImplementedError

        def _with_grounding(
            self, run: RunRecord, cont: _Continuation, step_input: DriverInput
        ) -> DriverInput:
            raise NotImplementedError

        async def _after_step_verified(
            self, cont: _Continuation, action: ActionRecord, *, next_step: NextStep
        ) -> RunRecord:
            raise NotImplementedError

        async def _queue_resume(self, run: RunRecord, action: ActionRecord) -> RunRecord:
            raise NotImplementedError

        async def _plan_approval(self, cont: _Continuation) -> ApprovalRecord:
            raise NotImplementedError

        async def _resume_plan(
            self,
            cont: _Continuation,
            latest: ActionRecord,
            actions: list[ActionRecord],
            *,
            next_step: NextStep,
        ) -> RunRecord | None:
            raise NotImplementedError

        async def _driver_state_mismatch(self, run: RunRecord) -> RunRecord:
            raise NotImplementedError

        async def _record_rejected_read(
            self, cont: _Continuation, request: ReadRequest, exc: KnownNoEffectError
        ) -> None:
            raise NotImplementedError

        async def _set_run_state(
            self,
            run: RunRecord,
            state: RunState,
            reason: str | None = None,
            *,
            code: ReasonCode | None = None,
            before: EventBatch = (),
            snapshot: bool = True,
            blocked_action_ids: Sequence[str] = (),
        ) -> RunRecord:
            raise NotImplementedError

        def _check_run_transition(self, run: RunRecord, to: RunState) -> None:
            raise NotImplementedError

        async def _exhausted(
            self, run: RunRecord, what: str, *, blocked_action_ids: Sequence[str] = ()
        ) -> RunRecord:
            raise NotImplementedError

        async def _transition(
            self,
            action: ActionRecord,
            to: ActionState,
            event: tuple[RunEventType, dict[str, Any]] | None = None,
            *,
            steps: Sequence[StepRecord] = (),
        ) -> ActionRecord:
            raise NotImplementedError

        async def _finish_verified(
            self,
            cont: _Continuation,
            external_refs: tuple[str, ...],
            fallback: str,
            *,
            acknowledge: bool = True,
            extra: EventBatch = (),
        ) -> RunRecord:
            raise NotImplementedError

        async def _dispatch(
            self, cont: _Continuation, action: ActionRecord, approval: ApprovalRecord
        ) -> RunRecord:
            raise NotImplementedError

        async def _drive(self, run: RunRecord, step_input: DriverInput) -> RunRecord:
            raise NotImplementedError

        async def _validate(
            self,
            ctx: TaskContext,
            cont: _Continuation,
            proposal: ActionProposal,
            binding: CapabilityBinding,
        ) -> ValidationResult:
            raise NotImplementedError

        async def _verify(
            self,
            cont: _Continuation,
            action: ActionRecord,
            receipt: ExecutionReceipt,
            *,
            next_step: NextStep,
        ) -> RunRecord:
            raise NotImplementedError

        async def _apply_receipt(
            self,
            cont: _Continuation,
            action: ActionRecord,
            receipt: ExecutionReceipt,
            *,
            next_step: NextStep,
        ) -> RunRecord:
            raise NotImplementedError

    async def _read_cont(
        self, tenant_id: str, run_id: str
    ) -> tuple[_Continuation, dict[str, Any] | None]:
        stored = await self._store.load_continuation(tenant_id, run_id)
        if stored is None:
            raise KernelError(ErrorCode.NOT_FOUND, "run has no continuation")
        state, driver_state = stored
        if state.get("schema") != CONTINUATION_SCHEMA:
            raise KernelError(ErrorCode.CONFLICT, "unsupported continuation schema")
        return _Continuation.model_validate(state["data"]), driver_state

    async def _peek_cont(self, tenant_id: str, run_id: str) -> _Continuation:
        """Read a continuation without caching it or restoring driver state (sweeper)."""
        cont = self._runs.get(run_id)
        if cont is not None:
            return cont
        return (await self._read_cont(tenant_id, run_id))[0]

    async def _load_cont(self, tenant_id: str, run_id: str) -> _Continuation:
        """The kernel continuation, cached; driver state is not restored here (ADR 0032 §8,
        review D3-60). Kernel-only operations (reconcile, the crash rules, cancel, approval
        reads and decisions) never touch the driver; a driver turn restores through
        `_restore_for_turn` first."""
        cont = self._runs.get(run_id)
        if cont is not None:
            return cont
        cont, driver_state = await self._read_cont(tenant_id, run_id)
        cont._stored_driver_state = driver_state  # whatever the driver supports (D3-70)
        self._runs[run_id] = cont
        return cont

    def _restore_for_turn(self, cont: _Continuation) -> bool:
        """Restore the driver state a load left pending, at most once per load, before the
        run's next driver turn (`_drive`, the acknowledgement turn) reads any driver state. A
        driver without ``restore`` starts fresh at its call. The stored state stays on the
        entry either way until ``advance`` is about to run (review D3-80). False on the typed
        refusal (D8): the kernel's ``rendering`` marker check, or the driver's own; nothing is
        restored, and the stored driver state stays as it was."""
        driver_state = cont._stored_driver_state
        restore = getattr(self._driver, "restore", None)
        if driver_state is None or restore is None or cont._restored:
            return True
        try:
            if rendering_mismatch(cont, driver_state):
                raise DriverStateMismatch
            restore(cont.ctx.run_id, driver_state)
        except DriverStateMismatch:
            return False
        cont._restored = True
        return True

    def _snapshot(self, run_id: str) -> tuple[dict[str, Any], dict[str, Any] | None] | None:
        cont = self._runs.get(run_id)
        if cont is None:
            return None
        snapshot = getattr(self._driver, "snapshot", None)
        driver_state = cont._stored_driver_state  # before the driver call: verbatim
        if driver_state is None and snapshot is not None:
            driver_state = snapshot(run_id)
        return ({"schema": CONTINUATION_SCHEMA, "data": cont.model_dump(mode="json")}, driver_state)

    async def _persist(self, run_id: str) -> None:
        snapshot = self._snapshot(run_id)
        if snapshot is not None:
            cont = self._runs[run_id]
            await self._store.save_continuation(cont.ctx.tenant_id, run_id, *snapshot)

    async def _timed[T](
        self,
        cont: _Continuation,
        call: Callable[[], Awaitable[T]],
        limit: int,
        *,
        cancellable: bool = True,
        driver_turn: bool = False,
    ) -> T:
        """Run ``call`` within the run's active-time budget and ``limit``. ``driver_turn``:
        the call is the driver's ``advance``, so the stored driver state is released as it
        starts, never before (review D3-80); the driver's own snapshot replaces it."""
        remaining = cont.ctx.budgets.max_active_seconds - cont.active_seconds
        if remaining <= 0:
            raise TimeoutError("active execution budget exhausted")
        started = time.perf_counter()

        async def invoke() -> T:
            if driver_turn:
                cont._stored_driver_state = None
            return await call()

        # An awaited child, not a background task: the caller handles its failure, so no log.
        task: asyncio.Task[T] = supervised_task(
            invoke(), name=f"kernel.call:{cont.ctx.run_id}", log_failure=False
        )
        if cancellable:
            self._active_calls[cont.ctx.run_id] = task
        try:
            async with asyncio.timeout(min(limit, remaining)):
                return await task
        finally:
            if self._active_calls.get(cont.ctx.run_id) is task:
                self._active_calls.pop(cont.ctx.run_id, None)
            cont.active_seconds += time.perf_counter() - started
            await self._persist(cont.ctx.run_id)
