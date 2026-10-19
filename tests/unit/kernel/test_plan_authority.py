"""Call-scoped plan authority (Task 2c.8b, Codex C-1, ADR 0025 amendment, ENG-TRUST-5).

The authority to start a later plan step travels with the call: only the approval call and
a fenced ``resume`` claim pass it. Reconciliation and recovery queue the resume instead, so
neither ever sends a write. Both stores run through `run_store` (ENG-STORE-1).
"""

import asyncio
from collections.abc import Callable
from typing import Any

from e_agent.contracts.events import RunEventType
from e_agent.contracts.features import FeatureMode, Features
from e_agent.contracts.run import ReasonCode, RunState

from .conftest import (
    TENANT,
    Kernel,
    run_resume_work,
)
from .test_action_plan_failures import (
    _actions,
    _decide,
    _fail_at,
    _of,
    _plan_kernel,
    _start,
)

MakeKernel = Callable[..., Kernel]
ON = Features(execution_ir=FeatureMode.ON)
APPROVED, MUTATED = "approved", "mutated"


# -- C-1: call-scoped plan authority -------------------------------------------------------
async def test_concurrent_reconcile_never_starts_the_next_step(make_kernel: MakeKernel) -> None:
    """Codex C-1: step 1 commits but its receipt is UNKNOWN; while the approval call is
    paused after NEEDS_RECONCILIATION is stored, an operator reconciles the run. The
    reconciliation proves step 1 and queues one resume item; it never starts step 2 on the
    approval call's authority, and the run is not SUCCEEDED by it. The resume claim then
    finishes the plan."""
    k = _plan_kernel(make_kernel)
    _fail_at(k, 0, "timeout")  # the provider commits step 1, then the call times out
    run = await _start(k)
    dispatch = k.coordinator._dispatch
    paused, gate = asyncio.Event(), asyncio.Event()

    async def pause_after(*args: Any, **kwargs: Any) -> Any:
        result = await dispatch(*args, **kwargs)
        if not paused.is_set():  # the approval call's first dispatch only
            paused.set()
            await gate.wait()
        return result

    k.coordinator._dispatch = pause_after  # type: ignore[method-assign]
    approval = asyncio.create_task(_decide(k, run.run_id))
    await paused.wait()
    stored = await k.store.get_run(TENANT, run.run_id)
    assert stored.state is RunState.NEEDS_RECONCILIATION
    reconciled = await k.coordinator.reconcile(k.approver, run.run_id)
    gate.set()
    await approval
    assert k.backend.create_calls == 1  # reconciliation sent nothing
    assert reconciled.state is RunState.VERIFYING
    assert (await k.store.get_run(TENANT, run.run_id)).state is RunState.VERIFYING
    assert [a.step_index for a in await _actions(k, run.run_id)] == [0]
    changes = [
        e.payload.get("to") for e in await _of(k, run.run_id, RunEventType.RUN_STATE_CHANGED)
    ]
    assert RunState.SUCCEEDED not in changes
    done = await run_resume_work(k.store, k.coordinator)  # the one queued resume item
    assert (done.state, done.reason_code) == (RunState.SUCCEEDED, ReasonCode.VERIFIED)
    assert k.backend.create_calls == 2
    assert await k.store.claim_work("probe") is None
