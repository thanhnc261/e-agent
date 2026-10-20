"""A driver-state mismatch (ADR 0032 §8, D8) is found only before a driver turn; kernel-only
operations load the continuation without restoring it (reviews D3-50, D3-60, D3-61).

Every case starts a run whose stored driver snapshot carries the ``pack`` rendering marker
on a run not pinned ``on``: any restore of it is refused. Reconciliation, the crash rules,
cancel and the approval read then work as for any run and never restore; the first run-loop
turn fails the run closed; an acknowledgement turn is skipped and the run keeps its
verified outcome. The stored driver state is written back unchanged, and the run's events
reconstruct to its stored rows after each case (ADR 0031 §2-§3). Both stores, through the
kernel suite's ``run_store`` fixture.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from e_agent.contracts.action import ActionState
from e_agent.contracts.context import Budgets
from e_agent.contracts.events import RunEventType
from e_agent.contracts.run import ReasonCode, RunRecord, RunState
from e_agent.kernel.coordinator import RunCoordinator
from e_agent.kernel.features import TERMINAL_MESSAGES
from e_agent.kernel.policy import DefaultPolicy
from e_agent.kernel.reconstruct import BLOCKED_KEY, reconstruct

from tests.conformance.test_reconstruction import _approve, _assert_equal, _rows
from tests.unit.kernel import conftest as notes
from tests.unit.kernel.conftest import TENANT, Kernel, NotesDriver
from tests.unit.kernel.test_context_on import PackNotesDriver, StatefulDriver
from tests.unit.kernel.test_mode_pinning import HOSTED_UNDECLARED

run_store = notes.run_store  # the kernel suite's fixtures: both stores (ENG-STORE-1)
make_kernel = notes.make_kernel

MakeKernel = Callable[..., Kernel]
MISMATCH = TERMINAL_MESSAGES[ReasonCode.DRIVER_STATE_MISMATCH]


class Crash(BaseException):
    """A process dying mid-call."""


def _restart(k: Kernel, driver: Any = None) -> tuple[RunCoordinator, Any]:
    """A new process on the same store and backend, with a driver holding no run."""
    driver = driver or StatefulDriver(notes=True)
    fresh = RunCoordinator(
        store=k.store,
        registry=k.coordinator._registry,
        connections=k.connections,
        policy=DefaultPolicy(),
        driver=driver,
        clock=k.clock,
    )
    return fresh, driver


async def _waiting_approval(make_kernel: MakeKernel) -> tuple[Kernel, RunRecord]:
    k = make_kernel(driver=StatefulDriver(notes=True, marker="pack"))  # pinned off
    run = await k.coordinator.start_run(k.requester, "write standup note", k.scope)
    assert run.state is RunState.WAITING_APPROVAL
    return k, run


async def _driver_state(k: Kernel, run_id: str) -> dict[str, Any] | None:
    stored = await k.store.load_continuation(TENANT, run_id)
    assert stored is not None
    return stored[1]


async def _reconstructs(k: Kernel, run_id: str, name: str) -> Any:
    rows = await _rows(k.store, await k.store.get_run(TENANT, run_id))
    _assert_equal(name, reconstruct(rows.events), rows)
    return rows


def _skipped_acknowledgement(rows: Any) -> None:
    """The run kept its verified outcome; its acknowledgement turn was skipped (§8)."""
    assert (rows.run.state, rows.run.reason_code) == (RunState.SUCCEEDED, ReasonCode.VERIFIED)
    assert [a.state for a in rows.actions.values()] == [ActionState.VERIFIED]
    failed = [e.payload for e in rows.events if e.type is RunEventType.CONTEXT_FAILED]
    assert failed == [
        {
            "reason_code": ReasonCode.DRIVER_STATE_MISMATCH,
            "message": MISMATCH,
            "turn": "acknowledgement",
        }
    ]


async def test_reconcile_resolves_a_mismatched_run(make_kernel: MakeKernel) -> None:
    k, run = await _waiting_approval(make_kernel)
    k.backend.fail_mode = "timeout"  # committed, then the response was lost
    assert (await _approve(k, run.run_id)).state is RunState.NEEDS_RECONCILIATION
    k.backend.fail_mode = None
    stored = await _driver_state(k, run.run_id)
    assert stored is not None and stored["rendering"] == "pack"

    fresh, driver = _restart(k)
    reconciled = await fresh.reconcile(k.approver, run.run_id)
    assert reconciled.state is RunState.SUCCEEDED
    assert (driver.restored, driver.calls) == ([], 0)
    assert k.backend.create_calls == 1, "reconciliation never re-sends a write"
    assert await _driver_state(k, run.run_id) == stored
    _skipped_acknowledgement(await _reconstructs(k, run.run_id, "reconcile"))


async def test_recovery_moves_a_dispatching_action_to_unknown(make_kernel: MakeKernel) -> None:
    k, run = await _waiting_approval(make_kernel)
    original = k.backend.execute

    async def commit_then_die(*args: Any) -> Any:
        await original(*args)
        raise Crash

    k.backend.execute = commit_then_die  # type: ignore[method-assign]
    try:
        with pytest.raises(Crash):
            await _approve(k, run.run_id)
    finally:
        k.backend.execute = original  # type: ignore[method-assign]
    [action] = await k.store.list_actions(TENANT, run.run_id)
    assert action.state is ActionState.DISPATCHING
    stored = await _driver_state(k, run.run_id)

    fresh, driver = _restart(k)
    [recovered] = await fresh.recover()
    assert (recovered.state, recovered.reason_code) == (
        RunState.NEEDS_RECONCILIATION,
        ReasonCode.EFFECT_UNKNOWN,
    )
    rows = await _reconstructs(k, run.run_id, "recovery dispatching")
    assert [a.state for a in rows.actions.values()] == [ActionState.UNKNOWN]
    assert await _driver_state(k, run.run_id) == stored

    assert (await fresh.reconcile(k.approver, run.run_id)).state is RunState.SUCCEEDED
    assert (driver.restored, driver.calls) == ([], 0)
    assert k.backend.create_calls == 1
    _skipped_acknowledgement(await _reconstructs(k, run.run_id, "recovery reconciled"))


async def test_recovery_verifies_a_committed_action(make_kernel: MakeKernel) -> None:
    k, run = await _waiting_approval(make_kernel)
    original = k.store.record_receipt

    async def commit_then_die(*args: Any) -> Any:
        await original(*args)
        raise Crash

    k.store.record_receipt = commit_then_die  # type: ignore[method-assign]
    try:
        with pytest.raises(Crash):
            await _approve(k, run.run_id)
    finally:
        k.store.record_receipt = original  # type: ignore[method-assign]
    [action] = await k.store.list_actions(TENANT, run.run_id)
    assert action.state is ActionState.COMMITTED
    stored = await _driver_state(k, run.run_id)

    fresh, driver = _restart(k)
    [recovered] = await fresh.recover()
    assert recovered.state is RunState.SUCCEEDED
    assert (driver.restored, driver.calls) == ([], 0)
    assert k.backend.create_calls == 1
    assert await _driver_state(k, run.run_id) == stored
    _skipped_acknowledgement(await _reconstructs(k, run.run_id, "recovery committed"))


async def test_the_approval_read_and_cancel_leave_the_d8_path_alone(
    make_kernel: MakeKernel,
) -> None:
    k, run = await _waiting_approval(make_kernel)
    before = await _rows(k.store, run)
    stored = await k.store.load_continuation(TENANT, run.run_id)

    fresh, driver = _restart(k)
    presentation = await fresh.pending_approval(TENANT, run.run_id)  # a read: nothing changes
    after = await _rows(k.store, run)
    assert presentation.action_id in before.actions
    assert (after.run, after.events) == (before.run, before.events)
    assert await k.store.load_continuation(TENANT, run.run_id) == stored

    cancelled = await fresh.cancel(k.requester, run.run_id)
    assert (cancelled.state, cancelled.reason_code) == (RunState.CANCELLED, ReasonCode.CANCELLED)
    assert (driver.restored, driver.calls) == ([], 0)
    assert await _driver_state(k, run.run_id) == stored[1]  # type: ignore[index]
    rows = await _reconstructs(k, run.run_id, "cancel")
    assert [a.state for a in rows.actions.values()] == [ActionState.BLOCKED]


async def test_the_first_driver_turn_fails_closed(make_kernel: MakeKernel) -> None:
    k = make_kernel(driver=StatefulDriver(marker="pack"))  # pinned off; asks a question
    run = await k.coordinator.start_run(k.requester, "write standup note", k.scope)
    assert run.state is RunState.WAITING_INPUT
    stored = await _driver_state(k, run.run_id)

    fresh, driver = _restart(k)
    ended = await fresh.resume_input(k.requester, run.run_id, "the standup", run.revision)
    assert (ended.state, ended.reason_code, ended.reason) == (
        RunState.FAILED,
        ReasonCode.DRIVER_STATE_MISMATCH,
        MISMATCH,
    )
    assert (driver.restored, driver.calls) == ([], 0)
    assert await _driver_state(k, run.run_id) == stored
    await _reconstructs(k, run.run_id, "driver turn")


async def test_the_handler_blocks_every_blockable_action(make_kernel: MakeKernel) -> None:
    """The handler's shape with an action still waiting (review D3-62): the action is
    blocked in the same kernel call and recorded on the state change (ADR 0031 §3)."""
    k, run = await _waiting_approval(make_kernel)
    [action] = await k.store.list_actions(TENANT, run.run_id)
    fresh, _ = _restart(k)
    await fresh._load_cont(TENANT, run.run_id)
    ended = await fresh._driver_state_mismatch(run)
    assert (ended.state, ended.reason_code) == (RunState.FAILED, ReasonCode.DRIVER_STATE_MISMATCH)
    rows = await _reconstructs(k, run.run_id, "handler")
    assert [a.state for a in rows.actions.values()] == [ActionState.BLOCKED]
    changes = [e.payload for e in rows.events if e.type is RunEventType.RUN_STATE_CHANGED]
    [failed] = [c for c in changes if c["to"] == RunState.FAILED]
    assert failed[BLOCKED_KEY] == [action.action_id]


async def test_a_driver_without_restore_keeps_the_stored_snapshot(
    make_kernel: MakeKernel,
) -> None:
    """Codex's case (review D3-70): a run started on a driver that snapshots, restarted on
    one with no ``restore``; the approval read and cancel write the stored snapshot back
    unchanged, never the new driver's null."""
    k = make_kernel(driver=StatefulDriver(notes=True))  # no marker: no mismatch involved
    run = await k.coordinator.start_run(k.requester, "write standup note", k.scope)
    assert run.state is RunState.WAITING_APPROVAL
    stored = await _driver_state(k, run.run_id)
    assert stored is not None

    driver = NotesDriver(texts=[])
    assert not hasattr(driver, "restore")
    fresh, _ = _restart(k, driver)
    await fresh.pending_approval(TENANT, run.run_id)
    assert await _driver_state(k, run.run_id) == stored
    cancelled = await fresh.cancel(k.requester, run.run_id)
    assert cancelled.state is RunState.CANCELLED
    assert await _driver_state(k, run.run_id) == stored
    await _reconstructs(k, run.run_id, "cancel without restore")


@pytest.mark.parametrize("stop", ["turn_budget", "route"])
async def test_a_turn_stopped_before_the_driver_call_keeps_the_stored_snapshot(
    make_kernel: MakeKernel, stop: str
) -> None:
    """Codex's case (review D3-80): a run started on a driver that snapshots, resumed on one
    with no ``restore``, whose turn a pre-turn check stops (the turn budget, or a route the
    run may not call). The replacement driver is never called, and the stored snapshot is
    written back unchanged."""
    budgets = Budgets(max_driver_turns=1) if stop == "turn_budget" else None
    k = make_kernel(budgets=budgets, driver=StatefulDriver())  # asks a question
    run = await k.coordinator.start_run(k.requester, "write standup note", k.scope)
    assert run.state is RunState.WAITING_INPUT
    stored = await _driver_state(k, run.run_id)
    assert stored is not None

    driver = PackNotesDriver(texts=["standup notes"])
    assert not hasattr(driver, "restore")
    route = HOSTED_UNDECLARED if stop == "route" else None
    restarted = make_kernel(budgets=budgets, driver=driver, route=route)
    ended = await restarted.coordinator.resume_input(
        restarted.requester, run.run_id, "the standup", run.revision
    )
    expected = (
        ReasonCode.BUDGET_EXHAUSTED if stop == "turn_budget" else ReasonCode.ROUTE_BOUNDARY_UNMET
    )
    assert (ended.state, ended.reason_code) == (RunState.FAILED, expected)
    assert driver.seen == []
    assert await _driver_state(k, run.run_id) == stored
    await _reconstructs(k, run.run_id, f"stopped before the call ({stop})")


async def test_a_skipped_acknowledgement_keeps_the_stored_snapshot(
    make_kernel: MakeKernel,
) -> None:
    """The acknowledgement site (review D3-80): reconciliation resolves the write on a
    restart with no ``restore``, on a route the run may not call; the acknowledgement turn
    is skipped before the driver call, and the stored snapshot is written back unchanged."""
    k, run = await _waiting_approval(make_kernel)
    k.backend.fail_mode = "timeout"
    assert (await _approve(k, run.run_id)).state is RunState.NEEDS_RECONCILIATION
    stored = await _driver_state(k, run.run_id)
    assert stored is not None

    driver = PackNotesDriver(texts=["standup notes"])
    restarted = make_kernel(driver=driver, route=HOSTED_UNDECLARED)
    restarted.backend.notes.update(k.backend.notes)  # the provider's committed note
    reconciled = await restarted.coordinator.reconcile(restarted.approver, run.run_id)
    assert reconciled.state is RunState.SUCCEEDED
    assert driver.seen == []
    assert await _driver_state(k, run.run_id) == stored
    rows = await _reconstructs(k, run.run_id, "skipped acknowledgement")
    failed = [e.payload for e in rows.events if e.type is RunEventType.CONTEXT_FAILED]
    assert [f["reason_code"] for f in failed] == [ReasonCode.ROUTE_BOUNDARY_UNMET]
