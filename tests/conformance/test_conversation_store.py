"""ConversationStore conformance: the same behaviour from both stores (ADR 0023 §3, ENG-STORE-1).

Every query filters by tenant and owner, so another owner's or tenant's conversation looks
absent (PR-24). ``create_run_in_conversation`` replays a known idempotency key before any
conversation check, and otherwise refuses a stale revision or a second active run with
``ConcurrencyConflict``: one active run per conversation is that check.
"""

import asyncio
import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from e_agent.contracts.conversation import Conversation
from e_agent.contracts.events import RunEventType
from e_agent.contracts.run import TERMINAL_RUN_STATES, RunRecord, RunState
from e_agent.kernel.memory_conversations import InMemoryConversationStore
from e_agent.sdk.store import ConcurrencyConflict, ConversationStore, NotFound, RunStore

DSN = os.environ.get("E_AGENT_TEST_PG_DSN")
KINDS = ["memory"] + (["postgres"] if DSN else [])
T0 = datetime(2026, 10, 6, tzinfo=UTC)
ACTOR = "principal:u1"
EV = (RunEventType.RUN_CREATED, {"task": "x"}, None)
ACTIVE_STATES = tuple(s for s in RunState if s not in TERMINAL_RUN_STATES)
pytestmark = pytest.mark.asyncio


async def _open_postgres() -> Any:
    from e_agent.adapters.postgres import PostgresRunStore, apply_migrations

    assert DSN
    await apply_migrations(DSN)
    pg = await PostgresRunStore.open(DSN)
    await pg.truncate_for_tests()
    return pg


@pytest.fixture(params=KINDS)
async def store(request: pytest.FixtureRequest) -> AsyncIterator[Any]:
    if request.param == "memory":
        yield InMemoryConversationStore()
        return
    pg = await _open_postgres()
    try:
        yield pg
    finally:
        await pg.close()


def _conv(
    cid: str = "conv_1", tenant: str = "t1", owner: str = "u1", at: datetime = T0, rev: int = 1
) -> Conversation:
    return Conversation(
        tenant_id=tenant,
        conversation_id=cid,
        owner_id=owner,
        revision=rev,
        created_at=at,
        updated_at=at,
    )


def _run(
    rid: str = "run_1",
    conv: str | None = "conv_1",
    tenant: str = "t1",
    state: RunState = RunState.CREATED,
    rev: int = 1,
    at: datetime = T0,
) -> RunRecord:
    return RunRecord(
        run_id=rid,
        tenant_id=tenant,
        requester_id="u1",
        task="x",
        state=state,
        revision=rev,
        logical_operation_id=f"op_{rid}",
        created_at=at,
        conversation_id=conv,
    )


async def _start(
    store: Any,
    rid: str,
    key: str,
    conversation_revision: int,
    conv: str = "conv_1",
    tenant: str = "t1",
    at: datetime = T0,
) -> tuple[str, str]:
    return await store.create_run_in_conversation(
        _run(rid, conv, tenant, at=at),
        [EV],
        {"step": rid},
        ACTOR,
        key,
        f"digest_{key}",
        conversation_revision,
    )


async def _end(store: Any, rid: str, state: RunState, tenant: str = "t1") -> None:
    run = await store.get_run(tenant, rid)
    moved = run.model_copy(update={"state": state, "revision": run.revision + 1})
    await store.update_run(moved, run.revision, [])


async def _linked(store: Any, cid: str = "conv_1") -> list[str]:
    return [r.run_id for r in await store.list_conversation_runs("t1", "u1", cid)]


async def test_create_and_get_conversation(store: Any) -> None:
    assert isinstance(store, ConversationStore) and isinstance(store, RunStore)
    await store.create_conversation(_conv())
    assert await store.get_conversation("t1", "u1", "conv_1") == _conv()
    assert await store.list_conversation_runs("t1", "u1", "conv_1") == ()
    cases = 0
    for refused, error in (
        (_conv(), ConcurrencyConflict),  # a conversation is never overwritten
        (_conv("conv_0", rev=0), ValueError),  # a new conversation starts at revision 1
    ):
        with pytest.raises(error):
            await store.create_conversation(refused)
        cases += 1
    with pytest.raises(NotFound):
        await store.get_conversation("t1", "u1", "conv_0")
    with pytest.raises(NotFound):
        await store.get_conversation("t1", "u1", "conv_missing")
    print(f"conversation create refusal cases: {cases}")
    assert cases == 2


async def test_foreign_owner_conversation_looks_absent(store: Any) -> None:
    await store.create_conversation(_conv())
    await _start(store, "run_1", "k1", 1)
    cases = 0
    for read in (
        store.get_conversation("t1", "u2", "conv_1"),
        store.list_conversation_runs("t1", "u2", "conv_1"),
        store.list_conversations("t1", "u2", after="conv_1", limit=10),
    ):
        with pytest.raises(NotFound):
            await read
        cases += 1
    assert (await store.list_conversations("t1", "u2", after=None, limit=10)).items == ()
    print(f"foreign owner cases: {cases}")
    assert cases == 3


async def test_foreign_tenant_conversation_looks_absent(store: Any) -> None:
    await store.create_conversation(_conv())
    cases = 0
    for read in (
        store.get_conversation("t2", "u1", "conv_1"),
        store.list_conversation_runs("t2", "u1", "conv_1"),
        store.list_conversations("t2", "u1", after="conv_1", limit=10),
        _start(store, "run_t2", "k_t2", 1, tenant="t2"),  # a run cannot join it either
    ):
        with pytest.raises(NotFound):
            await read
        cases += 1
    assert (await store.list_conversations("t2", "u1", after=None, limit=10)).items == ()
    with pytest.raises(NotFound):
        await store.get_run("t2", "run_t2")
    assert (await store.get_conversation("t1", "u1", "conv_1")).revision == 1
    print(f"foreign tenant cases: {cases}")
    assert cases == 4


async def test_list_conversations_is_paged_and_bounded(store: Any) -> None:
    for i in range(5):
        await store.create_conversation(_conv(f"conv_{i}", at=T0 + timedelta(minutes=i)))
    await store.create_conversation(_conv("conv_other", owner="u2", at=T0 + timedelta(hours=1)))
    await store.create_conversation(_conv("conv_t2", tenant="t2", at=T0 + timedelta(hours=1)))
    pages: list[list[str]] = []
    after: str | None = None
    while True:
        page = await store.list_conversations("t1", "u1", after=after, limit=2)
        pages.append([c.conversation_id for c in page.items])
        if page.next_after is None:
            break
        assert page.next_after == page.items[-1].conversation_id
        after = page.next_after
    assert pages == [["conv_4", "conv_3"], ["conv_2", "conv_1"], ["conv_0"]]  # newest first
    exact = await store.list_conversations("t1", "u1", after=None, limit=5)
    assert (len(exact.items), exact.next_after) == (5, None)
    assert len((await store.list_conversations("t1", "u1", after=None, limit=100)).items) == 5
    cases = 0
    for limit in (0, -1, 101):
        with pytest.raises(ValueError, match="limit"):
            await store.list_conversations("t1", "u1", after=None, limit=limit)
        cases += 1
    with pytest.raises(NotFound):
        await store.list_conversations("t1", "u1", after="conv_missing", limit=2)
    cases += 1
    print(f"list bound cases: {cases}, pages: {len(pages)}")
    assert cases == 4


async def test_run_creation_bumps_conversation_revision(store: Any) -> None:
    await store.create_conversation(_conv())
    assert await _start(store, "run_1", "k1", 1) == ("run_1", "digest_k1")
    conv = await store.get_conversation("t1", "u1", "conv_1")
    assert conv.revision == 2 and conv.updated_at > T0 and conv.created_at == T0
    assert (await store.get_run("t1", "run_1")).conversation_id == "conv_1"
    assert await store.load_continuation("t1", "run_1") == ({"step": "run_1"}, None)
    assert await store.has_pending_work("t1", "run_1")  # admitted as create_run_idempotent does
    assert [e.type for e in await store.list_events("t1", "run_1")] == [EV[0]]
    await _end(store, "run_1", RunState.SUCCEEDED)
    await _start(store, "run_2", "k2", 2, at=T0 + timedelta(seconds=1))
    assert (await store.get_conversation("t1", "u1", "conv_1")).revision == 3
    assert await _linked(store) == ["run_1", "run_2"]  # oldest first


async def test_stale_conversation_revision_is_refused(store: Any) -> None:
    await store.create_conversation(_conv())
    cases = 0
    for stale in (0, 2, 7):
        with pytest.raises(ConcurrencyConflict):
            await _start(store, f"run_{stale}", f"k{stale}", stale)
        with pytest.raises(NotFound):
            await store.get_run("t1", f"run_{stale}")
        assert await store.lookup_idempotent("t1", ACTOR, f"k{stale}") is None
        cases += 1
    assert (await store.get_conversation("t1", "u1", "conv_1")).revision == 1
    assert await _linked(store) == []
    print(f"stale revision cases: {cases}")
    assert cases == 3


async def test_second_active_run_in_conversation_is_refused(store: Any) -> None:
    await store.create_conversation(_conv())
    await _start(store, "run_1", "k1", 1)
    cases = 0
    for state in ACTIVE_STATES:
        if state is not RunState.CREATED:
            await _end(store, "run_1", state)
        with pytest.raises(ConcurrencyConflict):
            await _start(store, f"run_{state}", f"k_{state}", 2)
        assert await store.lookup_idempotent("t1", ACTOR, f"k_{state}") is None
        cases += 1
    assert (await store.get_conversation("t1", "u1", "conv_1")).revision == 2
    assert await _linked(store) == ["run_1"]
    print(f"active run states refused: {cases}")
    assert cases == len(ACTIVE_STATES) == 6


async def test_new_run_allowed_after_terminal_run(store: Any) -> None:
    cases = 0
    for state in sorted(TERMINAL_RUN_STATES):
        cid = f"conv_{state}"
        await store.create_conversation(_conv(cid))
        await _start(store, f"run_a_{state}", f"ka_{state}", 1, conv=cid)
        await _end(store, f"run_a_{state}", state)
        later = T0 + timedelta(seconds=1)
        await _start(store, f"run_b_{state}", f"kb_{state}", 2, conv=cid, at=later)
        assert (await store.get_conversation("t1", "u1", cid)).revision == 3
        assert await _linked(store, cid) == [f"run_a_{state}", f"run_b_{state}"]
        cases += 1
    print(f"terminal states that free the conversation: {cases}")
    assert cases == len(TERMINAL_RUN_STATES) == 3


async def test_idempotent_replay_starts_one_run(store: Any) -> None:
    await store.create_conversation(_conv())
    first = await _start(store, "run_1", "k1", 1)
    assert (await store.get_run("t1", "run_1")).state is RunState.CREATED  # still active
    # The replay carries a new run id and the revision it read before the first commit:
    # either would be refused by the conversation check, which a hit never runs.
    assert await _start(store, "run_retry", "k1", 1) == first
    await _end(store, "run_1", RunState.RUNNING)
    assert await _start(store, "run_retry", "k1", 1) == first
    with pytest.raises(NotFound):
        await store.get_run("t1", "run_retry")
    assert (await store.get_conversation("t1", "u1", "conv_1")).revision == 2  # bumped once
    assert await _linked(store) == ["run_1"]


async def test_concurrent_same_key_starts_one_run(store: Any) -> None:
    await store.create_conversation(_conv())
    got = await asyncio.gather(
        _start(store, "run_a", "k1", 1),
        _start(store, "run_b", "k1", 1),
    )
    assert got[0] == got[1] and got[0][1] == "digest_k1"
    assert await _linked(store) == [got[0][0]]
    assert (await store.get_conversation("t1", "u1", "conv_1")).revision == 2


async def test_lookup_idempotent_reads_without_writing(store: Any) -> None:
    await store.create_conversation(_conv())
    assert await store.lookup_idempotent("t1", ACTOR, "k1") is None
    assert await store.lookup_idempotent("t1", ACTOR, "k1") is None  # the miss wrote nothing
    # ... so the key is still free for the first writer:
    assert await store.claim_idempotency("t1", ACTOR, "k1", "d_claim", "run_x") == (
        "run_x",
        "d_claim",
    )
    assert await store.lookup_idempotent("t1", ACTOR, "k1") == ("run_x", "d_claim")
    await _start(store, "run_1", "k2", 1)
    plain = _run("run_plain", conv=None)
    await store.create_run_idempotent(plain, [EV], {}, ACTOR, "k3", "d3")
    cases = 0
    for (tenant, actor, key), want in {
        ("t1", ACTOR, "k2"): ("run_1", "digest_k2"),  # create_run_in_conversation's record
        ("t1", ACTOR, "k3"): ("run_plain", "d3"),  # create_run_idempotent's record
        ("t1", "principal:u2", "k2"): None,
        ("t2", ACTOR, "k2"): None,
    }.items():
        assert await store.lookup_idempotent(tenant, actor, key) == want
        cases += 1
    assert (await store.get_conversation("t1", "u1", "conv_1")).revision == 2
    print(f"idempotency lookup cases: {cases}")
    assert cases == 4


async def test_concurrent_messages_start_one_run(store: Any) -> None:
    await store.create_conversation(_conv())
    got = await asyncio.gather(
        _start(store, "run_a", "ka", 1),
        _start(store, "run_b", "kb", 1),
        return_exceptions=True,
    )
    started = [g for g in got if isinstance(g, tuple)]
    refused = [g for g in got if isinstance(g, ConcurrencyConflict)]
    assert (len(started), len(refused)) == (1, 1), got
    assert await _linked(store) == [started[0][0]]
    assert (await store.get_conversation("t1", "u1", "conv_1")).revision == 2


@pytest.mark.skipif(not DSN, reason="E_AGENT_TEST_PG_DSN unset")
async def test_runs_conversation_id_column_matches_record() -> None:
    """Migration 0007's ``runs.conversation_id`` is written from the record at every insert
    site, and the schema refuses a record that disagrees with it (4c.2 review R1-4)."""
    import psycopg

    pg = await _open_postgres()
    try:
        await pg.create_conversation(_conv())
        await pg.create_conversation(_conv("conv_2"))
        await pg.create_run(_run("run_create"), [EV])
        await pg.create_run(_run("run_unlinked", conv=None), [EV])
        await pg.create_run_idempotent(_run("run_idem"), [EV], {}, ACTOR, "k_idem", "d")
        await _start(pg, "run_conv", "k_conv", 1, conv="conv_2")
        async with pg._pool.connection() as conn:
            cur = await conn.execute(
                "SELECT run_id, conversation_id, record ->> 'conversation_id' FROM runs"
                " WHERE tenant_id = 't1' ORDER BY run_id"
            )
            rows = await cur.fetchall()
        assert rows == [
            ("run_conv", "conv_2", "conv_2"),
            ("run_create", "conv_1", "conv_1"),
            ("run_idem", "conv_1", "conv_1"),
            ("run_unlinked", None, None),
        ]
        cases = len(rows)
        moved = _run("run_create", conv="conv_2", rev=2)  # an update cannot move a run
        with pytest.raises(psycopg.errors.CheckViolation):
            await pg.update_run(moved, 1, [])
        cases += 1
        assert (await pg.get_run("t1", "run_create")).conversation_id == "conv_1"
        print(f"conversation_id column cases: {cases}")
        assert cases == 5
    finally:
        await pg.close()
