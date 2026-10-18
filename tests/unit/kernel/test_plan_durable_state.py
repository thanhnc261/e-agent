"""Durable plan step state (Task 2c.8b, Codex C-2, ADR 0025 amendment).

Whether a plan's steps are all done is read from the durable actions, never from the
continuation snapshot; and startup recovery writes no continuation for a resumable plan,
so a delayed recovery cannot overwrite a fenced worker's newer plan state (option (b)).
Both stores run through `run_store` (ENG-STORE-1).
"""

import asyncio
import copy
from collections.abc import Callable
from typing import Any

import pytest
from e_agent.contracts.action import ActionState
from e_agent.contracts.features import FeatureMode, Features
from e_agent.contracts.run import ReasonCode, RunState

from .conftest import (
    NOTES_TASK,
    TENANT,
    Kernel,
    run_resume_work,
)
from .test_action_plan_failures import (
    _actions,
    _decide,
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
