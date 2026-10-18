"""Dispatch of approved actions: staleness, reservation and receipts (Phase 1 split)."""

from __future__ import annotations

from typing import Any

from e_agent.contracts.action import ALLOWED_ACTION_TRANSITIONS, ActionRecord, ActionState
from e_agent.contracts.approval import ApprovalRecord
from e_agent.contracts.digest import canonicalize
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
    compute_digest,
    fact_digest,
    plan_digest_wrapper,
)
from .continuation import NextStep, _Continuation
from .errors import ErrorCode, KernelError
from .ir import LineageRejected, substitute_lineage
from .ir_on import IrOnMixin, _fixed

RECEIPT_STEP = {
    ReceiptStatus.COMMITTED: StepStatus.SUCCEEDED,
    ReceiptStatus.FAILED: StepStatus.FAILED,
    ReceiptStatus.UNKNOWN: StepStatus.UNKNOWN,
}
"""How a receipt ends a linked action's dispatch step (execution IR ``on``)."""

ARGUMENTS_CHANGED = "The action no longer matches what its approval bound."
"""The fixed message of the ``KERNEL-ARGUMENTS-CHANGED`` finding (Codex C-3)."""
CHANGED_REASON = "arguments changed since approval"
PLAN_DIGEST_CHANGED = "The plan's approved step inputs no longer match the approved plan digest."
"""The fixed message of the ``KERNEL-PLAN-DIGEST-MISMATCH`` finding (phase review P-3)."""
PLAN_CHANGED_REASON = "plan changed since approval"


def dispatch_input(approved: dict[str, Any], action: ActionRecord) -> dict[str, Any]:
    """``approved`` (a digest input, `digest_input`) with every field the action carries
    taken from ``action`` as it will be dispatched."""
    return {
        **approved,
        "tenant_id": action.tenant_id,
        "logical_operation_id": action.logical_operation_id,
        "contract_id": action.contract_id,
        "binding_id": action.binding_id,
        "connection_id": action.connection_id,
        "connection_version": str(action.connection_version),
        "credential_subject": action.credential_subject,
        "credential_version": action.credential_version,
        "arguments": action.arguments,
    }


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
        # After `_staleness`, the last call that reaches plugin code. A later step is still
        # PROPOSED here, so a change blocks it; the check below repeats it last (Codex C-3).
        # A plan step's approved inputs are first tied back to the approval (review P-3).
        if await self._plan_digest_changed(cont, action, approval):
            plan_changed = _fixed("KERNEL-PLAN-DIGEST-MISMATCH", PLAN_DIGEST_CHANGED)
            return await self._arguments_refused(cont, action, plan_changed, PLAN_CHANGED_REASON)
        if later_step and self._arguments_changed(cont, action, approval):
            return await self._arguments_refused(cont, action)
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

        dispatch_rows = await self._step_start(action, StepKind.DISPATCH, after=revalidated)
        reserved = action.model_copy(
            update={"state": ActionState.RESERVED, "revision": action.revision + 1}
        )
        # The last operation before the reservation, on every path (`off` included): the
        # action exactly as it will be dispatched against what the approval bound.
        if self._arguments_changed(cont, reserved, approval):
            return await self._arguments_refused(cont, action)
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
                    *dispatch_rows,
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
        # Only the approval call and a resume claim dispatch, so this call may start a plan's
        # next step once this one is verified (Codex C-1); reconciliation and recovery never do.
        return await self._apply_receipt(cont, action, receipt, next_step=NextStep.START)

    @staticmethod
    def _arguments_changed(
        cont: _Continuation, action: ActionRecord, approval: ApprovalRecord
    ) -> bool:
        """Whether the digest input of ``action`` as it will be dispatched differs from the
        approved one: a single action's against ``approval.action_digest``, a plan step's
        against its approved step input with its lineage substituted from the verified
        values. Anything that cannot be rebuilt counts as changed (fail closed)."""
        plan = cont.plan
        try:
            if (
                plan is not None
                and plan.plan_id == action.plan_id
                and action.step_index is not None
            ):
                approved = plan.inputs[action.step_index]
                expected = {
                    **approved,
                    "arguments": substitute_lineage(approved["arguments"], plan.verified),
                }
                return canonicalize(dispatch_input(approved, action)) != canonicalize(expected)
            rebuilt = dispatch_input(cont.canonical_proposal, action)
            return compute_digest(rebuilt) != approval.action_digest
        except (LineageRejected, KeyError, IndexError, ValueError):
            return True

    async def _plan_digest_changed(
        self, cont: _Continuation, action: ActionRecord, approval: ApprovalRecord
    ) -> bool:
        """Whether a multi-step plan step's approved inputs, as the continuation holds them,
        no longer rebuild the plan digest the approval bound: the ``plan.v1`` wrapper over
        the step ids, the stored plan's dependencies and those inputs, as `_propose_plan`
        digested them. False for any other action; anything that cannot be rebuilt counts
        as changed (fail closed)."""
        plan = cont.plan
        if plan is None or plan.plan_id != action.plan_id or action.step_index is None:
            return False
        stored = await self._store.get_plan(cont.ctx.tenant_id, plan.plan_id)
        if not len(stored.steps) == len(plan.step_ids) == len(plan.inputs):
            return True
        try:
            wrapper = plan_digest_wrapper(
                (step_id, step.depends_on, step_input)
                for step_id, step, step_input in zip(
                    plan.step_ids, stored.steps, plan.inputs, strict=True
                )
            )
            return compute_digest(wrapper) != approval.action_digest
        except ValueError:  # outside the digest profile: it cannot be the approved plan
            return True

    async def _arguments_refused(
        self,
        cont: _Continuation,
        action: ActionRecord,
        finding: Finding | None = None,
        reason: str = CHANGED_REASON,
    ) -> RunRecord:
        """Stop before the reservation: the action BLOCKED where its state allows it (a later
        plan step already VALIDATED has no BLOCKED transition and keeps its state), the
        fixed ``finding`` (by default ``KERNEL-ARGUMENTS-CHANGED``), and the run FAILED
        STALE."""
        finding = finding or _fixed("KERNEL-ARGUMENTS-CHANGED", ARGUMENTS_CHANGED)
        payload = {
            "status": "STALE",
            "reason": reason,
            "findings": [finding.model_dump(mode="json")],
        }
        before: list[Any] = []
        if ActionState.BLOCKED in ALLOWED_ACTION_TRANSITIONS[action.state]:
            await self._transition(
                action,
                ActionState.BLOCKED,
                (RunEventType.VALIDATION_COMPLETED, payload),
                steps=await self._revalidated(action, StepStatus.BLOCKED),
            )
        else:
            before = [(RunEventType.VALIDATION_COMPLETED, payload, action.action_id)]
        cont.pending_action_id = None
        run = await self._store.get_run(cont.ctx.tenant_id, cont.ctx.run_id)
        return await self._set_run_state(
            run, RunState.FAILED, reason, code=ReasonCode.STALE, before=before
        )

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
        self,
        cont: _Continuation,
        action: ActionRecord,
        receipt: ExecutionReceipt,
        *,
        next_step: NextStep,
    ) -> RunRecord:
        """Record ``receipt`` and verify a committed write. ``next_step`` is the call's
        authority to start a plan's next step after this one verifies (`_after_step_verified`)."""
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
        # A plan step queued for its resume attaches no plan state (ADR 0025 amendment).
        queued = (
            next_step is NextStep.QUEUE
            and self._ir_on
            and cont.plan is not None
            and cont.plan.plan_id == action.plan_id
        )
        run = await self._set_run_state(run, RunState.VERIFYING, snapshot=not queued)
        return await self._verify(cont, action, receipt, next_step=next_step)
