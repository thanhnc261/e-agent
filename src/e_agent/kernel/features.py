"""Feature toggle fallback (ADR 0027, target architecture §6.4.8).

A feature in ``on`` mode may return to the existing path only before the first write
reservation. The consumer decides when that applies; this helper records the
``feature.fallback`` event with a typed reason and leaves the run state unchanged,
because a fallback code never ends a run (ADR 0025).
"""

from __future__ import annotations

from e_agent.contracts.events import RunEventType
from e_agent.contracts.features import Features
from e_agent.contracts.run import TERMINAL_RUN_STATES, ReasonCode, RunRecord

from .continuation import ContinuationMixin
from .errors import ErrorCode, KernelError

FALLBACK_REASON_CODES = frozenset(
    {
        ReasonCode.IR_TASK_UNRESOLVED,
        ReasonCode.IR_COMPILE_FAILED,
        ReasonCode.IR_VALIDATION_FAILED,
    }
)
"""The `ReasonCode` members a fallback may carry (ADR 0025 names them for `execution_ir`)."""


class FeaturesMixin(ContinuationMixin):
    _features: Features

    async def record_fallback(
        self, run: RunRecord, feature: str, reason: ReasonCode, detail: str
    ) -> RunRecord:
        """Append ``feature.fallback`` in one transaction and return the updated run.

        The run's state, reason and reason code are unchanged; only its revision moves, so
        the caller keeps using the returned record.
        """
        if feature not in Features.model_fields:
            raise KernelError(ErrorCode.INVALID_REQUEST, f"unknown feature {feature!r}")
        if reason not in FALLBACK_REASON_CODES:
            raise KernelError(ErrorCode.INVALID_REQUEST, f"{reason} is not a fallback code")
        if run.state in TERMINAL_RUN_STATES:
            raise KernelError(ErrorCode.CONFLICT, "a finished run cannot fall back")
        return await self._store.update_run(
            run.model_copy(update={"revision": run.revision + 1}),
            run.revision,
            [
                (
                    RunEventType.FEATURE_FALLBACK,
                    {"feature": feature, "reason_code": reason, "detail": detail},
                    None,
                )
            ],
        )
