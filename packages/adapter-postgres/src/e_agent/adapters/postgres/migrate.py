"""Forward-only SQL migrations with checksums.

Migrations are packaged resources (``migrations/NNNN_name.sql``). Applied
versions and checksums are recorded; a changed, already-applied file is an
error. Concurrent runners are serialized with an advisory lock. Changes that
must overlap deployments follow expand -> migrate -> contract (HLD §8).
"""

from __future__ import annotations

import hashlib
from importlib.resources import files

import psycopg

LOCK_KEY = 7_420_011  # arbitrary constant for the migration advisory lock


class MigrationError(RuntimeError):
    pass


def _migrations() -> list[tuple[str, str]]:
    root = files("e_agent.adapters.postgres").joinpath("migrations")
    found = sorted(p.name for p in root.iterdir() if p.name.endswith(".sql"))
    return [(name, root.joinpath(name).read_text("utf-8")) for name in found]


async def apply_migrations(dsn: str) -> list[str]:
    applied_now: list[str] = []
    async with await psycopg.AsyncConnection.connect(dsn, autocommit=True) as conn:
        await conn.execute("SELECT pg_advisory_lock(%s)", (LOCK_KEY,))
        try:
            await conn.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations ("
                " version text PRIMARY KEY, checksum text NOT NULL,"
                " applied_at timestamptz NOT NULL DEFAULT now())"
            )
            cur = await conn.execute("SELECT version, checksum FROM schema_migrations")
            done = {row[0]: row[1] for row in await cur.fetchall()}
            for name, sql in _migrations():
                checksum = hashlib.sha256(sql.encode("utf-8")).hexdigest()
                if name in done:
                    if done[name] != checksum:
                        raise MigrationError(f"applied migration {name} was modified")
                    continue
                async with conn.transaction():
                    await conn.execute(sql.encode("utf-8"))
                    await conn.execute(
                        "INSERT INTO schema_migrations (version, checksum) VALUES (%s, %s)",
                        (name, checksum),
                    )
                applied_now.append(name)
        finally:
            await conn.execute("SELECT pg_advisory_unlock(%s)", (LOCK_KEY,))
    return applied_now
