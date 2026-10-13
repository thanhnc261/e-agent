"""Run and action transition enforcement (Phase 1 split of coordinator.py)."""

from __future__ import annotations

from typing import Any

from e_agent.contracts.action import ALLOWED_ACTION_TRANSITIONS, ActionRecord, ActionState
from e_agent.contracts.events import RunEventType
from e_agent.contracts.run import (
    ALLOWED_RUN_TRANSITIONS,
    TERMINAL_RUN_STATES,
    ReasonCode,
    RunRecord,
    RunState,
)
from e_agent.sdk.store import EventSpec

from .continuation import ContinuationMixin
from .errors import ErrorCode, KernelError


class TransitionsMixin(ContinuationMixin):
    def _check_run_transition(self, run: RunRecord, to: RunState) -> None:
        if to not in ALLOWED_RUN_TRANSITIONS[run.state]:
            raise KernelError(ErrorCode.CONFLICT, f"illegal run transition {run.state}->{to}")

    async def _set_run_state(
        self,
        run: RunRecord,
        state: RunState,
        reason: str | None = None,
        *,
        code: ReasonCode | None = None,
    ) -> RunRecord:
        self._check_run_transition(run, state)
        events: list[EventSpec] = [
            (
                RunEventType.RUN_STATE_CHANGED,
                {"from": run.state, "to": state, "reason": reason, "reason_code": code},
                None,
            )
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
    ) -> ActionRecord:
        if to not in ALLOWED_ACTION_TRANSITIONS[action.state]:
            raise KernelError(ErrorCode.CONFLICT, f"illegal transition {action.state}->{to}")
        updated = action.model_copy(update={"state": to, "revision": action.revision + 1})
        events: list[EventSpec] = []
        if event is not None:
            events.append((event[0], event[1], action.action_id))
        return await self._store.put_action(updated, action.revision, events)
