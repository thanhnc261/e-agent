"""A restore mismatch (ADR 0032 §8, D8) found by recovery or cancel stops that caller, and
the run's events reconstruct to its stored rows (review D3-50, ADR 0031 §2-§3).

`_load_cont`'s handler ends the run itself: it blocks every action still waiting for
approval or dispatch in the same kernel call, recorded on the state change
(``blocked_action_ids``), and raises `DriverStateConflict`. Recovery logs and skips the run;
cancel returns the run as the handler left it. Neither writes anything more on the run
record it held. Both stores, through the kernel suite's ``run_store`` fixture.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from e_agent.contracts.action import ActionState
from e_agent.contracts.events import RunEventType
from e_agent.contracts.run import ReasonCode, RunState
from e_agent.kernel.continuation import DriverStateConflict
from e_agent.kernel.features import TERMINAL_MESSAGES
from e_agent.kernel.reconstruct import BLOCKED_KEY, reconstruct

from tests.conformance.test_reconstruction import _approve, _assert_equal, _rows
from tests.unit.kernel import conftest as notes
from tests.unit.kernel.conftest import TENANT, Kernel
from tests.unit.kernel.test_context_on import StatefulDriver

run_store = notes.run_store  # the kernel suite's fixtures: both stores (ENG-STORE-1)
make_kernel = notes.make_kernel

MakeKernel = Callable[..., Kernel]
MISMATCH = TERMINAL_MESSAGES[ReasonCode.DRIVER_STATE_MISMATCH]


class Crash(BaseException):
    """A process dying mid-call."""


def _restarted(make_kernel: MakeKernel) -> tuple[Kernel, StatefulDriver]:
    driver = StatefulDriver(notes=True)
    return make_kernel(driver=driver), driver


async def _check(k: Kernel, run_id: str, blocked: list[str]) -> None:
    rows = await _rows(k.store, await k.store.get_run(TENANT, run_id))
    assert (rows.run.state, rows.run.reason_code, rows.run.reason) == (
        RunState.FAILED,
        ReasonCode.DRIVER_STATE_MISMATCH,
        MISMATCH,
    )
    assert [a.state for a in rows.actions.values()] == [ActionState.BLOCKED]
    changes = [e.payload for e in rows.events if e.type is RunEventType.RUN_STATE_CHANGED]
    failed = [c for c in changes if c["to"] == RunState.FAILED]
    assert len(failed) == 1, "a second state change on the stale record"
    assert failed[0][BLOCKED_KEY] == blocked
    assert failed[0]["reason_code"] == ReasonCode.DRIVER_STATE_MISMATCH
    _assert_equal("restore mismatch", reconstruct(rows.events), rows)


async def test_recovery_with_an_approved_action_stops_on_a_restore_mismatch(
    make_kernel: MakeKernel, caplog: pytest.LogCaptureFixture
) -> None:
    started = make_kernel(driver=StatefulDriver(notes=True, marker="pack"))  # pinned off
    run = await started.coordinator.start_run(
        started.requester, "write standup note", started.scope
    )
    assert run.state is RunState.WAITING_APPROVAL
    original = started.store.reserve_operation

    async def die(*_args: Any, **_kwargs: Any) -> Any:
        raise Crash

    started.store.reserve_operation = die
    try:
        with pytest.raises(Crash):
            await _approve(started, run.run_id)
    finally:
        started.store.reserve_operation = original
    [action] = await started.store.list_actions(TENANT, run.run_id)
    assert action.state is ActionState.APPROVED

    restarted, driver = _restarted(make_kernel)
    recovered = await restarted.coordinator.recover()
    assert run.run_id not in {r.run_id for r in recovered}  # logged and skipped
    assert "startup recovery skipped run" in caplog.text
    assert (driver.restored, driver.calls) == ([], 0)
    await _check(restarted, run.run_id, [action.action_id])
    assert started.backend.create_calls + restarted.backend.create_calls == 0
    # the run has ended: a later recovery leaves it alone
    again = await restarted.coordinator.recover_run(TENANT, run.run_id)
    assert again.state is RunState.FAILED
    await _check(restarted, run.run_id, [action.action_id])


async def test_cancel_stops_on_a_restore_mismatch(make_kernel: MakeKernel) -> None:
    started = make_kernel(driver=StatefulDriver(notes=True, marker="pack"))  # pinned off
    run = await started.coordinator.start_run(
        started.requester, "write standup note", started.scope
    )
    assert run.state is RunState.WAITING_APPROVAL
    [action] = await started.store.list_actions(TENANT, run.run_id)
    assert action.state is ActionState.AWAITING_APPROVAL

    restarted, driver = _restarted(make_kernel)
    cancelled = await restarted.coordinator.cancel(restarted.requester, run.run_id)
    assert (cancelled.state, cancelled.reason_code) == (
        RunState.FAILED,
        ReasonCode.DRIVER_STATE_MISMATCH,
    )
    assert cancelled == await restarted.store.get_run(TENANT, run.run_id)
    assert (driver.restored, driver.calls) == ([], 0)
    await _check(restarted, run.run_id, [action.action_id])


async def test_the_handler_conflict_is_typed(make_kernel: MakeKernel) -> None:
    started = make_kernel(driver=StatefulDriver(marker="pack"))
    run = await started.coordinator.start_run(
        started.requester, "write standup note", started.scope
    )
    restarted = make_kernel(driver=StatefulDriver())
    with pytest.raises(DriverStateConflict):
        await restarted.coordinator.resume_input(
            restarted.requester, run.run_id, "the standup", run.revision
        )
