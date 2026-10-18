"""RunStore conformance: the same behaviour from every implementation (I05)."""

import asyncio
import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import pytest
from e_agent.contracts.action import ActionRecord, ActionState
from e_agent.contracts.digest import CanonicalizationError
from e_agent.contracts.events import RunEventType
from e_agent.contracts.plan import ActionPlan, ActionProposal, LineageRef, PlannedStep
from e_agent.contracts.run import RunRecord, RunState
from e_agent.contracts.step import StepKind, StepRecord, StepStatus
from e_agent.kernel.memory_store import InMemoryRunStore
from e_agent.sdk.store import (
    ConcurrencyConflict,
    ConnectionBusy,
    DuplicateOperation,
    NotFound,
    actor_scope,
)

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
    op: str = "op_1",
    tenant: str = "t1",
    conn: str = "c",
) -> ActionRecord:
    return ActionRecord(
        action_id=aid,
        tenant_id=tenant,
        run_id=run_id,
        logical_operation_id=op,
        contract_id="notes.note.create.v1",
        binding_id="b",
        connection_id=conn,
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


async def test_expire_work_kind_is_accepted_by_the_queue(store: Any) -> None:
    await store.create_run(_run(), [(RunEventType.RUN_CREATED, {}, None)])
    payload = {"action_id": "act_1", "requested_at": "2026-10-06T00:00:00+00:00"}
    await store.enqueue_work("t1", "run_1", "expire", payload, "digest-expire-1")
    await store.enqueue_work("t1", "run_1", "expire", payload, "digest-expire-1")  # idempotent
    claim = await store.claim_work("w1")
    assert claim is not None and claim.kind == "expire" and claim.payload == payload
    assert await store.claim_work("w2") is None


async def test_resume_work_kind_is_accepted_by_the_queue(store: Any) -> None:
    """A plan resumes after a crash only as fenced ``resume`` work (ADR 0025 amendment,
    migration 0006); a repeated enqueue of one verified step is one item."""
    await store.create_run(_run(), [(RunEventType.RUN_CREATED, {}, None)])
    payload = {"action_id": "act_1"}
    await store.enqueue_work("t1", "run_1", "resume", payload, "digest-resume-1")
    await store.enqueue_work("t1", "run_1", "resume", payload, "digest-resume-1")  # idempotent
    assert await store.has_pending_work("t1", "run_1")
    claim = await store.claim_work("w1")
    assert claim is not None and claim.kind == "resume" and claim.payload == payload
    assert await store.claim_work("w2") is None
    async with store.work_scope(claim):
        await store.finish_work(claim)
    assert not await store.has_pending_work("t1", "run_1")
    assert await store.claim_work("w2") is None  # one item, not two


async def test_list_events_pages_in_sequence_order(store: Any) -> None:
    await store.create_run(_run(), [(RunEventType.RUN_CREATED, {}, None)])
    await store.update_run(
        _run(rev=2),
        1,
        [
            (RunEventType.RUN_STATE_CHANGED, {"n": 2}, None),
            (RunEventType.RUN_STATE_CHANGED, {"n": 3}, None),
        ],
    )
    first = await store.list_events("t1", "run_1", 0, limit=2)
    assert [e.sequence for e in first] == [1, 2]
    rest = await store.list_events("t1", "run_1", first[-1].sequence, limit=2)
    assert [e.sequence for e in rest] == [3]
    assert [e.sequence for e in await store.list_events("t1", "run_1")] == [1, 2, 3]


@pytest.mark.parametrize(
    "busy_state", [ActionState.RESERVED, ActionState.DISPATCHING, ActionState.UNKNOWN]
)
async def test_reservation_is_refused_while_the_connection_has_an_unresolved_write(
    store: Any, busy_state: ActionState
) -> None:
    await store.create_run(_run("run_1"), [(RunEventType.RUN_CREATED, {}, None)])
    await store.create_run(_run("run_2"), [(RunEventType.RUN_CREATED, {}, None)])
    in_flight = _action("act_1", rev=1, state=busy_state, run_id="run_1", op="op_1")
    await store.put_action(in_flight, None, [])
    proposed = _action("act_2", rev=1, state=ActionState.PROPOSED, run_id="run_2", op="op_2")
    await store.put_action(proposed, None, [])
    reserved = proposed.model_copy(update={"state": ActionState.RESERVED, "revision": 2})
    with pytest.raises(ConnectionBusy):
        await store.reserve_operation(reserved, 1, [])
    # The earlier write resolves; the reservation now succeeds.
    resolved = in_flight.model_copy(update={"state": ActionState.COMMITTED, "revision": 2})
    await store.put_action(resolved, 1, [])
    assert (await store.reserve_operation(reserved, 1, [])).state is ActionState.RESERVED


@pytest.mark.parametrize("scope", ["other_connection", "other_tenant"])
async def test_busy_row_on_another_connection_or_tenant_does_not_refuse(
    store: Any, scope: str
) -> None:
    other_tenant = "t2" if scope == "other_tenant" else "t1"
    other_conn = "c2" if scope == "other_connection" else "c"
    await store.create_run(_run("run_1"), [(RunEventType.RUN_CREATED, {}, None)])
    await store.create_run(
        _run("run_2", tenant=other_tenant), [(RunEventType.RUN_CREATED, {}, None)]
    )
    busy = _action(
        "act_1",
        state=ActionState.DISPATCHING,
        run_id="run_2",
        op="op_9",
        tenant=other_tenant,
        conn=other_conn,
    )
    await store.put_action(busy, None, [])
    proposed = _action("act_2", state=ActionState.PROPOSED, run_id="run_1", op="op_2")
    await store.put_action(proposed, None, [])
    reserved = proposed.model_copy(update={"state": ActionState.RESERVED, "revision": 2})
    assert (await store.reserve_operation(reserved, 1, [])).state is ActionState.RESERVED


def _step_record(
    sequence: int,
    step_id: str = "st_1",
    status: StepStatus = StepStatus.STARTED,
    tenant: str = "t1",
    run_id: str = "run_1",
) -> StepRecord:
    return StepRecord(
        tenant_id=tenant,
        run_id=run_id,
        step_id=step_id,
        sequence=sequence,
        kind=StepKind.DISPATCH,
        status=status,
        started_at=T0,
    )


def _plan(plan_id: str = "plan_1", task_version: str = "1") -> ActionPlan:
    ref = LineageRef(step_id="s1", path="/partner_id")

    def proposal(**arguments: Any) -> ActionProposal:
        return ActionProposal(
            contract_id="notes.note.create.v1", connection_id="c", arguments=arguments
        )

    return ActionPlan(
        plan_id=plan_id,
        task_id="purchase_order",
        task_version=task_version,
        steps=(
            PlannedStep(step_id="s1", proposal=proposal(text="hi")),
            PlannedStep(
                step_id="s2",
                proposal=proposal(vendor=ref, lines=[{"ref": ref, "qty": "1"}]),
                depends_on=("s1",),
            ),
        ),
    )


async def test_put_and_get_plan(store: Any) -> None:
    await store.create_run(_run(), [EV])
    plan = _plan()
    step = _step_record(0)
    await store.put_plan("t1", "run_1", plan, [EV, step])
    got = await store.get_plan("t1", "plan_1")
    assert got == plan
    assert isinstance(got.steps[1].proposal.arguments["vendor"], LineageRef)
    assert isinstance(got.steps[1].proposal.arguments["lines"][0]["ref"], LineageRef)
    assert len(await store.list_events("t1", "run_1")) == 2
    assert await store.list_steps("t1", "run_1") == [step]
    # A plan is never overwritten; the refused put leaves no events or steps.
    with pytest.raises(ConcurrencyConflict):
        await store.put_plan("t1", "run_1", _plan(task_version="2"), [EV, _step_record(1)])
    assert await store.get_plan("t1", "plan_1") == plan
    assert len(await store.list_events("t1", "run_1")) == 2
    assert await store.list_steps("t1", "run_1") == [step]
    # A refused step in the batch leaves no plan row either (2c.3 review R-3).
    with pytest.raises(ConcurrencyConflict):
        await store.put_plan("t1", "run_1", _plan("plan_3"), [EV, _step_record(0, step_id="st_9")])
    with pytest.raises(NotFound):
        await store.get_plan("t1", "plan_3")
    assert len(await store.list_events("t1", "run_1")) == 2
    with pytest.raises(NotFound):
        await store.put_plan("t1", "run_missing", _plan("plan_2"), [])
    with pytest.raises(NotFound):
        await store.get_plan("t1", "plan_2")


OUTSIDE_PROFILE: dict[str, object] = {
    # A JSON-mode dump would coerce this key to `'$lineage'`, minting a placeholder on read
    # (Codex review C-1).
    "bytes lineage key": {b"$lineage": {"step": "s1", "path": "/partner_id"}},
    "int key": {1: "a"},
    "number": 4,
    "set": {"x", "y"},
}


async def test_put_plan_refuses_arguments_outside_the_digest_profile(store: Any) -> None:
    await store.create_run(_run(), [EV])
    cases = 0
    for name, value in OUTSIDE_PROFILE.items():
        plan = _plan(f"plan_{cases}")
        plan.steps[1].proposal.arguments["lines"].append({"x": value})
        with pytest.raises(CanonicalizationError):
            await store.put_plan("t1", "run_1", plan, [_step_record(cases)])
        with pytest.raises(NotFound):
            await store.get_plan("t1", plan.plan_id)
        assert len(await store.list_events("t1", "run_1")) == 1, name
        assert await store.list_steps("t1", "run_1") == [], name
        cases += 1
    print(f"put_plan profile cases: {cases}")
    assert cases == len(OUTSIDE_PROFILE) == 4


async def test_steps_commit_with_events_atomically(store: Any) -> None:
    started = _step_record(0)
    succeeded = _step_record(1, status=StepStatus.SUCCEEDED)
    await store.create_run(_run(), [EV, started])
    first = ({"schema": "s", "turn": 1}, None)
    await store.update_run(_run(rev=2), 1, [EV, succeeded], continuation=first)
    # A step-only batch commits too.
    await store.put_action(_action(), None, [_step_record(2, step_id="st_2")])
    assert [s.sequence for s in await store.list_steps("t1", "run_1")] == [0, 1, 2]
    before = await store.list_steps("t1", "run_1")
    # Valid events, a valid step, then a step whose sequence does not increase.
    bad_batch = [EV, _step_record(3, step_id="st_3"), EV, _step_record(2, step_id="st_4")]
    with pytest.raises(ConcurrencyConflict):
        await store.update_run(
            _run(rev=3),
            2,
            bad_batch,
            continuation=({"schema": "s", "turn": 2}, {"bad": True}),
            work=("input", {}, "request-x"),
        )
    assert (await store.get_run("t1", "run_1")).revision == 2
    assert len(await store.list_events("t1", "run_1")) == 2
    assert await store.list_steps("t1", "run_1") == before
    assert await store.load_continuation("t1", "run_1") == first
    assert not await store.has_pending_work("t1", "run_1")
    with pytest.raises(ConcurrencyConflict):
        await store.put_action(_action("act_2", op="op_2"), None, [EV, _step_record(1)])
    with pytest.raises(NotFound):
        await store.get_action("t1", "act_2")
    assert len(await store.list_events("t1", "run_1")) == 2
    assert await store.list_steps("t1", "run_1") == before


async def test_step_sequence_is_monotonic_per_run(store: Any) -> None:
    await store.create_run(_run("run_1"), [EV])
    await store.create_run(_run("run_2"), [EV])
    revision = 1

    async def write(*steps: StepRecord, run_id: str = "run_1") -> None:
        nonlocal revision
        rev = revision if run_id == "run_1" else 1
        await store.update_run(_run(run_id, rev=rev + 1), rev, [EV, *steps])
        if run_id == "run_1":
            revision += 1

    # A status change appends a new state row with the same step id.
    await write(_step_record(0, "st_1"), _step_record(1, "st_1", StepStatus.SUCCEEDED))
    await write(_step_record(5, "st_2"))
    for refused in (
        (_step_record(5, "st_3"),),
        (_step_record(3, "st_3"),),
        (_step_record(6, "st_3"), _step_record(6, "st_4")),
        (_step_record(7, "st_3"), _step_record(6, "st_4")),
    ):
        with pytest.raises(ConcurrencyConflict):
            await write(*refused)
    steps = await store.list_steps("t1", "run_1")
    assert [(s.step_id, s.sequence, s.status) for s in steps] == [
        ("st_1", 0, StepStatus.STARTED),
        ("st_1", 1, StepStatus.SUCCEEDED),
        ("st_2", 5, StepStatus.STARTED),
    ]
    assert (await store.get_run("t1", "run_1")).revision == 3
    # Sequences are per run: another run starts at 0.
    await write(_step_record(0, "st_1", run_id="run_2"), run_id="run_2")
    assert [s.sequence for s in await store.list_steps("t1", "run_2")] == [0]


async def test_tenant_scope_on_plans_and_steps(store: Any) -> None:
    await store.create_run(_run(), [EV])
    await store.create_run(_run(tenant="t2"), [EV])
    plan = _plan()
    await store.put_plan("t1", "run_1", plan, [_step_record(0)])
    with pytest.raises(NotFound):
        await store.get_plan("t2", "plan_1")
    assert await store.list_steps("t2", "run_1") == []
    # The same plan id in another tenant is a different plan.
    other = _plan(task_version="2")
    await store.put_plan("t2", "run_1", other, [_step_record(0, tenant="t2")])
    assert await store.get_plan("t2", "plan_1") == other
    assert await store.get_plan("t1", "plan_1") == plan
    assert [s.tenant_id for s in await store.list_steps("t2", "run_1")] == ["t2"]
    # A step for another tenant or run is refused in the batch of this run.
    for foreign in (_step_record(1, tenant="t2"), _step_record(1, run_id="run_2")):
        with pytest.raises(ValueError, match="step"):
            await store.update_run(_run(rev=2), 1, [EV, foreign])
    assert (await store.get_run("t1", "run_1")).revision == 1
    assert [s.tenant_id for s in await store.list_steps("t1", "run_1")] == ["t1"]
    with pytest.raises(NotFound):
        await store.put_plan("t3", "run_1", _plan("plan_3"), [])


async def test_existing_rows_have_null_plan_id(store: Any) -> None:
    await store.create_run(_run(), [EV])
    await store.put_plan("t1", "run_1", _plan(), [])
    await store.put_action(_action(), None, [])
    linked = _action("act_2", op="op_2").model_copy(update={"plan_id": "plan_1", "step_index": 1})
    await store.put_action(linked, None, [])
    moved = linked.model_copy(update={"state": ActionState.VALIDATED, "revision": 2})
    await store.put_action(moved, 1, [])
    plain = await store.get_action("t1", "act_1")
    assert (plain.plan_id, plain.step_index) == (None, None)
    got = await store.get_action("t1", "act_2")
    assert (got.plan_id, got.step_index, got.state) == ("plan_1", 1, ActionState.VALIDATED)
    pool = getattr(store, "_pool", None)
    if pool is not None:  # Postgres: the indexed columns follow the record.
        async with pool.connection() as conn:
            cur = await conn.execute(
                "SELECT action_id, plan_id, step_index FROM actions"
                " WHERE tenant_id = %s ORDER BY action_id",
                ("t1",),
            )
            rows = await cur.fetchall()
        assert rows == [("act_1", None, None), ("act_2", "plan_1", 1)]


async def test_action_plan_link_refused_for_unknown_plan(store: Any) -> None:
    """An action's ``plan_id`` must name a stored plan of its tenant and run (2c.3 review
    R-5); a refused write leaves no action and no events. The check is the store's."""
    await store.create_run(_run(), [EV])
    await store.create_run(_run("run_2"), [EV])
    await store.put_plan("t1", "run_2", _plan("plan_other_run"), [])
    await store.create_run(_run(tenant="t2"), [EV])
    await store.put_plan("t2", "run_1", _plan("plan_other_tenant"), [])
    cases = 0
    for plan_id in ("plan_missing", "plan_other_run", "plan_other_tenant"):
        linked = _action(f"act_{plan_id}", op=f"op_{plan_id}").model_copy(
            update={"plan_id": plan_id, "step_index": 0}
        )
        with pytest.raises(ValueError, match="plan"):
            await store.put_action(linked, None, [EV])
        with pytest.raises(NotFound):
            await store.get_action("t1", linked.action_id)
        cases += 1
    # An update that adds an unknown plan link to an existing action is refused too.
    await store.put_action(_action(), None, [])
    moved = _action(rev=2, state=ActionState.VALIDATED).model_copy(
        update={"plan_id": "plan_missing", "step_index": 0}
    )
    with pytest.raises(ValueError, match="plan"):
        await store.put_action(moved, 1, [EV])
    cases += 1
    assert (await store.get_action("t1", "act_1")).revision == 1
    assert [e.type for e in await store.list_events("t1", "run_1")] == [EV[0]]
    # A link to the run's own plan is accepted.
    await store.put_plan("t1", "run_1", _plan(), [])
    ok = moved.model_copy(update={"plan_id": "plan_1"})
    assert (await store.put_action(ok, 1, [])).plan_id == "plan_1"
    print(f"plan link refusal cases: {cases}")
    assert cases == 4
