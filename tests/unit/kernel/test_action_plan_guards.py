"""The guards of a multi-step plan between its approval and a later step's reservation
(Task 2c.7 review R-1 to R-4, ADR 0024, ADR 0025).

Each test names the guard it pins: domain validation of the resolved lineage values, a
placeholder step whose wire form cannot be validated, a stored plan that no longer matches
its approved step inputs, recovery between the steps, the approval's lifetime, and the write
budget a plan sees after an earlier write. Both stores run through `run_store`
(ENG-STORE-1).
"""

from collections.abc import Callable
from datetime import timedelta
from typing import Any

import pytest
from e_agent.contracts.action import ActionState
from e_agent.contracts.approval import ApprovalDecision
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
    NOTE_INPUT,
    NOTES_TASK,
    PLAN_BUDGETS,
    TENANT,
    Kernel,
    NotesPlanDriver,
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
@pytest.mark.parametrize("failure", ["raises", "error-status"])
async def test_unvalidatable_placeholder_step_refuses_plan_before_approval(
    make_kernel: MakeKernel, failure: str
) -> None:
    """A validator that raises on the follow-up's wire form (the kernel's sentinel bundle
    ``error``) or reports ERROR leaves no real rule bundle to bind: the plan is refused with
    a fixed finding before any approval, and no sentinel reaches a digest."""
    k = _plan_kernel(make_kernel)

    def on_wire_form(item: ValidationInput) -> ValidationResult | None:
        if not isinstance(item.proposal.arguments.get("parent"), dict):
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
@pytest.mark.parametrize("change", ["arguments", "contract", "connection", "effects"])
async def test_tampered_stored_plan_stops_before_the_later_step_reserves(
    make_kernel: MakeKernel, change: str
) -> None:
    """Step 2 is rebuilt from the stored plan; if it no longer matches the step input the
    approval bound (contract, connection, expected effects, wire-form arguments), the plan
    fails closed (STALE) before step 2 reserves."""
    k = _plan_kernel(make_kernel)
    get_plan = k.store.get_plan

    async def tampered(tenant_id: str, plan_id: str) -> ActionPlan:
        plan = await get_plan(tenant_id, plan_id)
        step = plan.steps[1]
        proposal = step.proposal
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


# -- R-4a: recovery between the steps -----------------------------------------------------
@pytest.mark.parametrize("left_in", [RunState.VERIFYING, RunState.RUNNING])
async def test_recovery_with_an_unstarted_step_ends_interrupted(
    make_kernel: MakeKernel, left_in: RunState
) -> None:
    """The worker dies after step 1 verified and before step 2 started, the run left in
    VERIFYING or RUNNING: recovery finds the latest action VERIFIED, and a plan with a step
    never started fails INTERRUPTED, never SUCCEEDED."""
    k = _plan_kernel(make_kernel)
    target = "_after_step_verified" if left_in is RunState.VERIFYING else "_start_step"

    async def worker_lost(*_a: Any) -> Any:
        raise RuntimeError("worker lost between plan steps")

    run = await _start(k)
    setattr(k.coordinator, target, worker_lost)
    with pytest.raises(RuntimeError):
        await _decide(k, run.run_id)
    assert (await k.store.get_run(TENANT, run.run_id)).state is left_in
    run = await k.coordinator.recover_run(TENANT, run.run_id)
    assert (run.state, run.reason_code) == (RunState.FAILED, ReasonCode.INTERRUPTED)
    assert [a.state for a in await _actions(k, run.run_id)] == [ActionState.VERIFIED]
    assert k.backend.create_calls == 1


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
