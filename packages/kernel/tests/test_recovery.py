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


async def _crash_two_runs(k: Kernel) -> None:
    async def die(*args: Any) -> Any:
        raise Crash

    k.backend.read = die  # type: ignore[method-assign]
    for _ in range(2):
        with pytest.raises(Crash):
            await k.coordinator.start_run(k.requester, "x", k.scope)


async def test_one_failing_run_does_not_stop_recovery_of_the_others(
    make_kernel: MakeKernel, caplog: pytest.LogCaptureFixture
) -> None:
    k = make_kernel()
    await _crash_two_runs(k)
    first, second = (r.run_id for r in await k.store.list_unfinished_runs())
    fresh = restart(k)
    real = fresh._recover_run

    async def flaky(run: Any) -> Any:
        if run.run_id == first:
            raise RuntimeError("corrupt continuation")
        return await real(run)

    fresh._recover_run = flaky  # type: ignore[method-assign]
    with caplog.at_level("WARNING"):
        recovered = await fresh.recover()
    assert [r.run_id for r in recovered] == [second]
    assert recovered[0].state is RunState.FAILED
    assert (await k.store.get_run(TENANT, first)).state is RunState.RUNNING
    [record] = [r for r in caplog.records if "skipped run" in r.getMessage()]
    assert first in record.getMessage() and record.exc_info is not None


async def test_cancellation_is_not_swallowed_by_the_per_run_guard(make_kernel: MakeKernel) -> None:
    import asyncio

    k = make_kernel()
    await _crash_two_runs(k)
    fresh = restart(k)

    async def cancelled(run: Any) -> Any:
        raise asyncio.CancelledError

    fresh._recover_run = cancelled  # type: ignore[method-assign]
    with pytest.raises(asyncio.CancelledError):
        await fresh.recover()


@pytest.mark.parametrize("boundary", ["record_receipt", "record_outcome"])
async def test_recovery_uses_durable_effect_when_run_state_lags(
    make_kernel: MakeKernel,
    boundary: str,
) -> None:
    k = make_kernel()
    run = await k.coordinator.start_run(k.requester, "x", k.scope)
    original = getattr(k.store, boundary)

    async def commit_then_die(*args: Any) -> Any:
        await original(*args)
        raise Crash

    setattr(k.store, boundary, commit_then_die)
    with pytest.raises(Crash):
        await _approve(k.coordinator, k, run.run_id)
    setattr(k.store, boundary, original)
    [recovered] = await restart(k).recover()
    assert recovered.state is RunState.SUCCEEDED
    assert k.backend.create_calls == 1
    assert [a.state for a in await k.store.list_actions(TENANT, run.run_id)] == [
        ActionState.VERIFIED
    ]


async def test_verified_earlier_answer_cannot_hide_unknown_write(make_kernel: MakeKernel) -> None:
    from e_agent.contracts.common import new_id

    k = make_kernel()
    k.backend.fail_mode = "timeout"
    run = await k.coordinator.start_run(k.requester, "x", k.scope)
    run = await _approve(k.coordinator, k, run.run_id)
    assert run.state is RunState.NEEDS_RECONCILIATION
    [write] = await k.store.list_actions(TENANT, run.run_id)
    answer = write.model_copy(
        update={
            "action_id": new_id("act"),
            "contract_id": "notes.answer.v1",
            "state": ActionState.VERIFIED,
            "revision": 1,
        }
    )
    await k.store.put_action(answer, None, [])
    recovered = await restart(k).recover_run(TENANT, run.run_id)
    assert recovered.state is RunState.NEEDS_RECONCILIATION
    assert k.backend.create_calls == 1


class _AskDriver:
    driver_id = "ask-driver"

    async def advance(self, ctx: Any, step_input: Any) -> Any:
        from e_agent.sdk.ports import AskClarification

        return AskClarification(question="which note?")


async def test_waiting_input_run_with_failed_answer_verification_recovers_to_failed(
    make_kernel: MakeKernel,
) -> None:
    """`_recover_run` fails a run whose latest action is VERIFICATION_FAILED even while the
    run waits for input (an answer failed verification with repairs left, then the driver
    asked a question). That WAITING_INPUT->FAILED pair must stay in the transition table,
    otherwise one such run raises CONFLICT and aborts startup recovery."""
    from e_agent.contracts.common import new_id
    from e_agent.contracts.events import RunEventType

    k = make_kernel()
    template_run = await k.coordinator.start_run(k.requester, "x", k.scope)
    [template] = await k.store.list_actions(TENANT, template_run.run_id)
    k.coordinator._driver = _AskDriver()  # type: ignore[assignment]
    run = await k.coordinator.start_run(k.requester, "y", k.scope)
    assert run.state is RunState.WAITING_INPUT
    failed_answer = template.model_copy(
        update={
            "action_id": new_id("act"),
            "run_id": run.run_id,
            "state": ActionState.VERIFICATION_FAILED,
            "revision": 1,
        }
    )
    await k.store.put_action(
        failed_answer,
        None,
        [(RunEventType.PROPOSAL_CREATED, {}, failed_answer.action_id)],
    )
    recovered = await restart(k).recover_run(TENANT, run.run_id)
    assert recovered.state is RunState.FAILED
    assert recovered.reason == "outcome verification failed"
