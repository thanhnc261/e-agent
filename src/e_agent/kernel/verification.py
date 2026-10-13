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
from e_agent.sdk.ports import (
    DriverInput,
    FinalAnswer,
)

from .continuation import ContinuationMixin, _Continuation, _GatewayReader


class VerificationMixin(ContinuationMixin):
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
