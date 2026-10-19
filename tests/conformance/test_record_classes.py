"""Every stored record kind declares a record class and a retention class (ADR 0030, ENG-STORE-1).

The declarations live once, store-neutrally, in ``contracts/data_classes.py``. This test
reads the record kinds each store actually keeps (the in-memory store's collections, the
PostgreSQL schema's tables) and requires them to equal the declared kinds both ways, so a
new collection or table without a declaration fails, and so does a stale declaration.
It prints how many kinds it checked and fails on zero (PR-31).
"""

import os
from collections.abc import AsyncIterator

import pytest
from e_agent.contracts.data_classes import RECORD_KINDS
from e_agent.kernel.memory_store import InMemoryRunStore

DSN = os.environ.get("E_AGENT_TEST_PG_DSN")
KINDS = ["memory"] + (["postgres"] if DSN else [])

MEMORY_COLLECTIONS = {
    "_runs": "runs",
    "_events": "run_events",
    "_actions": "actions",
    "_reservations": "operation_reservations",
    "_approvals": "approvals",
    "_receipts": "receipts",
    "_outcomes": "outcome_reports",
    "_continuations": "continuations",
    "_idempotency": "api_idempotency",
    "_work": "run_work",
    "_plans": "action_plans",
    "_steps": "run_steps",
}
"""The in-memory store's collection for each record kind."""
NOT_RECORD_KINDS = {
    "_writer_locks": "process-local asyncio locks, never stored data",
    "schema_migrations": "migration bookkeeping of the PostgreSQL adapter, not run data",
}
"""What a store holds that is not a record kind, each with its reason."""


@pytest.fixture(params=KINDS)
async def store_kinds(request: pytest.FixtureRequest) -> AsyncIterator[set[str]]:
    if request.param == "memory":
        store = InMemoryRunStore()
        held = {name for name, value in vars(store).items() if isinstance(value, dict)}
        unknown = sorted(held - set(MEMORY_COLLECTIONS) - set(NOT_RECORD_KINDS))
        assert not unknown, f"in-memory collections with no record kind: {unknown}"
        yield {MEMORY_COLLECTIONS[name] for name in held if name in MEMORY_COLLECTIONS}
        return
    import psycopg
    from e_agent.adapters.postgres import apply_migrations

    assert DSN
    await apply_migrations(DSN)  # the schema the adapter's migrations create
    async with await psycopg.AsyncConnection.connect(DSN) as conn:
        cur = await conn.execute(
            "SELECT table_name FROM information_schema.tables"
            " WHERE table_schema = current_schema() AND table_type = 'BASE TABLE'"
        )
        tables = {str(row[0]) for row in await cur.fetchall()}
    yield tables - set(NOT_RECORD_KINDS)


def check_declared(store_kinds: set[str]) -> int:
    """Assert the store's record kinds equal the declared kinds; return how many."""
    assert store_kinds, "the store holds no record kinds: 0 cases is a failure (PR-31)"
    undeclared = sorted(store_kinds - set(RECORD_KINDS))
    assert not undeclared, f"record kinds with no record and retention class: {undeclared}"
    stale = sorted(set(RECORD_KINDS) - store_kinds)
    assert not stale, f"declared record kinds this store does not keep: {stale}"
    return len(store_kinds)


def test_every_store_record_kind_declares_a_class(store_kinds: set[str]) -> None:
    print(f"record kinds checked: {len(store_kinds)}")
    assert check_declared(store_kinds) == len(RECORD_KINDS)


def test_the_check_fails_on_a_missing_declaration_and_on_zero_kinds() -> None:
    with pytest.raises(AssertionError, match="new_table"):
        check_declared(set(RECORD_KINDS) | {"new_table"})
    with pytest.raises(AssertionError, match="0 cases"):
        check_declared(set())
    with pytest.raises(AssertionError, match="does not keep"):
        check_declared(set(RECORD_KINDS) - {"runs"})
