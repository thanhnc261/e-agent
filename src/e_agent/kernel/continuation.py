"""Run continuation state shared by the coordinator mixins (Phase 1 split of coordinator.py).

ContinuationMixin is the base of every coordinator mixin: it declares the
attributes RunCoordinator.__init__ sets and, for type checking only, the
methods one mixin calls on another.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable, Mapping
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from e_agent.contracts.action import ActionRecord, ActionState
from e_agent.contracts.approval import ApprovalRecord
from e_agent.contracts.capability import CapabilityBinding
from e_agent.contracts.common import new_id
from e_agent.contracts.context import Budgets, TaskContext
from e_agent.contracts.events import RunEventType
from e_agent.contracts.evidence import Completeness
from e_agent.contracts.plan import ActionProposal
from e_agent.contracts.receipt import ExecutionReceipt
from e_agent.contracts.run import (
    ReasonCode,
    RunRecord,
    RunState,
)
from e_agent.contracts.validation import Finding, ValidationResult
from e_agent.sdk.auth import CredentialVersionProvider
from e_agent.sdk.errors import KnownNoEffectError
from e_agent.sdk.ports import (
    AgentDriver,
    DriverInput,
    Observation,
    PolicyEvaluator,
    ReadRequest,
)
from e_agent.sdk.store import RunStore
from pydantic import BaseModel, Field

from .connections import ConnectionCatalog
from .errors import ErrorCode, KernelError
from .registry import PluginRegistry

LOG = logging.getLogger("e_agent.kernel.coordinator")


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
            self, run: RunRecord, cont: _Continuation, proposal: ActionProposal
        ) -> RunRecord | DriverInput:
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
        ) -> RunRecord:
            raise NotImplementedError

        def _check_run_transition(self, run: RunRecord, to: RunState) -> None:
            raise NotImplementedError

        async def _exhausted(self, run: RunRecord, what: str) -> RunRecord:
            raise NotImplementedError

        async def _transition(
            self,
            action: ActionRecord,
            to: ActionState,
            event: tuple[RunEventType, dict[str, Any]] | None = None,
        ) -> ActionRecord:
            raise NotImplementedError

        async def _finish_verified(
            self,
            cont: _Continuation,
            external_refs: tuple[str, ...],
            fallback: str,
            *,
            acknowledge: bool = True,
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
            self, cont: _Continuation, action: ActionRecord, receipt: ExecutionReceipt
        ) -> RunRecord:
            raise NotImplementedError

        async def _apply_receipt(
            self, cont: _Continuation, action: ActionRecord, receipt: ExecutionReceipt
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
