"""Restart and crash-boundary recovery (MVP design §9 crash/retry rules)."""

from collections.abc import Callable
from typing import Any

import pytest
from e_agent.contracts.action import ActionState
from e_agent.contracts.approval import ApprovalDecision
from e_agent.contracts.run import RunState
from e_agent.kernel.coordinator import RunCoordinator
from e_agent.kernel.policy import DefaultPolicy

from .conftest import TENANT, Kernel, NotesDriver

pytestmark = pytest.mark.asyncio
MakeKernel = Callable[..., Kernel]


class Crash(BaseException):
    """Simulates the process dying (not an Exception, so nothing catches it)."""


def restart(k: Kernel) -> RunCoordinator:
    """A new process: same durable store, fresh coordinator and driver instances."""
    return RunCoordinator(
        store=k.store,
        registry=k.coordinator._registry,
        connections=k.connections,
        policy=DefaultPolicy(),
        driver=NotesDriver(texts=[]),
        clock=k.clock,
    )


async def _approve(coordinator: RunCoordinator, k: Kernel, run_id: str):  # type: ignore[no-untyped-def]
    pres = await coordinator.pending_approval(TENANT, run_id)
    return await coordinator.decide(
        actor=k.approver,
        run_id=run_id,
        action_id=pres.action_id,
        action_digest=pres.digest,
        expected_run_revision=pres.run_revision,
        decision=ApprovalDecision.APPROVED,
    )


async def test_waiting_approval_survives_restart(make_kernel: MakeKernel) -> None:
    k = make_kernel()
    run = await k.coordinator.start_run(k.requester, "x", k.scope)
    fresh = restart(k)
    await fresh.recover()
    run = await _approve(fresh, k, run.run_id)
    assert run.state is RunState.SUCCEEDED
    assert k.backend.create_calls == 1


async def test_crash_during_provider_call_becomes_unknown(make_kernel: MakeKernel) -> None:
    k = make_kernel()
    run = await k.coordinator.start_run(k.requester, "x", k.scope)
    original = k.backend.execute

    async def commit_then_die(*args: Any) -> Any:
        await original(*args)
        raise Crash

    k.backend.execute = commit_then_die  # type: ignore[method-assign]
    with pytest.raises(Crash):
        await _approve(k.coordinator, k, run.run_id)
    k.backend.execute = original  # type: ignore[method-assign]
    fresh = restart(k)
    [recovered] = await fresh.recover()
    assert recovered.state is RunState.NEEDS_RECONCILIATION
    run = await fresh.reconcile(k.approver, run.run_id)
    assert run.state is RunState.SUCCEEDED
    assert k.backend.create_calls == 1, "recovery never re-sends a write"


async def test_crash_after_reservation_before_dispatch_blocks(make_kernel: MakeKernel) -> None:
    k = make_kernel()
    run = await k.coordinator.start_run(k.requester, "x", k.scope)
    original = k.store.put_action

    async def die_on_dispatching(action, expected, events):  # type: ignore[no-untyped-def]
        if action.state is ActionState.DISPATCHING:
            raise Crash
        return await original(action, expected, events)

    k.store.put_action = die_on_dispatching  # type: ignore[method-assign]
    with pytest.raises(Crash):
        await _approve(k.coordinator, k, run.run_id)
    k.store.put_action = original  # type: ignore[method-assign]
    [recovered] = await restart(k).recover()
    assert recovered.state is RunState.FAILED
    assert k.backend.create_calls == 0
    states = [a.state for a in await k.store.list_actions(TENANT, run.run_id)]
    assert states == [ActionState.BLOCKED]


async def test_crash_before_receipt_persisted_reconciles_by_operation(
    make_kernel: MakeKernel,
) -> None:
    k = make_kernel()
    run = await k.coordinator.start_run(k.requester, "x", k.scope)
    original = k.store.record_receipt

    async def die(*args: Any) -> Any:
        raise Crash

    k.store.record_receipt = die  # type: ignore[method-assign]
    with pytest.raises(Crash):
        await _approve(k.coordinator, k, run.run_id)
    k.store.record_receipt = original  # type: ignore[method-assign]
    assert k.backend.create_calls == 1  # the provider committed
    fresh = restart(k)
    await fresh.recover()
    run = await fresh.reconcile(k.approver, run.run_id)
    assert run.state is RunState.SUCCEEDED
    assert k.backend.create_calls == 1


async def test_crash_during_driver_turn_fails_without_effects(make_kernel: MakeKernel) -> None:
    k = make_kernel()

    async def die(*args: Any) -> Any:
        raise Crash

    k.backend.read = die  # type: ignore[method-assign]
    with pytest.raises(Crash):
        await k.coordinator.start_run(k.requester, "x", k.scope)
    [recovered] = await restart(k).recover()
    assert recovered.state is RunState.FAILED
    assert k.backend.create_calls == 0
