"""Run coordinator: drives the agent, gates every effect, owns approval and dispatch.

The coordinator is the only component that moves actions through the state
machine (MVP design §7-9, ADR 0003). Drivers only propose; validators only
report findings; executors only execute admitted invocations.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable, Mapping
from datetime import datetime, timedelta
from functools import partial
from typing import Any

from e_agent.contracts.action import ALLOWED_ACTION_TRANSITIONS, ActionRecord, ActionState
from e_agent.contracts.approval import ApprovalDecision, ApprovalRecord
from e_agent.contracts.capability import CapabilityBinding, EffectKind
from e_agent.contracts.common import new_id, utc_now
from e_agent.contracts.context import Budgets, HostContext, Principal, TaskContext
from e_agent.contracts.digest import CanonicalizationError, digest
from e_agent.contracts.events import RunEventType
from e_agent.contracts.evidence import ApprovedFact, Completeness
from e_agent.contracts.outcome import OutcomeReport, OutcomeStatus
from e_agent.contracts.plan import ActionProposal
from e_agent.contracts.receipt import ExecutionReceipt, ReceiptStatus
from e_agent.contracts.run import (
    ALLOWED_RUN_TRANSITIONS,
    TERMINAL_RUN_STATES,
    ReasonCode,
    RunRecord,
    RunState,
)
from e_agent.contracts.validation import Finding, ValidationResult, ValidationStatus
from e_agent.sdk.auth import CredentialVersionProvider
from e_agent.sdk.errors import DriverBudgetExceeded, KnownNoEffectError
from e_agent.sdk.ports import (
    AgentDriver,
    AskClarification,
    DriverInput,
    FinalAnswer,
    Observation,
    PolicyEvaluator,
    ProposeAction,
    ReadRequest,
    RequestReads,
    SafeTextSink,
    ValidationInput,
)
from e_agent.sdk.store import DuplicateOperation, EventSpec, RunStore
from pydantic import BaseModel, Field

from .approval import (
    ApprovalPresentation,
    compute_digest,
    digest_input,
    fact_digest,
    presentation_for,
)
from .connections import ConnectionCatalog
from .errors import ErrorCode, KernelError
from .policy import APPROVER_ROLE
from .registry import PluginRegistry

LOG = logging.getLogger(__name__)
DEFAULT_APPROVAL_TTL = timedelta(minutes=15)


CONTINUATION_SCHEMA = "kernel-continuation-v1"


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
    repairs: int = 0
    writes: int = 0
    pending_action_id: str | None = None
    last_action_id: str | None = None  # repairs link to the action they supersede
    canonical_proposal: dict[str, Any] = Field(default_factory=dict)
    last_validation: ValidationResult | None = None
    approval_requested_at: datetime | None = None
    active_seconds: float = 0
    surface_digest: str = ""  # tool surface at run start; resume is blocked if it changed


class _GatewayReader:
    """ScopedReader handed to verifiers: authorized, recorded reads only."""

    def __init__(self, coordinator: RunCoordinator, cont: _Continuation, connection_id: str):
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


class RunCoordinator:
    def __init__(
        self,
        *,
        store: RunStore,
        registry: PluginRegistry,
        connections: ConnectionCatalog,
        policy: PolicyEvaluator,
        driver: AgentDriver,
        clock: Callable[[], datetime] = utc_now,
        approval_ttl: timedelta = DEFAULT_APPROVAL_TTL,
        allow_self_approval: bool = False,
        budgets: Budgets | None = None,
        credentials: CredentialVersionProvider | None = None,
    ) -> None:
        self._store = store
        self._registry = registry
        self._connections = connections
        self._policy = policy
        self._credentials = credentials
        self._driver = driver
        self._clock = clock
        self._approval_ttl = approval_ttl
        self._allow_self_approval = allow_self_approval
        self._budgets = budgets or Budgets()
        self._runs: dict[str, _Continuation] = {}
        self._active_calls: dict[str, asyncio.Task[Any]] = {}

    # ------------------------------------------------------------------ runs
    def _prepare_run(
        self,
        principal: Principal,
        task: str,
        resource_scope: frozenset[str],
        *,
        run_id: str | None = None,
        host_context: HostContext | None = None,
    ) -> tuple[RunRecord, _Continuation, list[EventSpec]]:
        run_id = run_id or new_id("run")
        ctx = TaskContext(
            run_id=run_id,
            tenant_id=principal.tenant_id,
            principal=principal,
            resource_scope=resource_scope,
            budgets=self._budgets,
        )
        run = RunRecord(
            run_id=run_id,
            tenant_id=principal.tenant_id,
            requester_id=principal.principal_id,
            task=task,
            state=RunState.CREATED,
            revision=1,
            logical_operation_id=new_id("op"),  # host-assigned; survives repairs
            created_at=self._clock(),
        )
        created: dict[str, Any] = {"task": task, "driver": self._driver.driver_id}
        if host_context is not None:
            resolved, dropped = self._connections.resolve_hints(ctx, host_context.resource_hints)
            # Recorded as untrusted context; selection text is never persisted.
            created["host_context"] = {
                "host_kind": host_context.host_kind,
                "page_url_origin": host_context.page_url_origin,
                "locale": host_context.locale,
                "resolved_hints": [h.model_dump() for h in resolved],
                "dropped_hints": dropped,
            }
        cont = _Continuation(ctx=ctx, surface_digest=self._registry.surface_digest())
        return run, cont, [(RunEventType.RUN_CREATED, created, None)]

    async def start_run(
        self,
        principal: Principal,
        task: str,
        resource_scope: frozenset[str],
        *,
        run_id: str | None = None,
        host_context: HostContext | None = None,
    ) -> RunRecord:
        run, cont, events = self._prepare_run(
            principal, task, resource_scope, run_id=run_id, host_context=host_context
        )
        await self._store.create_run(run, events)
        self._runs[run.run_id] = cont
        run = await self._set_run_state(run, RunState.RUNNING)
        return await self._drive(run, DriverInput(task=task))

    async def admit_run(
        self,
        principal: Principal,
        task: str,
        resource_scope: frozenset[str],
        *,
        run_id: str,
        idempotency_key: str,
        request_digest: str,
        host_context: HostContext | None = None,
    ) -> tuple[str, bool]:
        run, cont, events = self._prepare_run(
            principal, task, resource_scope, run_id=run_id, host_context=host_context
        )
        claimed, previous_digest = await self._store.create_run_idempotent(
            run,
            events,
            {"schema": CONTINUATION_SCHEMA, "data": cont.model_dump(mode="json")},
            principal.principal_id,
            idempotency_key,
            request_digest,
        )
        if previous_digest != request_digest:
            raise KernelError(ErrorCode.CONFLICT, "idempotency key reused with another request")
        return claimed, claimed == run_id

    async def start_admitted_run(self, tenant_id: str, run_id: str) -> RunRecord:
        run = await self._store.get_run(tenant_id, run_id)
        if run.state is not RunState.CREATED:
            raise KernelError(ErrorCode.CONFLICT, "run has already started")
        await self._load_cont(tenant_id, run_id)
        run = await self._set_run_state(run, RunState.RUNNING)
        return await self._drive(run, DriverInput(task=run.task))

    def set_text_sink(self, sink: SafeTextSink) -> None:
        attach = getattr(self._driver, "set_text_sink", None)
        if attach is not None:
            attach(sink)

    def release_continuation(self, run_id: str) -> None:
        """Discard a worker's cached checkpoint before a new host claim loads it."""
        self._runs.pop(run_id, None)

    async def get_run(self, tenant_id: str, run_id: str) -> RunRecord:
        return await self._store.get_run(tenant_id, run_id)

    def _check_run_transition(self, run: RunRecord, to: RunState) -> None:
        if to not in ALLOWED_RUN_TRANSITIONS[run.state]:
            raise KernelError(ErrorCode.CONFLICT, f"illegal run transition {run.state}->{to}")

    async def _set_run_state(
        self,
        run: RunRecord,
        state: RunState,
        reason: str | None = None,
        *,
        code: ReasonCode | None = None,
    ) -> RunRecord:
        self._check_run_transition(run, state)
        events: list[EventSpec] = [
            (
                RunEventType.RUN_STATE_CHANGED,
                {"from": run.state, "to": state, "reason": reason, "reason_code": code},
                None,
            )
        ]
        if state in TERMINAL_RUN_STATES:
            events.append(
                (
                    RunEventType.RUN_TERMINAL,
                    {"state": state, "reason": reason, "reason_code": code},
                    None,
                )
            )
        updated = run.model_copy(
            update={
                "state": state,
                "revision": run.revision + 1,
                "reason": reason,
                "reason_code": code,
            }
        )
        return await self._store.update_run(
            updated,
            run.revision,
            events,
            continuation=self._snapshot(run.run_id),
        )

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
        cont = self._runs.get(run_id)
        if cont is not None:
            return cont
        cont, driver_state = await self._read_cont(tenant_id, run_id)
        restore = getattr(self._driver, "restore", None)
        if driver_state is not None and restore is not None:
            restore(run_id, driver_state)
        self._runs[run_id] = cont
        return cont

    def _snapshot(self, run_id: str) -> tuple[dict[str, Any], dict[str, Any] | None] | None:
        cont = self._runs.get(run_id)
        if cont is None:
            return None
        snapshot = getattr(self._driver, "snapshot", None)
        driver_state = snapshot(run_id) if snapshot is not None else None
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
    ) -> T:
        remaining = cont.ctx.budgets.max_active_seconds - cont.active_seconds
        if remaining <= 0:
            raise TimeoutError("active execution budget exhausted")
        started = time.perf_counter()

        async def invoke() -> T:
            return await call()

        task: asyncio.Task[T] = asyncio.create_task(invoke())
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

    # ---------------------------------------------------------------- driving
    async def _drive(self, run: RunRecord, step_input: DriverInput) -> RunRecord:
        cont = await self._load_cont(run.tenant_id, run.run_id)
        ctx = cont.ctx
        while True:
            if cont.turns >= ctx.budgets.max_driver_turns:
                return await self._exhausted(run, "driver turns")
            cont.turns += 1
            tokens_used = getattr(self._driver, "tokens_used", lambda _: 0)(ctx.run_id)
            if tokens_used >= ctx.budgets.max_model_tokens:
                return await self._exhausted(run, "model tokens")
            try:
                step = await self._timed(
                    cont,
                    partial(self._driver.advance, ctx, step_input),
                    ctx.budgets.model_timeout_seconds,
                )
            except DriverBudgetExceeded:
                return await self._exhausted(run, "model usage")
            except TimeoutError:
                return await self._exhausted(run, "active time or model deadline")

            if (
                getattr(self._driver, "tokens_used", lambda _: 0)(ctx.run_id)
                >= ctx.budgets.max_model_tokens
            ):
                return await self._exhausted(run, "model tokens")
            if isinstance(step, RequestReads):
                for request in step.reads:
                    if cont.read_calls >= ctx.budgets.max_read_calls:
                        return await self._exhausted(run, "read calls")
                    try:
                        obs = await self._gateway_read(cont, request, count_budget=True)
                    except TimeoutError:
                        return await self._exhausted(run, "active time or provider deadline")
                    cont.reads[request.request_id] = request
                    cont.observations[request.request_id] = obs
                await self._persist(run.run_id)
                step_input = DriverInput(
                    task=run.task, observations=tuple(cont.observations.values())
                )
                continue

            if isinstance(step, ProposeAction):
                run = await self._store.get_run(run.tenant_id, run.run_id)
                outcome = await self._handle_proposal(run, cont, step.proposal)
                if isinstance(outcome, RunRecord):
                    return outcome
                step_input = outcome
                continue

            if isinstance(step, AskClarification):
                run = await self._store.get_run(run.tenant_id, run.run_id)
                await self._store.update_run(
                    run.model_copy(update={"revision": run.revision + 1}),
                    run.revision,
                    [(RunEventType.INPUT_REQUESTED, {"question": step.question}, None)],
                )
                run = await self._store.get_run(run.tenant_id, run.run_id)
                return await self._set_run_state(run, RunState.WAITING_INPUT)

            if isinstance(step, FinalAnswer):
                run = await self._store.get_run(run.tenant_id, run.run_id)
                last_action = (
                    await self._store.get_action(run.tenant_id, cont.last_action_id)
                    if cont.last_action_id
                    else None
                )
                if cont.pending_action_id is None and (
                    last_action is None or last_action.state is not ActionState.VERIFIED
                ):
                    if cont.repairs >= ctx.budgets.max_validation_repairs:
                        return await self._set_run_state(
                            run,
                            RunState.FAILED,
                            "no independently verified outcome",
                            code=ReasonCode.VERIFICATION_FAILED,
                        )
                    cont.repairs += 1
                    await self._persist(run.run_id)
                    step_input = DriverInput(
                        task=run.task,
                        observations=tuple(cont.observations.values()),
                        findings=(
                            Finding(
                                rule_id="KERNEL-VERIFICATION",
                                rule_version="1",
                                status=ValidationStatus.FAIL,
                                message=(
                                    "Plain text cannot complete this task. "
                                    "Propose a structured answer "
                                    "for independent verification, propose the requested action, "
                                    "or request clarification for missing user details."
                                ),
                            ),
                        ),
                    )
                    continue
                run = await self._store.update_run(
                    run.model_copy(update={"revision": run.revision + 1}),
                    run.revision,
                    [(RunEventType.MESSAGE_FINAL, {"text": step.text}, None)],
                )
                if cont.pending_action_id is None:
                    return await self._set_run_state(
                        run, RunState.SUCCEEDED, "answered", code=ReasonCode.ANSWERED
                    )
                return run
            raise KernelError(ErrorCode.INVALID_REQUEST, "driver returned an unknown step")

    async def accept_input(
        self,
        actor: Principal,
        run_id: str,
        text: str,
        expected_revision: int,
        *,
        enqueue: bool = False,
    ) -> RunRecord:
        """Resume the requester's persisted run; input grants no additional authority."""
        run = await self._store.get_run(actor.tenant_id, run_id)
        if actor.principal_id != run.requester_id:
            raise KernelError(ErrorCode.FORBIDDEN, "only the requester may answer")
        if run.revision != expected_revision or run.state is not RunState.WAITING_INPUT:
            raise KernelError(ErrorCode.CONFLICT, "input does not match the pending question")
        if not text.strip() or len(text) > 4000:
            raise KernelError(ErrorCode.INVALID_REQUEST, "input must contain 1..4000 characters")
        await self._load_cont(actor.tenant_id, run_id)
        self._check_run_transition(run, RunState.RUNNING)
        run = await self._store.update_run(
            run.model_copy(
                update={
                    "revision": run.revision + 1,
                    "state": RunState.RUNNING,
                    "reason": None,
                    "reason_code": None,
                }
            ),
            run.revision,
            [
                (
                    RunEventType.INPUT_RECEIVED,
                    {"input": text, "expected_revision": expected_revision},
                    None,
                ),
                (RunEventType.RUN_STATE_CHANGED, {"state": RunState.RUNNING}, None),
            ],
            continuation=self._snapshot(run_id),
            work=("input", {}, digest({"revision": str(expected_revision), "input": text}))
            if enqueue
            else None,
        )
        return run

    async def continue_input(self, tenant_id: str, run_id: str) -> RunRecord:
        run = await self._store.get_run(tenant_id, run_id)
        if run.state is not RunState.RUNNING:
            raise KernelError(ErrorCode.CONFLICT, "run is no longer awaiting input work")
        events = await self._store.list_events(tenant_id, run_id)
        received = [e for e in events if e.type is RunEventType.INPUT_RECEIVED]
        if not received:
            raise KernelError(ErrorCode.CONFLICT, "no accepted input")
        cont = await self._load_cont(tenant_id, run_id)
        return await self._drive(
            run,
            DriverInput(
                task=run.task,
                user_input=str(received[-1].payload["input"]),
                observations=tuple(cont.observations.values()),
            ),
        )

    async def resume_input(
        self,
        actor: Principal,
        run_id: str,
        text: str,
        expected_revision: int,
    ) -> RunRecord:
        await self.accept_input(actor, run_id, text, expected_revision)
        return await self.continue_input(actor.tenant_id, run_id)

    async def _exhausted(self, run: RunRecord, what: str) -> RunRecord:
        run = await self._store.get_run(run.tenant_id, run.run_id)
        run = await self._store.update_run(
            run.model_copy(update={"revision": run.revision + 1}),
            run.revision,
            [(RunEventType.BUDGET_EXHAUSTED, {"budget": what}, None)],
        )
        return await self._set_run_state(
            run, RunState.FAILED, f"budget exhausted: {what}", code=ReasonCode.BUDGET_EXHAUSTED
        )

    # ---------------------------------------------------------------- reads
    async def _gateway_read(
        self, cont: _Continuation, request: ReadRequest, *, count_budget: bool
    ) -> Observation:
        ctx = cont.ctx
        if count_budget and cont.read_calls >= ctx.budgets.max_read_calls:
            raise KernelError(ErrorCode.DEPENDENCY_UNAVAILABLE, "read call budget exhausted")
        descriptor = self._registry.descriptor(request.contract_id)
        if descriptor.effect is not EffectKind.READ:
            raise KernelError(ErrorCode.INVALID_REQUEST, "write capability requested as a read")
        self._connections.usable(ctx, request.connection_id)
        decision = self._policy.evaluate(ctx, descriptor, request.connection_id)
        if not decision.permitted:
            raise KernelError(ErrorCode.FORBIDDEN, "read not permitted")
        binding = self._registry.resolve(request.contract_id, request.connection_id)
        obs = await self._timed(
            cont,
            lambda: self._registry.executor_for(binding).read(ctx, binding, request),
            ctx.budgets.provider_timeout_seconds,
        )
        if (
            obs.evidence.tenant_id != ctx.tenant_id
            or obs.request_id != request.request_id
            or obs.contract_id != request.contract_id
        ):
            raise KernelError(
                ErrorCode.FORBIDDEN, "read result does not match the authorized request"
            )
        if count_budget:
            cont.read_calls += 1
        run = await self._store.get_run(ctx.tenant_id, ctx.run_id)
        await self._store.update_run(
            run.model_copy(update={"revision": run.revision + 1}),
            run.revision,
            [
                (
                    RunEventType.READ_RECORDED,
                    {
                        "request_id": request.request_id,
                        "contract_id": request.contract_id,
                        "connection_id": request.connection_id,
                        "evidence_id": obs.evidence.evidence_id,
                        "revision": obs.evidence.revision,
                    },
                    None,
                )
            ],
        )
        return obs

    # ------------------------------------------------------------- proposals
    async def _handle_proposal(
        self, run: RunRecord, cont: _Continuation, proposal: ActionProposal
    ) -> RunRecord | DriverInput:
        ctx = cont.ctx
        descriptor = self._registry.descriptor(proposal.contract_id)
        if descriptor.effect is EffectKind.ANSWER:
            return await self._handle_answer(run, cont, proposal)
        if descriptor.effect is not EffectKind.WRITE:
            raise KernelError(ErrorCode.INVALID_REQUEST, "proposals are for write capabilities")
        if cont.writes >= ctx.budgets.max_admitted_writes:
            return await self._exhausted(run, "admitted writes")
        connection = self._connections.usable(ctx, proposal.connection_id)
        binding = self._registry.resolve(proposal.contract_id, proposal.connection_id)
        decision = self._policy.evaluate(ctx, descriptor, proposal.connection_id)
        validation = await self._validate(ctx, cont, proposal, binding)

        credential_version = (
            await self._credentials.version(ctx, proposal.connection_id)
            if self._credentials
            else "none"
        )
        evidence = [cont.observations[r].evidence for r in sorted(cont.observations)]
        canonical = digest_input(
            tenant_id=ctx.tenant_id,
            requester_id=ctx.principal.principal_id,
            logical_operation_id=run.logical_operation_id,
            contract_id=proposal.contract_id,
            binding_id=binding.binding_id,
            connection_id=connection.connection_id,
            connection_version=connection.version,
            credential_subject=connection.credential_subject(),
            arguments=dict(proposal.arguments),
            expected_effects=proposal.expected_effects,
            evidence=evidence,
            rule_bundle_version=validation.rule_bundle_version,
            policy_version=decision.policy_version,
            credential_version=credential_version,
            fact_digests={
                o.evidence.evidence_id: fact_digest(o.data)
                for o in cont.observations.values()
                if o.evidence.revision is None
            },
        )
        try:
            action_digest = compute_digest(canonical)
        except CanonicalizationError as exc:
            validation = ValidationResult(
                status=ValidationStatus.FAIL,
                findings=(
                    Finding(
                        rule_id="KERNEL-ARGS",
                        rule_version="1",
                        status=ValidationStatus.FAIL,
                        message=f"arguments outside the digest profile: {exc}",
                    ),
                ),
                rule_bundle_version=validation.rule_bundle_version,
                validator_id="kernel",
            )
            action_digest = "invalid"

        previous = cont.last_action_id
        action = ActionRecord(
            action_id=new_id("act"),
            tenant_id=ctx.tenant_id,
            run_id=run.run_id,
            logical_operation_id=run.logical_operation_id,
            contract_id=proposal.contract_id,
            binding_id=binding.binding_id,
            connection_id=connection.connection_id,
            connection_version=connection.version,
            credential_subject=connection.credential_subject(),
            credential_version=credential_version,
            approved_facts=tuple(
                ApprovedFact(contract_id=o.contract_id, data=dict(o.data), evidence=o.evidence)
                for o in cont.observations.values()
            ),
            arguments=dict(proposal.arguments),
            digest=action_digest,
            state=ActionState.PROPOSED,
            revision=1,
            supersedes_action_id=previous,
        )
        await self._store.put_action(
            action,
            None,
            [
                (
                    RunEventType.PROPOSAL_CREATED,
                    {
                        "contract_id": action.contract_id,
                        "arguments": action.arguments,
                        "supersedes": previous,
                    },
                    action.action_id,
                )
            ],
        )
        cont.last_action_id = action.action_id
        findings_payload = [f.model_dump(mode="json") for f in validation.findings]
        blocked = validation.blocks_write or not decision.permitted
        if blocked:
            action = await self._transition(
                action,
                ActionState.BLOCKED,
                (
                    RunEventType.VALIDATION_COMPLETED,
                    {
                        "status": validation.status,
                        "findings": findings_payload,
                        "policy_reasons": list(decision.reasons),
                    },
                ),
            )
            cont.pending_action_id = None
            if not decision.permitted:
                run = await self._store.get_run(run.tenant_id, run.run_id)
                return await self._set_run_state(
                    run, RunState.FAILED, "policy denied", code=ReasonCode.POLICY_DENIED
                )
            if cont.repairs >= ctx.budgets.max_validation_repairs:
                run = await self._store.get_run(run.tenant_id, run.run_id)
                return await self._set_run_state(
                    run, RunState.FAILED, "validation blocked", code=ReasonCode.VALIDATION_FAILED
                )
            cont.repairs += 1
            cont.findings = validation.findings
            return DriverInput(
                task=run.task,
                observations=tuple(cont.observations.values()),
                findings=validation.findings,
            )

        action = await self._transition(
            action,
            ActionState.VALIDATED,
            (
                RunEventType.VALIDATION_COMPLETED,
                {"status": validation.status, "findings": findings_payload},
            ),
        )
        cont.pending_action_id = action.action_id
        cont.canonical_proposal = canonical
        cont.last_validation = validation
        cont.approval_requested_at = self._clock()
        run = await self._store.get_run(run.tenant_id, run.run_id)
        self._check_run_transition(run, RunState.WAITING_APPROVAL)
        waiting = run.model_copy(
            update={
                "state": RunState.WAITING_APPROVAL,
                "revision": run.revision + 1,
                "reason": None,
                "reason_code": None,
            }
        )
        checkpoint = self._snapshot(run.run_id)
        assert checkpoint is not None
        await self._store.wait_for_approval(
            action.model_copy(
                update={"state": ActionState.AWAITING_APPROVAL, "revision": action.revision + 1}
            ),
            action.revision,
            waiting,
            run.revision,
            checkpoint,
            [
                (
                    RunEventType.APPROVAL_REQUESTED,
                    {
                        "digest": action.digest,
                        "expires_at": (cont.approval_requested_at + self._approval_ttl).isoformat(),
                    },
                    action.action_id,
                ),
                (
                    RunEventType.RUN_STATE_CHANGED,
                    {
                        "from": run.state,
                        "to": RunState.WAITING_APPROVAL,
                        "reason": None,
                        "reason_code": None,
                    },
                    None,
                ),
            ],
        )
        return waiting

    async def _handle_answer(
        self, run: RunRecord, cont: _Continuation, proposal: ActionProposal
    ) -> RunRecord | DriverInput:
        """Structured answers: no approval or dispatch; the domain verifier recomputes
        the answer from fresh, independent reads (MVP plan ERP-01/02/06/08)."""
        ctx = cont.ctx
        connection = self._connections.usable(ctx, proposal.connection_id)
        verifier = self._registry.verifier_for(proposal.contract_id)
        if verifier is None:
            raise KernelError(ErrorCode.DEPENDENCY_UNAVAILABLE, "no verifier for answer")
        try:
            action_digest = compute_digest(
                {"contract_id": proposal.contract_id, "arguments": dict(proposal.arguments)}
            )
        except CanonicalizationError:
            action_digest = "invalid"
        if cont.last_action_id is not None:
            previous = await self._store.get_action(ctx.tenant_id, cont.last_action_id)
            if (
                previous.state is ActionState.VERIFIED
                and previous.contract_id == proposal.contract_id
                and previous.connection_id == connection.connection_id
                and previous.digest == action_digest
                and previous.arguments == dict(proposal.arguments)
            ):
                return await self._finish_verified(
                    cont, (), "The structured answer was independently verified.", acknowledge=False
                )
        action = ActionRecord(
            action_id=new_id("act"),
            tenant_id=ctx.tenant_id,
            run_id=run.run_id,
            logical_operation_id=run.logical_operation_id,
            contract_id=proposal.contract_id,
            binding_id="answer",
            connection_id=connection.connection_id,
            connection_version=connection.version,
            credential_subject=connection.credential_subject(),
            arguments=dict(proposal.arguments),
            digest=action_digest,
            state=ActionState.PROPOSED,
            revision=1,
            supersedes_action_id=cont.last_action_id,
        )
        await self._store.put_action(
            action,
            None,
            [
                (
                    RunEventType.PROPOSAL_CREATED,
                    {
                        "contract_id": action.contract_id,
                        "arguments": action.arguments,
                        "kind": "answer",
                        "supersedes": cont.last_action_id,
                    },
                    action.action_id,
                )
            ],
        )
        cont.last_action_id = action.action_id
        action = await self._transition(action, ActionState.VALIDATED)
        reader = _GatewayReader(self, cont, connection.connection_id)
        try:
            report = await verifier.verify(ctx, action, None, reader)
        except Exception as exc:  # verification unavailable: never claim the answer
            report = OutcomeReport(
                run_id=ctx.run_id,
                action_id=action.action_id,
                status=OutcomeStatus.UNKNOWN,
                checks=(),
                verifier_id=verifier.verifier_id,
                verifier_version=type(exc).__name__,
                reported_at=self._clock(),
            )
        verified = report.status is OutcomeStatus.VERIFIED
        target = ActionState.VERIFIED if verified else ActionState.VERIFICATION_FAILED
        await self._store.record_outcome(
            ctx.tenant_id,
            report,
            action.model_copy(update={"state": target, "revision": action.revision + 1}),
            action.revision,
            [(RunEventType.OUTCOME_REPORTED, report.model_dump(mode="json"), action.action_id)],
        )
        if verified:
            return DriverInput(
                task=run.task,
                observations=tuple(cont.observations.values()),
                action_result={"status": "VERIFIED"},
            )
        run = await self._store.get_run(run.tenant_id, run.run_id)
        if cont.repairs >= ctx.budgets.max_validation_repairs:
            return await self._set_run_state(
                run, RunState.FAILED, "answer not verified", code=ReasonCode.VERIFICATION_FAILED
            )
        cont.repairs += 1
        findings = tuple(
            Finding(
                rule_id=f"VERIFY-{c.name}",
                rule_version="1",
                status=ValidationStatus.FAIL,
                message=f"answer check {c.name} failed",
                expected=c.expected,
                observed=c.observed,
            )
            for c in report.checks
            if not c.passed
        ) or (
            Finding(
                rule_id="VERIFY",
                rule_version="1",
                status=ValidationStatus.UNKNOWN,
                message="answer could not be verified",
            ),
        )
        return DriverInput(
            task=run.task, observations=tuple(cont.observations.values()), findings=findings
        )

    async def _validate(
        self,
        ctx: TaskContext,
        cont: _Continuation,
        proposal: ActionProposal,
        binding: CapabilityBinding,
    ) -> ValidationResult:
        if any(
            o.evidence.completeness is not Completeness.COMPLETE for o in cont.observations.values()
        ):
            return ValidationResult(
                status=ValidationStatus.UNKNOWN,
                findings=(
                    Finding(
                        rule_id="KERNEL-EVIDENCE",
                        rule_version="1",
                        status=ValidationStatus.UNKNOWN,
                        message="proposal evidence is incomplete",
                    ),
                ),
                rule_bundle_version="kernel-evidence-v1",
                validator_id="kernel",
            )
        validators = self._registry.validators_for(proposal.contract_id)
        if not validators:
            return ValidationResult(
                status=ValidationStatus.UNKNOWN,
                findings=(
                    Finding(
                        rule_id="KERNEL-NO-VALIDATOR",
                        rule_version="1",
                        status=ValidationStatus.UNKNOWN,
                        message="no validator registered for capability",
                    ),
                ),
                rule_bundle_version="none",
                validator_id="kernel",
            )
        item = ValidationInput(proposal=proposal, observations=tuple(cont.observations.values()))
        results: list[ValidationResult] = []
        for validator in validators:
            try:
                results.append(
                    await self._timed(
                        cont,
                        partial(validator.validate, ctx, item),
                        ctx.budgets.provider_timeout_seconds,
                    )
                )
            except Exception as exc:  # engine failure blocks the write (MVP §11)
                results.append(
                    ValidationResult(
                        status=ValidationStatus.ERROR,
                        findings=(
                            Finding(
                                rule_id="KERNEL-VALIDATOR-ERROR",
                                rule_version="1",
                                status=ValidationStatus.ERROR,
                                message=type(exc).__name__,
                            ),
                        ),
                        rule_bundle_version="error",
                        validator_id=validator.validator_id,
                    )
                )
        order = [ValidationStatus.ERROR, ValidationStatus.FAIL, ValidationStatus.UNKNOWN]
        status = next(
            (s for s in order if any(r.status is s for r in results)), ValidationStatus.PASS
        )
        return ValidationResult(
            status=status,
            findings=tuple(f for r in results for f in r.findings),
            rule_bundle_version="+".join(sorted(r.rule_bundle_version for r in results)),
            validator_id="+".join(sorted(r.validator_id for r in results)),
        )

    async def _transition(
        self,
        action: ActionRecord,
        to: ActionState,
        event: tuple[RunEventType, dict[str, Any]] | None = None,
    ) -> ActionRecord:
        if to not in ALLOWED_ACTION_TRANSITIONS[action.state]:
            raise KernelError(ErrorCode.CONFLICT, f"illegal transition {action.state}->{to}")
        updated = action.model_copy(update={"state": to, "revision": action.revision + 1})
        events: list[EventSpec] = []
        if event is not None:
            events.append((event[0], event[1], action.action_id))
        return await self._store.put_action(updated, action.revision, events)

    # ------------------------------------------------------------- approvals
    async def pending_approval(self, tenant_id: str, run_id: str) -> ApprovalPresentation:
        run = await self._store.get_run(tenant_id, run_id)
        cont = await self._load_cont(run.tenant_id, run_id)
        if run.state is not RunState.WAITING_APPROVAL or cont.pending_action_id is None:
            raise KernelError(ErrorCode.NOT_FOUND, "no pending approval")
        action = await self._store.get_action(tenant_id, cont.pending_action_id)
        assert cont.approval_requested_at is not None
        previous = None
        if action.supersedes_action_id is not None:
            superseded = await self._store.get_action(tenant_id, action.supersedes_action_id)
            previous = superseded.arguments
        return presentation_for(
            action,
            previous_arguments=previous,
            input_schema=self._registry.input_schemas.get(
                self._registry.descriptor(action.contract_id).input_schema_id
            ),
            run_revision=run.revision,
            canonical_proposal=cont.canonical_proposal,
            findings=cont.last_validation.findings if cont.last_validation else (),
            expires_at=cont.approval_requested_at + self._approval_ttl,
        )

    async def _expire_pending(self, cont: _Continuation, action: ActionRecord) -> RunRecord:
        """Expiry outcome of a pending approval, shared by decide and the sweeper (ADR 0019).

        The continuation is persisted by `_set_run_state` together with the run update.
        """
        if action.state is not ActionState.BLOCKED:  # BLOCKED: resuming an interrupted expiry
            await self._transition(
                action,
                ActionState.BLOCKED,
                (RunEventType.APPROVAL_DECIDED, {"decision": "expired"}),
            )
        cont.pending_action_id = None
        run = await self._store.get_run(cont.ctx.tenant_id, cont.ctx.run_id)
        return await self._set_run_state(
            run, RunState.FAILED, "approval expired", code=ReasonCode.APPROVAL_EXPIRED
        )

    async def _enqueue_expiry(self, run: RunRecord, now: datetime) -> bool:
        if await self._store.has_pending_work(run.tenant_id, run.run_id):
            return False  # a decision or an earlier sweep is already queued or running
        try:
            cont = await self._peek_cont(run.tenant_id, run.run_id)
        except KernelError:
            return False
        if cont.pending_action_id is None or cont.approval_requested_at is None:
            return False
        if now <= cont.approval_requested_at + self._approval_ttl:
            return False
        payload = {
            "action_id": cont.pending_action_id,
            "requested_at": cont.approval_requested_at.isoformat(),
        }
        await self._store.enqueue_work(
            run.tenant_id, run.run_id, "expire", payload, digest(payload)
        )
        return True

    async def sweep_expired_approvals(self) -> int:
        """Enqueue fenced `expire` work for every approval past its TTL.

        Never mutates run, action or continuation state: the worker applies the expiry
        under a work claim (ADR 0019).
        """
        now = self._clock()
        queued = 0
        for run in await self._store.list_unfinished_runs():
            if run.state is not RunState.WAITING_APPROVAL:
                continue
            try:
                if await self._enqueue_expiry(run, now):
                    queued += 1
            except Exception as exc:  # one bad run must not block the rest of the sweep
                LOG.warning(
                    "approval sweep skipped run %s/%s (%s)",
                    run.tenant_id,
                    run.run_id,
                    type(exc).__name__,
                )
        return queued

    async def expire_approval(self, tenant_id: str, run_id: str, action_id: str) -> RunRecord:
        """Executed under a work claim: re-check everything, then apply the expiry outcome."""
        run = await self._store.get_run(tenant_id, run_id)
        if run.state is not RunState.WAITING_APPROVAL:
            return run
        cont = await self._load_cont(tenant_id, run_id)
        if cont.pending_action_id != action_id or cont.approval_requested_at is None:
            return run
        if self._clock() <= cont.approval_requested_at + self._approval_ttl:
            return run
        action = await self._store.get_action(tenant_id, action_id)
        return await self._expire_pending(cont, action)

    async def decide(
        self,
        *,
        actor: Principal,
        run_id: str,
        action_id: str,
        action_digest: str,
        expected_run_revision: int,
        decision: ApprovalDecision,
    ) -> RunRecord:
        run = await self._store.get_run(actor.tenant_id, run_id)
        if APPROVER_ROLE not in actor.roles:
            raise KernelError(ErrorCode.FORBIDDEN, "actor is not an approver")
        if actor.principal_id == run.requester_id and not self._allow_self_approval:
            raise KernelError(ErrorCode.FORBIDDEN, "the requester cannot approve their own run")
        if run.revision != expected_run_revision:
            raise KernelError(ErrorCode.CONFLICT, "run changed; reload before deciding")
        cont = await self._load_cont(run.tenant_id, run_id)
        if run.state is not RunState.WAITING_APPROVAL or cont.pending_action_id != action_id:
            raise KernelError(ErrorCode.CONFLICT, "action is not awaiting approval")
        action = await self._store.get_action(actor.tenant_id, action_id)
        if action.digest != action_digest:
            raise KernelError(ErrorCode.APPROVAL_STALE, "digest does not match pending action")
        if cont.surface_digest and cont.surface_digest != self._registry.surface_digest():
            # Plugins, schemas or bindings changed since the proposal was made (T17).
            await self._transition(
                action,
                ActionState.BLOCKED,
                (RunEventType.APPROVAL_DECIDED, {"decision": "surface_changed"}),
            )
            cont.pending_action_id = None
            run = await self._store.get_run(actor.tenant_id, run_id)
            await self._set_run_state(
                run, RunState.FAILED, "capability surface changed", code=ReasonCode.SURFACE_CHANGED
            )
            raise KernelError(ErrorCode.APPROVAL_STALE, "capabilities changed; start a new run")
        now = self._clock()
        assert cont.approval_requested_at is not None
        if now > cont.approval_requested_at + self._approval_ttl:
            await self._expire_pending(cont, action)
            raise KernelError(ErrorCode.APPROVAL_STALE, "approval window expired")

        record = ApprovalRecord(
            approval_id=new_id("apr"),
            tenant_id=actor.tenant_id,
            run_id=run_id,
            action_id=action_id,
            action_digest=action_digest,
            actor_id=actor.principal_id,
            decision=decision,
            policy_version=str(cont.canonical_proposal["policy_version"]),
            issued_at=now,
            expires_at=now + self._approval_ttl,
        )
        approved_action = action.model_copy(
            update={
                "state": ActionState.BLOCKED
                if decision is ApprovalDecision.REJECTED
                else ActionState.APPROVED,
                "revision": action.revision + 1,
            }
        )
        await self._store.record_approval(
            record,
            [
                (
                    RunEventType.APPROVAL_DECIDED,
                    {"decision": decision, "actor_id": actor.principal_id, "digest": action_digest},
                    action_id,
                )
            ],
            action=approved_action,
            expected_revision=action.revision,
        )
        if decision is ApprovalDecision.REJECTED:
            cont.pending_action_id = None
            run = await self._store.get_run(actor.tenant_id, run_id)
            return await self._set_run_state(
                run, RunState.FAILED, "rejected by approver", code=ReasonCode.APPROVAL_REJECTED
            )
        return await self._dispatch(cont, approved_action, record)

    # -------------------------------------------------------------- dispatch
    async def _dispatch(
        self, cont: _Continuation, action: ActionRecord, approval: ApprovalRecord
    ) -> RunRecord:
        ctx = cont.ctx
        run = await self._store.get_run(ctx.tenant_id, ctx.run_id)
        try:
            stale_reason = await self._staleness(cont, action)
        except TimeoutError:
            await self._transition(action, ActionState.BLOCKED)
            cont.pending_action_id = None
            return await self._exhausted(run, "active time or provider deadline")
        run = await self._store.get_run(ctx.tenant_id, ctx.run_id)  # reads advanced revision
        if stale_reason is None and self._clock() > approval.expires_at:
            stale_reason = "approval expired before dispatch"
        if stale_reason is not None:
            await self._transition(
                action,
                ActionState.BLOCKED,
                (RunEventType.VALIDATION_COMPLETED, {"status": "STALE", "reason": stale_reason}),
            )
            cont.pending_action_id = None
            if cont.repairs >= ctx.budgets.max_validation_repairs:
                return await self._set_run_state(
                    run, RunState.FAILED, stale_reason, code=ReasonCode.STALE
                )
            cont.repairs += 1
            run = await self._set_run_state(
                run, RunState.RUNNING, stale_reason, code=ReasonCode.STALE
            )
            stale = Finding(
                rule_id="KERNEL-STALE",
                rule_version="1",
                status=ValidationStatus.FAIL,
                message=stale_reason,
            )
            return await self._drive(
                run,
                DriverInput(
                    task=run.task, observations=tuple(cont.observations.values()), findings=(stale,)
                ),
            )

        reserved = action.model_copy(
            update={"state": ActionState.RESERVED, "revision": action.revision + 1}
        )
        try:
            action = await self._store.reserve_operation(
                reserved,
                action.revision,
                [
                    (
                        RunEventType.ACTION_RESERVED,
                        {"logical_operation_id": action.logical_operation_id},
                        action.action_id,
                    )
                ],
            )
        except DuplicateOperation:
            await self._transition(action, ActionState.BLOCKED)
            return await self._set_run_state(
                run,
                RunState.FAILED,
                "operation already reserved",
                code=ReasonCode.OPERATION_RESERVED,
            )
        cont.writes += 1
        action = await self._transition(
            action, ActionState.DISPATCHING, (RunEventType.ACTION_DISPATCHING, {"attempt": 1})
        )
        binding = self._registry.resolve(action.contract_id, action.connection_id)
        executor = self._registry.executor_for(binding)
        dispatch_ctx = ctx.model_copy(
            update={
                "credential_versions": {
                    **ctx.credential_versions,
                    action.connection_id: action.credential_version,
                }
            }
        )
        started = self._clock()
        try:
            async with self._store.writer_lock(ctx.tenant_id, action.connection_id):
                receipt = await self._timed(
                    cont,
                    lambda: executor.execute(dispatch_ctx, binding, action, 1),
                    ctx.budgets.provider_timeout_seconds,
                    cancellable=False,
                )
        except KnownNoEffectError as exc:
            receipt = ExecutionReceipt(
                action_id=action.action_id,
                attempt=1,
                status=ReceiptStatus.FAILED,
                sanitized_error=exc.code,
                started_at=started,
                finished_at=self._clock(),
            )
        except Exception as exc:  # ambiguous: the provider may have committed
            receipt = ExecutionReceipt(
                action_id=action.action_id,
                attempt=1,
                status=ReceiptStatus.UNKNOWN,
                sanitized_error=type(exc).__name__,
                started_at=started,
                finished_at=self._clock(),
            )
        return await self._apply_receipt(cont, action, receipt)

    async def _staleness(self, cont: _Continuation, action: ActionRecord) -> str | None:
        ctx = cont.ctx
        try:
            connection = self._connections.usable(ctx, action.connection_id)
        except KernelError as exc:
            return f"connection unavailable: {exc.code}"
        if (
            connection.version != action.connection_version
            or connection.credential_subject() != action.credential_subject
        ):
            return "connection changed since approval"
        if self._registry.surface_digest() != cont.surface_digest:
            return "tool surface changed since approval"
        if self._credentials is not None:
            current_version = await self._credentials.version(ctx, action.connection_id)
            if current_version != action.credential_version:
                return "credential changed since approval"
        descriptor = self._registry.descriptor(action.contract_id)
        decision = self._policy.evaluate(ctx, descriptor, action.connection_id)
        if not decision.permitted:
            return "policy no longer permits the action"
        if decision.policy_version != cont.canonical_proposal.get("policy_version"):
            return "policy changed since approval"
        stale_reason = None
        for request_id, request in cont.reads.items():
            fresh = await self._gateway_read(cont, request, count_budget=True)
            before = cont.observations[request_id]
            cont.observations[request_id] = fresh
            if (
                fresh.evidence.revision != before.evidence.revision
                or fresh.evidence.completeness != before.evidence.completeness
                or (
                    (fresh.evidence.revision is None or before.evidence.revision is None)
                    and fact_digest(fresh.data) != fact_digest(before.data)
                )
            ):
                stale_reason = f"material source changed: {request.contract_id}"
        binding = self._registry.resolve(action.contract_id, action.connection_id)
        validation = await self._validate(
            ctx,
            cont,
            ActionProposal(
                contract_id=action.contract_id,
                connection_id=action.connection_id,
                arguments=action.arguments,
                expected_effects=tuple(cont.canonical_proposal.get("expected_effects", [])),
            ),
            binding,
        )
        if validation.blocks_write:
            return "fresh validation blocked the action"
        if validation.rule_bundle_version != cont.canonical_proposal.get("rule_bundle_version"):
            return "rules changed since approval"
        return stale_reason

    async def _apply_receipt(
        self, cont: _Continuation, action: ActionRecord, receipt: ExecutionReceipt
    ) -> RunRecord:
        ctx = cont.ctx
        target = {
            ReceiptStatus.COMMITTED: ActionState.COMMITTED,
            ReceiptStatus.FAILED: ActionState.FAILED,
            ReceiptStatus.UNKNOWN: ActionState.UNKNOWN,
        }[receipt.status]
        if target not in ALLOWED_ACTION_TRANSITIONS[action.state]:
            raise KernelError(ErrorCode.CONFLICT, f"illegal transition {action.state}->{target}")
        event_type = (
            RunEventType.ACTION_UNKNOWN
            if target is ActionState.UNKNOWN
            else RunEventType.ACTION_RECEIPT_RECORDED
        )
        action = await self._store.record_receipt(
            receipt,
            action.model_copy(update={"state": target, "revision": action.revision + 1}),
            action.revision,
            [(event_type, receipt.model_dump(mode="json"), action.action_id)],
        )
        run = await self._store.get_run(ctx.tenant_id, ctx.run_id)
        if target is ActionState.UNKNOWN:
            return await self._set_run_state(
                run,
                RunState.NEEDS_RECONCILIATION,
                "write outcome unknown; reconcile before any retry",
                code=ReasonCode.EFFECT_UNKNOWN,
            )
        if target is ActionState.FAILED:
            cont.pending_action_id = None
            return await self._set_run_state(
                run, RunState.FAILED, "provider rejected the write", code=ReasonCode.PROVIDER_ERROR
            )
        run = await self._set_run_state(run, RunState.VERIFYING)
        return await self._verify(cont, action, receipt)

    async def _verify(
        self, cont: _Continuation, action: ActionRecord, receipt: ExecutionReceipt
    ) -> RunRecord:
        ctx = cont.ctx
        verifier = self._registry.verifier_for(action.contract_id)
        run = await self._store.get_run(ctx.tenant_id, ctx.run_id)
        if verifier is None:
            return await self._set_run_state(
                run,
                RunState.VERIFYING,
                "no verifier registered",
                code=ReasonCode.VERIFICATION_PENDING,
            )
        reader = _GatewayReader(self, cont, action.connection_id)
        try:
            report = await verifier.verify(ctx, action, receipt, reader)
        except Exception as exc:  # verification unavailable: keep unresolved, never retry write
            report = OutcomeReport(
                run_id=ctx.run_id,
                action_id=action.action_id,
                status=OutcomeStatus.UNKNOWN,
                checks=(),
                verifier_id=verifier.verifier_id,
                verifier_version="?",
                reported_at=self._clock(),
            )
            await self._store.record_outcome(
                ctx.tenant_id,
                report,
                None,
                None,
                [
                    (
                        RunEventType.OUTCOME_REPORTED,
                        {"status": "UNKNOWN", "error": type(exc).__name__},
                        action.action_id,
                    )
                ],
            )
            run = await self._store.get_run(ctx.tenant_id, ctx.run_id)
            return await self._set_run_state(
                run,
                RunState.VERIFYING,
                "verification unavailable",
                code=ReasonCode.VERIFICATION_PENDING,
            )
        target = (
            ActionState.VERIFIED
            if report.status is OutcomeStatus.VERIFIED
            else ActionState.VERIFICATION_FAILED
        )
        if report.status is OutcomeStatus.UNKNOWN:
            await self._store.record_outcome(
                ctx.tenant_id,
                report,
                None,
                None,
                [(RunEventType.OUTCOME_REPORTED, report.model_dump(mode="json"), action.action_id)],
            )
            run = await self._store.get_run(ctx.tenant_id, ctx.run_id)
            return await self._set_run_state(
                run,
                RunState.VERIFYING,
                "verification inconclusive",
                code=ReasonCode.VERIFICATION_PENDING,
            )
        current = await self._store.get_action(ctx.tenant_id, action.action_id)
        await self._store.record_outcome(
            ctx.tenant_id,
            report,
            current.model_copy(update={"state": target, "revision": current.revision + 1}),
            current.revision,
            [(RunEventType.OUTCOME_REPORTED, report.model_dump(mode="json"), action.action_id)],
        )
        cont.pending_action_id = None
        run = await self._store.get_run(ctx.tenant_id, ctx.run_id)
        if target is ActionState.VERIFICATION_FAILED:
            return await self._set_run_state(
                run,
                RunState.FAILED,
                "outcome verification failed",
                code=ReasonCode.VERIFICATION_FAILED,
            )
        return await self._finish_verified(
            cont, receipt.external_refs, "The approved action was independently verified."
        )

    async def _finish_verified(
        self,
        cont: _Continuation,
        external_refs: tuple[str, ...],
        fallback: str,
        *,
        acknowledge: bool = True,
    ) -> RunRecord:
        """Finish a verified write or repeated answer without executing acknowledgement tools."""
        ctx = cont.ctx
        run = await self._store.get_run(ctx.tenant_id, ctx.run_id)
        final: Any = FinalAnswer(text=fallback)
        try:
            if acknowledge and (
                getattr(self._driver, "tokens_used", lambda _: 0)(ctx.run_id)
                < ctx.budgets.max_model_tokens
            ):
                final = await self._timed(
                    cont,
                    lambda: self._driver.advance(
                        ctx,
                        DriverInput(
                            task=run.task,
                            observations=tuple(cont.observations.values()),
                            action_result={
                                "status": "VERIFIED",
                                "external_refs": list(external_refs),
                            },
                        ),
                    ),
                    ctx.budgets.model_timeout_seconds,
                )
        except Exception as exc:
            run = await self._store.get_run(ctx.tenant_id, ctx.run_id)
            run = await self._store.update_run(
                run.model_copy(update={"revision": run.revision + 1}),
                run.revision,
                [
                    (
                        RunEventType.BUDGET_EXHAUSTED,
                        {"budget": "final response", "error": type(exc).__name__},
                        None,
                    )
                ],
            )
        if not isinstance(final, FinalAnswer):
            final = FinalAnswer(text=fallback)
        if isinstance(final, FinalAnswer):
            run = await self._store.update_run(
                run.model_copy(update={"revision": run.revision + 1}),
                run.revision,
                [(RunEventType.MESSAGE_FINAL, {"text": final.text}, None)],
            )
        return await self._set_run_state(
            run, RunState.SUCCEEDED, "outcome verified", code=ReasonCode.VERIFIED
        )

    # --------------------------------------------------------- reconciliation
    async def reconcile(self, operator: Principal, run_id: str) -> RunRecord:
        """Read-only reconciliation of UNKNOWN actions. Never re-sends a write."""
        run = await self._store.get_run(operator.tenant_id, run_id)
        if run.state is not RunState.NEEDS_RECONCILIATION:
            raise KernelError(ErrorCode.CONFLICT, "run does not need reconciliation")
        cont = await self._load_cont(run.tenant_id, run_id)
        actions = [
            a
            for a in await self._store.list_actions(operator.tenant_id, run_id)
            if a.state is ActionState.UNKNOWN
        ]
        if not actions:
            raise KernelError(ErrorCode.CONFLICT, "no unresolved action")
        action = actions[0]
        binding = self._registry.resolve(action.contract_id, action.connection_id)
        found = await self._registry.executor_for(binding).reconcile(cont.ctx, binding, action)
        await self._store.update_run(
            run.model_copy(update={"revision": run.revision + 1}),
            run.revision,
            [
                (
                    RunEventType.RECONCILIATION_COMPLETED,
                    {"found": found.status if found else "not_found"},
                    action.action_id,
                )
            ],
        )
        if found is None:
            return await self._store.get_run(operator.tenant_id, run_id)  # stays unresolved
        return await self._apply_receipt(cont, action, found)

    async def cancel(self, actor: Principal, run_id: str) -> RunRecord:
        run = await self._store.get_run(actor.tenant_id, run_id)
        if run.state in TERMINAL_RUN_STATES:
            return run
        unresolved = [
            a
            for a in await self._store.list_actions(actor.tenant_id, run_id)
            if a.state in {ActionState.DISPATCHING, ActionState.UNKNOWN}
        ]
        run = await self._store.update_run(
            run.model_copy(update={"revision": run.revision + 1}),
            run.revision,
            [(RunEventType.RUN_CANCEL_REQUESTED, {"actor_id": actor.principal_id}, None)],
        )
        if unresolved:
            return await self._set_run_state(
                run,
                RunState.NEEDS_RECONCILIATION,
                "cancel requested; effect must be reconciled",
                code=ReasonCode.EFFECT_UNKNOWN,
            )
        try:
            cont: _Continuation | None = await self._load_cont(actor.tenant_id, run_id)
        except KernelError:
            cont = None
        if cont and cont.pending_action_id:
            pending = await self._store.get_action(actor.tenant_id, cont.pending_action_id)
            if ActionState.BLOCKED in ALLOWED_ACTION_TRANSITIONS[pending.state]:
                await self._transition(pending, ActionState.BLOCKED)
            cont.pending_action_id = None
        cancelled = await self._set_run_state(
            run, RunState.CANCELLED, "cancelled before dispatch", code=ReasonCode.CANCELLED
        )
        active = self._active_calls.get(run_id)
        if active is not None:
            active.cancel()
        return cancelled

    # --------------------------------------------------------------- recovery
    async def recover(self) -> list[RunRecord]:
        """Startup recovery (MVP design §9 crash rules). Never sends a write.

        - DISPATCHING: the call may have executed -> UNKNOWN, reconcile later.
        - APPROVED/RESERVED without dispatch: blocked; a new approval is required.
        - COMMITTED while VERIFYING: re-run the independent read-back.
        - RUNNING with no pending effect: the driver turn was lost -> FAILED.
        """
        recovered: list[RunRecord] = []
        for run in await self._store.list_unfinished_runs():
            if await self._store.has_pending_work(run.tenant_id, run.run_id):
                continue
            result = await self._recover_run(run)
            if result is not None:
                recovered.append(result)
        return recovered

    async def recover_run(self, tenant_id: str, run_id: str) -> RunRecord:
        """Apply the crash rules to one run whose host-side work died unexpectedly."""
        run = await self._store.get_run(tenant_id, run_id)
        if run.state in TERMINAL_RUN_STATES:
            return run
        self._runs.pop(run_id, None)  # the in-memory continuation may be mid-mutation
        return await self._recover_run(run) or run

    async def _recover_run(self, run: RunRecord) -> RunRecord | None:
        actions = await self._store.list_actions(run.tenant_id, run.run_id)
        events = await self._store.list_events(run.tenant_id, run.run_id)
        latest_id = next(
            (
                event.action_id
                for event in reversed(events)
                if event.type is RunEventType.PROPOSAL_CREATED
            ),
            None,
        )
        latest = next((action for action in actions if action.action_id == latest_id), None)
        try:
            cont = await self._load_cont(run.tenant_id, run.run_id)
        except KernelError:
            cont = None
        dispatching = [a for a in actions if a.state is ActionState.DISPATCHING]
        undispatched = [
            a for a in actions if a.state in {ActionState.APPROVED, ActionState.RESERVED}
        ]
        committed = [a for a in actions if a.state is ActionState.COMMITTED]
        if dispatching and cont is not None:
            action = dispatching[0]
            now = self._clock()
            receipt = ExecutionReceipt(
                action_id=action.action_id,
                attempt=1,
                status=ReceiptStatus.UNKNOWN,
                sanitized_error="worker lost during dispatch",
                started_at=now,
                finished_at=now,
            )
            return await self._apply_receipt(cont, action, receipt)
        elif undispatched:
            for action in undispatched:
                await self._transition(action, ActionState.BLOCKED)
            if cont is not None:
                cont.pending_action_id = None
            run = await self._store.get_run(run.tenant_id, run.run_id)
            return await self._set_run_state(
                run,
                RunState.FAILED,
                "interrupted before dispatch; approve a new run",
                code=ReasonCode.INTERRUPTED,
            )
        elif committed and cont is not None:
            receipts = await self._store.list_receipts(run.tenant_id, committed[0].action_id)
            return await self._verify(cont, committed[0], receipts[-1])
        elif any(a.state is ActionState.UNKNOWN for a in actions):
            return await self._set_run_state(
                run,
                RunState.NEEDS_RECONCILIATION,
                "persisted write outcome unknown",
                code=ReasonCode.EFFECT_UNKNOWN,
            )
        elif (
            latest is not None
            and latest.state is ActionState.VERIFIED
            and run.state
            not in {
                RunState.WAITING_APPROVAL,
                RunState.WAITING_INPUT,
            }
        ):
            if cont is not None:
                cont.pending_action_id = None
            return await self._set_run_state(
                run, RunState.SUCCEEDED, "outcome verified", code=ReasonCode.VERIFIED
            )
        elif latest is not None and latest.state is ActionState.VERIFICATION_FAILED:
            return await self._set_run_state(
                run,
                RunState.FAILED,
                "outcome verification failed",
                code=ReasonCode.VERIFICATION_FAILED,
            )
        elif run.state in {RunState.RUNNING, RunState.CREATED}:
            return await self._set_run_state(
                run, RunState.FAILED, "interrupted during driver turn", code=ReasonCode.INTERRUPTED
            )
        return None
