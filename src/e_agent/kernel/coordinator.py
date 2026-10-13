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

from e_agent.contracts.action import ALLOWED_ACTION_TRANSITIONS, ActionRecord, ActionState
from e_agent.contracts.approval import ApprovalDecision, ApprovalRecord
from e_agent.contracts.common import new_id, utc_now
from e_agent.contracts.context import Budgets, HostContext, Principal, TaskContext
from e_agent.contracts.digest import digest
from e_agent.contracts.events import RunEventType
from e_agent.contracts.outcome import OutcomeReport, OutcomeStatus
from e_agent.contracts.plan import ActionProposal
from e_agent.contracts.receipt import ExecutionReceipt, ReceiptStatus
from e_agent.contracts.run import (
    TERMINAL_RUN_STATES,
    ReasonCode,
    RunRecord,
    RunState,
)
from e_agent.contracts.validation import Finding, ValidationStatus
from e_agent.sdk.auth import CredentialVersionProvider
from e_agent.sdk.errors import KnownNoEffectError
from e_agent.sdk.ports import (
    AgentDriver,
    DriverInput,
    FinalAnswer,
    PolicyEvaluator,
    SafeTextSink,
)
from e_agent.sdk.store import ConnectionBusy, DuplicateOperation, EventSpec, RunStore

from .approval import (
    ApprovalPresentation,
    fact_digest,
    presentation_for,
)
from .connections import ConnectionCatalog
from .continuation import CONTINUATION_SCHEMA as CONTINUATION_SCHEMA
from .continuation import LOG as LOG
from .continuation import _Continuation as _Continuation
from .continuation import _GatewayReader as _GatewayReader
from .errors import ErrorCode, KernelError
from .gateway import GatewayMixin
from .policy import APPROVER_ROLE
from .proposals import ProposalsMixin
from .registry import PluginRegistry
from .run_loop import RunLoopMixin
from .transitions import TransitionsMixin

DEFAULT_APPROVAL_TTL = timedelta(minutes=15)


class RunCoordinator(TransitionsMixin, RunLoopMixin, GatewayMixin, ProposalsMixin):
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
            LOG.debug("approval sweep: no continuation for run %s/%s", run.tenant_id, run.run_id)
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
                    exc_info=True,
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
        except ConnectionBusy:
            # ADR 0020: another action on this connection is RESERVED, DISPATCHING or UNKNOWN.
            # Caught here, before any generic ConcurrencyConflict handler, so it never escapes
            # as an HTTP 409.
            await self._transition(action, ActionState.BLOCKED)
            cont.pending_action_id = None
            return await self._set_run_state(
                run,
                RunState.FAILED,
                "connection has an unresolved write; reconcile it first",
                code=ReasonCode.CONNECTION_BUSY,
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
            try:
                result = await self._recover_run(run)
            except Exception as exc:  # one bad run must not block the rest of recovery
                LOG.warning(
                    "startup recovery skipped run %s/%s (%s)",
                    run.tenant_id,
                    run.run_id,
                    type(exc).__name__,
                    exc_info=True,
                )
                continue
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
