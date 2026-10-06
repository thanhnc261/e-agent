"""PostgreSQL implementation of the RunStore port.

Each method is one short local transaction; no transaction is ever held
across a model or provider call (ADR 0003). Event sequences are assigned
under the run's row lock and published with NOTIFY in the same transaction.
"""

from __future__ import annotations

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
from e_agent.sdk.store import ConcurrencyConflict, DuplicateOperation, EventSpec, NotFound
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
                " receipts, outcome_reports, continuations, api_idempotency"
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
        self, run: RunRecord, expected_revision: int, events: Sequence[EventSpec]
    ) -> RunRecord:
        if run.revision != expected_revision + 1:
            raise ConcurrencyConflict("new revision must be expected + 1")
        async with self._pool.connection() as conn, conn.transaction():
            cur = await conn.execute(
                "UPDATE runs SET state = %s, revision = %s, record = %s, updated_at = now()"
                " WHERE tenant_id = %s AND run_id = %s AND revision = %s",
                (run.state, run.revision, _json(run), run.tenant_id, run.run_id, expected_revision),
            )
            if cur.rowcount != 1:
                raise ConcurrencyConflict(f"run {run.run_id} changed")
            await self._append(conn, run.tenant_id, run.run_id, events)
        return run

    # -- actions --------------------------------------------------------------
    async def put_action(
        self, action: ActionRecord, expected_revision: int | None, events: Sequence[EventSpec]
    ) -> ActionRecord:
        async with self._pool.connection() as conn, conn.transaction():
            await self._cas_action(conn, action, expected_revision)
            await self._append(conn, action.tenant_id, action.run_id, events)
        return action

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

    async def record_approval(self, approval: ApprovalRecord, events: Sequence[EventSpec]) -> None:
        async with self._pool.connection() as conn, conn.transaction():
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
        self, tenant_id: str, run_id: str, after_sequence: int = 0
    ) -> list[RunEvent]:
        rows = await self._records(
            "SELECT record FROM run_events WHERE tenant_id = %s AND run_id = %s"
            " AND sequence > %s ORDER BY sequence",
            (tenant_id, run_id, after_sequence),
        )
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
                yield
            finally:
                await conn.execute("SELECT pg_advisory_unlock(hashtextextended(%s, 0))", (key,))
                await conn.set_autocommit(False)
