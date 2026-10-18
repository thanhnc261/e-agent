"""Dispatch of approved actions: staleness, reservation and receipts (Phase 1 split)."""

from __future__ import annotations

from e_agent.contracts.action import ALLOWED_ACTION_TRANSITIONS, ActionRecord, ActionState
from e_agent.contracts.approval import ApprovalRecord
from e_agent.contracts.events import RunEventType
from e_agent.contracts.plan import ActionProposal
from e_agent.contracts.receipt import ExecutionReceipt, ReceiptStatus
from e_agent.contracts.run import (
    ReasonCode,
    RunRecord,
    RunState,
)
from e_agent.contracts.step import StepKind, StepRecord, StepStatus
from e_agent.contracts.validation import Finding, ValidationStatus
from e_agent.sdk.errors import KnownNoEffectError
from e_agent.sdk.ports import (
    DriverInput,
)
from e_agent.sdk.store import ConnectionBusy, DuplicateOperation

from .approval import (
    fact_digest,
)
from .continuation import _Continuation
from .errors import ErrorCode, KernelError
from .ir_on import IrOnMixin

RECEIPT_STEP = {
    ReceiptStatus.COMMITTED: StepStatus.SUCCEEDED,
    ReceiptStatus.FAILED: StepStatus.FAILED,
    ReceiptStatus.UNKNOWN: StepStatus.UNKNOWN,
}
"""How a receipt ends a linked action's dispatch step (execution IR ``on``)."""


class DispatchMixin(IrOnMixin):
    # -------------------------------------------------------------- dispatch
    async def _dispatch(
        self, cont: _Continuation, action: ActionRecord, approval: ApprovalRecord
    ) -> RunRecord:
        ctx = cont.ctx
        run = await self._store.get_run(ctx.tenant_id, ctx.run_id)
        # A plan step after the first: created PROPOSED by `_start_step`, its validate step
        # open, approved by the plan digest. Derived from the plan, not the action state.
        later_step = cont.plan is not None and (action.step_index or 0) > 0
        try:
            stale_reason = await self._staleness(cont, action)
        except TimeoutError:  # the revalidation's rows end with the block
            timeout = {"status": "STALE", "reason": "revalidation deadline"}
            event = (RunEventType.VALIDATION_COMPLETED, timeout) if later_step else None
            steps = await self._revalidated(action, StepStatus.FAILED)
            await self._transition(action, ActionState.BLOCKED, event, steps=steps)
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
                steps=await self._revalidated(action, StepStatus.BLOCKED),
            )
            cont.pending_action_id = None
            if later_step or cont.repairs >= ctx.budgets.max_validation_repairs:
                # After the first reservation a plan never repairs: it stops (§6.4.6).
                return await self._set_run_state(
                    run, RunState.FAILED, stale_reason, code=ReasonCode.STALE
                )
            cont.repairs += 1
            cont.plan = None  # the driver proposes again; an unstarted plan is dropped
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
        revalidated: list[StepRecord] = []  # a first step's pass, stored with its reservation
        if later_step:  # revalidated with its resolved lineage: approved by the plan digest
            action = await self._transition(
                action,
                ActionState.VALIDATED,
                (RunEventType.VALIDATION_COMPLETED, {"status": "PASS", "findings": []}),
                steps=await self._step_finish(action, StepKind.VALIDATE, StepStatus.SUCCEEDED),
            )
        else:
            revalidated = await self._step_pair(action, StepKind.VALIDATE, StepStatus.SUCCEEDED)

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
                    ),
                    *revalidated,
                    *await self._step_start(action, StepKind.DISPATCH, after=revalidated),
                ],
            )
        except ConnectionBusy:
            # ADR 0020: another action on this connection is RESERVED, DISPATCHING or UNKNOWN.
            # Caught here, before any generic ConcurrencyConflict handler, so it never escapes
            # as an HTTP 409.
            await self._block_if_allowed(action, revalidated)
            cont.pending_action_id = None
            return await self._set_run_state(
                run,
                RunState.FAILED,
                "connection has an unresolved write; reconcile it first",
                code=ReasonCode.CONNECTION_BUSY,
            )
        except DuplicateOperation:
            await self._block_if_allowed(action, revalidated)
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

    async def _block_if_allowed(self, action: ActionRecord, revalidated: list[StepRecord]) -> None:
        """BLOCKED from an approved action, with the passing revalidation rows its refused
        reservation did not store; a plan's later step is VALIDATED when it reserves and has
        no BLOCKED transition, so it keeps its state and the run fails (2c.8)."""
        if ActionState.BLOCKED in ALLOWED_ACTION_TRANSITIONS[action.state]:
            await self._transition(action, ActionState.BLOCKED, steps=revalidated)

    async def _staleness(self, cont: _Continuation, action: ActionRecord) -> str | None:
        ctx = cont.ctx
        approved = self._approved_input(cont)
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
        if decision.policy_version != approved.get("policy_version"):
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
                expected_effects=tuple(approved.get("expected_effects", [])),
            ),
            binding,
        )
        if validation.blocks_write:
            return "fresh validation blocked the action"
        if validation.rule_bundle_version != approved.get("rule_bundle_version"):
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
            [
                (event_type, receipt.model_dump(mode="json"), action.action_id),
                *await self._step_finish(action, StepKind.DISPATCH, RECEIPT_STEP[receipt.status]),
            ],
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
