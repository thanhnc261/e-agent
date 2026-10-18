"""Durable plan step state (Task 2c.8b, Codex C-2, ADR 0025 amendment).

Whether a plan's steps are all done is read from the durable actions, never from the
continuation snapshot; and startup recovery writes no continuation for a resumable plan,
so a delayed recovery cannot overwrite a fenced worker's newer plan state (option (b)).
Both stores run through `run_store` (ENG-STORE-1).
"""

import asyncio
import contextlib
import copy
from collections.abc import Callable
from typing import Any

import pytest
from e_agent.contracts.action import ActionState
from e_agent.contracts.features import FeatureMode, Features
from e_agent.contracts.run import TERMINAL_RUN_STATES, ReasonCode, RunState
from e_agent.kernel.errors import KernelError
from e_agent.sdk.store import ConcurrencyConflict

from .conftest import (
    NOTES_TASK,
    TENANT,
    Kernel,
    run_resume_work,
)
from .test_action_plan_failures import (
    _actions,
    _decide,
    _fail_at,
    _plan_kernel,
    _start,
    _step_statuses,
)
from .test_recovery import PLAN_CRASH_POINTS, Crash, _crash_between_steps, _restart_plan

MakeKernel = Callable[..., Kernel]
ON = Features(execution_ir=FeatureMode.ON)
APPROVED, MUTATED = "approved", "mutated"


# -- C-2: durable step state, no stale continuation write ---------------------------------
async def test_delayed_recovery_save_never_reports_a_verified_plan_interrupted(
    make_kernel: MakeKernel,
) -> None:
    """Codex C-2: recovery A's continuation save is held after step 1 verified; recovery B
    queues the resume; a fenced worker verifies step 2 and dies after its outcome is stored;
    A's save is released; then the claim is taken over (fence 2, resume disabled). The run
    ends SUCCEEDED with both steps verified, never 'interrupted, remaining steps not
    started'. With the fix, recovery A makes no continuation save to hold at all."""
    k = _recovery_plan_kernel(make_kernel)
    run_id = await _crash_between_steps(k, "_after_step_verified")
    save = k.store.save_continuation
    paused, gate = asyncio.Event(), asyncio.Event()
    hold = {"next": True}

    async def held(*args: Any) -> Any:
        if hold["next"]:
            hold["next"] = False
            paused.set()
            await gate.wait()
        return await save(*args)

    k.store.save_continuation = held
    recovery_a = asyncio.create_task(_restart_plan(k).recover())
    waiting = asyncio.create_task(paused.wait())
    await asyncio.wait({recovery_a, waiting}, return_when=asyncio.FIRST_COMPLETED)
    hold["next"] = False  # only A's first save is held
    await _restart_plan(k).recover()  # recovery B

    record = k.store.record_outcome

    async def die_after_step_two(tenant: str, outcome: Any, action: Any, *rest: Any) -> Any:
        await record(tenant, outcome, action, *rest)
        if action is not None and action.step_index == 1:
            raise Crash

    k.store.record_outcome = die_after_step_two
    claim = await k.store.claim_work("worker-1")
    assert claim is not None and claim.kind == "resume"
    with pytest.raises(Crash):
        async with k.store.work_scope(claim):
            await _restart_plan(k).resume_plan(TENANT, run_id)
    k.store.record_outcome = record
    gate.set()
    await recovery_a
    waiting.cancel()
    k.store.save_continuation = save

    final = await _restart_plan(k).recover_run(TENANT, run_id, resume=False)  # the takeover
    first, second = await _actions(k, run_id)
    assert (first.state, second.state) == (ActionState.VERIFIED, ActionState.VERIFIED)
    assert (final.state, final.reason_code) == (RunState.SUCCEEDED, ReasonCode.VERIFIED)
    assert k.backend.create_calls == 2
    assert await _step_statuses(k, run_id) == ["verified", "verified"]


async def test_plan_success_is_read_from_durable_actions(make_kernel: MakeKernel) -> None:
    """C-2 (i): the stored continuation is the one from before step 2 started (a stale
    save won), while both steps are VERIFIED in the store. Recovery with resume disabled
    decides from the durable actions: SUCCEEDED, not INTERRUPTED."""
    k = _recovery_plan_kernel(make_kernel)
    run = await k.coordinator.start_run(
        k.requester, "write standup note", k.scope, task_kind=NOTES_TASK.task_id
    )
    record = k.store.record_outcome
    stale: list[Any] = []

    async def keep_then_die(tenant: str, outcome: Any, action: Any, *rest: Any) -> Any:
        await record(tenant, outcome, action, *rest)
        if action is not None and action.step_index == 0:
            stale.append(copy.deepcopy(await k.store.load_continuation(TENANT, run.run_id)))
        if action is not None and action.step_index == 1:
            raise Crash

    k.store.record_outcome = keep_then_die
    with pytest.raises(Crash):
        await _decide(k, run.run_id)
    k.store.record_outcome = record
    (state, driver_state) = stale[0]
    first, _ = await _actions(k, run.run_id)
    state["data"]["plan"]["action_ids"] = [first.action_id]  # the shape before 2c.8b
    await k.store.save_continuation(TENANT, run.run_id, state, driver_state)

    final = await _restart_plan(k).recover_run(TENANT, run.run_id, resume=False)
    assert (final.state, final.reason_code) == (RunState.SUCCEEDED, ReasonCode.VERIFIED)
    assert [a.state for a in await _actions(k, run.run_id)] == [ActionState.VERIFIED] * 2
    assert k.backend.create_calls == 2


@pytest.mark.parametrize("point", PLAN_CRASH_POINTS)
async def test_recovery_writes_no_continuation_for_a_resumable_plan(
    make_kernel: MakeKernel, point: str
) -> None:
    """C-2 (ii), option (b): startup recovery of a resumable ``on`` plan writes no plan
    state, neither an unfenced continuation save nor a continuation with a run update; a
    committed step is verified under the resume claim. The resume still finishes the plan."""
    k = _recovery_plan_kernel(make_kernel)
    await _crash_between_steps(k, point)
    writes: list[str] = []
    save, update = k.store.save_continuation, k.store.update_run

    async def counted_save(*args: Any) -> Any:
        writes.append("save_continuation")
        return await save(*args)

    async def counted_update(*args: Any, **kwargs: Any) -> Any:
        if kwargs.get("continuation") is not None:
            writes.append("update_run+continuation")
        return await update(*args, **kwargs)

    k.store.save_continuation, k.store.update_run = counted_save, counted_update
    coordinator = _restart_plan(k)
    [queued] = await coordinator.recover()
    assert writes == []
    assert queued.state in {RunState.VERIFYING, RunState.RUNNING}
    assert k.backend.create_calls == 1
    k.store.save_continuation, k.store.update_run = save, update
    done = await run_resume_work(k.store, coordinator)
    assert (done.state, done.reason_code) == (RunState.SUCCEEDED, ReasonCode.VERIFIED)
    assert k.backend.create_calls == 2


def _recovery_plan_kernel(make_kernel: MakeKernel) -> Kernel:
    from .test_recovery import _plan_kernel as recovery_kernel

    return recovery_kernel(make_kernel)


# -- Codex round 2 (C2-1, C2-2) ------------------------------------------------------------
async def test_a_resume_disabled_recovery_never_disables_a_concurrent_resume(
    make_kernel: MakeKernel,
) -> None:
    """C2-1: ``recover_run(resume=False)`` for run X is paused mid-call while a fenced resume
    claim for X runs in the same coordinator. The disabling is the paused call's own, not
    shared state: the resume proceeds and the plan succeeds, step 1 sent once."""
    k = _recovery_plan_kernel(make_kernel)
    run_id = await _crash_between_steps(k, "_after_step_verified")
    coordinator = _restart_plan(k)
    await coordinator.recover()  # queues the resume
    list_actions = k.store.list_actions
    paused, gate = asyncio.Event(), asyncio.Event()

    async def held(*args: Any) -> Any:
        if not paused.is_set():
            paused.set()
            await gate.wait()
        return await list_actions(*args)

    k.store.list_actions = held
    stuck = asyncio.create_task(coordinator.recover_run(TENANT, run_id, resume=False))
    await paused.wait()
    done = await run_resume_work(k.store, coordinator)
    gate.set()
    with contextlib.suppress(ConcurrencyConflict, KernelError):
        await stuck  # its view of the run is stale by now: refused, never a write
    k.store.list_actions = list_actions
    assert (done.state, done.reason_code) == (RunState.SUCCEEDED, ReasonCode.VERIFIED)
    assert (await k.store.get_run(TENANT, run_id)).state is RunState.SUCCEEDED
    assert k.backend.create_calls == 2


async def test_a_step_its_claim_left_unverified_is_queued_again(make_kernel: MakeKernel) -> None:
    """C2-2: step 2's receipt is UNKNOWN; reconciliation proves the effect and queues the
    resume; the claim cannot verify it (the verifier is down), so the run is VERIFYING with
    step 2 COMMITTED, as any inconclusive verification leaves a run. Startup recovery must
    queue a new resume item: the earlier item for the same action is DONE, and a key derived
    from the action alone made the enqueue a silent no-op, stranding the run. Step 2 is
    verified, never re-sent."""
    k = _plan_kernel(make_kernel)
    _fail_at(k, 1, "timeout")
    run = await _start(k)
    run = await _decide(k, run.run_id)
    assert run.state is RunState.NEEDS_RECONCILIATION
    verify = k.verifier.verify
    k.verifier.verify = _verifier_down  # type: ignore[method-assign]
    run = await k.coordinator.reconcile(k.approver, run.run_id)
    assert run.state is RunState.VERIFYING and await _pending(k, run.run_id)
    run = await run_resume_work(k.store, k.coordinator)
    assert run.state is RunState.VERIFYING  # verification pending (ReasonCode)
    assert [a.state for a in await _actions(k, run.run_id)] == [
        ActionState.VERIFIED,
        ActionState.COMMITTED,
    ]
    k.verifier.verify = verify  # type: ignore[method-assign]
    coordinator = _restart_plan(k)
    await coordinator.recover()
    assert await _pending(k, run.run_id)  # not stranded
    done = await run_resume_work(k.store, coordinator)
    assert (done.state, done.reason_code) == (RunState.SUCCEEDED, ReasonCode.VERIFIED)
    assert k.backend.create_calls == 2


async def _verifier_down(*_a: Any) -> Any:
    raise RuntimeError("verifier down")


async def _pending(k: Kernel, run_id: str) -> bool:
    return bool(await k.store.has_pending_work(TENANT, run_id))


AWAITING = {RunState.WAITING_APPROVAL, RunState.NEEDS_RECONCILIATION}
"""Non-terminal states that wait for a person: an approver, or an operator's reconcile."""


async def _awaits_something(k: Kernel, run_id: str) -> None:
    """The liveness invariant of an ``on`` plan run: once startup recovery has run, a run
    that is not terminal has pending work, a pending approval, or awaits reconciliation."""
    run = await k.store.get_run(TENANT, run_id)
    if run.state in TERMINAL_RUN_STATES or run.state in AWAITING:
        return
    assert await _pending(k, run_id), (run.state, run.reason)


async def _drain(k: Kernel, run_id: str) -> Any:
    """Run every queued item as the worker would, recovering at startup between them, and
    check the invariant after each; returns the final run."""
    for _ in range(10):
        await _restart_plan(k).recover()
        await _awaits_something(k, run_id)
        claim = await k.store.claim_work("drain")
        if claim is None:
            break
        async with k.store.work_scope(claim):
            await _restart_plan(k).resume_plan(claim.tenant_id, claim.run_id)
            await k.store.finish_work(claim)
    return await k.store.get_run(TENANT, run_id)


LIVENESS = [
    *(f"crash:{point}" for point in PLAN_CRASH_POINTS),
    "verify-down-in-approval-call",
    "verify-down-in-claim",
    "reconciled",
]


@pytest.mark.parametrize("scenario", LIVENESS)
async def test_a_non_terminal_plan_run_always_awaits_something(
    make_kernel: MakeKernel, scenario: str
) -> None:
    """C2-2's invariant over the paths that leave an ``on`` plan run non-terminal: a crash
    between the steps, a verification left inconclusive in the approval call or in a resume
    claim, and a reconciled UNKNOWN step. After startup recovery each has pending work, a
    pending approval or awaits reconciliation; draining the work finishes the plan without
    re-sending a step."""
    if scenario.startswith("crash:"):
        k = _recovery_plan_kernel(make_kernel)
        run_id = await _crash_between_steps(k, scenario.removeprefix("crash:"))
    else:
        k = _plan_kernel(make_kernel)
        verify = k.verifier.verify
        if scenario == "verify-down-in-approval-call":
            k.verifier.verify = _verifier_down  # type: ignore[method-assign]
        else:
            _fail_at(k, 1, "timeout")
        run = await _start(k)
        run_id = run.run_id
        run = await _decide(k, run_id)
        if scenario != "verify-down-in-approval-call":
            await _awaits_something(k, run_id)  # NEEDS_RECONCILIATION
            if scenario == "verify-down-in-claim":
                k.verifier.verify = _verifier_down  # type: ignore[method-assign]
            await k.coordinator.reconcile(k.approver, run_id)
            await _awaits_something(k, run_id)
            if scenario == "verify-down-in-claim":
                await run_resume_work(k.store, k.coordinator)
        k.verifier.verify = verify  # type: ignore[method-assign]
    final = await _drain(k, run_id)
    assert (final.state, final.reason_code) == (RunState.SUCCEEDED, ReasonCode.VERIFIED)
    assert k.backend.create_calls == 2


# -- 2c.8b review (R-2, R-3) ---------------------------------------------------------------
async def test_reconciling_a_plan_step_writes_no_continuation(make_kernel: MakeKernel) -> None:
    """R-2: reconciliation proves an ``on`` plan step committed and queues the resume. It
    writes no plan state: no continuation save, and no continuation attached to any run
    update, including the ``VERIFYING`` transition before the step is queued (ADR 0025
    amendment). The claim then verifies the step and finishes the plan without re-sending."""
    k = _plan_kernel(make_kernel)
    _fail_at(k, 1, "timeout")
    run = await _start(k)
    run = await _decide(k, run.run_id)
    assert run.state is RunState.NEEDS_RECONCILIATION
    writes: list[str] = []
    save, update = k.store.save_continuation, k.store.update_run

    async def counted_save(*args: Any) -> Any:
        writes.append("save_continuation")
        return await save(*args)

    async def counted_update(*args: Any, **kwargs: Any) -> Any:
        if kwargs.get("continuation") is not None:
            writes.append("update_run+continuation")
        return await update(*args, **kwargs)

    k.store.save_continuation, k.store.update_run = counted_save, counted_update
    run = await k.coordinator.reconcile(k.approver, run.run_id)
    assert writes == []
    assert run.state is RunState.VERIFYING and await _pending(k, run.run_id)
    k.store.save_continuation, k.store.update_run = save, update
    done = await run_resume_work(k.store, k.coordinator)
    assert (done.state, done.reason_code) == (RunState.SUCCEEDED, ReasonCode.VERIFIED)
    assert k.backend.create_calls == 2


@pytest.mark.parametrize("authority", ["stop", "unknown"])
async def test_a_failed_claims_recovery_verifies_a_step_but_never_starts_the_next(
    make_kernel: MakeKernel, authority: str
) -> None:
    """R-3: a three-step plan is [VERIFIED, COMMITTED, unstarted] (the process died before
    step 2's outcome was stored). Recovery after a failed resume claim (``resume=False``,
    ``NextStep.STOP``) reads step 2 back inline with a working verifier, and must then fail
    the run INTERRUPTED: it never starts step 3, so nothing is sent. Only ``START`` starts
    a step: an authority that is none of the three is refused, never treated as START."""
    k = _plan_kernel(make_kernel, steps=3)
    record = k.store.record_outcome

    async def die_before_step_two_outcome(
        tenant: str, outcome: Any, action: Any, *rest: Any
    ) -> Any:
        if action is not None and action.step_index == 1:
            raise Crash
        return await record(tenant, outcome, action, *rest)

    k.store.record_outcome = die_before_step_two_outcome
    run = await _start(k)
    with pytest.raises(Crash):
        await _decide(k, run.run_id)
    k.store.record_outcome = record
    assert [a.state for a in await _actions(k, run.run_id)] == [
        ActionState.VERIFIED,
        ActionState.COMMITTED,
    ]
    sent = k.backend.create_calls
    coordinator = _restart_plan(k)
    if authority == "unknown":
        real = coordinator._after_step_verified

        async def unknown(cont: Any, action: Any, *, next_step: Any) -> Any:
            return await real(cont, action, next_step="unknown")

        coordinator._after_step_verified = unknown  # type: ignore[method-assign]
        with pytest.raises(AssertionError):
            await coordinator.recover_run(TENANT, run.run_id, resume=False)
        assert k.backend.create_calls == sent == 2
        assert len(await _actions(k, run.run_id)) == 2
        return
    final = await coordinator.recover_run(TENANT, run.run_id, resume=False)
    assert (final.state, final.reason_code) == (RunState.FAILED, ReasonCode.INTERRUPTED)
    assert final.reason == "plan resume failed before step 3 reserved"
    assert k.backend.create_calls == sent == 2
    assert len(await _actions(k, run.run_id)) == 2
    assert not await _pending(k, run.run_id)
