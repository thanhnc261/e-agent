"""Run coordinator: drives the agent, gates every effect, owns approval and dispatch.

The coordinator is the only component that moves actions through the state
machine (MVP design §7-9, ADR 0003). Drivers only propose; validators only
report findings; executors only execute admitted invocations.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from e_agent.contracts.common import new_id, utc_now
from e_agent.contracts.context import Budgets, HostContext, Principal, TaskContext
from e_agent.contracts.events import RunEventType
from e_agent.contracts.features import Features
from e_agent.contracts.run import (
    RunRecord,
    RunState,
)
from e_agent.sdk.auth import CredentialVersionProvider
from e_agent.sdk.ports import (
    AgentDriver,
    DriverInput,
    PolicyEvaluator,
    SafeTextSink,
)
from e_agent.sdk.store import EventSpec, RunStore

from .approval_flow import ApprovalFlowMixin
from .connections import ConnectionCatalog
from .continuation import CONTINUATION_SCHEMA as CONTINUATION_SCHEMA
from .continuation import LOG as LOG
from .continuation import _Continuation as _Continuation
from .continuation import _GatewayReader as _GatewayReader
from .dispatch import DispatchMixin
from .errors import ErrorCode, KernelError
from .features import FeaturesMixin
from .gateway import GatewayMixin
from .ir_on import merged_budgets
from .plan_flow import PlanFlowMixin
from .recovery import RecoveryMixin
from .registry import PluginRegistry
from .run_loop import RunLoopMixin
from .transitions import TransitionsMixin
from .verification import VerificationMixin

DEFAULT_APPROVAL_TTL = timedelta(minutes=15)


class RunCoordinator(
    TransitionsMixin,
    RunLoopMixin,
    GatewayMixin,
    PlanFlowMixin,
    ApprovalFlowMixin,
    DispatchMixin,
    VerificationMixin,
    RecoveryMixin,
    FeaturesMixin,
):
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
        features: Features | None = None,
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
        self._features = features or Features()  # profile toggles (ADR 0027)
        self._runs: dict[str, _Continuation] = {}
        self._active_calls: dict[str, asyncio.Task[Any]] = {}
        self._resume_disabled: set[str] = set()

    # ------------------------------------------------------------------ runs
    def _prepare_run(
        self,
        principal: Principal,
        task: str,
        resource_scope: frozenset[str],
        *,
        run_id: str | None = None,
        host_context: HostContext | None = None,
        task_kind: str | None = None,
    ) -> tuple[RunRecord, _Continuation, list[EventSpec]]:
        run_id = run_id or new_id("run")
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
        run, admitted = self._admit_task(run, task_kind)  # execution IR (ADR 0027, ADR 0028)
        # `on` only: the admitted definition narrows the budgets (D7) and is snapshotted into
        # the continuation, which the run uses for its whole life (Codex C-1).
        definition = self._run_task(run) if self._ir_on else None
        ctx = TaskContext(
            run_id=run_id,
            tenant_id=principal.tenant_id,
            principal=principal,
            resource_scope=resource_scope,
            budgets=self._budgets
            if definition is None
            else merged_budgets(self._budgets, definition),
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
        cont = _Continuation(
            ctx=ctx, surface_digest=self._registry.surface_digest(), task=definition
        )
        return run, cont, [(RunEventType.RUN_CREATED, created, None), *admitted]

    async def start_run(
        self,
        principal: Principal,
        task: str,
        resource_scope: frozenset[str],
        *,
        run_id: str | None = None,
        host_context: HostContext | None = None,
        task_kind: str | None = None,
    ) -> RunRecord:
        """``task_kind`` names the run's task definition (D8, ADR 0028); in Phase 2 only the
        CLI passes it. ``off`` ignores it, and the run record is today's."""
        run, cont, events = self._prepare_run(
            principal,
            task,
            resource_scope,
            run_id=run_id,
            host_context=host_context,
            task_kind=task_kind,
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
        task_kind: str | None = None,
    ) -> tuple[str, bool]:
        """``task_kind`` as in `start_run`; the API passes none in Phase 2 (D8)."""
        run, cont, events = self._prepare_run(
            principal,
            task,
            resource_scope,
            run_id=run_id,
            host_context=host_context,
            task_kind=task_kind,
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
