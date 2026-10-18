"""A plan step's approved inputs are bound to the approval's plan digest (phase review P-3).

Before a plan step reserves, the kernel compares the action with its approved step input
from the continuation (`cont.plan.inputs`, Codex C-3), and `_start_step` compares the stored
plan step with the same input (2c.7 R-3). Nothing tied those inputs back to
``approval.action_digest``: a continuation and a stored plan changed together, consistently,
would have sent a step the approver never saw. Now the plan digest is recomputed from the
inputs (the ``plan.v1`` wrapper) and compared with the approval's before the step reserves;
a mismatch blocks the step and fails the run STALE with ``KERNEL-PLAN-DIGEST-MISMATCH``.
Both stores run through `run_store` (ENG-STORE-1).
"""

from collections.abc import Callable
from typing import Any

import pytest
from e_agent.contracts.approval import ApprovalDecision
from e_agent.contracts.events import RunEventType
from e_agent.contracts.plan import ActionPlan
from e_agent.contracts.run import ReasonCode, RunState

from .conftest import TENANT, Kernel, run_resume_work
from .test_recovery import _crash_between_steps, _plan_kernel, _restart_plan

MakeKernel = Callable[..., Kernel]
REWRITTEN = "rewritten after approval"


def _rewrite_stored_plan(k: Kernel) -> None:
    """The stored plan's step 2 now carries ``REWRITTEN``: alone, `_start_step` refuses it."""
    get_plan = k.store.get_plan

    async def rewritten(tenant_id: str, plan_id: str) -> ActionPlan:
        plan = await get_plan(tenant_id, plan_id)
        step = plan.steps[1]
        arguments = {**step.proposal.arguments, "text": REWRITTEN}
        proposal = step.proposal.model_copy(update={"arguments": arguments})
        changed = step.model_copy(update={"proposal": proposal})
        return plan.model_copy(update={"steps": (plan.steps[0], changed)})

    k.store.get_plan = rewritten


async def _rules(k: Kernel, run_id: str) -> set[str]:
    return {
        f["rule_id"]
        for e in await k.store.list_events(TENANT, run_id)
        if e.type is RunEventType.VALIDATION_COMPLETED
        for f in e.payload.get("findings", [])
    }


async def _stopped_before_step_2_reserved(k: Kernel, run: Any, sent: int = 1) -> None:
    assert (run.state, run.reason_code) == (RunState.FAILED, ReasonCode.STALE), run.reason
    assert "KERNEL-PLAN-DIGEST-MISMATCH" in await _rules(k, run.run_id)
    assert k.backend.create_calls == sent
    assert all(n["text"] != REWRITTEN for n in k.backend.notes.values())
    events = await k.store.list_events(TENANT, run.run_id)
    assert len([e for e in events if e.type is RunEventType.ACTION_RESERVED]) == sent
    assert not await k.store.has_pending_work(TENANT, run.run_id)


async def test_tampered_continuation_inputs_stop_the_resumed_step(make_kernel: MakeKernel) -> None:
    """The process dies after step 1 verified. The stored continuation's step 2 input and the
    stored plan's step 2 are then rewritten to agree with each other; the resume claim stops
    the plan before step 2 reserves, and the rewritten note is never sent."""
    k = _plan_kernel(make_kernel)
    run_id = await _crash_between_steps(k, "_after_step_verified")
    loaded = await k.store.load_continuation(TENANT, run_id)
    assert loaded is not None
    state, driver_state = loaded
    state["data"]["plan"]["inputs"][1]["arguments"]["text"] = REWRITTEN
    await k.store.save_continuation(TENANT, run_id, state, driver_state)
    _rewrite_stored_plan(k)

    coordinator = _restart_plan(k)
    await coordinator.recover()
    run = await run_resume_work(k.store, coordinator)
    await _stopped_before_step_2_reserved(k, run)


@pytest.mark.parametrize("when", ["before-step-1", "after-step-1"])
async def test_tampered_inputs_stop_the_plan_in_the_approval_call(
    make_kernel: MakeKernel, when: str
) -> None:
    """The same change made to the continuation the approval call holds. Made after step 1's
    outcome, step 2 is stopped before it reserves; made before the approval, the check runs
    for the first step too, and nothing is sent at all."""
    k = _plan_kernel(make_kernel)
    run = await k.coordinator.start_run(
        k.requester, "write standup note", k.scope, task_kind="standup-note"
    )
    pres = await k.coordinator.pending_approval(TENANT, run.run_id)
    cont = k.coordinator._runs[run.run_id]
    assert cont.plan is not None
    plan_state = cont.plan

    def tamper() -> None:
        plan_state.inputs[1]["arguments"]["text"] = REWRITTEN
        _rewrite_stored_plan(k)

    if when == "before-step-1":
        tamper()
    else:
        record = k.store.record_outcome

        async def then_tamper(*args: Any) -> Any:
            stored = await record(*args)
            tamper()
            return stored

        k.store.record_outcome = then_tamper
    run = await k.coordinator.decide(
        actor=k.approver,
        run_id=run.run_id,
        action_id=pres.action_id,
        action_digest=pres.digest,
        expected_run_revision=pres.run_revision,
        decision=ApprovalDecision.APPROVED,
    )
    sent = 0 if when == "before-step-1" else 1
    await _stopped_before_step_2_reserved(k, run, sent=sent)


async def test_untampered_plan_still_runs_both_steps(make_kernel: MakeKernel) -> None:
    """The control: the recomputed digest equals the approval's for an unchanged plan, after
    a restart as in the approval call, so both steps are sent once."""
    k = _plan_kernel(make_kernel)
    run_id = await _crash_between_steps(k, "_after_step_verified")
    coordinator = _restart_plan(k)
    await coordinator.recover()
    run = await run_resume_work(k.store, coordinator)
    assert (run.state, run.reason_code) == (RunState.SUCCEEDED, ReasonCode.VERIFIED)
    assert k.backend.create_calls == 2
    assert "KERNEL-PLAN-DIGEST-MISMATCH" not in await _rules(k, run_id)
