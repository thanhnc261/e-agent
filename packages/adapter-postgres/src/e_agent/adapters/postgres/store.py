"""PostgreSQL implementation of the RunStore port.

Each method is one short local transaction; no transaction is ever held
across a model or provider call (ADR 0003). Event sequences are assigned
under the run's row lock and published with NOTIFY in the same transaction.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping, Sequence
from contextlib import asynccontextmanager
from contextvars import ContextVar
from typing import Any

from e_agent.contracts.action import ActionRecord
from e_agent.contracts.approval import ApprovalRecord
from e_agent.contracts.common import new_id, utc_now
from e_agent.contracts.events import RunEvent
from e_agent.contracts.outcome import OutcomeReport
from e_agent.contracts.receipt import ExecutionReceipt
from e_agent.contracts.run import TERMINAL_RUN_STATES, RunRecord
from e_agent.contracts.work import WorkClaim
from e_agent.sdk.store import (
    ConcurrencyConflict,
    ConnectionBusy,
    DuplicateOperation,
    EventSpec,
    NotFound,
    current_actor,
)
from psycopg import AsyncConnection, errors
from psycopg.types.json import Jsonb
from psycopg_pool import AsyncConnectionPool

NOTIFY_CHANNEL = "e_agent_run_events"


def _json(model: Any) -> Jsonb:
    return Jsonb(model.model_dump(mode="json"))


class PostgresRunStore:
    durable = True

    def __init__(self, pool: AsyncConnectionPool[AsyncConnection[Any]]) -> None:
        self._pool = pool
        self._work_claim: ContextVar[WorkClaim | None] = ContextVar(
            "postgres_work_claim", default=None
        )

    @classmethod
    async def open(cls, dsn: str, *, min_size: int = 1, max_size: int = 8) -> PostgresRunStore:
        pool: AsyncConnectionPool[AsyncConnection[Any]] = AsyncConnectionPool(
            dsn, min_size=min_size, max_size=max_size, open=False
        )
        await pool.open(wait=True)
        return cls(pool)

    async def close(self) -> None:
        await self._pool.close()

    async def truncate_for_tests(self) -> None:
        """Test helper: empty all ledger tables (never called by product code)."""
        async with self._pool.connection() as conn:
            await conn.execute(
                "TRUNCATE runs, run_events, actions, operation_reservations, approvals,"
                " receipts, outcome_reports, continuations, api_idempotency, run_work"
            )

    # -- helpers --------------------------------------------------------------
    @staticmethod
    async def _append(
        conn: AsyncConnection[Any], tenant_id: str, run_id: str, events: Sequence[EventSpec]
    ) -> None:
        if not events:
            return
        cur = await conn.execute(
            "SELECT 1 FROM runs WHERE tenant_id = %s AND run_id = %s FOR UPDATE",
            (tenant_id, run_id),
        )
        if await cur.fetchone() is None:
            raise NotFound(run_id)
        cur = await conn.execute(
            "SELECT coalesce(max(sequence), 0) FROM run_events"
            " WHERE tenant_id = %s AND run_id = %s",
            (tenant_id, run_id),
        )
        row = await cur.fetchone()
        sequence = int(row[0]) if row else 0
        for event_type, payload, action_id in events:
            sequence += 1
            event = RunEvent(
                event_id=new_id("evt"),
                tenant_id=tenant_id,
                run_id=run_id,
                sequence=sequence,
                type=event_type,
                occurred_at=utc_now(),
                action_id=action_id,
                actor=current_actor.get(),
                payload=dict(payload),
            )
            await conn.execute(
                "INSERT INTO run_events"
                " (event_id, tenant_id, run_id, sequence, type, action_id, record)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (event.event_id, tenant_id, run_id, sequence, event.type, action_id, _json(event)),
            )
        await conn.execute("SELECT pg_notify(%s, %s)", (NOTIFY_CHANNEL, f"{tenant_id}/{run_id}"))

    @staticmethod
    async def _cas_action(
        conn: AsyncConnection[Any], action: ActionRecord, expected: int | None
    ) -> None:
        if action.revision != (0 if expected is None else expected) + 1:
            raise ConcurrencyConflict("new revision must be expected + 1")
        if expected is None:
            try:
                async with conn.transaction():
                    await conn.execute(
                        "INSERT INTO actions (tenant_id, action_id, run_id, logical_operation_id,"
                        " connection_id, state, revision, record)"
                        " VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                        (
                            action.tenant_id,
                            action.action_id,
                            action.run_id,
                            action.logical_operation_id,
                            action.connection_id,
                            action.state,
                            action.revision,
                            _json(action),
                        ),
                    )
            except errors.UniqueViolation as exc:
                raise ConcurrencyConflict(f"action {action.action_id} exists") from exc
            return
        cur = await conn.execute(
            "UPDATE actions SET state = %s, revision = %s, record = %s"
            " WHERE tenant_id = %s AND action_id = %s AND revision = %s",
            (
                action.state,
                action.revision,
                _json(action),
                action.tenant_id,
                action.action_id,
                expected,
            ),
        )
        if cur.rowcount != 1:
            raise ConcurrencyConflict(f"action {action.action_id} changed")

    # -- runs ---------------------------------------------------------------
    async def create_run(self, run: RunRecord, events: Sequence[EventSpec]) -> None:
        async with self._pool.connection() as conn, conn.transaction():
            await self._fence(conn)
            try:
                async with conn.transaction():
                    await conn.execute(
                        "INSERT INTO runs (tenant_id, run_id, state, revision, record)"
                        " VALUES (%s, %s, %s, %s, %s)",
                        (run.tenant_id, run.run_id, run.state, run.revision, _json(run)),
                    )
            except errors.UniqueViolation as exc:
                raise ConcurrencyConflict(f"run {run.run_id} exists") from exc
            await self._append(conn, run.tenant_id, run.run_id, events)

    async def create_run_idempotent(
        self,
        run: RunRecord,
        events: Sequence[EventSpec],
        state: Mapping[str, Any],
        actor_id: str,
        key: str,
        request_digest: str,
    ) -> tuple[str, str]:
        async with self._pool.connection() as conn, conn.transaction():
            cur = await conn.execute(
                "INSERT INTO api_idempotency"
                " (tenant_id, actor_id, idem_key, request_digest, run_id)"
                " VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING RETURNING run_id",
                (run.tenant_id, actor_id, key, request_digest, run.run_id),
            )
            if await cur.fetchone() is None:
                cur = await conn.execute(
                    "SELECT run_id, request_digest FROM api_idempotency"
                    " WHERE tenant_id = %s AND actor_id = %s AND idem_key = %s",
                    (run.tenant_id, actor_id, key),
                )
                row = await cur.fetchone()
                assert row is not None
                return str(row[0]), str(row[1])
            await conn.execute(
                "INSERT INTO runs (tenant_id, run_id, state, revision, record)"
                " VALUES (%s, %s, %s, %s, %s)",
                (run.tenant_id, run.run_id, run.state, run.revision, _json(run)),
            )
            await self._save_continuation(conn, run.tenant_id, run.run_id, state, None)
            await self._append(conn, run.tenant_id, run.run_id, events)
            await conn.execute(
                "INSERT INTO run_work"
                " (work_id, tenant_id, run_id, kind, payload, request_digest)"
                " VALUES (%s, %s, %s, 'start', '{}', %s)",
                (new_id("work"), run.tenant_id, run.run_id, request_digest),
            )
            return run.run_id, request_digest

    async def get_run(self, tenant_id: str, run_id: str) -> RunRecord:
        async with self._pool.connection() as conn:
            cur = await conn.execute(
                "SELECT record FROM runs WHERE tenant_id = %s AND run_id = %s",
                (tenant_id, run_id),
            )
            row = await cur.fetchone()
        if row is None:
            raise NotFound(run_id)
        return RunRecord.model_validate(row[0])

    async def update_run(
        self,
        run: RunRecord,
        expected_revision: int,
        events: Sequence[EventSpec],
        *,
        continuation: tuple[Mapping[str, Any], Mapping[str, Any] | None] | None = None,
        work: tuple[str, Mapping[str, Any], str] | None = None,
    ) -> RunRecord:
        if run.revision != expected_revision + 1:
            raise ConcurrencyConflict("new revision must be expected + 1")
        async with self._pool.connection() as conn, conn.transaction():
            await self._fence(conn)
            cur = await conn.execute(
                "UPDATE runs SET state = %s, revision = %s, record = %s, updated_at = now()"
                " WHERE tenant_id = %s AND run_id = %s AND revision = %s",
                (run.state, run.revision, _json(run), run.tenant_id, run.run_id, expected_revision),
            )
            if cur.rowcount != 1:
                raise ConcurrencyConflict(f"run {run.run_id} changed")
            if continuation is not None:
                state, driver_state = continuation
                await self._save_continuation(conn, run.tenant_id, run.run_id, state, driver_state)
            if work is not None:
                kind, payload, request_digest = work
                await conn.execute(
                    "INSERT INTO run_work"
                    " (work_id, tenant_id, run_id, kind, payload, request_digest)"
                    " VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
                    (
                        new_id("work"),
                        run.tenant_id,
                        run.run_id,
                        kind,
                        Jsonb(dict(payload)),
                        request_digest,
                    ),
                )
            await self._append(conn, run.tenant_id, run.run_id, events)
        return run

    # -- actions --------------------------------------------------------------
    async def put_action(
        self, action: ActionRecord, expected_revision: int | None, events: Sequence[EventSpec]
    ) -> ActionRecord:
        async with self._pool.connection() as conn, conn.transaction():
            await self._fence(conn)
            await self._cas_action(conn, action, expected_revision)
            await self._append(conn, action.tenant_id, action.run_id, events)
        return action

    async def wait_for_approval(
        self,
        action: ActionRecord,
        expected_action_revision: int,
        run: RunRecord,
        expected_run_revision: int,
        continuation: tuple[Mapping[str, Any], Mapping[str, Any] | None],
        events: Sequence[EventSpec],
    ) -> None:
        if run.revision != expected_run_revision + 1:
            raise ConcurrencyConflict("new revision must be expected + 1")
        async with self._pool.connection() as conn, conn.transaction():
            await self._fence(conn)
            cur = await conn.execute(
                "UPDATE runs SET state = %s, revision = %s, record = %s, updated_at = now()"
                " WHERE tenant_id = %s AND run_id = %s AND revision = %s",
                (
                    run.state,
                    run.revision,
                    _json(run),
                    run.tenant_id,
                    run.run_id,
                    expected_run_revision,
                ),
            )
            if cur.rowcount != 1:
                raise ConcurrencyConflict("run changed before approval checkpoint")
            await self._cas_action(conn, action, expected_action_revision)
            await self._save_continuation(conn, run.tenant_id, run.run_id, *continuation)
            await self._append(conn, run.tenant_id, run.run_id, events)

    async def get_action(self, tenant_id: str, action_id: str) -> ActionRecord:
        async with self._pool.connection() as conn:
            cur = await conn.execute(
                "SELECT record FROM actions WHERE tenant_id = %s AND action_id = %s",
                (tenant_id, action_id),
            )
            row = await cur.fetchone()
        if row is None:
            raise NotFound(action_id)
        return ActionRecord.model_validate(row[0])

    async def reserve_operation(
        self, action: ActionRecord, expected_revision: int, events: Sequence[EventSpec]
    ) -> ActionRecord:
        async with self._pool.connection() as conn, conn.transaction():
            await self._fence(conn)
            # ADR 0020: serialize admission per connection inside this short transaction, then
            # refuse while another action on the connection is DISPATCHING or UNKNOWN.
            await conn.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                (f"e-agent-admit:{action.tenant_id}:{action.connection_id}",),
            )
            cur = await conn.execute(
                "SELECT action_id FROM actions WHERE tenant_id = %s AND connection_id = %s"
                " AND state IN ('DISPATCHING', 'UNKNOWN') AND action_id <> %s LIMIT 1",
                (action.tenant_id, action.connection_id, action.action_id),
            )
            if await cur.fetchone() is not None:
                raise ConnectionBusy(action.connection_id)
            await self._cas_action(conn, action, expected_revision)
            try:
                async with conn.transaction():
                    await conn.execute(
                        "INSERT INTO operation_reservations"
                        " (tenant_id, connection_id, logical_operation_id, action_id)"
                        " VALUES (%s, %s, %s, %s)",
                        (
                            action.tenant_id,
                            action.connection_id,
                            action.logical_operation_id,
                            action.action_id,
                        ),
                    )
            except errors.UniqueViolation as exc:
                raise DuplicateOperation(action.logical_operation_id) from exc
            await self._append(conn, action.tenant_id, action.run_id, events)
        return action

    async def record_approval(
        self,
        approval: ApprovalRecord,
        events: Sequence[EventSpec],
        *,
        action: ActionRecord | None = None,
        expected_revision: int | None = None,
    ) -> None:
        async with self._pool.connection() as conn, conn.transaction():
            await self._fence(conn)
            if action is not None:
                if expected_revision is None:
                    raise ConcurrencyConflict("approval transition requires a revision")
                await self._cas_action(conn, action, expected_revision)
            await conn.execute(
                "INSERT INTO approvals (tenant_id, approval_id, action_id, record)"
                " VALUES (%s, %s, %s, %s)",
                (approval.tenant_id, approval.approval_id, approval.action_id, _json(approval)),
            )
            await self._append(conn, approval.tenant_id, approval.run_id, events)

    async def record_receipt(
        self,
        receipt: ExecutionReceipt,
        action: ActionRecord,
        expected_revision: int,
        events: Sequence[EventSpec],
    ) -> ActionRecord:
        async with self._pool.connection() as conn, conn.transaction():
            await self._fence(conn)
            await self._cas_action(conn, action, expected_revision)
            await conn.execute(
                "INSERT INTO receipts (tenant_id, action_id, record) VALUES (%s, %s, %s)",
                (action.tenant_id, action.action_id, _json(receipt)),
            )
            await self._append(conn, action.tenant_id, action.run_id, events)
        return action

    async def record_outcome(
        self,
        tenant_id: str,
        outcome: OutcomeReport,
        action: ActionRecord | None,
        expected_revision: int | None,
        events: Sequence[EventSpec],
    ) -> None:
        async with self._pool.connection() as conn, conn.transaction():
            await self._fence(conn)
            if action is not None:
                await self._cas_action(conn, action, expected_revision)
            await conn.execute(
                "INSERT INTO outcome_reports (tenant_id, run_id, action_id, record)"
                " VALUES (%s, %s, %s, %s)",
                (tenant_id, outcome.run_id, outcome.action_id, _json(outcome)),
            )
            await self._append(conn, tenant_id, outcome.run_id, events)

    # -- queries --------------------------------------------------------------
    async def _records(self, sql: str, params: tuple[Any, ...]) -> list[Any]:
        async with self._pool.connection() as conn:
            cur = await conn.execute(sql, params)
            return [row[0] for row in await cur.fetchall()]

    async def list_events(
        self, tenant_id: str, run_id: str, after_sequence: int = 0, limit: int | None = None
    ) -> list[RunEvent]:
        sql = (
            "SELECT record FROM run_events WHERE tenant_id = %s AND run_id = %s"
            " AND sequence > %s ORDER BY sequence"
        )
        params: tuple[Any, ...] = (tenant_id, run_id, after_sequence)
        if limit is not None:
            sql += " LIMIT %s"
            params += (limit,)
        rows = await self._records(sql, params)
        return [RunEvent.model_validate(r) for r in rows]

    async def list_actions(self, tenant_id: str, run_id: str) -> list[ActionRecord]:
        rows = await self._records(
            "SELECT record FROM actions WHERE tenant_id = %s AND run_id = %s ORDER BY action_id",
            (tenant_id, run_id),
        )
        return [ActionRecord.model_validate(r) for r in rows]

    async def list_receipts(self, tenant_id: str, action_id: str) -> list[ExecutionReceipt]:
        rows = await self._records(
            "SELECT record FROM receipts WHERE tenant_id = %s AND action_id = %s ORDER BY id",
            (tenant_id, action_id),
        )
        return [ExecutionReceipt.model_validate(r) for r in rows]

    async def list_approvals(self, tenant_id: str, action_id: str) -> list[ApprovalRecord]:
        rows = await self._records(
            "SELECT record FROM approvals WHERE tenant_id = %s AND action_id = %s"
            " ORDER BY approval_id",
            (tenant_id, action_id),
        )
        return [ApprovalRecord.model_validate(r) for r in rows]

    async def claim_idempotency(
        self, tenant_id: str, actor_id: str, key: str, request_digest: str, run_id: str
    ) -> tuple[str, str]:
        async with self._pool.connection() as conn, conn.transaction():
            await self._fence(conn)
            await conn.execute(
                "INSERT INTO api_idempotency"
                " (tenant_id, actor_id, idem_key, request_digest, run_id)"
                " VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
                (tenant_id, actor_id, key, request_digest, run_id),
            )
            cur = await conn.execute(
                "SELECT run_id, request_digest FROM api_idempotency"
                " WHERE tenant_id = %s AND actor_id = %s AND idem_key = %s",
                (tenant_id, actor_id, key),
            )
            row = await cur.fetchone()
        assert row is not None
        return str(row[0]), str(row[1])

    async def list_unfinished_runs(self) -> list[RunRecord]:
        terminal = [str(s) for s in TERMINAL_RUN_STATES]
        rows = await self._records(
            "SELECT record FROM runs WHERE NOT (state = ANY(%s)) ORDER BY tenant_id, run_id",
            (terminal,),
        )
        return [RunRecord.model_validate(r) for r in rows]

    async def save_continuation(
        self,
        tenant_id: str,
        run_id: str,
        state: Mapping[str, Any],
        driver_state: Mapping[str, Any] | None,
    ) -> None:
        async with self._pool.connection() as conn, conn.transaction():
            await self._fence(conn)
            await self._save_continuation(conn, tenant_id, run_id, state, driver_state)

    @staticmethod
    async def _save_continuation(
        conn: AsyncConnection[Any],
        tenant_id: str,
        run_id: str,
        state: Mapping[str, Any],
        driver_state: Mapping[str, Any] | None,
    ) -> None:
        await conn.execute(
            "INSERT INTO continuations (tenant_id, run_id, state, driver_state)"
            " VALUES (%s, %s, %s, %s)"
            " ON CONFLICT (tenant_id, run_id) DO UPDATE"
            " SET state = EXCLUDED.state, driver_state = EXCLUDED.driver_state,"
            " updated_at = now()",
            (
                tenant_id,
                run_id,
                Jsonb(dict(state)),
                Jsonb(dict(driver_state)) if driver_state is not None else None,
            ),
        )

    async def load_continuation(
        self, tenant_id: str, run_id: str
    ) -> tuple[dict[str, Any], dict[str, Any] | None] | None:
        async with self._pool.connection() as conn:
            cur = await conn.execute(
                "SELECT state, driver_state FROM continuations"
                " WHERE tenant_id = %s AND run_id = %s",
                (tenant_id, run_id),
            )
            row = await cur.fetchone()
        return None if row is None else (row[0], row[1])

    @asynccontextmanager
    async def writer_lock(self, tenant_id: str, connection_id: str) -> AsyncIterator[None]:
        """Session-level advisory lock on a dedicated pooled connection (no transaction)."""
        key = f"e-agent-writer:{tenant_id}:{connection_id}"
        async with self._pool.connection() as conn:
            await conn.set_autocommit(True)
            await conn.execute("SELECT pg_advisory_lock(hashtextextended(%s, 0))", (key,))
            try:
                await self._fence(conn)
                yield
            finally:
                await conn.execute("SELECT pg_advisory_unlock(hashtextextended(%s, 0))", (key,))
                await conn.set_autocommit(False)

    async def _fence(self, conn: AsyncConnection[Any]) -> None:
        claim = self._work_claim.get()
        if claim is None:
            return
        cur = await conn.execute(
            "SELECT 1 FROM run_work WHERE work_id = %s AND owner = %s AND fence = %s"
            " AND state = 'CLAIMED' AND lease_until > now() FOR UPDATE",
            (claim.work_id, claim.owner, claim.fence),
        )
        if await cur.fetchone() is None:
            raise ConcurrencyConflict("worker lease or fencing token is stale")

    async def enqueue_work(
        self,
        tenant_id: str,
        run_id: str,
        kind: str,
        payload: Mapping[str, Any],
        request_digest: str,
    ) -> None:
        async with self._pool.connection() as conn, conn.transaction():
            await conn.execute(
                "INSERT INTO run_work"
                " (work_id, tenant_id, run_id, kind, payload, request_digest)"
                " VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
                (new_id("work"), tenant_id, run_id, kind, Jsonb(dict(payload)), request_digest),
            )
            cur = await conn.execute(
                "SELECT payload FROM run_work WHERE tenant_id = %s AND run_id = %s"
                " AND kind = %s AND request_digest = %s",
                (tenant_id, run_id, kind, request_digest),
            )
            row = await cur.fetchone()
            if row is None or row[0] != dict(payload):
                raise ConcurrencyConflict("work request conflicts with the admitted command")

    async def claim_work(self, owner: str, lease_seconds: int = 30) -> WorkClaim | None:
        async with self._pool.connection() as conn, conn.transaction():
            # Lock the parent run too: concurrent claimers cannot select two jobs for one run.
            cur = await conn.execute(
                "SELECT w.work_id FROM run_work w JOIN runs r"
                " ON r.tenant_id = w.tenant_id AND r.run_id = w.run_id WHERE w.state != 'DONE'"
                " AND (w.lease_until IS NULL OR w.lease_until <= now())"
                " AND NOT EXISTS (SELECT 1 FROM run_work active"
                " WHERE active.tenant_id = w.tenant_id"
                " AND active.run_id = w.run_id AND active.state = 'CLAIMED'"
                " AND active.lease_until > now()) ORDER BY w.created_at, w.work_id"
                " FOR UPDATE OF w, r SKIP LOCKED LIMIT 1"
            )
            row = await cur.fetchone()
            if row is None:
                return None
            cur = await conn.execute(
                "UPDATE run_work SET state = 'CLAIMED', owner = %s, fence = fence + 1,"
                " lease_until = now() + make_interval(secs => %s) WHERE work_id = %s"
                " RETURNING work_id, tenant_id, run_id, kind, payload, owner, fence, lease_until",
                (owner, lease_seconds, row[0]),
            )
            claimed = await cur.fetchone()
            assert claimed is not None
            return WorkClaim.model_validate(dict(zip(WorkClaim.model_fields, claimed, strict=True)))

    async def renew_work(self, claim: WorkClaim, lease_seconds: int = 30) -> bool:
        async with self._pool.connection() as conn, conn.transaction():
            cur = await conn.execute(
                "UPDATE run_work SET lease_until = now() + make_interval(secs => %s)"
                " WHERE work_id = %s AND owner = %s AND fence = %s AND state = 'CLAIMED'"
                " AND lease_until > now()",
                (lease_seconds, claim.work_id, claim.owner, claim.fence),
            )
            return cur.rowcount == 1

    async def finish_work(self, claim: WorkClaim) -> None:
        async with self.work_scope(claim), self._pool.connection() as conn, conn.transaction():
            await self._fence(conn)
            await conn.execute(
                "UPDATE run_work SET state = 'DONE' WHERE work_id = %s", (claim.work_id,)
            )

    @asynccontextmanager
    async def work_scope(self, claim: WorkClaim) -> AsyncIterator[None]:
        token = self._work_claim.set(claim)
        try:
            yield
        finally:
            self._work_claim.reset(token)

    async def has_pending_work(self, tenant_id: str, run_id: str) -> bool:
        async with self._pool.connection() as conn:
            cur = await conn.execute(
                "SELECT 1 FROM run_work WHERE tenant_id = %s AND run_id = %s"
                " AND state != 'DONE' LIMIT 1",
                (tenant_id, run_id),
            )
            return await cur.fetchone() is not None
