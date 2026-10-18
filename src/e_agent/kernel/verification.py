"""Independent outcome verification (Phase 1 split of coordinator.py)."""

from __future__ import annotations

from typing import Any

from e_agent.contracts.action import ActionRecord, ActionState
from e_agent.contracts.events import RunEventType
from e_agent.contracts.outcome import OutcomeReport, OutcomeStatus
from e_agent.contracts.receipt import ExecutionReceipt
from e_agent.contracts.run import (
    ReasonCode,
    RunRecord,
    RunState,
)
from e_agent.contracts.step import StepKind, StepRecord, StepStatus
from e_agent.sdk.ports import (
    DriverInput,
    FinalAnswer,
)
from e_agent.sdk.store import EventSpec

from .continuation import _Continuation, _GatewayReader
from .ir_on import IrOnMixin

OUTCOME_STEP = {
    OutcomeStatus.VERIFIED: StepStatus.SUCCEEDED,
    OutcomeStatus.FAILED: StepStatus.FAILED,
    OutcomeStatus.UNKNOWN: StepStatus.UNKNOWN,
}
"""How an outcome ends a linked action's verify step (execution IR ``on``)."""


def outcome_payload(report: OutcomeReport) -> dict[str, Any]:
    """The ``outcome.reported`` payload: the report without its read-back values, which only
    the stored outcome and a plan's lineage see, so they never reach an export (PR-26)."""
    return report.model_dump(mode="json", exclude={"verified_values"})


class VerificationMixin(IrOnMixin):
    async def _verify(
        self, cont: _Continuation, action: ActionRecord, receipt: ExecutionReceipt
    ) -> RunRecord:
        ctx = cont.ctx
        verifier = self._registry.verifier_for(action.contract_id)
        run = await self._store.get_run(ctx.tenant_id, ctx.run_id)
        if verifier is None:  # the verify stage ends UNKNOWN, as an unavailable verifier's
            return await self._set_run_state(
                run,
                RunState.VERIFYING,
                "no verifier registered",
                code=ReasonCode.VERIFICATION_PENDING,
                before=await self._step_pair(action, StepKind.VERIFY, StepStatus.UNKNOWN),
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
                    ),
                    *await self._step_pair(action, StepKind.VERIFY, StepStatus.UNKNOWN),
                ],
            )
            run = await self._store.get_run(ctx.tenant_id, ctx.run_id)
            return await self._set_run_state(
                run,
                RunState.VERIFYING,
                "verification unavailable",
                code=ReasonCode.VERIFICATION_PENDING,
            )
        report = self._kept(report)
        target = (
            ActionState.VERIFIED
            if report.status is OutcomeStatus.VERIFIED
            else ActionState.VERIFICATION_FAILED
        )
        steps: list[EventSpec | StepRecord] = [
            *await self._step_pair(action, StepKind.VERIFY, OUTCOME_STEP[report.status])
        ]
        outcome = (RunEventType.OUTCOME_REPORTED, outcome_payload(report), action.action_id)
        plan = cont.plan if cont.plan is not None and cont.plan.plan_id == action.plan_id else None
        if plan is not None and report.status is OutcomeStatus.VERIFIED:
            assert action.step_index is not None
            step_id = plan.step_ids[action.step_index]
            if report.verified_values is not None:  # the one lineage source (ADR 0025)
                plan.verified[step_id] = dict(report.verified_values)
                # Stored before the outcome, so a crash after it leaves recovery the values
                # to resume with; a crash before it leaves the step COMMITTED, re-verified.
                await self._persist(ctx.run_id)
            verified = {
                "plan_id": plan.plan_id,
                "step_id": step_id,
                "step_index": action.step_index,
            }
            steps.append((RunEventType.IR_STEP_VERIFIED, verified, action.action_id))
        if report.status is OutcomeStatus.UNKNOWN:
            await self._store.record_outcome(ctx.tenant_id, report, None, None, [outcome, *steps])
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
            [outcome, *steps],
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
        if plan is not None and (action.step_index or 0) + 1 < len(plan.step_ids):
            return await self._after_step_verified(cont, action)  # steps remain (ADR 0025)
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
        gap = await self._acceptance_gap(run, cont)
        if gap is not None:  # `on`: no acknowledgement for an unmet task
            return await self._fail_unmet(run, gap)
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
                        self._with_tools(
                            run,
                            cont,
                            DriverInput(
                                task=run.task,
                                observations=tuple(cont.observations.values()),
                                action_result={
                                    "status": "VERIFIED",
                                    "external_refs": list(external_refs),
                                },
                            ),
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
