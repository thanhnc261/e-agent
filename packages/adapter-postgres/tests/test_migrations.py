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
    assert await migrate.apply_migrations(dsn) == ["0001_initial.sql"]
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
