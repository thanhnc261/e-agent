"""Multi-step action plans in `execution_ir: on` (Task 2c.7, ADR 0024, ADR 0025, ADR 0029).

A driver proposes an N-step plan (`ProposePlan`). The kernel validates it as a whole, asks
for one approval bound to the plan digest, then dispatches the steps serially in step-index
order: step N + 1 reserves only after step N is verified, its lineage placeholders resolved
from step N's verified outcome and its facts and policy revalidated first. The notes fixture
domain stands in for any domain (no plugin is imported); both stores run through
`run_store` (ENG-STORE-1). Partial failure and recovery of a plan (Task 2c.8) are pinned in
`test_action_plan_failures.py` and `test_recovery.py`.
"""

import dataclasses
from collections.abc import Callable
from typing import Any

import pytest
from e_agent.contracts.action import ActionState
from e_agent.contracts.approval import ApprovalDecision
from e_agent.contracts.capability import Reversibility, Risk
from e_agent.contracts.context import Budgets
from e_agent.contracts.events import RunEventType
from e_agent.contracts.features import FeatureMode, Features
from e_agent.contracts.outcome import OutcomeReport
from e_agent.contracts.plan import ActionPlan, ActionProposal, LineageRef, PlannedStep
from e_agent.contracts.run import (
    ALLOWED_RUN_TRANSITIONS,
    PLAN_STEP_RUN_TRANSITIONS,
    ReasonCode,
    RunState,
)
from e_agent.contracts.step import StepKind, StepStatus
from e_agent.kernel.approval import compute_digest
from e_agent.kernel.errors import ErrorCode, KernelError
from e_agent.kernel.ir import step_operation_id
from e_agent.sdk.ports import DriverInput

from .conftest import (
    CREATE,
    FIRST,
    FOLLOW_UP,
    NOTE_INPUT,
    NOTES_TASK,
    PIN,
    PLAN_BUDGETS,
    TENANT,
    Kernel,
    NotesPlanDriver,
    run_resume_work,
    two_step_plan,
)

MakeKernel = Callable[..., Kernel]
ON = Features(execution_ir=FeatureMode.ON)
SCHEMAS = {"c": NOTE_INPUT, "p": NOTE_INPUT}


def _plan_kernel(make_kernel: MakeKernel, **kw: Any) -> Kernel:
    kw.setdefault("features", ON)
    kw.setdefault("budgets", PLAN_BUDGETS)
    kw.setdefault("driver", NotesPlanDriver())
    kw.setdefault("input_schemas", SCHEMAS)
    return make_kernel(**kw)


async def _start(k: Kernel) -> Any:
    return await k.coordinator.start_run(
        k.requester, "write standup note", k.scope, task_kind=NOTES_TASK.task_id
    )


async def _of(k: Kernel, run_id: str, kind: RunEventType) -> list[Any]:
    return [e for e in await k.store.list_events(TENANT, run_id) if e.type is kind]


async def _decide(k: Kernel, run_id: str, digest: str | None = None) -> Any:
    pres = await k.coordinator.pending_approval(TENANT, run_id)
    return await k.coordinator.decide(
        actor=k.approver,
        run_id=run_id,
        action_id=pres.action_id,
        action_digest=pres.digest if digest is None else digest,
        expected_run_revision=pres.run_revision,
        decision=ApprovalDecision.APPROVED,
    )


async def _actions(k: Kernel, run_id: str) -> list[Any]:
    actions = await k.store.list_actions(TENANT, run_id)
    return sorted(actions, key=lambda a: a.step_index if a.step_index is not None else -1)


def _types(events: list[Any]) -> list[RunEventType]:
    return [e.type for e in events]


# -- approval once, dispatch in order ----------------------------------------------------
async def test_plan_approved_once_dispatches_steps_in_order(make_kernel: MakeKernel) -> None:
    k = _plan_kernel(make_kernel)
    run = await _start(k)
    assert run.state is RunState.WAITING_APPROVAL
    pres = await k.coordinator.pending_approval(TENANT, run.run_id)
    assert pres.canonical_proposal["plan_schema"] == "plan.v1"
    assert pres.digest == compute_digest(pres.canonical_proposal)  # the plan digest
    (requested,) = await _of(k, run.run_id, RunEventType.APPROVAL_REQUESTED)
    assert requested.payload["digest"] == pres.digest

    run = await _decide(k, run.run_id)
    assert (run.state, run.reason_code) == (RunState.SUCCEEDED, ReasonCode.VERIFIED)

    first, second = await _actions(k, run.run_id)
    assert (first.state, second.state) == (ActionState.VERIFIED, ActionState.VERIFIED)
    assert (first.step_index, second.step_index) == (0, 1)
    assert first.plan_id == second.plan_id and first.plan_id is not None
    assert first.digest == second.digest == pres.digest
    assert first.logical_operation_id == step_operation_id(first.plan_id, FIRST)
    assert second.logical_operation_id == step_operation_id(first.plan_id, FOLLOW_UP)
    plan = await k.store.get_plan(TENANT, first.plan_id)
    assert [s.step_id for s in plan.steps] == [FIRST, FOLLOW_UP]
    assert (plan.task_id, plan.task_version) == (NOTES_TASK.task_id, NOTES_TASK.version)

    # One approval, recorded once, for the plan digest; none for the later step.
    assert len(await _of(k, run.run_id, RunEventType.APPROVAL_DECIDED)) == 1
    (approval,) = await k.store.list_approvals(TENANT, first.action_id)
    assert approval.action_digest == pres.digest
    assert await k.store.list_approvals(TENANT, second.action_id) == []

    reserved = await _of(k, run.run_id, RunEventType.ACTION_RESERVED)
    assert [e.action_id for e in reserved] == [first.action_id, second.action_id]
    verified = await _of(k, run.run_id, RunEventType.IR_STEP_VERIFIED)
    assert [(e.action_id, e.payload["step_id"]) for e in verified] == [
        (first.action_id, FIRST),
        (second.action_id, FOLLOW_UP),
    ]
    changes = [
        (e.payload["from"], e.payload["to"])
        for e in await _of(k, run.run_id, RunEventType.RUN_STATE_CHANGED)
        if "from" in e.payload
    ]
    assert (RunState.VERIFYING, RunState.RUNNING) in changes
    assert (RunState.RUNNING, RunState.VERIFYING) in changes
    assert k.backend.create_calls == 2
    assert k.driver.calls == 3  # read, plan, acknowledge: no driver turn between the steps


async def test_each_step_reserves_after_previous_verified(make_kernel: MakeKernel) -> None:
    k = _plan_kernel(make_kernel)
    states_at_reserve: list[list[tuple[int | None, ActionState]]] = []
    reserve = k.store.reserve_operation

    async def recording(action: Any, expected: int, events: Any) -> Any:
        others = await k.store.list_actions(TENANT, action.run_id)
        states_at_reserve.append(
            [(a.step_index, a.state) for a in others if a.action_id != action.action_id]
        )
        return await reserve(action, expected, events)

    k.store.reserve_operation = recording
    run = await _start(k)
    run = await _decide(k, run.run_id)
    assert run.state is RunState.SUCCEEDED
    assert states_at_reserve == [[], [(0, ActionState.VERIFIED)]]
    events = await k.store.list_events(TENANT, run.run_id)
    first, second = await _actions(k, run.run_id)
    order = [
        (e.type, e.action_id)
        for e in events
        if e.type
        in {
            RunEventType.ACTION_RESERVED,
            RunEventType.OUTCOME_REPORTED,
            RunEventType.IR_STEP_VERIFIED,
        }
    ]
    assert order == [
        (RunEventType.ACTION_RESERVED, first.action_id),
        (RunEventType.OUTCOME_REPORTED, first.action_id),
        (RunEventType.IR_STEP_VERIFIED, first.action_id),
        (RunEventType.ACTION_RESERVED, second.action_id),
        (RunEventType.OUTCOME_REPORTED, second.action_id),
        (RunEventType.IR_STEP_VERIFIED, second.action_id),
    ]


# -- lineage -----------------------------------------------------------------------------
async def test_lineage_value_resolved_and_recorded_before_reservation(
    make_kernel: MakeKernel,
) -> None:
    """The follow-up's ``parent`` is the first note's key as its verifier read it back,
    recorded in ``ir.lineage_resolved`` and a validate step before the follow-up reserves.
    The ``outcome.reported`` events never carry the read-back values (PR-26)."""
    k = _plan_kernel(make_kernel)
    run = await _start(k)
    run = await _decide(k, run.run_id)
    assert run.state is RunState.SUCCEEDED
    first, second = await _actions(k, run.run_id)
    key = first.logical_operation_id
    assert second.arguments == {"text": "follow-up", "parent": key}
    assert k.backend.notes[second.logical_operation_id]["parent"] == key

    events = await k.store.list_events(TENANT, run.run_id)
    (resolved,) = [e for e in events if e.type is RunEventType.IR_LINEAGE_RESOLVED]
    assert resolved.action_id == second.action_id
    assert resolved.payload == {
        "plan_id": first.plan_id,
        "step_id": FOLLOW_UP,
        "step_index": 1,
        "values": [{"argument": "/parent", "from_step": FIRST, "path": "/key", "value": key}],
    }
    reserved = next(
        e
        for e in events
        if e.type is RunEventType.ACTION_RESERVED and e.action_id == second.action_id
    )
    assert resolved.sequence < reserved.sequence

    steps = [
        s for s in await k.store.list_steps(TENANT, run.run_id) if s.action_id == second.action_id
    ]
    assert [(s.kind, s.status) for s in steps] == [
        (StepKind.VALIDATE, StepStatus.STARTED),
        (StepKind.VALIDATE, StepStatus.SUCCEEDED),
        (StepKind.DISPATCH, StepStatus.STARTED),
        (StepKind.DISPATCH, StepStatus.SUCCEEDED),
        (StepKind.VERIFY, StepStatus.STARTED),
        (StepKind.VERIFY, StepStatus.SUCCEEDED),
    ]
    assert {s.step_id for s in steps} == {
        f"{first.plan_id}/{FOLLOW_UP}/{kind}" for kind in ("validate", "dispatch", "verify")
    }
    for outcome in (e for e in events if e.type is RunEventType.OUTCOME_REPORTED):
        assert "verified_values" not in outcome.payload
        OutcomeReport.model_validate(outcome.payload)


async def test_lineage_missing_value_stops_plan_before_reservation(
    make_kernel: MakeKernel,
) -> None:
    """A pointer the verified outcome does not hold stops the plan before the later step
    reserves; the earlier step stays committed and verified (``PLAN_LINEAGE_REJECTED``)."""
    k = _plan_kernel(make_kernel, driver=NotesPlanDriver(plan=two_step_plan(path="/nope")))
    run = await _start(k)
    run = await _decide(k, run.run_id)
    assert run.state is RunState.FAILED
    (first,) = await _actions(k, run.run_id)
    assert first.state is ActionState.VERIFIED
    assert k.backend.create_calls == 1
    (finding,) = [
        f
        for e in await _of(k, run.run_id, RunEventType.VALIDATION_COMPLETED)
        for f in e.payload.get("findings", [])
        if f["rule_id"] == "KERNEL-PLAN-LINEAGE"
    ]
    assert "nope" not in finding["message"]  # a fixed message


async def test_lineage_type_mismatch_stops_plan_before_reservation(
    make_kernel: MakeKernel,
) -> None:
    """The copied value must have the type the consuming input schema declares."""
    k = _plan_kernel(make_kernel, driver=NotesPlanDriver(plan=two_step_plan(path="/count")))
    verify = k.verifier.verify

    async def with_count(*args: Any) -> OutcomeReport:
        report = await verify(*args)
        values = {**(report.verified_values or {}), "count": 3}
        return report.model_copy(update={"verified_values": values})

    k.verifier.verify = with_count  # type: ignore[method-assign]
    run = await _start(k)
    run = await _decide(k, run.run_id)
    assert run.state is RunState.FAILED
    assert [a.state for a in await _actions(k, run.run_id)] == [ActionState.VERIFIED]
    assert k.backend.create_calls == 1


async def test_placeholder_without_a_declared_type_is_a_finding(make_kernel: MakeKernel) -> None:
    """Before approval a placeholder is typed by its input schema; an argument the schema
    does not declare cannot be type-checked, so the plan returns to the driver."""
    k = _plan_kernel(make_kernel, input_schemas={})
    run = await _start(k)
    assert run.state is RunState.FAILED and run.reason_code is ReasonCode.VALIDATION_FAILED
    assert await k.store.list_actions(TENANT, run.run_id) == []
    rules = {
        f["rule_id"]
        for e in await _of(k, run.run_id, RunEventType.VALIDATION_COMPLETED)
        for f in e.payload["findings"]
    }
    assert rules == {"KERNEL-PLAN-LINEAGE"}


# -- revalidation ------------------------------------------------------------------------
async def test_stale_fact_before_step_two_stops_plan(make_kernel: MakeKernel) -> None:
    """ENG-TRUST-3: a material fact that changes after step 1 verifies stops the plan
    before step 2 reserves; step 1 stays verified and nothing is re-sent."""
    k = _plan_kernel(make_kernel)
    verify = k.verifier.verify

    async def then_change(*args: Any) -> OutcomeReport:
        report = await verify(*args)
        k.backend.revision += 1  # someone edits the source between the steps
        return report

    k.verifier.verify = then_change  # type: ignore[method-assign]
    run = await _start(k)
    run = await _decide(k, run.run_id)
    assert (run.state, run.reason_code) == (RunState.FAILED, ReasonCode.STALE)
    first, second = await _actions(k, run.run_id)
    assert (first.state, second.state) == (ActionState.VERIFIED, ActionState.BLOCKED)
    assert k.backend.create_calls == 1
    reserved = await _of(k, run.run_id, RunEventType.ACTION_RESERVED)
    assert [e.action_id for e in reserved] == [first.action_id]
    steps = [
        s for s in await k.store.list_steps(TENANT, run.run_id) if s.action_id == second.action_id
    ]
    assert [(s.kind, s.status) for s in steps] == [
        (StepKind.VALIDATE, StepStatus.STARTED),
        (StepKind.VALIDATE, StepStatus.BLOCKED),
    ]


@pytest.mark.parametrize("change", ["rules", "policy"])
async def test_rule_or_policy_change_before_step_two_stops_plan(
    make_kernel: MakeKernel, change: str
) -> None:
    """Every step's digest binds the rule bundle and policy versions known when the plan was
    proposed; a change after step 1 verifies stops the plan before step 2 reserves."""
    k = _plan_kernel(make_kernel)
    verify = k.verifier.verify
    policy = k.coordinator._policy

    class Changed:
        def evaluate(self, ctx: Any, descriptor: Any, connection_id: str) -> Any:
            decision = policy.evaluate(ctx, descriptor, connection_id)
            return dataclasses.replace(decision, policy_version="changed")

    async def then_change(*args: Any) -> OutcomeReport:
        report = await verify(*args)
        if change == "rules":
            k.validator.bundle = "notes@2"
        else:
            k.coordinator._policy = Changed()
        return report

    k.verifier.verify = then_change  # type: ignore[method-assign]
    run = await _start(k)
    pres = await k.coordinator.pending_approval(TENANT, run.run_id)
    bound = [s["input"] for s in pres.canonical_proposal["steps"]]
    assert {i["rule_bundle_version"] for i in bound} == {"notes@1"}  # the real bundle, each step
    assert len({i["policy_version"] for i in bound}) == 1
    run = await _decide(k, run.run_id)
    assert (run.state, run.reason_code) == (RunState.FAILED, ReasonCode.STALE)
    first, second = await _actions(k, run.run_id)
    assert (first.state, second.state) == (ActionState.VERIFIED, ActionState.BLOCKED)
    assert k.backend.create_calls == 1


# -- what `off` stores -------------------------------------------------------------------
@pytest.mark.parametrize("mode", [FeatureMode.OFF, FeatureMode.SHADOW, FeatureMode.ON])
async def test_read_back_values_are_stored_only_in_on(
    make_kernel: MakeKernel, mode: FeatureMode
) -> None:
    """`off` and `shadow` store each outcome exactly as before Task 2c.7: the verifier's
    read-back values are dropped before the store; `on` keeps them for lineage."""
    k = make_kernel(features=Features(execution_ir=mode))
    stored: list[OutcomeReport] = []
    record = k.store.record_outcome

    async def recording(tenant: str, outcome: OutcomeReport, *rest: Any) -> Any:
        stored.append(outcome)
        return await record(tenant, outcome, *rest)

    k.store.record_outcome = recording
    run = await _start(k)
    run = await _decide(k, run.run_id)
    assert run.state is RunState.SUCCEEDED
    (outcome,) = stored
    if mode is FeatureMode.ON:
        assert outcome.verified_values is not None
    else:
        assert outcome.verified_values is None
        assert "verified_values" not in outcome.model_dump(mode="json")


# -- approval binding --------------------------------------------------------------------
async def test_approval_for_other_digest_rejected(make_kernel: MakeKernel) -> None:
    """The plan's one approval binds the plan digest: step 1's own action digest, or any
    other digest, is refused and nothing is dispatched."""
    k = _plan_kernel(make_kernel)
    run = await _start(k)
    pres = await k.coordinator.pending_approval(TENANT, run.run_id)
    step_one = compute_digest(pres.canonical_proposal["steps"][0]["input"])
    assert step_one != pres.digest
    for other in (step_one, "jcs-sha256-v1:" + "0" * 64):
        with pytest.raises(KernelError) as caught:
            await _decide(k, run.run_id, digest=other)
        assert caught.value.code is ErrorCode.APPROVAL_STALE
    assert k.backend.create_calls == 0
    assert await _of(k, run.run_id, RunEventType.APPROVAL_DECIDED) == []
    run = await _decide(k, run.run_id)
    assert run.state is RunState.SUCCEEDED and k.backend.create_calls == 2


async def test_presentation_shows_highest_risk_and_irreversible_steps(
    make_kernel: MakeKernel,
) -> None:
    """ADR 0029: the card lists every step, placeholders as "from step N: <path>", the
    plan's highest declared risk and its irreversible steps. A 1-step plan leaves them empty."""
    plan = two_step_plan()
    pin = PlannedStep(
        step_id="pin",
        proposal=ActionProposal(
            contract_id=PIN.contract_id,
            connection_id=plan.steps[0].proposal.connection_id,
            arguments={"text": "pin it", "parent": LineageRef(step_id=FIRST, path="/key")},
        ),
        depends_on=(FIRST,),
    )
    plan = plan.model_copy(update={"steps": (plan.steps[0], pin)})
    task = NOTES_TASK.model_copy(
        update={"capabilities": (*NOTES_TASK.capabilities, PIN.contract_id)}
    )
    k = _plan_kernel(make_kernel, driver=NotesPlanDriver(plan=plan), task=task, with_pin=True)
    run = await _start(k)
    pres = await k.coordinator.pending_approval(TENANT, run.run_id)
    assert pres.highest_risk is Risk.WRITE_HIGH
    assert pres.irreversible_steps == (FIRST,)
    assert [(s.step_id, s.step_index, s.contract_id) for s in pres.plan_steps] == [
        (FIRST, 0, CREATE.contract_id),
        ("pin", 1, PIN.contract_id),
    ]
    assert [(s.risk, s.reversibility) for s in pres.plan_steps] == [
        (Risk.WRITE_LOW, Reversibility.IRREVERSIBLE),
        (Risk.WRITE_HIGH, Reversibility.COMPENSABLE),
    ]
    assert pres.plan_steps[1].depends_on == (FIRST,)
    fields = {f.path: f.value for f in pres.plan_steps[1].material_fields}
    assert fields == {"parent": "from step 1: /key", "text": "pin it"}
    assert {f.path: f.value for f in pres.material_fields} == {"text": "standup notes"}

    single = make_kernel(features=ON)
    run = await _start(single)
    one = await single.coordinator.pending_approval(TENANT, run.run_id)
    assert (one.plan_steps, one.highest_risk, one.irreversible_steps) == ((), None, ())


# -- refusals before the plan path -------------------------------------------------------
async def test_propose_plan_is_a_repair_finding_outside_on_and_with_one_write(
    make_kernel: MakeKernel,
) -> None:
    """`off` and `shadow` cannot run a plan, nor can a run that admits one write: the plan
    returns to the driver as a fixed repair finding, never as a fallback."""
    cases = [
        (Features(), PLAN_BUDGETS, "KERNEL-PLAN-UNSUPPORTED"),
        (Features(execution_ir=FeatureMode.SHADOW), PLAN_BUDGETS, "KERNEL-PLAN-UNSUPPORTED"),
        (ON, Budgets(), "KERNEL-PLAN-WRITES"),
    ]
    for features, budgets, rule in cases:
        driver = NotesPlanDriver()
        k = _plan_kernel(make_kernel, features=features, budgets=budgets, driver=driver)
        run = await _start(k)
        assert (run.state, run.reason_code) == (RunState.FAILED, ReasonCode.VALIDATION_FAILED)
        assert await k.store.list_actions(TENANT, run.run_id) == []
        assert not await _of(k, run.run_id, RunEventType.FEATURE_FALLBACK)
        findings = [
            f
            for e in await _of(k, run.run_id, RunEventType.VALIDATION_COMPLETED)
            for f in e.payload["findings"]
        ]
        assert {f["rule_id"] for f in findings} == {rule}
        assert len({f["message"] for f in findings}) == 1
        seen: list[DriverInput] = driver.seen
        assert [f.rule_id for f in seen[-1].findings] == [rule]
        truncate = getattr(k.store, "truncate_for_tests", None)
        if truncate is not None:
            await truncate()
    print(f"refusal cases: {len(cases)}")


async def test_plan_with_too_many_writes_is_a_finding(make_kernel: MakeKernel) -> None:
    plan = two_step_plan()
    third = plan.steps[1].model_copy(update={"step_id": "third"})
    plan = plan.model_copy(update={"steps": (*plan.steps, third)})
    k = _plan_kernel(make_kernel, driver=NotesPlanDriver(plan=plan))
    run = await _start(k)
    assert run.state is RunState.FAILED
    rules = {
        f["rule_id"]
        for e in await _of(k, run.run_id, RunEventType.VALIDATION_COMPLETED)
        for f in e.payload["findings"]
    }
    assert rules == {"KERNEL-PLAN-WRITES"}


# -- the plan-only run pairs -------------------------------------------------------------
async def test_verifying_to_running_allowed_only_between_plan_steps(
    make_kernel: MakeKernel,
) -> None:
    """ADR 0025 widens the run table by two pairs; the kernel accepts them only while a
    multi-step plan runs (a step verified with steps left, a later step committed)."""
    pairs = {(RunState.VERIFYING, RunState.RUNNING), (RunState.RUNNING, RunState.VERIFYING)}
    assert set(PLAN_STEP_RUN_TRANSITIONS) == pairs
    for source, target in pairs:
        assert target in ALLOWED_RUN_TRANSITIONS[source]

    # A 1-step run left VERIFYING (verification unavailable) cannot go back to RUNNING.
    k = make_kernel(features=ON)

    async def unavailable(*_a: Any) -> OutcomeReport:
        raise RuntimeError("verifier down")

    k.verifier.verify = unavailable  # type: ignore[method-assign]
    run = await _start(k)
    run = await _decide(k, run.run_id)
    assert run.state is RunState.VERIFYING
    with pytest.raises(KernelError) as caught:
        await k.coordinator._set_run_state(run, RunState.RUNNING)
    assert caught.value.code is ErrorCode.CONFLICT
    # A RUNNING run outside a plan cannot go to VERIFYING either.
    running = run.model_copy(update={"state": RunState.RUNNING})
    with pytest.raises(KernelError):
        k.coordinator._check_run_transition(running, RunState.VERIFYING)

    # Inside a plan both pairs are used, once each, between the two steps.
    k = _plan_kernel(make_kernel)
    run = await _start(k)
    run = await _decide(k, run.run_id)
    changes = [
        (e.payload["from"], e.payload["to"])
        for e in await _of(k, run.run_id, RunEventType.RUN_STATE_CHANGED)
        if "from" in e.payload
    ]
    assert sorted(p for p in changes if p in pairs) == sorted(pairs)


# -- genericity --------------------------------------------------------------------------
async def test_notes_two_step_plan(make_kernel: MakeKernel) -> None:
    """The whole plan lifecycle in a non-ERP domain: two notes written, the second linked
    to the first through lineage, acceptance met, every stage of each step recorded."""
    k = _plan_kernel(make_kernel)
    run = await _start(k)
    run = await _decide(k, run.run_id)
    assert (run.state, run.reason_code) == (RunState.SUCCEEDED, ReasonCode.VERIFIED)
    notes = list(k.backend.notes.values())
    assert [n["text"] for n in notes] == ["standup notes", "follow-up"]
    assert notes[1]["parent"] == notes[0]["key"]
    first, second = await _actions(k, run.run_id)
    steps = await k.store.list_steps(TENANT, run.run_id)
    assert [s.sequence for s in steps] == list(range(len(steps)))
    kinds = {(s.action_id, s.kind) for s in steps if s.status is StepStatus.SUCCEEDED}
    assert kinds == {
        (first.action_id, StepKind.VALIDATE),
        (first.action_id, StepKind.APPROVAL_WAIT),
        (first.action_id, StepKind.DISPATCH),
        (first.action_id, StepKind.VERIFY),
        (second.action_id, StepKind.VALIDATE),
        (second.action_id, StepKind.DISPATCH),
        (second.action_id, StepKind.VERIFY),
    }
    (final,) = await _of(k, run.run_id, RunEventType.MESSAGE_FINAL)
    assert final.payload["text"] == "done"


async def test_a_one_step_plan_runs_as_a_single_proposal(make_kernel: MakeKernel) -> None:
    plan = two_step_plan()
    single = ActionPlan(plan_id="x", task_id="x", task_version="x", steps=(plan.steps[0],))
    k = _plan_kernel(make_kernel, driver=NotesPlanDriver(plan=single))
    run = await _start(k)
    pres = await k.coordinator.pending_approval(TENANT, run.run_id)
    assert "plan_schema" not in pres.canonical_proposal and pres.plan_steps == ()
    run = await _decide(k, run.run_id)
    assert run.state is RunState.SUCCEEDED
    (action,) = await _actions(k, run.run_id)
    assert action.logical_operation_id == run.logical_operation_id


async def test_plan_resumes_after_recovery_reverifies_its_committed_step(
    make_kernel: MakeKernel,
) -> None:
    """Recovery never sends a write: a plan whose first step committed and is re-verified
    by recovery queues its resume; the resume claim goes on with the next step, revalidated
    before it reserves (Task 2c.8; 2c.7 stopped it INTERRUPTED). The committed step is sent
    once (ENG-TRUST-5)."""
    k = _plan_kernel(make_kernel)
    run = await _start(k)
    apply = k.coordinator._apply_receipt

    async def crash_after_commit(cont: Any, action: Any, receipt: Any, **kw: Any) -> Any:
        if action.step_index == 0:
            await k.store.record_receipt(
                receipt,
                action.model_copy(
                    update={"state": ActionState.COMMITTED, "revision": action.revision + 1}
                ),
                action.revision,
                [
                    (
                        RunEventType.ACTION_RECEIPT_RECORDED,
                        receipt.model_dump(mode="json"),
                        action.action_id,
                    )
                ],
            )
            raise RuntimeError("worker lost after commit")
        return await apply(cont, action, receipt, **kw)

    k.coordinator._apply_receipt = crash_after_commit  # type: ignore[method-assign]
    with pytest.raises(RuntimeError):
        await _decide(k, run.run_id)
    k.coordinator._apply_receipt = apply  # type: ignore[method-assign]
    run = await k.coordinator.recover_run(TENANT, run.run_id)
    assert run.state is RunState.VERIFYING and k.backend.create_calls == 1  # queued only
    run = await run_resume_work(k.store, k.coordinator)
    assert (run.state, run.reason_code) == (RunState.SUCCEEDED, ReasonCode.VERIFIED)
    assert [a.state for a in await _actions(k, run.run_id)] == [ActionState.VERIFIED] * 2
    assert k.backend.create_calls == 2
