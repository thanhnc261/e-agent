"""In-memory RunStore for tests and the fixture walking skeleton.

It implements the same atomicity contract as the PostgreSQL adapter (I05):
each method applies its state change and events together or not at all.
Not durable; never use it for live runs.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import AsyncIterator, Mapping, Sequence
from contextlib import asynccontextmanager
from typing import Any

from e_agent.contracts.action import ActionRecord
from e_agent.contracts.approval import ApprovalRecord
from e_agent.contracts.common import new_id, utc_now
from e_agent.contracts.events import RunEvent
from e_agent.contracts.outcome import OutcomeReport
from e_agent.contracts.receipt import ExecutionReceipt
from e_agent.contracts.run import TERMINAL_RUN_STATES, RunRecord
from e_agent.sdk.store import (
    ConcurrencyConflict,
    DuplicateOperation,
    EventSpec,
    NotFound,
)

_Stored = tuple[dict[str, Any], dict[str, Any] | None]


class InMemoryRunStore:
    durable = False

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._runs: dict[tuple[str, str], RunRecord] = {}
        self._actions: dict[tuple[str, str], ActionRecord] = {}
        self._events: dict[tuple[str, str], list[RunEvent]] = defaultdict(list)
        self._reservations: dict[tuple[str, str, str], str] = {}
        self._approvals: dict[tuple[str, str], list[ApprovalRecord]] = defaultdict(list)
        self._receipts: dict[tuple[str, str], list[ExecutionReceipt]] = defaultdict(list)
        self._outcomes: dict[tuple[str, str], list[OutcomeReport]] = defaultdict(list)
        self._continuations: dict[
            tuple[str, str], tuple[dict[str, Any], dict[str, Any] | None]
        ] = {}
        self._writer_locks: dict[tuple[str, str], asyncio.Lock] = defaultdict(asyncio.Lock)
        self._idempotency: dict[tuple[str, str, str], tuple[str, str]] = {}

    # -- helpers (caller holds the lock) --------------------------------------
    def _append(self, tenant_id: str, run_id: str, events: Sequence[EventSpec]) -> None:
        log = self._events[(tenant_id, run_id)]
        for event_type, payload, action_id in events:
            log.append(
                RunEvent(
                    event_id=new_id("evt"),
                    tenant_id=tenant_id,
                    run_id=run_id,
                    sequence=len(log) + 1,
                    type=event_type,
                    occurred_at=utc_now(),
                    action_id=action_id,
                    payload=dict(payload),
                )
            )

    def _check_action_cas(self, action: ActionRecord, expected: int | None) -> None:
        current = self._actions.get((action.tenant_id, action.action_id))
        if expected is None:
            if current is not None:
                raise ConcurrencyConflict(f"action {action.action_id} already exists")
        elif current is None or current.revision != expected:
            raise ConcurrencyConflict(f"action {action.action_id} changed")
        if action.revision != (0 if expected is None else expected) + 1:
            raise ConcurrencyConflict("new revision must be expected + 1")

    # -- runs ---------------------------------------------------------------
    async def create_run(self, run: RunRecord, events: Sequence[EventSpec]) -> None:
        async with self._lock:
            key = (run.tenant_id, run.run_id)
            if key in self._runs:
                raise ConcurrencyConflict(f"run {run.run_id} exists")
            self._runs[key] = run
            self._append(run.tenant_id, run.run_id, events)

    async def get_run(self, tenant_id: str, run_id: str) -> RunRecord:
        try:
            return self._runs[(tenant_id, run_id)]
        except KeyError:
            raise NotFound(run_id) from None

    async def update_run(
        self, run: RunRecord, expected_revision: int, events: Sequence[EventSpec]
    ) -> RunRecord:
        async with self._lock:
            key = (run.tenant_id, run.run_id)
            current = self._runs.get(key)
            if current is None or current.revision != expected_revision:
                raise ConcurrencyConflict(f"run {run.run_id} changed")
            if run.revision != expected_revision + 1:
                raise ConcurrencyConflict("new revision must be expected + 1")
            self._runs[key] = run
            self._append(run.tenant_id, run.run_id, events)
            return run

    # -- actions --------------------------------------------------------------
    async def put_action(
        self, action: ActionRecord, expected_revision: int | None, events: Sequence[EventSpec]
    ) -> ActionRecord:
        async with self._lock:
            self._check_action_cas(action, expected_revision)
            self._actions[(action.tenant_id, action.action_id)] = action
            self._append(action.tenant_id, action.run_id, events)
            return action

    async def get_action(self, tenant_id: str, action_id: str) -> ActionRecord:
        try:
            return self._actions[(tenant_id, action_id)]
        except KeyError:
            raise NotFound(action_id) from None

    async def reserve_operation(
        self, action: ActionRecord, expected_revision: int, events: Sequence[EventSpec]
    ) -> ActionRecord:
        async with self._lock:
            key = (action.tenant_id, action.connection_id, action.logical_operation_id)
            if key in self._reservations:
                raise DuplicateOperation(action.logical_operation_id)
            self._check_action_cas(action, expected_revision)
            self._reservations[key] = action.action_id
            self._actions[(action.tenant_id, action.action_id)] = action
            self._append(action.tenant_id, action.run_id, events)
            return action

    async def record_approval(self, approval: ApprovalRecord, events: Sequence[EventSpec]) -> None:
        async with self._lock:
            self._approvals[(approval.tenant_id, approval.action_id)].append(approval)
            self._append(approval.tenant_id, approval.run_id, events)

    async def record_receipt(
        self,
        receipt: ExecutionReceipt,
        action: ActionRecord,
        expected_revision: int,
        events: Sequence[EventSpec],
    ) -> ActionRecord:
        async with self._lock:
            self._check_action_cas(action, expected_revision)
            self._receipts[(action.tenant_id, action.action_id)].append(receipt)
            self._actions[(action.tenant_id, action.action_id)] = action
            self._append(action.tenant_id, action.run_id, events)
            return action

    async def record_outcome(
        self,
        tenant_id: str,
        outcome: OutcomeReport,
        action: ActionRecord | None,
        expected_revision: int | None,
        events: Sequence[EventSpec],
    ) -> None:
        async with self._lock:
            run = self._runs[(tenant_id, outcome.run_id)]
            if action is not None:
                self._check_action_cas(action, expected_revision)
                self._actions[(action.tenant_id, action.action_id)] = action
            self._outcomes[(run.tenant_id, outcome.run_id)].append(outcome)
            self._append(run.tenant_id, outcome.run_id, events)

    # -- queries --------------------------------------------------------------
    async def list_events(
        self, tenant_id: str, run_id: str, after_sequence: int = 0
    ) -> list[RunEvent]:
        return [e for e in self._events[(tenant_id, run_id)] if e.sequence > after_sequence]

    async def list_actions(self, tenant_id: str, run_id: str) -> list[ActionRecord]:
        return [a for (t, _), a in self._actions.items() if t == tenant_id and a.run_id == run_id]

    async def list_receipts(self, tenant_id: str, action_id: str) -> list[ExecutionReceipt]:
        return list(self._receipts[(tenant_id, action_id)])

    async def list_approvals(self, tenant_id: str, action_id: str) -> list[ApprovalRecord]:
        return list(self._approvals[(tenant_id, action_id)])

    async def claim_idempotency(
        self, tenant_id: str, actor_id: str, key: str, request_digest: str, run_id: str
    ) -> tuple[str, str]:
        async with self._lock:
            return self._idempotency.setdefault(
                (tenant_id, actor_id, key), (run_id, request_digest)
            )

    async def list_unfinished_runs(self) -> list[RunRecord]:
        return [r for r in self._runs.values() if r.state not in TERMINAL_RUN_STATES]

    async def save_continuation(
        self,
        tenant_id: str,
        run_id: str,
        state: Mapping[str, Any],
        driver_state: Mapping[str, Any] | None,
    ) -> None:
        self._continuations[(tenant_id, run_id)] = (
            dict(state),
            dict(driver_state) if driver_state is not None else None,
        )

    async def load_continuation(
        self, tenant_id: str, run_id: str
    ) -> tuple[dict[str, Any], dict[str, Any] | None] | None:
        return self._continuations.get((tenant_id, run_id))

    @asynccontextmanager
    async def writer_lock(self, tenant_id: str, connection_id: str) -> AsyncIterator[None]:
        async with self._writer_locks[(tenant_id, connection_id)]:
            yield
