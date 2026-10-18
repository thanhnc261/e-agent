"""In-memory RunStore for tests and the fixture walking skeleton.

It implements the same atomicity contract as the PostgreSQL adapter (I05):
each method applies its state change and events together or not at all.
Not durable; never use it for live runs.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from contextvars import ContextVar
from datetime import timedelta
from typing import Any

from e_agent.contracts.action import ActionRecord, ActionState
from e_agent.contracts.approval import ApprovalRecord
from e_agent.contracts.common import new_id, utc_now
from e_agent.contracts.events import RunEvent
from e_agent.contracts.outcome import OutcomeReport
from e_agent.contracts.plan import ActionPlan
from e_agent.contracts.receipt import ExecutionReceipt
from e_agent.contracts.run import TERMINAL_RUN_STATES, RunRecord
from e_agent.contracts.step import StepRecord
from e_agent.contracts.work import WorkClaim
from e_agent.sdk.store import (
    ConcurrencyConflict,
    ConnectionBusy,
    DuplicateOperation,
    EventBatch,
    NotFound,
    current_actor,
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
        self._work: dict[str, dict[str, Any]] = {}
        self._work_claim: ContextVar[WorkClaim | None] = ContextVar(
            "memory_work_claim", default=None
        )
        self._idempotency: dict[tuple[str, str, str], tuple[str, str]] = {}
        # (tenant, plan_id) -> (run_id, wire form): kept as Postgres keeps it, read back validated.
        self._plans: dict[tuple[str, str], tuple[str, dict[str, Any]]] = {}
        self._steps: dict[tuple[str, str], list[StepRecord]] = defaultdict(list)

    # -- helpers (caller holds the lock) --------------------------------------
    def _begin(self, tenant_id: str, run_id: str, events: EventBatch) -> None:
        """The pure checks a fenced write runs before its first mutation."""
        self._fence()
        self._check_steps(tenant_id, run_id, events)

    def _check_steps(self, tenant_id: str, run_id: str, events: EventBatch) -> None:
        """Steps must be this run's, strictly increasing; a refused one leaves nothing."""
        last = max((s.sequence for s in self._steps.get((tenant_id, run_id), ())), default=-1)
        for step in (item for item in events if isinstance(item, StepRecord)):
            if (step.tenant_id, step.run_id) != (tenant_id, run_id):
                raise ValueError(f"step {step.step_id} does not belong to run {run_id}")
            if step.sequence <= last:
                raise ConcurrencyConflict(f"step sequence {step.sequence} is not after {last}")
            last = step.sequence

    def _append(self, tenant_id: str, run_id: str, events: EventBatch) -> None:
        log = self._events[(tenant_id, run_id)]
        self._steps[(tenant_id, run_id)].extend(e for e in events if isinstance(e, StepRecord))
        for event_type, payload, action_id in (e for e in events if not isinstance(e, StepRecord)):
            log.append(
                RunEvent(
                    event_id=new_id("evt"),
                    tenant_id=tenant_id,
                    run_id=run_id,
                    sequence=len(log) + 1,
                    type=event_type,
                    occurred_at=utc_now(),
                    action_id=action_id,
                    actor=current_actor.get(),
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
    async def create_run(self, run: RunRecord, events: EventBatch) -> None:
        async with self._lock:
            self._begin(run.tenant_id, run.run_id, events)
            key = (run.tenant_id, run.run_id)
            if key in self._runs:
                raise ConcurrencyConflict(f"run {run.run_id} exists")
            self._runs[key] = run
            self._append(run.tenant_id, run.run_id, events)

    async def create_run_idempotent(
        self,
        run: RunRecord,
        events: EventBatch,
        state: Mapping[str, Any],
        actor_id: str,
        key: str,
        request_digest: str,
    ) -> tuple[str, str]:
        async with self._lock:
            idem = (run.tenant_id, actor_id, key)
            if idem in self._idempotency:
                return self._idempotency[idem]
            run_key = (run.tenant_id, run.run_id)
            if run_key in self._runs:
                raise ConcurrencyConflict("run already exists")
            self._check_steps(run.tenant_id, run.run_id, events)
            self._runs[run_key] = run
            self._continuations[run_key] = (dict(state), None)
            self._append(run.tenant_id, run.run_id, events)
            self._idempotency[idem] = (run.run_id, request_digest)
            wid = new_id("work")
            self._work[wid] = dict(
                work_id=wid,
                tenant_id=run.tenant_id,
                run_id=run.run_id,
                kind="start",
                payload={},
                request_digest=request_digest,
                state="PENDING",
                owner=None,
                fence=0,
                lease_until=None,
            )
            return run.run_id, request_digest

    async def get_run(self, tenant_id: str, run_id: str) -> RunRecord:
        try:
            return self._runs[(tenant_id, run_id)]
        except KeyError:
            raise NotFound(run_id) from None

    async def update_run(
        self,
        run: RunRecord,
        expected_revision: int,
        events: EventBatch,
        *,
        continuation: tuple[Mapping[str, Any], Mapping[str, Any] | None] | None = None,
        work: tuple[str, Mapping[str, Any], str] | None = None,
    ) -> RunRecord:
        async with self._lock:
            self._begin(run.tenant_id, run.run_id, events)
            key = (run.tenant_id, run.run_id)
            current = self._runs.get(key)
            if current is None or current.revision != expected_revision:
                raise ConcurrencyConflict(f"run {run.run_id} changed")
            if run.revision != expected_revision + 1:
                raise ConcurrencyConflict("new revision must be expected + 1")
            if continuation is not None:
                state, driver_state = continuation
                self._continuations[key] = (
                    dict(state),
                    dict(driver_state) if driver_state else None,
                )
            if work is not None:
                kind, payload, request_digest = work
                self._enqueue_work(run.tenant_id, run.run_id, kind, payload, request_digest)
            self._runs[key] = run
            self._append(run.tenant_id, run.run_id, events)
            return run

    # -- actions --------------------------------------------------------------
    async def put_action(
        self, action: ActionRecord, expected_revision: int | None, events: EventBatch
    ) -> ActionRecord:
        async with self._lock:
            self._begin(action.tenant_id, action.run_id, events)
            self._check_action_cas(action, expected_revision)
            self._actions[(action.tenant_id, action.action_id)] = action
            self._append(action.tenant_id, action.run_id, events)
            return action

    async def wait_for_approval(
        self,
        action: ActionRecord,
        expected_action_revision: int,
        run: RunRecord,
        expected_run_revision: int,
        continuation: tuple[Mapping[str, Any], Mapping[str, Any] | None],
        events: EventBatch,
    ) -> None:
        async with self._lock:
            self._begin(run.tenant_id, run.run_id, events)
            self._check_action_cas(action, expected_action_revision)
            current = self._runs.get((run.tenant_id, run.run_id))
            if (
                current is None
                or current.revision != expected_run_revision
                or run.revision != expected_run_revision + 1
            ):
                raise ConcurrencyConflict("run changed before approval checkpoint")
            state, driver_state = continuation
            self._actions[(action.tenant_id, action.action_id)] = action
            self._runs[(run.tenant_id, run.run_id)] = run
            self._continuations[(run.tenant_id, run.run_id)] = (
                dict(state),
                dict(driver_state) if driver_state is not None else None,
            )
            self._append(run.tenant_id, run.run_id, events)

    async def get_action(self, tenant_id: str, action_id: str) -> ActionRecord:
        try:
            return self._actions[(tenant_id, action_id)]
        except KeyError:
            raise NotFound(action_id) from None

    async def reserve_operation(
        self, action: ActionRecord, expected_revision: int, events: EventBatch
    ) -> ActionRecord:
        async with self._lock:
            self._begin(action.tenant_id, action.run_id, events)
            key = (action.tenant_id, action.connection_id, action.logical_operation_id)
            if key in self._reservations:
                raise DuplicateOperation(action.logical_operation_id)
            self._check_action_cas(action, expected_revision)
            busy = any(
                a.connection_id == action.connection_id
                and a.state in {ActionState.RESERVED, ActionState.DISPATCHING, ActionState.UNKNOWN}
                and a.action_id != action.action_id
                for (t, _), a in self._actions.items()
                if t == action.tenant_id
            )
            if busy:
                raise ConnectionBusy(action.connection_id)
            self._reservations[key] = action.action_id
            self._actions[(action.tenant_id, action.action_id)] = action
            self._append(action.tenant_id, action.run_id, events)
            return action

    async def record_approval(
        self,
        approval: ApprovalRecord,
        events: EventBatch,
        *,
        action: ActionRecord | None = None,
        expected_revision: int | None = None,
    ) -> None:
        async with self._lock:
            self._begin(approval.tenant_id, approval.run_id, events)
            if action is not None:
                if expected_revision is None:
                    raise ConcurrencyConflict("approval transition requires a revision")
                self._check_action_cas(action, expected_revision)
                self._actions[(action.tenant_id, action.action_id)] = action
            self._approvals[(approval.tenant_id, approval.action_id)].append(approval)
            self._append(approval.tenant_id, approval.run_id, events)

    async def record_receipt(
        self,
        receipt: ExecutionReceipt,
        action: ActionRecord,
        expected_revision: int,
        events: EventBatch,
    ) -> ActionRecord:
        async with self._lock:
            self._begin(action.tenant_id, action.run_id, events)
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
        events: EventBatch,
    ) -> None:
        async with self._lock:
            self._begin(tenant_id, outcome.run_id, events)
            run = self._runs[(tenant_id, outcome.run_id)]
            if action is not None:
                self._check_action_cas(action, expected_revision)
                self._actions[(action.tenant_id, action.action_id)] = action
            self._outcomes[(run.tenant_id, outcome.run_id)].append(outcome)
            self._append(run.tenant_id, outcome.run_id, events)

    # -- plans ----------------------------------------------------------------
    async def put_plan(
        self, tenant_id: str, run_id: str, plan: ActionPlan, events: EventBatch
    ) -> None:
        async with self._lock:
            self._begin(tenant_id, run_id, events)
            if (tenant_id, run_id) not in self._runs:
                raise NotFound(run_id)
            key = (tenant_id, plan.plan_id)
            if key in self._plans:
                raise ConcurrencyConflict(f"plan {plan.plan_id} exists")
            self._plans[key] = (run_id, plan.model_dump(mode="json"))
            self._append(tenant_id, run_id, events)

    async def get_plan(self, tenant_id: str, plan_id: str) -> ActionPlan:
        if (tenant_id, plan_id) not in self._plans:
            raise NotFound(plan_id)
        return ActionPlan.model_validate(self._plans[(tenant_id, plan_id)][1])

    # -- queries --------------------------------------------------------------
    async def list_steps(self, tenant_id: str, run_id: str) -> list[StepRecord]:
        return sorted(self._steps.get((tenant_id, run_id), ()), key=lambda s: s.sequence)

    async def list_events(
        self, tenant_id: str, run_id: str, after_sequence: int = 0, limit: int | None = None
    ) -> list[RunEvent]:
        events = [e for e in self._events[(tenant_id, run_id)] if e.sequence > after_sequence]
        return events if limit is None else events[:limit]

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
            self._fence()
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
        self._fence()
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
            self._fence()
            yield

    def _fence(self) -> None:
        claim = self._work_claim.get()
        if claim is None:
            return
        current = self._work.get(claim.work_id)
        if (
            current is None
            or current["state"] != "CLAIMED"
            or current["owner"] != claim.owner
            or current["fence"] != claim.fence
            or current["lease_until"] <= utc_now()
        ):
            raise ConcurrencyConflict("worker lease or fencing token is stale")

    async def enqueue_work(
        self,
        tenant_id: str,
        run_id: str,
        kind: str,
        payload: Mapping[str, Any],
        request_digest: str,
    ) -> None:
        async with self._lock:
            self._enqueue_work(tenant_id, run_id, kind, payload, request_digest)

    def _enqueue_work(
        self,
        tenant_id: str,
        run_id: str,
        kind: str,
        payload: Mapping[str, Any],
        request_digest: str,
    ) -> None:
        for work in self._work.values():
            if (
                work["tenant_id"] == tenant_id
                and work["run_id"] == run_id
                and work["kind"] == kind
                and work["request_digest"] == request_digest
            ):
                if work["payload"] != dict(payload):
                    raise ConcurrencyConflict("work request conflicts with the admitted command")
                return
        wid = new_id("work")
        self._work[wid] = dict(
            work_id=wid,
            tenant_id=tenant_id,
            run_id=run_id,
            kind=kind,
            payload=dict(payload),
            request_digest=request_digest,
            state="PENDING",
            owner=None,
            fence=0,
            lease_until=None,
        )

    async def claim_work(self, owner: str, lease_seconds: int = 30) -> WorkClaim | None:
        async with self._lock:
            now = utc_now()
            for item in self._work.values():
                if item["state"] == "DONE" or (item["lease_until"] and item["lease_until"] > now):
                    continue
                if any(
                    other["tenant_id"] == item["tenant_id"]
                    and other["run_id"] == item["run_id"]
                    and other["state"] == "CLAIMED"
                    and other["lease_until"] > now
                    for other in self._work.values()
                ):
                    continue
                item.update(
                    state="CLAIMED",
                    owner=owner,
                    fence=item["fence"] + 1,
                    lease_until=now + timedelta(seconds=lease_seconds),
                )
                return WorkClaim.model_validate({k: item[k] for k in WorkClaim.model_fields})
            return None

    async def renew_work(self, claim: WorkClaim, lease_seconds: int = 30) -> bool:
        async with self._lock:
            item = self._work.get(claim.work_id)
            if (
                item is None
                or item["owner"] != claim.owner
                or item["fence"] != claim.fence
                or item["state"] != "CLAIMED"
                or item["lease_until"] <= utc_now()
            ):
                return False
            item["lease_until"] = utc_now() + timedelta(seconds=lease_seconds)
            return True

    async def finish_work(self, claim: WorkClaim) -> None:
        async with self._lock:
            token = self._work_claim.set(claim)
            try:
                self._fence()
                self._work[claim.work_id]["state"] = "DONE"
            finally:
                self._work_claim.reset(token)

    @asynccontextmanager
    async def work_scope(self, claim: WorkClaim) -> AsyncIterator[None]:
        token = self._work_claim.set(claim)
        try:
            self._fence()
            yield
        finally:
            self._work_claim.reset(token)

    async def has_pending_work(self, tenant_id: str, run_id: str) -> bool:
        return any(
            w["tenant_id"] == tenant_id and w["run_id"] == run_id and w["state"] != "DONE"
            for w in self._work.values()
        )
