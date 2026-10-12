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
from e_agent.sdk.store import ConcurrencyConflict, DuplicateOperation, NotFound, actor_scope

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


async def test_idempotency_claims(store: Any) -> None:
    assert await store.claim_idempotency("t1", "u", "k1", "d1", "run_a") == ("run_a", "d1")
    assert await store.claim_idempotency("t1", "u", "k1", "d2", "run_b") == ("run_a", "d1")
    assert await store.claim_idempotency("t1", "v", "k1", "d1", "run_c") == ("run_c", "d1")


async def test_run_checkpoint_is_atomic_with_events_and_cas(store: Any) -> None:
    await store.create_run(_run(), [EV])
    first = ({"schema": "test", "pending_action_id": "act-1"}, {"turn": 1})
    await store.update_run(_run(rev=2), 1, [EV], continuation=first)
    assert await store.load_continuation("t1", "run_1") == first
    with pytest.raises(ConcurrencyConflict):
        await store.update_run(
            _run(rev=3), 1, [EV], continuation=({"pending_action_id": "wrong"}, None)
        )
    assert await store.load_continuation("t1", "run_1") == first
    assert len(await store.list_events("t1", "run_1")) == 2


async def test_request_admission_includes_run_checkpoint_and_start_work(store: Any) -> None:
    checkpoint = {"schema": "fixture", "data": {"task": "x"}}
    result = await store.create_run_idempotent(_run(), [EV], checkpoint, "u", "request-1", "d1")
    assert result == ("run_1", "d1")
    assert await store.load_continuation("t1", "run_1") == (checkpoint, None)
    again = await store.create_run_idempotent(_run("unused"), [EV], {}, "u", "request-1", "d2")
    assert again == ("run_1", "d1")
    with pytest.raises(NotFound):
        await store.get_run("t1", "unused")
    claim = await store.claim_work("worker-1")
    assert claim and claim.run_id == "run_1" and claim.kind == "start"
    assert await store.claim_work("worker-2") is None
    await store.finish_work(claim)
    assert not await store.has_pending_work("t1", "run_1")


async def test_parallel_claimers_cannot_own_two_jobs_for_one_run(store: Any) -> None:
    await store.create_run(_run(), [EV])
    await store.enqueue_work("t1", "run_1", "input", {}, "request-1")
    await store.enqueue_work("t1", "run_1", "input", {}, "request-2")
    claims = await asyncio.gather(store.claim_work("worker-1"), store.claim_work("worker-2"))
    owned = [c for c in claims if c is not None]
    assert len(owned) == 1
    await store.finish_work(owned[0])
    assert await store.claim_work("worker-3") is not None


async def test_expired_worker_cannot_commit_or_overwrite_continuation(store: Any) -> None:
    await store.create_run(_run(), [EV])
    await store.enqueue_work("t1", "run_1", "input", {}, "request-1")
    old = await store.claim_work("worker-old", lease_seconds=1)
    assert old is not None
    await asyncio.sleep(1.05)
    new = await store.claim_work("worker-new")
    assert new is not None and new.fence == old.fence + 1
    assert not await store.renew_work(old)
    with pytest.raises(ConcurrencyConflict):
        async with store.work_scope(old):
            await store.update_run(_run(rev=2), 1, [EV], continuation=({"bad": True}, None))
    assert await store.load_continuation("t1", "run_1") is None
    assert len(await store.list_events("t1", "run_1")) == 1
    async with store.work_scope(new):
        await store.update_run(_run(rev=2), 1, [EV], continuation=({"owner": "new"}, None))
    assert await store.load_continuation("t1", "run_1") == ({"owner": "new"}, None)


async def test_work_replay_requires_the_exact_admitted_payload(store: Any) -> None:
    await store.create_run(_run(), [EV])
    await store.enqueue_work("t1", "run_1", "decide", {"decision": "approved"}, "approval-slot")
    await store.enqueue_work("t1", "run_1", "decide", {"decision": "approved"}, "approval-slot")
    with pytest.raises(ConcurrencyConflict):
        await store.enqueue_work("t1", "run_1", "decide", {"decision": "rejected"}, "approval-slot")
    claim = await store.claim_work("worker")
    assert claim is not None and claim.payload == {"decision": "approved"}
    await store.finish_work(claim)
    assert await store.claim_work("worker") is None


async def test_approval_and_action_transition_rollback_together(store: Any) -> None:
    from e_agent.contracts.approval import ApprovalDecision, ApprovalRecord

    await store.create_run(_run(), [EV])
    await store.put_action(_action(state=ActionState.AWAITING_APPROVAL), None, [])
    approval = ApprovalRecord(
        approval_id="approval-1",
        tenant_id="t1",
        run_id="run_1",
        action_id="act_1",
        action_digest="d",
        actor_id="approver",
        decision=ApprovalDecision.APPROVED,
        policy_version="1",
        issued_at=T0,
        expires_at=T0,
    )
    with pytest.raises(ConcurrencyConflict):
        await store.record_approval(
            approval, [EV], action=_action(rev=2, state=ActionState.APPROVED), expected_revision=7
        )
    assert await store.list_approvals("t1", "act_1") == []
    assert (await store.get_action("t1", "act_1")).state == ActionState.AWAITING_APPROVAL
    await store.record_approval(
        approval, [EV], action=_action(rev=2, state=ActionState.APPROVED), expected_revision=1
    )
    assert (await store.get_action("t1", "act_1")).state == ActionState.APPROVED
    assert len(await store.list_approvals("t1", "act_1")) == 1


async def test_events_record_the_current_actor(store: Any) -> None:
    await store.create_run(_run(), [(RunEventType.RUN_CREATED, {}, None)])
    with actor_scope("principal:alice"):
        await store.update_run(_run(rev=2), 1, [(RunEventType.RUN_STATE_CHANGED, {}, None)])
    events = await store.list_events("t1", "run_1")
    assert [e.actor for e in events] == ["system:kernel", "principal:alice"]
