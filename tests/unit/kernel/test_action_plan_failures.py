"""Partial failure of a multi-step plan (Task 2c.8, ADR 0025, target §6.4.6, ADR 0029).

After the plan's first reservation nothing falls back to today's single-action loop. A step
that fails keeps the earlier steps committed and verified; a step whose outcome is UNKNOWN
stops the remainder and sends the run to reconciliation, never to a re-send (ENG-TRUST-5,
PR-18); a lineage value that is not in the earlier step's verified read-back stops the plan
with ``PLAN_LINEAGE_REJECTED``. A step's reason code is the code the same failure has on a
1-step run. The evidence bundle lists the plan and each step's status. Both stores run
through `run_store` (ENG-STORE-1); no plugin is imported.
"""

import json
from collections.abc import Callable
from typing import Any

import pytest
from e_agent.contracts.action import ActionState
from e_agent.contracts.approval import ApprovalDecision
from e_agent.contracts.capability import Idempotency
from e_agent.contracts.connection import ConnectionDescriptor, ConnectionOwnership
from e_agent.contracts.context import Budgets
from e_agent.contracts.events import RunEventType
from e_agent.contracts.features import FeatureMode, Features
from e_agent.contracts.outcome import OutcomeReport, OutcomeStatus
from e_agent.contracts.plan import ActionPlan, ActionProposal, LineageRef, PlannedStep
from e_agent.contracts.run import ReasonCode, RunState
from e_agent.kernel.evidence import build_evidence, classify
from e_agent.sdk.store import ConnectionBusy

from .conftest import (
    BINDINGS,
    CONN,
    CREATE,
    FIRST,
    FOLLOW_UP,
    NOTE_INPUT,
    NOTES_TASK,
    PLAN_BUDGETS,
    TENANT,
    Kernel,
    NotesDriver,
    NotesPlanDriver,
    two_step_plan,
)

MakeKernel = Callable[..., Kernel]
ON = Features(execution_ir=FeatureMode.ON)
SCHEMAS = {"c": NOTE_INPUT, "p": NOTE_INPUT}
THIRD = "third"
THREE_WRITES = Budgets(max_admitted_writes=3)


def three_step_plan() -> ActionPlan:
    """`two_step_plan` and a third note whose ``parent`` is the follow-up's verified key."""
    plan = two_step_plan()
    third = PlannedStep(
        step_id=THIRD,
        proposal=ActionProposal(
            contract_id=CREATE.contract_id,
            connection_id=CONN,
            arguments={"text": "third", "parent": LineageRef(step_id=FOLLOW_UP, path="/key")},
        ),
        depends_on=(FOLLOW_UP,),
    )
    return plan.model_copy(update={"steps": (*plan.steps, third)})


def _plan_kernel(make_kernel: MakeKernel, *, steps: int = 2, **kw: Any) -> Kernel:
    kw.setdefault("features", ON)
    kw.setdefault("budgets", THREE_WRITES if steps == 3 else PLAN_BUDGETS)
    plan = three_step_plan() if steps == 3 else two_step_plan()
    kw.setdefault("driver", NotesPlanDriver(plan=plan))
    kw.setdefault("input_schemas", SCHEMAS)
    return make_kernel(**kw)


async def _start(k: Kernel) -> Any:
    return await k.coordinator.start_run(
        k.requester, "write standup note", k.scope, task_kind=NOTES_TASK.task_id
    )


async def _decide(k: Kernel, run_id: str) -> Any:
    pres = await k.coordinator.pending_approval(TENANT, run_id)
    return await k.coordinator.decide(
        actor=k.approver,
        run_id=run_id,
        action_id=pres.action_id,
        action_digest=pres.digest,
        expected_run_revision=pres.run_revision,
        decision=ApprovalDecision.APPROVED,
    )


async def _actions(k: Kernel, run_id: str) -> list[Any]:
    actions = await k.store.list_actions(TENANT, run_id)
    return sorted(actions, key=lambda a: a.step_index if a.step_index is not None else -1)


async def _of(k: Kernel, run_id: str, kind: RunEventType) -> list[Any]:
    return [e for e in await k.store.list_events(TENANT, run_id) if e.type is kind]


async def _reserved(k: Kernel, run_id: str) -> list[str | None]:
    return [e.action_id for e in await _of(k, run_id, RunEventType.ACTION_RESERVED)]


async def _rules(k: Kernel, run_id: str) -> set[str]:
    return {
        f["rule_id"]
        for e in await _of(k, run_id, RunEventType.VALIDATION_COMPLETED)
        for f in e.payload.get("findings", [])
    }


async def _bundle(k: Kernel, run_id: str) -> dict[str, Any]:
    return await build_evidence(
        k.store, TENANT, run_id, environment="fixture", versions={}, features=ON
    )


async def _step_statuses(k: Kernel, run_id: str) -> list[str]:
    return [s["status"] for s in (await _bundle(k, run_id))["plan"]["steps"]]


def _fail_at(k: Kernel, index: int | None, mode: str) -> None:
    """The backend fails in ``mode`` (`NotesBackend.fail_mode`) for the action at step
    ``index`` only; ``None`` is an unlinked action (a run in ``off``)."""
    execute = k.backend.execute

    async def failing(ctx: Any, binding: Any, action: Any, attempt: int) -> Any:
        k.backend.fail_mode = mode if action.step_index == index else None
        try:
            return await execute(ctx, binding, action, attempt)
        finally:
            k.backend.fail_mode = None

    k.backend.execute = failing  # type: ignore[method-assign]


def _fail_verification_at(k: Kernel, index: int | None) -> None:
    """The read-back disagrees for the action at step ``index`` only."""
    verify = k.verifier.verify

    async def failing(ctx: Any, action: Any, receipt: Any, reader: Any) -> OutcomeReport:
        report = await verify(ctx, action, receipt, reader)
        if action.step_index != index:
            return report
        return report.model_copy(update={"status": OutcomeStatus.FAILED, "verified_values": None})

    k.verifier.verify = failing  # type: ignore[method-assign]


def _after_first_verified(k: Kernel, then: Callable[[], None]) -> None:
    """Run ``then`` right after step 1's read-back, before step 2 starts."""
    verify = k.verifier.verify

    async def wrapped(ctx: Any, action: Any, receipt: Any, reader: Any) -> OutcomeReport:
        report = await verify(ctx, action, receipt, reader)
        if action.step_index == 0:
            then()
        return report

    k.verifier.verify = wrapped  # type: ignore[method-assign]


# -- no fallback after the first reservation (ENG-TOGGLE-2, PR-22) ------------------------
@pytest.mark.parametrize(
    "failure", ["step-one-rejected", "step-two-rejected", "step-two-unknown", "step-two-stale"]
)
async def test_no_fallback_after_first_reservation(make_kernel: MakeKernel, failure: str) -> None:
    """Whatever stops a plan after its first reservation, the run fails closed or goes to
    reconciliation: no ``feature.fallback``, no driver turn, no other plan and no unlinked
    action on today's path."""
    k = _plan_kernel(make_kernel)
    if failure == "step-one-rejected":
        _fail_at(k, 0, "reject")
    elif failure == "step-two-rejected":
        _fail_at(k, 1, "reject")
    elif failure == "step-two-unknown":
        _fail_at(k, 1, "timeout")
    else:
        _after_first_verified(k, lambda: setattr(k.validator, "bundle", "notes@2"))
    run = await _start(k)
    driver_calls = k.driver.calls
    run = await _decide(k, run.run_id)
    assert run.state in {RunState.FAILED, RunState.NEEDS_RECONCILIATION}
    assert await _of(k, run.run_id, RunEventType.FEATURE_FALLBACK) == []
    assert k.driver.calls == driver_calls  # the driver never proposes again
    assert len(await _of(k, run.run_id, RunEventType.IR_PLAN_COMPILED)) == 1
    actions = await _actions(k, run.run_id)
    assert all(a.plan_id == actions[0].plan_id is not None for a in actions)
    assert len(await _reserved(k, run.run_id)) >= 1


# -- a failed step keeps the earlier ones ------------------------------------------------
@pytest.mark.parametrize(
    ("failure", "code"),
    [("reject", ReasonCode.PROVIDER_ERROR), ("verification", ReasonCode.VERIFICATION_FAILED)],
)
async def test_step_failure_keeps_verified_steps_and_reports_remainder(
    make_kernel: MakeKernel, failure: str, code: ReasonCode
) -> None:
    """Step 2 of 3 fails (the provider rejects it, or its read-back disagrees): the run ends
    with today's code, step 1 stays committed and verified, step 3 never starts, and the
    evidence lists the steps as verified, failed and unstarted."""
    k = _plan_kernel(make_kernel, steps=3)
    if failure == "reject":
        _fail_at(k, 1, "reject")
    else:
        _fail_verification_at(k, 1)
    run = await _start(k)
    run = await _decide(k, run.run_id)
    assert (run.state, run.reason_code) == (RunState.FAILED, code)
    first, second = await _actions(k, run.run_id)
    assert first.state is ActionState.VERIFIED
    assert second.state is (
        ActionState.FAILED if failure == "reject" else ActionState.VERIFICATION_FAILED
    )
    assert first.logical_operation_id in k.backend.notes  # the committed effect stays
    assert await _reserved(k, run.run_id) == [first.action_id, second.action_id]
    assert k.backend.create_calls == 2
    assert await _step_statuses(k, run.run_id) == ["verified", "failed", "unstarted"]


# -- UNKNOWN stops the remainder ---------------------------------------------------------
async def test_unknown_step_blocks_remaining_steps(make_kernel: MakeKernel) -> None:
    """Step 2 of 3 times out after the provider committed it: the run needs reconciliation
    (``EFFECT_UNKNOWN``, as on a 1-step run), step 3 never starts, and recovery leaves the
    UNKNOWN step for reconciliation without sending anything (ENG-TRUST-5)."""
    k = _plan_kernel(make_kernel, steps=3)
    _fail_at(k, 1, "timeout")
    run = await _start(k)
    run = await _decide(k, run.run_id)
    assert (run.state, run.reason_code) == (
        RunState.NEEDS_RECONCILIATION,
        ReasonCode.EFFECT_UNKNOWN,
    )
    first, second = await _actions(k, run.run_id)
    assert (first.state, second.state) == (ActionState.VERIFIED, ActionState.UNKNOWN)
    assert k.backend.create_calls == 2
    assert await _step_statuses(k, run.run_id) == ["verified", "unknown", "unstarted"]

    run = await k.coordinator.recover_run(TENANT, run.run_id)
    assert run.state is RunState.NEEDS_RECONCILIATION
    assert k.backend.create_calls == 2
    assert len(await k.store.list_actions(TENANT, run.run_id)) == 2
    assert await _reserved(k, run.run_id) == [first.action_id, second.action_id]


@pytest.mark.parametrize("expired", [False, True])
async def test_reconciled_step_continues_plan_after_revalidation(
    make_kernel: MakeKernel, expired: bool
) -> None:
    """Reconciliation proves step 2's effect and its read-back verifies it: the plan goes on
    with step 3 only after step 3's revalidation (``NEEDS_RECONCILIATION -> VERIFYING ->
    RUNNING``, target §6.4.6). An approval that expired meanwhile stops it before step 3
    reserves; step 2 is never re-sent."""
    k = _plan_kernel(make_kernel, steps=3)
    _fail_at(k, 1, "timeout")
    run = await _start(k)
    run = await _decide(k, run.run_id)
    assert run.state is RunState.NEEDS_RECONCILIATION
    if expired:
        k.clock.advance(minutes=30)  # past the default 15-minute approval
    run = await k.coordinator.reconcile(k.approver, run.run_id)
    actions = await _actions(k, run.run_id)
    assert [a.step_index for a in actions] == [0, 1, 2]
    assert actions[1].state is ActionState.VERIFIED
    if expired:
        assert (run.state, run.reason_code) == (RunState.FAILED, ReasonCode.STALE)
        assert "approval expired" in (run.reason or "")
        assert actions[2].state is ActionState.BLOCKED
        assert k.backend.create_calls == 2
        assert await _reserved(k, run.run_id) == [a.action_id for a in actions[:2]]
    else:
        assert (run.state, run.reason_code) == (RunState.SUCCEEDED, ReasonCode.VERIFIED)
        assert [a.state for a in actions] == [ActionState.VERIFIED] * 3
        assert k.backend.create_calls == 3
        assert await _reserved(k, run.run_id) == [a.action_id for a in actions]
    changes = [
        (e.payload["from"], e.payload["to"])
        for e in await _of(k, run.run_id, RunEventType.RUN_STATE_CHANGED)
        if "from" in e.payload
    ]
    reconciled = changes.index((RunState.NEEDS_RECONCILIATION, RunState.VERIFYING))
    assert changes[reconciled + 1] == (RunState.VERIFYING, RunState.RUNNING)


async def test_unknown_step_not_resent_even_with_provider_key(make_kernel: MakeKernel) -> None:
    """The notes binding declares ``provider_key``, yet an UNKNOWN step is never re-sent in
    Phase 2 (ADR 0029): neither recovery, a restart's recovery nor a reconciliation that
    finds nothing dispatches it again."""
    k = _plan_kernel(make_kernel)
    binding = k.coordinator._registry.resolve(CREATE.contract_id, CONN)
    assert binding.idempotency is Idempotency.PROVIDER_KEY
    _fail_at(k, 1, "timeout-no-commit")
    run = await _start(k)
    run = await _decide(k, run.run_id)
    assert run.state is RunState.NEEDS_RECONCILIATION
    run = await k.coordinator.recover_run(TENANT, run.run_id)
    assert run.state is RunState.NEEDS_RECONCILIATION
    await k.coordinator.recover()
    run = await k.coordinator.reconcile(k.approver, run.run_id)
    assert run.state is RunState.NEEDS_RECONCILIATION  # nothing found; still unresolved
    first, second = await _actions(k, run.run_id)
    assert second.state is ActionState.UNKNOWN
    assert k.backend.create_calls == 2
    dispatching = await _of(k, run.run_id, RunEventType.ACTION_DISPATCHING)
    assert [(e.action_id, e.payload["attempt"]) for e in dispatching] == [
        (first.action_id, 1),
        (second.action_id, 1),
    ]


async def test_connection_busy_on_step_two_stops_plan(make_kernel: MakeKernel) -> None:
    """The connection holds an unresolved write when step 2 reserves (ADR 0020): the plan
    stops with ``CONNECTION_BUSY``, as a 1-step run does; step 2 never reserves or sends."""
    k = _plan_kernel(make_kernel)
    reserve = k.store.reserve_operation

    async def busy_for_step_two(action: Any, expected: int, events: Any) -> Any:
        if action.step_index == 1:
            raise ConnectionBusy("another write on the connection is unresolved")
        return await reserve(action, expected, events)

    k.store.reserve_operation = busy_for_step_two
    run = await _start(k)
    run = await _decide(k, run.run_id)
    assert (run.state, run.reason_code) == (RunState.FAILED, ReasonCode.CONNECTION_BUSY)
    first, second = await _actions(k, run.run_id)
    # VALIDATED has no BLOCKED transition: the never-reserved step keeps its state.
    assert (first.state, second.state) == (ActionState.VERIFIED, ActionState.VALIDATED)
    assert await _reserved(k, run.run_id) == [first.action_id]
    assert k.backend.create_calls == 1
    assert await _step_statuses(k, run.run_id) == ["verified", "unstarted"]


# -- lineage only from the verified read-back --------------------------------------------
@pytest.mark.parametrize("source", ["missing-path", "no-read-back", "wrong-type"])
async def test_lineage_value_outside_verified_outcome_stops_plan(
    make_kernel: MakeKernel, source: str
) -> None:
    """Step 2's placeholder must resolve from step 1's verified read-back, with the type its
    input schema declares. A pointer the read-back does not hold, a step 1 whose verifier
    read back no values (the value is still in step 1's own arguments), or a value of
    another type stops the plan before step 2 exists: ``PLAN_LINEAGE_REJECTED``, classified
    blocked-by-design (ADR 0025)."""
    path = {"missing-path": "/nope", "no-read-back": "/text", "wrong-type": "/count"}[source]
    k = _plan_kernel(make_kernel, driver=NotesPlanDriver(plan=two_step_plan(path=path)))
    verify = k.verifier.verify

    async def reported(*args: Any) -> OutcomeReport:
        report = await verify(*args)
        if source == "no-read-back":
            return report.model_copy(update={"verified_values": None})
        if source == "wrong-type":
            values = {**(report.verified_values or {}), "count": 3}
            return report.model_copy(update={"verified_values": values})
        return report

    k.verifier.verify = reported  # type: ignore[method-assign]
    run = await _start(k)
    assert run.state is RunState.WAITING_APPROVAL
    run = await _decide(k, run.run_id)
    assert (run.state, run.reason_code) == (RunState.FAILED, ReasonCode.PLAN_LINEAGE_REJECTED)
    assert classify(run.state, run.reason, "fixture", run.reason_code) == (
        "fixture:blocked-by-design"
    )
    assert "KERNEL-PLAN-LINEAGE" in await _rules(k, run.run_id)
    (first,) = await _actions(k, run.run_id)
    assert first.state is ActionState.VERIFIED
    assert await _reserved(k, run.run_id) == [first.action_id]
    assert k.backend.create_calls == 1


# -- reason codes ------------------------------------------------------------------------
@pytest.mark.parametrize("failure", ["reject", "timeout", "verification"])
async def test_step_reason_codes_independent_of_plan_length(
    make_kernel: MakeKernel, failure: str
) -> None:
    """A failure on step 2 of a plan ends the run with the state, reason, code and
    evidence class the same failure has on a 1-step run today (``off``, ADR 0018)."""

    def arm(k: Kernel, index: int | None) -> None:
        if failure == "verification":
            _fail_verification_at(k, index)
        else:
            _fail_at(k, index, failure)

    # The 1-step run writes through another connection of the same store, so its UNKNOWN
    # write cannot make the plan's connection busy (ADR 0020).
    other = ConnectionDescriptor(
        tenant_id=TENANT,
        connection_id="conn-single",
        version=1,
        integration_id="notes-mem",
        ownership=ConnectionOwnership.TENANT_SHARED,
        provider_subject="svc",
    )
    single = make_kernel(
        driver=NotesDriver(texts=["standup notes"], connection_id=other.connection_id),
        connections=[other],
        binding_connections={b.binding_id: (other.connection_id,) for b in BINDINGS},
    )
    arm(single, None)
    one = await single.coordinator.start_run(
        single.requester, "x", frozenset({other.connection_id})
    )
    one = await _decide(single, one.run_id)

    k = _plan_kernel(make_kernel)
    arm(k, 1)
    run = await _start(k)
    run = await _decide(k, run.run_id)
    assert (run.state, run.reason, run.reason_code) == (one.state, one.reason, one.reason_code)
    assert classify(run.state, run.reason, "fixture", run.reason_code) == classify(
        one.state, one.reason, "fixture", one.reason_code
    )
    assert run.reason_code is not None


# -- evidence ----------------------------------------------------------------------------
async def test_evidence_lists_plan_and_steps(make_kernel: MakeKernel) -> None:
    """The bundle of an ``on`` run carries the plan it executed, each step with its action
    and status, and the run's step records; never the read-back values (PR-26). An ``off``
    bundle carries neither key (ENG-TOGGLE-1)."""
    k = _plan_kernel(make_kernel)
    run = await _start(k)
    run = await _decide(k, run.run_id)
    assert run.state is RunState.SUCCEEDED
    first, second = await _actions(k, run.run_id)
    bundle = await _bundle(k, run.run_id)
    plan = bundle["plan"]
    assert plan["plan_id"] == first.plan_id
    assert (plan["task_id"], plan["task_version"]) == (NOTES_TASK.task_id, NOTES_TASK.version)
    assert plan["step_count"] == 2
    assert [
        (s["step_id"], s["step_index"], s["action_id"], s["action_state"], s["status"])
        for s in plan["steps"]
    ] == [
        (FIRST, 0, first.action_id, "VERIFIED", "verified"),
        (FOLLOW_UP, 1, second.action_id, "VERIFIED", "verified"),
    ]
    stored = await k.store.list_steps(TENANT, run.run_id)
    assert stored and bundle["steps"] == [s.model_dump(mode="json") for s in stored]
    assert "verified_values" not in json.dumps(bundle)

    off = make_kernel()
    off_run = await off.coordinator.start_run(off.requester, "x", off.scope)
    off_run = await _decide(off, off_run.run_id)
    off_bundle = await build_evidence(
        off.store, TENANT, off_run.run_id, environment="fixture", versions={}, features=Features()
    )
    assert "plan" not in off_bundle and "steps" not in off_bundle


async def test_evidence_lists_a_one_step_plan(make_kernel: MakeKernel) -> None:
    """A single proposal in ``on`` runs as a 1-step plan; its bundle lists that plan."""
    k = make_kernel(features=ON)
    run = await k.coordinator.start_run(k.requester, "x", k.scope, task_kind=NOTES_TASK.task_id)
    run = await _decide(k, run.run_id)
    assert run.state is RunState.SUCCEEDED
    (action,) = await _actions(k, run.run_id)
    bundle = await _bundle(k, run.run_id)
    assert bundle["plan"]["plan_id"] == action.plan_id
    assert [s["status"] for s in bundle["plan"]["steps"]] == ["verified"]
    assert bundle["steps"]
