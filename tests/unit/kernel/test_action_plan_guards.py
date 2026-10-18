"""The guards of a multi-step plan between its approval and a later step's reservation
(Task 2c.7 review R-1 to R-4, ADR 0024, ADR 0025).

Each test names the guard it pins: domain validation of the resolved lineage values, a
placeholder step whose wire form cannot be validated, a stored plan that no longer matches
its approved step inputs, recovery between the steps, the approval's lifetime, and the write
budget a plan sees after an earlier write. Recovery between the steps resumes the plan
(Task 2c.8); the resume guards are pinned in `test_recovery.py`. Both stores run through `run_store`
(ENG-STORE-1).
"""

from collections.abc import Callable
from datetime import timedelta
from typing import Any

import pytest
from e_agent.contracts.action import ActionState
from e_agent.contracts.approval import ApprovalDecision
from e_agent.contracts.connection import ConnectionDescriptor, ConnectionOwnership
from e_agent.contracts.context import TaskContext
from e_agent.contracts.events import RunEventType
from e_agent.contracts.features import FeatureMode, Features
from e_agent.contracts.outcome import OutcomeReport
from e_agent.contracts.plan import ActionPlan
from e_agent.contracts.run import ReasonCode, RunState
from e_agent.contracts.validation import Finding, ValidationResult, ValidationStatus
from e_agent.sdk.ports import (
    ValidationInput,
)

from .conftest import (
    CONN,
    CREATE,
    NOTE_INPUT,
    NOTES_TASK,
    PIN,
    PLAN_BUDGETS,
    TENANT,
    Kernel,
    MetadataDriver,
    NotesPlanDriver,
    run_resume_work,
    two_step_plan,
)

MakeKernel = Callable[..., Kernel]
ON = Features(execution_ir=FeatureMode.ON)


def _plan_kernel(make_kernel: MakeKernel, **kw: Any) -> Kernel:
    kw.setdefault("features", ON)
    kw.setdefault("budgets", PLAN_BUDGETS)
    kw.setdefault("driver", NotesPlanDriver())
    kw.setdefault("input_schemas", {"c": NOTE_INPUT, "p": NOTE_INPUT})
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


async def _rules(k: Kernel, run_id: str) -> set[str]:
    return {
        f["rule_id"]
        for e in await k.store.list_events(TENANT, run_id)
        if e.type is RunEventType.VALIDATION_COMPLETED
        for f in e.payload.get("findings", [])
    }


async def _reserved(k: Kernel, run_id: str) -> list[str | None]:
    events = await k.store.list_events(TENANT, run_id)
    return [e.action_id for e in events if e.type is RunEventType.ACTION_RESERVED]


def _wrap_validate(k: Kernel, decide: Callable[[ValidationInput], ValidationResult | None]) -> None:
    """Replace the notes validator's verdict where ``decide`` returns one."""
    validate = k.validator.validate

    async def wrapped(ctx: TaskContext, item: ValidationInput) -> ValidationResult:
        verdict = decide(item)
        return verdict if verdict is not None else await validate(ctx, item)

    k.validator.validate = wrapped  # type: ignore[method-assign]


def _result(status: ValidationStatus, bundle: str = "notes@1") -> ValidationResult:
    finding = Finding(rule_id="NOTE-002", rule_version="1", status=status, message="parent")
    return ValidationResult(
        status=status, findings=(finding,), rule_bundle_version=bundle, validator_id="notes-rules"
    )


# -- R-1: the resolved values are domain-validated before the step reserves ---------------
async def test_resolved_lineage_value_failing_validation_stops_plan(
    make_kernel: MakeKernel,
) -> None:
    """The follow-up's resolved ``parent`` (the key step 1 read back) fails a domain rule:
    the revalidation in `_staleness` blocks it before it reserves; step 1 stays verified."""
    k = _plan_kernel(make_kernel)

    def block_resolved_parent(item: ValidationInput) -> ValidationResult | None:
        parent = item.proposal.arguments.get("parent")
        return _result(ValidationStatus.FAIL) if isinstance(parent, str) else None

    _wrap_validate(k, block_resolved_parent)
    run = await _start(k)
    assert run.state is RunState.WAITING_APPROVAL  # the wire form passed before approval
    run = await _decide(k, run.run_id)
    assert (run.state, run.reason_code) == (RunState.FAILED, ReasonCode.STALE)
    first, second = await _actions(k, run.run_id)
    assert (first.state, second.state) == (ActionState.VERIFIED, ActionState.BLOCKED)
    assert isinstance(second.arguments["parent"], str)  # the resolved value was validated
    assert await _reserved(k, run.run_id) == [first.action_id]
    assert k.backend.create_calls == 1


# -- R-2: a placeholder step whose wire form cannot be validated --------------------------
@pytest.mark.parametrize("failure", ["raises", "error-status", "no-validator"])
async def test_unvalidatable_placeholder_step_refuses_plan_before_approval(
    make_kernel: MakeKernel, failure: str
) -> None:
    """The follow-up's wire form leaves no real rule bundle to bind, so the plan is refused
    with a fixed finding before any approval and no sentinel reaches a digest:
    - ``raises``: the validator raises; `_validate` reports status ERROR (bundle ``error``),
      caught by the status check;
    - ``error-status``: the validator reports ERROR under its real bundle;
    - ``no-validator``: no validator supports the follow-up's contract; `_validate` reports
      UNKNOWN with the sentinel bundle ``none``, caught only by the sentinel check (2c.7 R2-1).
    """
    plan, task = two_step_plan(), NOTES_TASK
    if failure == "no-validator":  # the follow-up writes through PIN, which nothing validates
        follow_up = plan.steps[1]
        pin = follow_up.proposal.model_copy(update={"contract_id": PIN.contract_id})
        plan = plan.model_copy(
            update={"steps": (plan.steps[0], follow_up.model_copy(update={"proposal": pin}))}
        )
        task = NOTES_TASK.model_copy(
            update={"capabilities": (*NOTES_TASK.capabilities, PIN.contract_id)}
        )
    k = _plan_kernel(make_kernel, driver=NotesPlanDriver(plan=plan), task=task, with_pin=True)
    if failure == "no-validator":
        k.validator.supports = lambda cid: cid == CREATE.contract_id  # type: ignore[method-assign]
        assert k.coordinator._registry.validators_for(PIN.contract_id) == []

    def on_wire_form(item: ValidationInput) -> ValidationResult | None:
        if failure == "no-validator" or not isinstance(item.proposal.arguments.get("parent"), dict):
            return None
        if failure == "raises":
            raise RuntimeError("engine cannot read a placeholder")
        return _result(ValidationStatus.ERROR)

    _wrap_validate(k, on_wire_form)
    run = await _start(k)
    assert run.state is RunState.FAILED
    assert "KERNEL-PLAN-STEP-UNVALIDATABLE" in await _rules(k, run.run_id)
    events = await k.store.list_events(TENANT, run.run_id)
    assert not [e for e in events if e.type is RunEventType.APPROVAL_REQUESTED]
    assert await k.store.list_actions(TENANT, run.run_id) == []
    assert k.backend.create_calls == 0


# -- R-3: the stored plan must still be the approved one ----------------------------------
@pytest.mark.parametrize("change", ["arguments", "contract", "connection", "effects", "step_id"])
async def test_tampered_stored_plan_stops_before_the_later_step_reserves(
    make_kernel: MakeKernel, change: str
) -> None:
    """Step 2 is rebuilt from the stored plan; if it no longer matches the step input the
    approval bound (step id, contract, connection, expected effects, wire-form arguments),
    the plan fails closed (STALE) before step 2 reserves."""
    k = _plan_kernel(make_kernel)
    get_plan = k.store.get_plan

    async def tampered(tenant_id: str, plan_id: str) -> ActionPlan:
        plan = await get_plan(tenant_id, plan_id)
        step = plan.steps[1]
        proposal = step.proposal
        if change == "step_id":  # the same proposal under another step's name
            renamed = step.model_copy(update={"step_id": "renamed"})
            return plan.model_copy(update={"steps": (plan.steps[0], renamed)})
        update: dict[str, Any] = {
            "arguments": {"arguments": {**proposal.arguments, "text": "rewritten"}},
            "contract": {"contract_id": "notes.pin.v1"},
            "connection": {"connection_id": "conn-other"},
            "effects": {"expected_effects": ("note.deleted",)},
        }[change]
        changed = step.model_copy(update={"proposal": proposal.model_copy(update=update)})
        return plan.model_copy(update={"steps": (plan.steps[0], changed)})

    run = await _start(k)
    pres = await k.coordinator.pending_approval(TENANT, run.run_id)
    k.store.get_plan = tampered  # after the approver saw the plan: only dispatch reads it
    run = await k.coordinator.decide(
        actor=k.approver,
        run_id=run.run_id,
        action_id=pres.action_id,
        action_digest=pres.digest,
        expected_run_revision=pres.run_revision,
        decision=ApprovalDecision.APPROVED,
    )
    assert (run.state, run.reason_code) == (RunState.FAILED, ReasonCode.STALE)
    assert "KERNEL-PLAN-STEP-CHANGED" in await _rules(k, run.run_id)
    (first,) = await _actions(k, run.run_id)
    assert first.state is ActionState.VERIFIED
    assert await _reserved(k, run.run_id) == [first.action_id]
    assert k.backend.create_calls == 1


# -- R-4a: recovery between the steps (resume since Task 2c.8) ---------------------------
@pytest.mark.parametrize("left_in", [RunState.VERIFYING, RunState.RUNNING])
async def test_recovery_between_the_steps_resumes_the_plan(
    make_kernel: MakeKernel, left_in: RunState
) -> None:
    """The worker dies after step 1 verified and before step 2 started, the run left in
    VERIFYING or RUNNING: recovery finds the latest action VERIFIED with step 2 unstarted
    and queues the resume, sending nothing; the resume claim runs step 2 (2c.7 ended it
    INTERRUPTED). Step 1 is not re-sent."""
    k = _plan_kernel(make_kernel)
    target = "_after_step_verified" if left_in is RunState.VERIFYING else "_start_step"

    async def worker_lost(*_a: Any, **_kw: Any) -> Any:
        raise RuntimeError("worker lost between plan steps")

    run = await _start(k)
    setattr(k.coordinator, target, worker_lost)
    with pytest.raises(RuntimeError):
        await _decide(k, run.run_id)
    delattr(k.coordinator, target)  # the worker that recovers is a healthy one
    assert (await k.store.get_run(TENANT, run.run_id)).state is left_in
    run = await k.coordinator.recover_run(TENANT, run.run_id)
    assert run.state is left_in and k.backend.create_calls == 1  # queued only
    run = await run_resume_work(k.store, k.coordinator)
    assert (run.state, run.reason_code) == (RunState.SUCCEEDED, ReasonCode.VERIFIED)
    assert [a.state for a in await _actions(k, run.run_id)] == [ActionState.VERIFIED] * 2
    assert k.backend.create_calls == 2


# -- R-4b: the approval's lifetime covers every step --------------------------------------
async def test_approval_expiring_between_steps_stops_plan(make_kernel: MakeKernel) -> None:
    """The one approval expires while step 1 is verified: step 2 is blocked before it
    reserves, and nothing re-asks for approval inside the plan."""
    k = _plan_kernel(make_kernel, approval_ttl=timedelta(minutes=2))
    verify = k.verifier.verify

    async def then_expire(*args: Any) -> OutcomeReport:
        report = await verify(*args)
        k.clock.advance(minutes=3)
        return report

    k.verifier.verify = then_expire  # type: ignore[method-assign]
    run = await _start(k)
    run = await _decide(k, run.run_id)
    assert (run.state, run.reason_code) == (RunState.FAILED, ReasonCode.STALE)
    assert "approval expired" in (run.reason or "")
    first, second = await _actions(k, run.run_id)
    assert (first.state, second.state) == (ActionState.VERIFIED, ActionState.BLOCKED)
    assert await _reserved(k, run.run_id) == [first.action_id]
    assert k.backend.create_calls == 1


# -- R-4c: a plan sees only the writes the run has left -----------------------------------
@pytest.mark.parametrize(("writes", "refused"), [(0, False), (1, True)])
async def test_plan_after_an_earlier_write_is_refused_at_the_budget(
    make_kernel: MakeKernel, writes: int, refused: bool
) -> None:
    """With ``max_admitted_writes = 2`` and one write already counted, a 2-step plan exceeds
    the writes the run has left (``KERNEL-PLAN-WRITES``). Today no run reaches a driver turn
    after a reservation (a verified write finishes the run, `_finish_verified`), so the check
    is pinned on the plan checks themselves, against the run's own continuation."""
    k = _plan_kernel(make_kernel)
    run = await _start(k)
    cont = await k.coordinator._load_cont(TENANT, run.run_id)
    cont.writes = writes
    findings = k.coordinator._plan_findings(two_step_plan(), NOTES_TASK, cont)
    assert ("KERNEL-PLAN-WRITES" in {f.rule_id for f in findings}) is refused


# -- 2c.9: a plan step's connection is never the model's choice ------------------------------
SECOND_CONN = "conn-model-picked"


def _two_connections() -> list[ConnectionDescriptor]:
    return [
        ConnectionDescriptor(
            tenant_id=TENANT,
            connection_id=conn,
            version=1,
            integration_id="notes-mem",
            ownership=ConnectionOwnership.TENANT_SHARED,
            provider_subject="svc",
        )
        for conn in (CONN, SECOND_CONN)
    ]


async def _refused_without_effect(k: Kernel, run: Any) -> None:
    """The run ended FAILED on the fixed ``KERNEL-CONNECTION`` finding (2c.8b): nothing was
    proposed for approval, reserved or sent, and nothing is left for startup recovery."""
    assert (run.state, run.reason_code) == (RunState.FAILED, ReasonCode.VALIDATION_FAILED)
    findings = {
        f["rule_id"]
        for e in await k.store.list_events(TENANT, run.run_id)
        if e.type is RunEventType.VALIDATION_COMPLETED
        for f in e.payload.get("findings", [])
    }
    assert "KERNEL-CONNECTION" in findings
    assert await k.store.list_unfinished_runs() == []
    assert await k.store.list_actions(TENANT, run.run_id) == []
    assert not [
        e
        for e in await k.store.list_events(TENANT, run.run_id)
        if e.type in {RunEventType.APPROVAL_REQUESTED, RunEventType.IR_PLAN_COMPILED}
    ]
    assert await _reserved(k, run.run_id) == []
    assert k.backend.create_calls == 0


@pytest.mark.parametrize("in_scope", [False, True])
async def test_plan_step_on_a_connection_without_binding_is_refused(
    make_kernel: MakeKernel, in_scope: bool
) -> None:
    """The kernel half of PR-11 and PR-12 for plans (the driver half is
    `tests/unit/adapters/pydantic_ai/test_driver_plan.py::
    test_plan_with_model_chosen_connection_is_rejected`). A plan step that names a connection
    other than its capability's binding is refused before any action, approval or
    reservation exists: one outside the run's scope, and one inside it, usable by the
    requester, with no binding for the step's capability (`PluginRegistry.resolve`). Since
    2c.8b the refusal is the fixed ``KERNEL-CONNECTION`` repair finding, not an exception
    that left the run RUNNING for startup recovery: the driver proposes the same plan
    again until its repair budget ends the run FAILED."""
    driver = NotesPlanDriver(plan=two_step_plan(SECOND_CONN))
    k = _plan_kernel(make_kernel, driver=driver, connections=_two_connections())
    scope = k.scope | {SECOND_CONN} if in_scope else k.scope
    run = await k.coordinator.start_run(
        k.requester, "write standup note", scope, task_kind=NOTES_TASK.task_id
    )
    assert driver.calls > 2  # the read turn, the refused plan, then its repairs
    await _refused_without_effect(k, run)


@pytest.mark.parametrize("mode", ["off", "on"])
@pytest.mark.parametrize("in_scope", [False, True])
async def test_proposal_on_a_connection_without_binding_is_refused(
    make_kernel: MakeKernel, mode: str, in_scope: bool
) -> None:
    """The single-action path (shared with ``off``) refuses such a proposal the same way:
    the fixed ``KERNEL-CONNECTION`` finding, never an exception that strands the run. Only
    this failure path changes in ``off``; its happy path is the off golden's."""
    features = Features(execution_ir=FeatureMode.ON) if mode == "on" else Features()
    driver = MetadataDriver(propose_on=SECOND_CONN)
    k = make_kernel(features=features, driver=driver, connections=_two_connections())
    scope = k.scope | {SECOND_CONN} if in_scope else k.scope
    run = await k.coordinator.start_run(k.requester, "write standup note", scope)
    await _refused_without_effect(k, run)
