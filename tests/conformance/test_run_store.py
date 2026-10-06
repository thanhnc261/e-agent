"""RunStore conformance: the same behaviour from every implementation (I05)."""

import asyncio
import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import pytest
from e_agent.contracts.action import ActionRecord, ActionState
from e_agent.contracts.events import RunEventType
from e_agent.contracts.run import RunRecord, RunState
from e_agent.kernel.memory_store import InMemoryRunStore
from e_agent.sdk.store import ConcurrencyConflict, DuplicateOperation, NotFound

DSN = os.environ.get("E_AGENT_TEST_PG_DSN")
KINDS = ["memory"] + (["postgres"] if DSN else [])
T0 = datetime(2026, 10, 6, tzinfo=UTC)


@pytest.fixture(params=KINDS)
async def store(request: pytest.FixtureRequest) -> AsyncIterator[Any]:
    if request.param == "memory":
        yield InMemoryRunStore()
        return
    from e_agent.adapters.postgres import PostgresRunStore, apply_migrations

    assert DSN
    await apply_migrations(DSN)
    pg = await PostgresRunStore.open(DSN)
    await pg.truncate_for_tests()
    try:
        yield pg
    finally:
        await pg.close()


def _run(rid: str = "run_1", tenant: str = "t1", rev: int = 1) -> RunRecord:
    return RunRecord(
        run_id=rid,
        tenant_id=tenant,
        requester_id="u",
        task="x",
        state=RunState.RUNNING,
        revision=rev,
        logical_operation_id="op_1",
        created_at=T0,
    )


def _action(
    aid: str = "act_1",
    rev: int = 1,
    state: ActionState = ActionState.PROPOSED,
    run_id: str = "run_1",
) -> ActionRecord:
    return ActionRecord(
        action_id=aid,
        tenant_id="t1",
        run_id=run_id,
        logical_operation_id="op_1",
        contract_id="notes.note.create.v1",
        binding_id="b",
        connection_id="c",
        connection_version=1,
        credential_subject="c@1/s",
        arguments={"text": "hi", "n": "1"},
        digest="d",
        state=state,
        revision=rev,
    )


EV = (RunEventType.RUN_STATE_CHANGED, {"to": "RUNNING"}, None)
pytestmark = pytest.mark.asyncio


async def test_run_round_trip_and_cas(store: Any) -> None:
    await store.create_run(_run(), [EV])
    assert (await store.get_run("t1", "run_1")).revision == 1
    await store.update_run(_run(rev=2), 1, [EV])
    with pytest.raises(ConcurrencyConflict):
        await store.update_run(_run(rev=2), 1, [EV])
    with pytest.raises(ConcurrencyConflict):
        await store.update_run(_run(rev=5), 2, [])


async def test_failed_update_appends_no_events(store: Any) -> None:
    await store.create_run(_run(), [EV])
    with pytest.raises(ConcurrencyConflict):
        await store.update_run(_run(rev=3), 7, [EV, EV])
    assert len(await store.list_events("t1", "run_1")) == 1


async def test_events_are_gapless_and_cursorable(store: Any) -> None:
    await store.create_run(_run(), [EV, EV])
    await store.update_run(_run(rev=2), 1, [EV])
    events = await store.list_events("t1", "run_1")
    assert [e.sequence for e in events] == [1, 2, 3]
    assert [e.sequence for e in await store.list_events("t1", "run_1", after_sequence=2)] == [3]


async def test_tenant_isolation(store: Any) -> None:
    await store.create_run(_run(), [EV])
    with pytest.raises(NotFound):
        await store.get_run("t2", "run_1")
    assert await store.list_events("t2", "run_1") == []


async def test_action_cas_and_unique_reservation(store: Any) -> None:
    await store.create_run(_run(), [EV])
    await store.put_action(_action(), None, [])
    with pytest.raises(ConcurrencyConflict):
        await store.put_action(_action(), None, [])
    await store.put_action(_action(rev=2, state=ActionState.VALIDATED), 1, [])
    reserved = _action(rev=3, state=ActionState.RESERVED)
    await store.reserve_operation(reserved, 2, [EV])
    other = _action("act_2")
    await store.put_action(other, None, [])
    with pytest.raises(DuplicateOperation):
        await store.reserve_operation(_action("act_2", rev=2, state=ActionState.RESERVED), 1, [EV])
    assert (await store.get_action("t1", "act_2")).state is ActionState.PROPOSED


async def test_concurrent_reservations_admit_exactly_one(store: Any) -> None:
    await store.create_run(_run(), [EV])
    for aid in ("a1", "a2", "a3", "a4"):
        await store.put_action(_action(aid), None, [])

    async def attempt(aid: str) -> bool:
        try:
            await store.reserve_operation(_action(aid, rev=2, state=ActionState.RESERVED), 1, [EV])
            return True
        except DuplicateOperation:
            return False

    results = await asyncio.gather(*(attempt(a) for a in ("a1", "a2", "a3", "a4")))
    assert sum(results) == 1


async def test_continuation_round_trip(store: Any) -> None:
    await store.create_run(_run(), [EV])
    assert await store.load_continuation("t1", "run_1") is None
    await store.save_continuation("t1", "run_1", {"schema": "s", "data": {"k": "v"}}, None)
    await store.save_continuation("t1", "run_1", {"schema": "s", "data": {"k": "w"}}, {"d": "1"})
    assert await store.load_continuation("t1", "run_1") == (
        {"schema": "s", "data": {"k": "w"}},
        {"d": "1"},
    )


async def test_unfinished_runs(store: Any) -> None:
    await store.create_run(_run("r1"), [EV])
    await store.create_run(_run("r2"), [EV])
    done = _run("r2", rev=2).model_copy(update={"state": RunState.SUCCEEDED})
    await store.update_run(done, 1, [])
    assert [r.run_id for r in await store.list_unfinished_runs()] == ["r1"]


async def test_writer_lock_serializes(store: Any) -> None:
    order: list[str] = []

    async def worker(name: str) -> None:
        async with store.writer_lock("t1", "c"):
            order.append(f"{name}-in")
            await asyncio.sleep(0.05)
            order.append(f"{name}-out")

    await asyncio.gather(worker("a"), worker("b"))
    assert order in (["a-in", "a-out", "b-in", "b-out"], ["b-in", "b-out", "a-in", "a-out"])
