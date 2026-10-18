"""Run and action transition enforcement (Phase 1 split of coordinator.py).

Each transition is one write. `_set_run_state` takes the records that belong in the same
write ahead of its own events (an acceptance finding, a stage's step rows), and
`_transition` takes a stage's step rows after its event; with none, both write exactly what
they wrote before (ENG-TOGGLE-1).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from e_agent.contracts.action import ALLOWED_ACTION_TRANSITIONS, ActionRecord, ActionState
from e_agent.contracts.events import RunEventType
from e_agent.contracts.run import (
    ALLOWED_RUN_TRANSITIONS,
    PLAN_STEP_RUN_TRANSITIONS,
    TERMINAL_RUN_STATES,
    ReasonCode,
    RunRecord,
    RunState,
)
from e_agent.contracts.step import StepRecord
from e_agent.sdk.store import EventBatch, EventSpec

from .continuation import ContinuationMixin
from .errors import ErrorCode, KernelError


class TransitionsMixin(ContinuationMixin):
    def _check_run_transition(self, run: RunRecord, to: RunState) -> None:
        if to not in ALLOWED_RUN_TRANSITIONS[run.state] or (
            (run.state, to) in PLAN_STEP_RUN_TRANSITIONS and not self._between_plan_steps(run, to)
        ):
            raise KernelError(ErrorCode.CONFLICT, f"illegal run transition {run.state}->{to}")

    def _between_plan_steps(self, run: RunRecord, to: RunState) -> bool:
        """Whether a plan-only pair (ADR 0025) fits the run's multi-step plan in flight:
        ``VERIFYING -> RUNNING`` after a step verified with steps left, ``RUNNING ->
        VERIFYING`` after a later step committed. Any other run is refused the pair."""
        cont = self._runs.get(run.run_id)
        plan = cont.plan if cont is not None else None
        if plan is None or len(plan.step_ids) < 2:
            return False
        if to is RunState.RUNNING:
            return plan.current + 1 < len(plan.step_ids)
        return plan.current > 0

    async def _set_run_state(
        self,
        run: RunRecord,
        state: RunState,
        reason: str | None = None,
        *,
        code: ReasonCode | None = None,
        before: EventBatch = (),
    ) -> RunRecord:
        """Move ``run`` to ``state``; ``before`` is recorded ahead of the transition events,
        in the same write."""
        self._check_run_transition(run, state)
        events: list[EventSpec | StepRecord] = [
            *before,
            (
                RunEventType.RUN_STATE_CHANGED,
                {"from": run.state, "to": state, "reason": reason, "reason_code": code},
                None,
            ),
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

    async def _transition(
        self,
        action: ActionRecord,
        to: ActionState,
        event: tuple[RunEventType, dict[str, Any]] | None = None,
        *,
        steps: Sequence[StepRecord] = (),
    ) -> ActionRecord:
        """Move ``action`` to ``to``; ``steps`` are the stage's rows, after its event."""
        if to not in ALLOWED_ACTION_TRANSITIONS[action.state]:
            raise KernelError(ErrorCode.CONFLICT, f"illegal transition {action.state}->{to}")
        updated = action.model_copy(update={"state": to, "revision": action.revision + 1})
        events: list[EventSpec | StepRecord] = []
        if event is not None:
            events.append((event[0], event[1], action.action_id))
        events.extend(steps)
        return await self._store.put_action(updated, action.revision, events)
