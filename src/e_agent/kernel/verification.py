"""Independent outcome verification (Phase 1 split of coordinator.py)."""

from __future__ import annotations

from functools import partial
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
from e_agent.sdk.errors import ContextNotRendered, DriverStateMismatch
from e_agent.sdk.ports import (
    DriverInput,
    FinalAnswer,
)
from e_agent.sdk.store import EventSpec

from .context_on import ContextOnMixin, ContextUnavailable
from .continuation import NextStep, _Continuation, _GatewayReader
from .features import RouteRefused, context_failed_event
from .reconstruct import ACTION_STATE_KEY

OUTCOME_STEP = {
    OutcomeStatus.VERIFIED: StepStatus.SUCCEEDED,
    OutcomeStatus.FAILED: StepStatus.FAILED,
    OutcomeStatus.UNKNOWN: StepStatus.UNKNOWN,
}
"""How an outcome ends a linked action's verify step (execution IR ``on``)."""


def outcome_payload(report: OutcomeReport, action_state: ActionState | None) -> dict[str, Any]:
    """The ``outcome.reported`` payload: the report without its read-back values, which only
    the stored outcome and a plan's lineage see, so they never reach an export (PR-26), and
    the state the write leaves the action in, null when unchanged (ADR 0031 §3)."""
    payload = report.model_dump(mode="json", exclude={"verified_values"})
    return {**payload, ACTION_STATE_KEY: action_state}


class VerificationMixin(ContextOnMixin):
    async def _verify(
        self,
        cont: _Continuation,
        action: ActionRecord,
        receipt: ExecutionReceipt,
        *,
        next_step: NextStep,
    ) -> RunRecord:
        """The independent read-back of a committed ``action``. A multi-step plan's step in
        ``on`` is verified by the approval call or a resume claim (``NextStep.START``), or by
        recovery after a failed resume (``STOP``); reconciliation and startup recovery
        (``QUEUE``) queue the fenced resume instead and write no plan state (Codex C-2,
        option (b))."""
        ctx = cont.ctx
        run = await self._store.get_run(ctx.tenant_id, ctx.run_id)
        if next_step is NextStep.QUEUE and self._ir_on and self._plan_step(cont, action):
            return await self._queue_resume(run, action)
        verifier = self._registry.verifier_for(action.contract_id)
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
                        # the action is unchanged (ADR 0031 §3)
                        {"status": "UNKNOWN", "error": type(exc).__name__, ACTION_STATE_KEY: None},
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
        unchanged = report.status is OutcomeStatus.UNKNOWN  # recorded without the action
        payload = outcome_payload(report, None if unchanged else target)
        outcome = (RunEventType.OUTCOME_REPORTED, payload, action.action_id)
        plan = cont.plan if self._plan_step(cont, action) else None
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
            # Steps remain (ADR 0025): the call's own authority decides (Codex C-1).
            return await self._after_step_verified(cont, action, next_step=next_step)
        return await self._finish_verified(
            cont, receipt.external_refs, "The approved action was independently verified."
        )

    @staticmethod
    def _plan_step(cont: _Continuation, action: ActionRecord) -> bool:
        """Whether ``action`` is a step of the multi-step plan the run is executing."""
        return cont.plan is not None and cont.plan.plan_id == action.plan_id

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
        ack_input = DriverInput(
            task=run.task,
            observations=tuple(cont.observations.values()),
            action_result={"status": "VERIFIED", "external_refs": list(external_refs)},
        )
        # before any read of driver state; a refusal skips the turn below (D8, D3-60)
        restored = not acknowledge or self._restore_for_turn(cont)
        # pinned shadow only, above the final-response guard (ADR 0032 §7, review D3-30)
        shadow = (
            await self._context_shadow(run, cont, ack_input, acknowledgement=True)
            if acknowledge and restored
            else None
        )
        answered = False
        turn_input = ack_input
        try:
            if not restored:
                raise DriverStateMismatch
            if acknowledge and (
                getattr(self._driver, "tokens_used", lambda _: 0)(ctx.run_id)
                < ctx.budgets.max_model_tokens
            ):
                run, turn_input = await self._context_input(
                    run, cont, ack_input, acknowledgement=True
                )  # pinned on: the pack, or skipped below (ADR 0032 §7)
                final = await self._timed(
                    cont,
                    partial(self._driver.advance, ctx, self._with_tools(run, cont, turn_input)),
                    ctx.budgets.model_timeout_seconds,
                )
                answered = True
        except (RouteRefused, ContextUnavailable, ContextNotRendered, DriverStateMismatch) as exc:
            # skipped, recorded; the run keeps its outcome (ADR 0032 §7, §8, §9)
            code = (
                ReasonCode.ROUTE_BOUNDARY_UNMET
                if isinstance(exc, RouteRefused)
                else ReasonCode.DRIVER_STATE_MISMATCH
                if isinstance(exc, DriverStateMismatch)
                else ReasonCode.CONTEXT_UNAVAILABLE
            )
            run = await self._store.get_run(ctx.tenant_id, ctx.run_id)
            run = await self._store.update_run(
                run.model_copy(update={"revision": run.revision + 1}),
                run.revision,
                [context_failed_event(code)],
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
        if shadow is not None and answered:
            run = await self._record_context_shadow(run, shadow)
        if answered:  # `on` only: the call carried a pack
            run = await self._record_context_assembled(run, cont, turn_input, acknowledgement=True)
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
