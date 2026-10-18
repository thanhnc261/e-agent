"""`features.execution_ir: on`, single-step plans (Task 2c.6, ADR 0025, ADR 0027, ADR 0028).

The run resolves its task definition at admission; its tool set is the definition's
capabilities, passed to the driver on every turn and enforced by the kernel. A write proposal
compiles to a 1-step plan, validated and approved with today's digest and presentation, and
each stage writes step records in the same batch as its events. Acceptance is checked at run
end. Before the first reservation an IR failure falls back to today's path. Runs over both
stores through the `run_store` fixture (ENG-STORE-1); no plugin is imported.
"""

import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from e_agent.contracts.action import ActionState
from e_agent.contracts.approval import ApprovalDecision
from e_agent.contracts.context import Budgets
from e_agent.contracts.events import RunEventType
from e_agent.contracts.features import FeatureMode, Features
from e_agent.contracts.outcome import OutcomeCheck, OutcomeReport, OutcomeStatus
from e_agent.contracts.run import ReasonCode, RunState
from e_agent.contracts.step import StepKind, StepStatus
from e_agent.contracts.task import (
    AcceptanceSpec,
    AnswerCondition,
    RequiredEffect,
    TaskDefinition,
    acceptance_met,
)
from e_agent.contracts.validation import Finding, ValidationStatus
from e_agent.kernel import ir_on as ir_on_module
from e_agent.kernel.errors import ErrorCode, KernelError
from e_agent.kernel.evidence import classify
from e_agent.kernel.features import FALLBACK_MESSAGES
from e_agent.kernel.gateway import OUTSIDE_TASK
from e_agent.sdk.ports import DriverInput, FinalAnswer, RequestReads

from .conftest import CREATE, NOTES_TASK, READ, TENANT, Kernel
from .record_off_baseline import deterministic_ids

WRITE = "notes.note.create.v1"
ANSWER = "notes.summary.answer.v1"
T0 = datetime(2026, 10, 6, tzinfo=UTC)
MakeKernel = Callable[..., Kernel]
OFF = Features()
ON = Features(execution_ir=FeatureMode.ON)
SENTINEL = "SENTINEL-2c6-exception-text"


def _report(status: OutcomeStatus, *checks: tuple[str, bool, str]) -> OutcomeReport:
    return OutcomeReport(
        run_id="run_1",
        action_id="act_1",
        status=status,
        checks=tuple(
            OutcomeCheck(name=n, passed=p, expected=e, observed="model") for n, p, e in checks
        ),
        verifier_id="v",
        verifier_version="1",
        reported_at=T0,
    )


# -- acceptance (pure) -------------------------------------------------------------------
def test_acceptance_unmet_is_classified_failed() -> None:
    assert classify("FAILED", "acceptance unmet", "fixture", ReasonCode.ACCEPTANCE_UNMET) == (
        "fixture:failed"
    )


def test_acceptance_met_is_disjunctive() -> None:
    both = AcceptanceSpec(
        required_effects=(RequiredEffect(contract_id=WRITE, min_verified=2),),
        required_answer=ANSWER,
        answer_condition=AnswerCondition(check="count", expected="0"),
    )
    zero = _report(OutcomeStatus.VERIFIED, ("count", True, "0"))
    positive = _report(OutcomeStatus.VERIFIED, ("count", True, "3"))
    unverified = _report(OutcomeStatus.FAILED, ("count", True, "0"))
    cases = [
        (both, {WRITE: 2}, [], True),  # the effects alternative
        (both, {WRITE: 1}, [], False),  # below min_verified
        (both, {WRITE: 1}, [zero], True),  # the answer alternative, condition met
        (both, {}, [positive], False),  # an accurate positive answer is not the no-op
        (both, {}, [unverified], False),  # an unverified report never counts
        (AcceptanceSpec(required_answer=ANSWER), {}, [positive], True),  # no condition
        (AcceptanceSpec(required_answer=ANSWER), {WRITE: 5}, [], False),  # only the answer
        (AcceptanceSpec(required_effects=(RequiredEffect(contract_id=WRITE),)), {}, [zero], False),
        (AcceptanceSpec(), {}, [], True),  # nothing required
    ]
    for spec, verified, answers, expected in cases:
        assert acceptance_met(spec, verified, answers) is expected, (spec, verified, answers)
    print(f"acceptance cases: {len(cases)}")
    assert len(cases) == 9


# -- helpers -----------------------------------------------------------------------------
async def _start(k: Kernel, *, task_kind: str | None = NOTES_TASK.task_id) -> Any:
    return await k.coordinator.start_run(
        k.requester, "write standup note", k.scope, task_kind=task_kind
    )


async def _of(k: Kernel, run_id: str, kind: RunEventType) -> list[Any]:
    return [e for e in await k.store.list_events(TENANT, run_id) if e.type is kind]


async def _approve(k: Kernel, run_id: str) -> Any:
    pres = await k.coordinator.pending_approval(TENANT, run_id)
    return await k.coordinator.decide(
        actor=k.approver,
        run_id=run_id,
        action_id=pres.action_id,
        action_digest=pres.digest,
        expected_run_revision=pres.run_revision,
        decision=ApprovalDecision.APPROVED,
    )


async def _reset(store: Any) -> None:
    truncate = getattr(store, "truncate_for_tests", None)
    if truncate is not None:
        await truncate()
    else:
        store.__init__()


def _record_tool_sets(k: Kernel) -> list[tuple[str, ...] | None]:
    """Record the tool set the kernel passes on every driver turn."""
    seen: list[tuple[str, ...] | None] = []
    advance = k.driver.advance

    async def recording(ctx: Any, step_input: DriverInput) -> Any:
        seen.append(step_input.allowed_capabilities)
        return await advance(ctx, step_input)

    k.driver.advance = recording  # type: ignore[method-assign]
    return seen


def _task(**update: Any) -> TaskDefinition:
    return NOTES_TASK.model_copy(update=update)


FALLBACK = RunEventType.FEATURE_FALLBACK


# -- admission, tool set, budgets, TTL ---------------------------------------------------
async def test_on_run_records_task_id_and_version(make_kernel: MakeKernel) -> None:
    k = make_kernel(features=ON)
    run = await _start(k)
    stored = await k.store.get_run(TENANT, run.run_id)
    assert (stored.task_id, stored.task_version) == (NOTES_TASK.task_id, NOTES_TASK.version)
    assert not await _of(k, run.run_id, FALLBACK)


async def test_on_tool_set_equals_task_definition(make_kernel: MakeKernel) -> None:
    """Every driver turn, the acknowledgement turn included, carries the definition's
    capabilities; `off` passes no set, so the driver offers today's tools."""
    seen = {}
    for name, mode in (("off", OFF), ("on", ON)):
        k = make_kernel(features=mode)
        tool_sets = _record_tool_sets(k)
        run = await _start(k)
        run = await _approve(k, run.run_id)
        assert run.state is RunState.SUCCEEDED, name
        seen[name] = list(tool_sets)
        await _reset(k.store)
    assert len(seen["on"]) == len(seen["off"]) == 3  # read, propose, acknowledge
    assert seen["on"] == [NOTES_TASK.capabilities] * 3
    assert seen["off"] == [None] * 3


async def test_on_read_outside_task_definition_refused(make_kernel: MakeKernel) -> None:
    """The kernel is the boundary: a driver read of a capability outside the run's tool set
    never reaches the provider, and the driver is told it was rejected."""
    k = make_kernel(features=ON, task=_task(capabilities=(CREATE.contract_id,)))
    tool_sets = _record_tool_sets(k)
    run = await _start(k)
    assert k.backend.read_calls == 0
    rejected = await _of(k, run.run_id, RunEventType.READ_REJECTED)
    assert rejected and all(e.payload["code"] == OUTSIDE_TASK for e in rejected)
    assert all(e.payload["contract_id"] == READ.contract_id for e in rejected)
    assert not await _of(k, run.run_id, RunEventType.READ_RECORDED)
    assert set(tool_sets) == {(CREATE.contract_id,)}
    assert run.state is RunState.FAILED and run.reason_code is ReasonCode.BUDGET_EXHAUSTED


async def test_on_proposal_outside_task_definition_is_a_finding(make_kernel: MakeKernel) -> None:
    """A write outside the tool set is a repair finding, never a fallback to today's path."""
    k = make_kernel(
        features=ON, task=_task(capabilities=(READ.contract_id,), acceptance=AcceptanceSpec())
    )
    run = await _start(k)
    assert run.state is RunState.FAILED and run.reason_code is ReasonCode.VALIDATION_FAILED
    assert k.backend.create_calls == 0
    assert await k.store.list_actions(TENANT, run.run_id) == []
    assert not await _of(k, run.run_id, FALLBACK)
    validations = await _of(k, run.run_id, RunEventType.VALIDATION_COMPLETED)
    assert len(validations) == 3  # the first proposal and two repairs
    assert {f["rule_id"] for e in validations for f in e.payload["findings"]} == {
        "KERNEL-PLAN-CAPABILITY"
    }


async def test_on_definition_budgets_narrow_profile_budgets(make_kernel: MakeKernel) -> None:
    task = _task(budgets=Budgets(max_driver_turns=4))
    for mode, turns in ((OFF, 12), (ON, 4)):
        k = make_kernel(features=mode, task=task)
        run = await _start(k)
        assert k.coordinator._runs[run.run_id].ctx.budgets.max_driver_turns == turns
        await _reset(k.store)


async def test_on_definition_budget_merges_only_set_fields(make_kernel: MakeKernel) -> None:
    """R-2: a definition that sets one field leaves the other profile fields unchanged."""
    profile = Budgets(max_driver_turns=9, max_read_calls=7, max_validation_repairs=1)
    k = make_kernel(features=ON, budgets=profile, task=_task(budgets=Budgets(max_driver_turns=5)))
    run = await _start(k)
    budgets = k.coordinator._runs[run.run_id].ctx.budgets
    assert budgets == profile.model_copy(update={"max_driver_turns": 5})


async def test_on_task_approval_ttl_replaces_global(make_kernel: MakeKernel) -> None:
    ttl = timedelta(minutes=2)
    for mode, expected in ((OFF, timedelta(minutes=15)), (ON, ttl)):
        k = make_kernel(features=mode, task=_task(approval_ttl=ttl))
        requested = k.clock()
        run = await _start(k)
        pres = await k.coordinator.pending_approval(TENANT, run.run_id)
        assert pres.expires_at == requested + expected
        (event,) = await _of(k, run.run_id, RunEventType.APPROVAL_REQUESTED)
        assert event.payload["expires_at"] == (requested + expected).isoformat()
        k.clock.advance(minutes=3)
        if mode is OFF:
            assert await k.coordinator.sweep_expired_approvals() == 0
            assert (await _approve(k, run.run_id)).state is RunState.SUCCEEDED
        else:
            assert await k.coordinator.sweep_expired_approvals() == 1
            with pytest.raises(KernelError) as caught:
                await _approve(k, run.run_id)
            assert caught.value.code is ErrorCode.APPROVAL_STALE
            stored = await k.store.get_run(TENANT, run.run_id)
            assert stored.reason_code is ReasonCode.APPROVAL_EXPIRED
        await _reset(k.store)


async def test_on_approval_record_expires_with_the_task_ttl(make_kernel: MakeKernel) -> None:
    ttl = timedelta(minutes=2)
    k = make_kernel(features=ON, task=_task(approval_ttl=ttl))
    run = await _start(k)
    await _approve(k, run.run_id)
    (action,) = await k.store.list_actions(TENANT, run.run_id)
    (approval,) = await k.store.list_approvals(TENANT, action.action_id)
    assert approval.expires_at - approval.issued_at == ttl


# -- the 1-step plan ---------------------------------------------------------------------
async def test_on_single_step_run_records_steps_for_each_stage(make_kernel: MakeKernel) -> None:
    k = make_kernel(features=ON)
    run = await _start(k)
    run = await _approve(k, run.run_id)
    assert run.state is RunState.SUCCEEDED and run.reason_code is ReasonCode.VERIFIED

    (action,) = await k.store.list_actions(TENANT, run.run_id)
    assert action.state is ActionState.VERIFIED
    assert action.step_index == 0 and action.plan_id is not None
    plan = await k.store.get_plan(TENANT, action.plan_id)
    assert (plan.task_id, plan.task_version) == (NOTES_TASK.task_id, NOTES_TASK.version)
    assert [dict(s.proposal.arguments) for s in plan.steps] == [{"text": "standup notes"}]
    (compiled,) = await _of(k, run.run_id, RunEventType.IR_PLAN_COMPILED)
    assert compiled.payload["plan_id"] == plan.plan_id
    assert compiled.payload["plan_digest"] == action.digest

    steps = await k.store.list_steps(TENANT, run.run_id)
    expected = [
        (StepKind.VALIDATE, StepStatus.STARTED),
        (StepKind.VALIDATE, StepStatus.SUCCEEDED),
        (StepKind.APPROVAL_WAIT, StepStatus.STARTED),
        (StepKind.APPROVAL_WAIT, StepStatus.SUCCEEDED),
        (StepKind.DISPATCH, StepStatus.STARTED),
        (StepKind.DISPATCH, StepStatus.SUCCEEDED),
        (StepKind.VERIFY, StepStatus.STARTED),
        (StepKind.VERIFY, StepStatus.SUCCEEDED),
    ]
    assert [(s.kind, s.status) for s in steps] == expected
    assert [s.sequence for s in steps] == list(range(len(expected)))
    assert all(s.action_id == action.action_id for s in steps)
    assert {s.step_id for s in steps} == {
        f"{plan.plan_id}/step-1/{kind}"
        for kind in ("validate", "approval_wait", "dispatch", "verify")
    }
    assert all(s.finished_at is not None for s in steps if s.status is not StepStatus.STARTED)
    reads = await _of(k, run.run_id, RunEventType.READ_RECORDED)
    assert [r.evidence_id for r in steps[0].input_refs] == [reads[0].payload["evidence_id"]]


async def test_on_rejected_approval_closes_the_wait_step_blocked(make_kernel: MakeKernel) -> None:
    k = make_kernel(features=ON)
    run = await _start(k)
    pres = await k.coordinator.pending_approval(TENANT, run.run_id)
    run = await k.coordinator.decide(
        actor=k.approver,
        run_id=run.run_id,
        action_id=pres.action_id,
        action_digest=pres.digest,
        expected_run_revision=pres.run_revision,
        decision=ApprovalDecision.REJECTED,
    )
    assert run.reason_code is ReasonCode.APPROVAL_REJECTED
    steps = await k.store.list_steps(TENANT, run.run_id)
    assert [(s.kind, s.status) for s in steps][-2:] == [
        (StepKind.APPROVAL_WAIT, StepStatus.STARTED),
        (StepKind.APPROVAL_WAIT, StepStatus.BLOCKED),
    ]


async def test_on_single_step_approval_presentation_unchanged(make_kernel: MakeKernel) -> None:
    """The same `ApprovalPresentation` and digest as `off`, and the same outcome."""
    seen = {}
    for name, mode in (("off", OFF), ("on", ON)):
        k = make_kernel(features=mode)
        with deterministic_ids():
            run = await _start(k)
            pres = await k.coordinator.pending_approval(TENANT, run.run_id)
            done = await _approve(k, run.run_id)
        (action,) = await k.store.list_actions(TENANT, run.run_id)
        seen[name] = (pres, action.digest, done.state, done.reason_code)
        await _reset(k.store)
    assert seen["on"] == seen["off"]
    assert seen["on"][0].digest == seen["on"][1]
    assert seen["on"][2] is RunState.SUCCEEDED


# -- acceptance --------------------------------------------------------------------------
async def test_on_acceptance_unmet_fails_run_with_reason(make_kernel: MakeKernel) -> None:
    """A run whose verified effects fall short of the spec ends FAILED with ACCEPTANCE_UNMET;
    `off` ignores acceptance and succeeds on the same run."""
    twice = AcceptanceSpec(
        required_effects=(RequiredEffect(contract_id=CREATE.contract_id, min_verified=2),)
    )
    for mode, state, code in (
        (OFF, RunState.SUCCEEDED, ReasonCode.VERIFIED),
        (ON, RunState.FAILED, ReasonCode.ACCEPTANCE_UNMET),
    ):
        k = make_kernel(features=mode, task=_task(acceptance=twice))
        run = await _start(k)
        run = await _approve(k, run.run_id)
        assert (run.state, run.reason_code) == (state, code)
        (outcome,) = await _of(k, run.run_id, RunEventType.OUTCOME_REPORTED)
        assert outcome.payload["status"] == "VERIFIED"
        (terminal,) = await _of(k, run.run_id, RunEventType.RUN_TERMINAL)
        assert terminal.payload["reason_code"] == code
        assert classify(str(run.state), run.reason, "fixture", run.reason_code).endswith(
            "succeeded" if mode is OFF else "failed"
        )
        await _reset(k.store)


async def test_model_cannot_mark_plan_verified(make_kernel: MakeKernel) -> None:
    """ENG-TRUST-1: only the kernel's verifier marks a step verified. A driver that claims
    success, as text or after a failed read-back, never ends the run SUCCEEDED."""
    k = make_kernel(features=ON)
    k.verifier.tamper = True  # the independent read-back disagrees with the write
    advance = k.driver.advance

    async def claims_verified(ctx: Any, step_input: DriverInput) -> Any:
        step = await advance(ctx, step_input)
        return FinalAnswer(text="VERIFIED: done") if isinstance(step, FinalAnswer) else step

    k.driver.advance = claims_verified  # type: ignore[method-assign]
    run = await _start(k)
    run = await _approve(k, run.run_id)
    assert (run.state, run.reason_code) == (RunState.FAILED, ReasonCode.VERIFICATION_FAILED)
    (action,) = await k.store.list_actions(TENANT, run.run_id)
    assert action.state is ActionState.VERIFICATION_FAILED
    steps = await k.store.list_steps(TENANT, run.run_id)
    assert [(s.kind, s.status) for s in steps][-1] == (StepKind.VERIFY, StepStatus.FAILED)
    assert not any(s.kind is StepKind.VERIFY and s.status is StepStatus.SUCCEEDED for s in steps)

    # A driver that only claims the work is done, without a write, is never accepted.
    k2 = make_kernel(features=ON)

    async def text_only(ctx: Any, step_input: DriverInput) -> Any:
        if not step_input.observations and not step_input.findings:
            return RequestReads(reads=(await advance(ctx, step_input)).reads)
        return FinalAnswer(text="The note was created and independently VERIFIED.")

    k2.driver.advance = text_only  # type: ignore[method-assign]
    run = await _start(k2)
    assert (run.state, run.reason_code) == (RunState.FAILED, ReasonCode.VERIFICATION_FAILED)
    assert await k2.store.list_actions(TENANT, run.run_id) == []
    assert await k2.store.list_steps(TENANT, run.run_id) == []


# -- fallback ----------------------------------------------------------------------------
def _fallbacks(events: list[Any]) -> list[tuple[Any, ...]]:
    return [(e.payload, e.action_id) for e in events if e.type is FALLBACK]


def _payload(reason: ReasonCode) -> dict[str, Any]:
    return {"feature": "execution_ir", "reason_code": reason, "message": FALLBACK_MESSAGES[reason]}


async def test_on_unresolved_task_falls_back_with_reason(make_kernel: MakeKernel) -> None:
    """A run that names no definition (an API run, D8), or an unknown one, records one
    `feature.fallback` (`IR_TASK_UNRESOLVED`, fixed message) in its creating write and then
    runs exactly as `off`: today's tools, no plan, no step records, no acceptance check."""
    unresolved = _payload(ReasonCode.IR_TASK_UNRESOLVED)
    cases = 0
    for how in ("api", "no-kind", "unknown-kind"):
        seen = {}
        for name, mode in (("off", OFF), ("on", ON)):
            k = make_kernel(features=mode)
            tool_sets = _record_tool_sets(k)
            with deterministic_ids():
                if how == "api":
                    run_id, _ = await k.coordinator.admit_run(
                        k.requester,
                        "write standup note",
                        k.scope,
                        run_id="run-api",
                        idempotency_key="api-key",
                        request_digest="d",
                    )
                    run = await k.coordinator.start_admitted_run(TENANT, run_id)
                else:
                    run = await _start(k, task_kind=None if how == "no-kind" else "no-such-task")
                done = await _approve(k, run.run_id)
            events = await k.store.list_events(TENANT, run.run_id)
            seen[name] = {
                "events": events,
                "end": (done.state, done.reason_code),
                "tools": list(tool_sets),
                "steps": await k.store.list_steps(TENANT, run.run_id),
                "actions": [
                    (a.plan_id, a.step_index)
                    for a in await k.store.list_actions(TENANT, run.run_id)
                ],
                "stored": await k.store.get_run(TENANT, run.run_id),
            }
            await _reset(k.store)
        on, off = seen["on"], seen["off"]
        assert _fallbacks(on["events"]) == [(unresolved, None)], how
        assert [e.type for e in on["events"][:2]] == [RunEventType.RUN_CREATED, FALLBACK]
        assert [e.type for e in on["events"] if e.type is not FALLBACK] == [
            e.type for e in off["events"]
        ]
        assert on["end"] == off["end"] == (RunState.SUCCEEDED, ReasonCode.VERIFIED)
        assert on["tools"] == off["tools"] and set(on["tools"]) == {None}
        assert on["steps"] == [] and on["actions"] == [(None, None)]
        assert (on["stored"].task_id, on["stored"].task_version) == (None, None)
        cases += 1
    assert cases == 3


def _raise_sentinel(*_a: Any, **_kw: Any) -> Any:
    raise RuntimeError(SENTINEL)


def _sentinel_finding(*_a: Any, **_kw: Any) -> tuple[Finding, ...]:
    return (
        Finding(
            rule_id="KERNEL-PLAN-TASK",
            rule_version="1",
            status=ValidationStatus.FAIL,
            message=SENTINEL,
        ),
    )


def _perturbed(*args: Any, **kwargs: Any) -> dict[str, Any]:
    return {"perturbed": SENTINEL}


IR_FAULTS = [
    (ReasonCode.IR_COMPILE_FAILED, "compile_proposal", _raise_sentinel),
    (ReasonCode.IR_VALIDATION_FAILED, "validate_plan", _sentinel_finding),
    (ReasonCode.IR_VALIDATION_FAILED, "validate_plan", _raise_sentinel),
    (ReasonCode.IR_VALIDATION_FAILED, "plan_digest_input", _raise_sentinel),
    (ReasonCode.IR_VALIDATION_FAILED, "plan_digest_input", _perturbed),  # digest mismatch
]


@pytest.mark.parametrize(("reason", "target", "fault"), IR_FAULTS)
async def test_on_validation_error_before_reservation_falls_back(
    make_kernel: MakeKernel,
    monkeypatch: pytest.MonkeyPatch,
    reason: ReasonCode,
    target: str,
    fault: Callable[..., Any],
) -> None:
    """A compile or plan-validation failure before the reservation records one
    `feature.fallback` with its code and fixed message (no exception or finding text) and
    the proposal continues on today's path: same approval, no plan link, no step records."""
    off = make_kernel(features=OFF)
    with deterministic_ids():
        off_run = await _start(off)
    off_pres = await off.coordinator.pending_approval(TENANT, off_run.run_id)
    await _reset(off.store)
    k = make_kernel(features=ON)
    monkeypatch.setattr(ir_on_module, target, fault)
    with deterministic_ids():
        run = await _start(k)
    pres = await k.coordinator.pending_approval(TENANT, run.run_id)
    events = await k.store.list_events(TENANT, run.run_id)
    assert _fallbacks(events) == [(_payload(reason), None)]
    types = [e.type for e in events]
    assert types.index(FALLBACK) < types.index(RunEventType.APPROVAL_REQUESTED)
    assert not await _of(k, run.run_id, RunEventType.IR_PLAN_COMPILED)
    assert pres.model_dump(exclude={"run_revision"}) == off_pres.model_dump(
        exclude={"run_revision"}
    )
    assert pres.run_revision == off_pres.run_revision + 1  # the fallback event's write
    run = await _approve(k, run.run_id)
    assert (run.state, run.reason_code) == (RunState.SUCCEEDED, ReasonCode.VERIFIED)
    (action,) = await k.store.list_actions(TENANT, run.run_id)
    assert (action.plan_id, action.step_index) == (None, None)
    assert await k.store.list_steps(TENANT, run.run_id) == []
    stored = json.dumps(
        [e.model_dump(mode="json") for e in await k.store.list_events(TENANT, run.run_id)]
    )
    assert SENTINEL not in stored


async def test_on_linked_definition_gone_at_proposal_falls_back(make_kernel: MakeKernel) -> None:
    """A linked run whose definition is no longer admitted when it proposes (a resumed run
    after a redeploy) falls back for that proposal (`IR_TASK_UNRESOLVED`) before any
    reservation. Its acceptance cannot be checked at run end, so the run fails closed."""
    k = make_kernel(features=ON)
    advance = k.driver.advance

    async def drop_definition(ctx: Any, step_input: DriverInput) -> Any:
        if step_input.observations:
            k.coordinator._registry.task_definitions.pop(NOTES_TASK.task_id, None)
        return await advance(ctx, step_input)

    k.driver.advance = drop_definition  # type: ignore[method-assign]
    run = await _start(k)
    assert run.state is RunState.WAITING_APPROVAL
    events = await k.store.list_events(TENANT, run.run_id)
    assert _fallbacks(events) == [(_payload(ReasonCode.IR_TASK_UNRESOLVED), None)]
    assert not await _of(k, run.run_id, RunEventType.IR_PLAN_COMPILED)
    run = await _approve(k, run.run_id)
    (action,) = await k.store.list_actions(TENANT, run.run_id)
    assert action.state is ActionState.VERIFIED and action.plan_id is None
    assert await k.store.list_steps(TENANT, run.run_id) == []
    assert (run.state, run.reason_code) == (RunState.FAILED, ReasonCode.ACCEPTANCE_UNMET)
