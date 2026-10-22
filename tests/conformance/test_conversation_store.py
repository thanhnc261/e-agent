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
from e_agent.contracts.action import ActionRecord, ActionState
from e_agent.contracts.conversation import Conversation
from e_agent.contracts.events import RunEventType
from e_agent.contracts.run import TERMINAL_RUN_STATES, RunRecord, RunState
from e_agent.kernel.memory_conversations import InMemoryConversationStore
from e_agent.kernel.memory_store import InMemoryRunStore
from e_agent.sdk.store import (
    LINK_CHANGE_REFUSED,
    LINKED_RUN_REFUSED,
    ConcurrencyConflict,
    ConversationStore,
    NotFound,
    RunStore,
)

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
    digest: str | None = None,
) -> tuple[str, str]:
    return await store.create_run_in_conversation(
        _run(rid, conv, tenant, at=at),
        [EV],
        {"step": rid},
        ACTOR,
        key,
        digest or f"digest_{key}",
        conversation_revision,
    )


SCHEDULES = ("read", "admit")
"""Where the in-memory store yields (review A1-5), as a Postgres round trip would:

- ``read``: the idempotency read returns and then yields, so a second request can read the
  same miss before the first commits, and then meet the first request's bump;
- ``admit``: the parent's admission yields first, so both requests pass the conversation
  checks before either inserts.

Without ``_conversation_lock`` the same-key test fails under ``read`` (a replay becomes a
stale-revision refusal) and the two-message test under ``admit`` (two active runs). Postgres
contends through its own connections, so it is left as is."""
_READ = InMemoryConversationStore.lookup_idempotent
_ADMIT = InMemoryRunStore.create_run_idempotent


def _contend(store: Any, monkeypatch: pytest.MonkeyPatch, schedule: str) -> None:
    if not isinstance(store, InMemoryConversationStore):
        return

    async def slow_read(self: Any, *args: Any) -> Any:
        found = await _READ(self, *args)
        await asyncio.sleep(0)
        return found

    async def slow_admit(self: Any, *args: Any) -> Any:
        await asyncio.sleep(0)
        return await _ADMIT(self, *args)

    read, admit = (slow_read, _ADMIT) if schedule == "read" else (_READ, slow_admit)
    monkeypatch.setattr(InMemoryConversationStore, "lookup_idempotent", read)
    monkeypatch.setattr(InMemoryRunStore, "create_run_idempotent", admit)


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
        (_conv("conv_2", rev=2), ValueError),  # exactly 1 (4c.3 review R2-1)
    ):
        with pytest.raises(error):
            await store.create_conversation(refused)
        cases += 1
    for absent in ("conv_0", "conv_2", "conv_missing"):
        with pytest.raises(NotFound):
            await store.get_conversation("t1", "u1", absent)
    print(f"conversation create refusal cases: {cases}")
    assert cases == 3


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
    # A same-key retry with another request: the recorded digest comes back, so the caller
    # sees the mismatch (4d.1's CONFLICT), and nothing starts.
    assert await _start(store, "run_other", "k1", 2, digest="digest_other") == first
    for rid in ("run_retry", "run_other"):
        with pytest.raises(NotFound):
            await store.get_run("t1", rid)
    assert (await store.get_conversation("t1", "u1", "conv_1")).revision == 2  # bumped once
    assert await _linked(store) == ["run_1"]


async def test_concurrent_same_key_starts_one_run(
    store: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    cases = 0
    for schedule in SCHEDULES:
        cid = f"conv_{schedule}"
        await store.create_conversation(_conv(cid))
        _contend(store, monkeypatch, schedule)
        got = await asyncio.gather(
            _start(store, f"run_a_{schedule}", f"k_{schedule}", 1, conv=cid),
            _start(store, f"run_b_{schedule}", f"k_{schedule}", 1, conv=cid),
        )
        assert got[0] == got[1] and got[0][1] == f"digest_k_{schedule}", schedule
        assert await _linked(store, cid) == [got[0][0]]
        assert (await store.get_conversation("t1", "u1", cid)).revision == 2
        cases += 1
    print(f"same-key schedules: {cases}")
    assert cases == len(SCHEDULES) == 2


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


async def test_concurrent_messages_start_one_run(
    store: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    cases = 0
    for schedule in SCHEDULES:
        cid = f"conv_{schedule}"
        await store.create_conversation(_conv(cid))
        _contend(store, monkeypatch, schedule)
        got = await asyncio.gather(
            _start(store, f"run_a_{schedule}", f"ka_{schedule}", 1, conv=cid),
            _start(store, f"run_b_{schedule}", f"kb_{schedule}", 1, conv=cid),
            return_exceptions=True,
        )
        started = [g for g in got if isinstance(g, tuple)]
        refused = [g for g in got if isinstance(g, ConcurrencyConflict)]
        assert (len(started), len(refused)) == (1, 1), (schedule, got)
        assert await _linked(store, cid) == [started[0][0]]
        assert (await store.get_conversation("t1", "u1", cid)).revision == 2
        cases += 1
    print(f"two-message schedules: {cases}")
    assert cases == len(SCHEDULES) == 2


async def test_create_run_refuses_a_linked_run(store: Any) -> None:
    """Only ``create_run_in_conversation`` links a run (review A1-1, B1-2)."""
    await store.create_conversation(_conv())
    cases = 0
    for conv in ("conv_1", "conv_missing"):
        with pytest.raises(ValueError, match=LINKED_RUN_REFUSED):
            await store.create_run(_run(f"run_{conv}", conv=conv), [EV])
        with pytest.raises(NotFound):
            await store.get_run("t1", f"run_{conv}")
        cases += 1
    assert (await store.get_conversation("t1", "u1", "conv_1")).revision == 1
    assert await _linked(store) == []
    print(f"linked create_run refusals: {cases}")
    assert cases == 2


async def test_create_run_idempotent_refuses_a_linked_run(store: Any) -> None:
    await store.create_conversation(_conv())
    cases = 0
    for conv in ("conv_1", "conv_missing"):
        with pytest.raises(ValueError, match=LINKED_RUN_REFUSED):
            await store.create_run_idempotent(
                _run(f"run_{conv}", conv=conv), [EV], {}, ACTOR, f"k_{conv}", "d"
            )
        with pytest.raises(NotFound):
            await store.get_run("t1", f"run_{conv}")
        assert await store.lookup_idempotent("t1", ACTOR, f"k_{conv}") is None
        cases += 1
    assert (await store.get_conversation("t1", "u1", "conv_1")).revision == 1
    assert await _linked(store) == []
    print(f"linked create_run_idempotent refusals: {cases}")
    assert cases == 2


def _waiting_action(run_id: str) -> ActionRecord:
    return ActionRecord(
        action_id=f"act_{run_id}",
        tenant_id="t1",
        run_id=run_id,
        logical_operation_id=f"op_{run_id}",
        contract_id="notes.note.create.v1",
        binding_id="b",
        connection_id="c",
        connection_version=1,
        credential_subject="c@1/s",
        arguments={"text": "hi"},
        digest="d",
        state=ActionState.AWAITING_APPROVAL,
        revision=2,
    )


async def test_update_refuses_a_changed_conversation(store: Any) -> None:
    """A run's conversation never changes, so a write cannot move a run into or out of a
    conversation past the active-run check (review A1-2)."""
    await store.create_conversation(_conv())
    await store.create_conversation(_conv("conv_2"))
    await _start(store, "run_1", "k1", 1)
    await store.create_run(_run("run_plain", conv=None), [EV])
    for rid in ("run_1", "run_plain"):
        proposed = _waiting_action(rid).model_copy(
            update={"state": ActionState.PROPOSED, "revision": 1}
        )
        await store.put_action(proposed, None, [])
    cases = 0
    for rid, conv in (("run_1", "conv_2"), ("run_1", None), ("run_plain", "conv_2")):
        moved = _run(rid, conv=conv, state=RunState.RUNNING, rev=2)
        with pytest.raises(ValueError, match=LINK_CHANGE_REFUSED):
            await store.update_run(moved, 1, [EV])
        cases += 1
        with pytest.raises(ValueError, match=LINK_CHANGE_REFUSED):
            await store.wait_for_approval(_waiting_action(rid), 1, moved, 1, ({}, None), [EV])
        cases += 1
    for rid, conv in (("run_1", "conv_1"), ("run_plain", None)):
        run = await store.get_run("t1", rid)
        assert (run.revision, run.conversation_id, run.state) == (1, conv, RunState.CREATED)
        assert len(await store.list_events("t1", rid)) == 1
        assert (await store.get_action("t1", f"act_{rid}")).state is ActionState.PROPOSED
    assert await _linked(store) == ["run_1"]
    assert await _linked(store, "conv_2") == []
    # The same write with the link unchanged is accepted.
    await store.update_run(_run("run_1", state=RunState.RUNNING, rev=2), 1, [EV])
    print(f"conversation change refusals: {cases}")
    assert cases == 6


async def test_duplicate_run_id_admission_conflicts(store: Any) -> None:
    """Admitting a run id that exists is a ``ConcurrencyConflict`` on both stores and
    writes nothing, not even the idempotency record (review A1-7)."""
    await store.create_conversation(_conv())
    await store.create_run(_run("run_x", conv=None), [EV])
    cases = 0
    with pytest.raises(ConcurrencyConflict):
        await store.create_run_idempotent(_run("run_x", conv=None), [EV], {}, ACTOR, "k_a", "d")
    cases += 1
    with pytest.raises(ConcurrencyConflict):
        await _start(store, "run_x", "k_b", 1)
    cases += 1
    for key in ("k_a", "k_b"):
        assert await store.lookup_idempotent("t1", ACTOR, key) is None
    assert (await store.get_run("t1", "run_x")).conversation_id is None
    assert len(await store.list_events("t1", "run_x")) == 1
    assert (await store.get_conversation("t1", "u1", "conv_1")).revision == 1
    print(f"duplicate run id cases: {cases}")
    assert cases == 2


@pytest.mark.skipif(not DSN, reason="E_AGENT_TEST_PG_DSN unset")
async def test_runs_conversation_id_column_matches_record() -> None:
    """Migration 0007's ``runs.conversation_id`` is written from the record at every insert
    site: linked runs come only from ``create_run_in_conversation``, unlinked ones from
    ``create_run`` and ``create_run_idempotent`` (4c.2 review R1-4). The schema's FK and
    CHECK stay as a backstop behind the port's refusals."""
    pg = await _open_postgres()
    try:
        await pg.create_conversation(_conv())
        await pg.create_conversation(_conv("conv_2"))
        await pg.create_run(_run("run_create", conv=None), [EV])
        await pg.create_run_idempotent(_run("run_idem", conv=None), [EV], {}, ACTOR, "k_i", "d")
        await _start(pg, "run_conv_1", "k_c1", 1)
        await _start(pg, "run_conv_2", "k_c2", 1, conv="conv_2")
        await pg.update_run(_run("run_conv_1", state=RunState.RUNNING, rev=2), 1, [])
        async with pg._pool.connection() as conn:
            cur = await conn.execute(
                "SELECT run_id, conversation_id, record ->> 'conversation_id' FROM runs"
                " WHERE tenant_id = 't1' ORDER BY run_id"
            )
            rows = await cur.fetchall()
        assert rows == [
            ("run_conv_1", "conv_1", "conv_1"),
            ("run_conv_2", "conv_2", "conv_2"),
            ("run_create", None, None),
            ("run_idem", None, None),
        ]
        print(f"conversation_id column cases: {len(rows)}")
        assert len(rows) == 4
    finally:
        await pg.close()
