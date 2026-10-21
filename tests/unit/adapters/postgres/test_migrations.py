import os

import psycopg
import pytest
from e_agent.adapters.postgres import migrate

DSN = os.environ.get("E_AGENT_TEST_PG_DSN")
pytestmark = [pytest.mark.asyncio, pytest.mark.skipif(not DSN, reason="E_AGENT_TEST_PG_DSN unset")]


async def _fresh_db() -> str:
    assert DSN
    async with await psycopg.AsyncConnection.connect(DSN, autocommit=True) as conn:
        await conn.execute("DROP DATABASE IF EXISTS e_agent_migration_test")
        await conn.execute("CREATE DATABASE e_agent_migration_test")
    return DSN.replace("/e_agent_test", "/e_agent_migration_test")


async def test_migrations_apply_once_and_are_idempotent() -> None:
    dsn = await _fresh_db()
    assert await migrate.apply_migrations(dsn) == [
        "0001_initial.sql",
        "0002_api_idempotency.sql",
        "0003_run_work.sql",
        "0004_run_work_expire.sql",
        "0005_action_plans_and_steps.sql",
        "0006_run_work_resume.sql",
        "0007_conversations.sql",
    ]
    assert await migrate.apply_migrations(dsn) == []


async def test_migration_0007_applies_after_0006(monkeypatch: pytest.MonkeyPatch) -> None:
    """0007 applies to a ledger that already holds runs: it is forward-only and rewrites no
    data, so an existing run keeps its record and has no conversation (ADR 0023 §3)."""
    dsn = await _fresh_db()
    every = migrate._migrations()
    assert [name for name, _ in every][-2:] == [
        "0006_run_work_resume.sql",
        "0007_conversations.sql",
    ]
    monkeypatch.setattr(migrate, "_migrations", lambda: every[:-1])
    assert (await migrate.apply_migrations(dsn))[-1] == "0006_run_work_resume.sql"
    record = '{"run_id": "run_old", "tenant_id": "t1", "task": "x"}'
    async with await psycopg.AsyncConnection.connect(dsn, autocommit=True) as conn:
        await conn.execute(
            "INSERT INTO runs (tenant_id, run_id, state, revision, record)"
            " VALUES ('t1', 'run_old', 'SUCCEEDED', 3, %s::jsonb)",
            (record,),
        )
    monkeypatch.setattr(migrate, "_migrations", lambda: every)
    assert await migrate.apply_migrations(dsn) == ["0007_conversations.sql"]
    async with await psycopg.AsyncConnection.connect(dsn, autocommit=True) as conn:
        cur = await conn.execute(
            "SELECT conversation_id, record, revision FROM runs WHERE run_id = 'run_old'"
        )
        assert await cur.fetchone() == (
            None,
            {"run_id": "run_old", "tenant_id": "t1", "task": "x"},
            3,
        )
        cur = await conn.execute(
            "SELECT column_name FROM information_schema.columns"
            " WHERE table_name = 'conversations' ORDER BY ordinal_position"
        )
        columns = [row[0] for row in await cur.fetchall()]
        assert columns == [
            "tenant_id",
            "conversation_id",
            "owner_id",
            "revision",
            "created_at",
            "updated_at",
        ]
        # A run cannot name a conversation that does not exist in its tenant.
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            await conn.execute(
                "INSERT INTO runs (tenant_id, run_id, state, revision, record, conversation_id)"
                " VALUES ('t1', 'run_new', 'CREATED', 1,"
                " '{\"conversation_id\": \"conv_x\"}'::jsonb, 'conv_x')"
            )
    assert await migrate.apply_migrations(dsn) == []


async def test_modified_applied_migration_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    dsn = await _fresh_db()
    await migrate.apply_migrations(dsn)
    original = migrate._migrations()
    monkeypatch.setattr(
        migrate, "_migrations", lambda: [(n, sql + "\n-- edited") for n, sql in original]
    )
    with pytest.raises(migrate.MigrationError):
        await migrate.apply_migrations(dsn)
