"""Per-run mode pinning and the per-call route check (ADR 0032 §8, §9; Task 3b.2).

A run pins ``context_assembler``, ``kernel_repeat`` and ``grounded_answers`` when it is
prepared; the pin is written only when a mode is not ``off``, so an ``off`` continuation is
byte-identical. Before every model call `_with_tools` checks the pinned ``context_assembler``
against the current route: a run not pinned ``on``, on a route that is neither ``local`` nor
declared with ``data_processing``, makes no model call (T23). The kernel gets the route facts
as plain values; startup refuses such a route today (ADR 0030), so these tests construct the
coordinator directly, as a restart onto another route would. Runs over both stores through
the ``run_store`` fixture (ENG-STORE-1).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import pytest
from e_agent.contracts.action import ActionState
from e_agent.contracts.approval import ApprovalDecision
from e_agent.contracts.context import TaskContext
from e_agent.contracts.events import RunEventType
from e_agent.contracts.features import FeatureMode, Features, RunModes
from e_agent.contracts.run import ReasonCode, RunState
from e_agent.kernel.continuation import CONTINUATION_SCHEMA, _Continuation
from e_agent.kernel.evidence import build_evidence, classify
from e_agent.kernel.features import TERMINAL_MESSAGES
from e_agent.sdk.ports import AskClarification, DriverInput, DriverStep

from .conftest import TENANT, Kernel

MakeKernel = Callable[..., Kernel]

HOSTED_UNDECLARED = {
    "data_boundary": "hosted:unknown",
    "data_boundary_basis": "default",
    "data_processing_declared": False,
}
HOSTED_DECLARED = {**HOSTED_UNDECLARED, "data_processing_declared": True}
LOCAL = {
    "data_boundary": "local",
    "data_boundary_basis": "verified",
    "data_processing_declared": False,
}

OFF_CONTINUATION_KEYS = {
    "ctx",
    "reads",
    "observations",
    "findings",
    "turns",
    "read_calls",
    "read_errors",
    "repairs",
    "writes",
    "pending_action_id",
    "last_action_id",
    "canonical_proposal",
    "last_validation",
    "approval_requested_at",
    "active_seconds",
    "surface_digest",
}
"""The ``off`` continuation's keys as stored before Task 3b.2 (``kernel-continuation-v1``)."""

UNMET = TERMINAL_MESSAGES[ReasonCode.ROUTE_BOUNDARY_UNMET]


@dataclass
class ClarifyDriver:
    """Asks one question, then answers; counts its model calls."""

    driver_id: str = "clarify-driver"
    calls: int = 0
    seen: list[DriverInput] = field(default_factory=list)

    async def advance(self, ctx: TaskContext, step_input: DriverInput) -> DriverStep:
        self.calls += 1
        self.seen.append(step_input)
        if step_input.user_input is None:
            return AskClarification(question="Which note?")
        return AskClarification(question="Anything else?")


async def _stored(k: Kernel, run_id: str) -> dict[str, Any]:
    stored = await k.store.load_continuation(TENANT, run_id)
    assert stored is not None
    state: dict[str, Any] = stored[0]
    assert state["schema"] == CONTINUATION_SCHEMA
    return state


async def _approve(k: Kernel, run_id: str) -> Any:
    pres = await k.coordinator.pending_approval(TENANT, run_id)
    return await k.coordinator.decide(
        actor=k.approver,
        run_id=run_id,
        action_id=pres.action_id,
        action_digest=pres.digest,
        expected_run_revision=pres.run_revision,
        decision=ApprovalDecision.APPROVED,
    )


# ------------------------------------------------------------------------------ pinning
async def test_modes_are_pinned_at_start(make_kernel: MakeKernel) -> None:
    features = Features(context_assembler=FeatureMode.SHADOW, grounded_answers=FeatureMode.ON)
    pinned = RunModes(context_assembler=FeatureMode.SHADOW, grounded_answers=FeatureMode.ON)
    k = make_kernel(features=features)
    run = await k.coordinator.start_run(k.requester, "write standup note", k.scope)
    assert (await _stored(k, run.run_id))["data"]["modes"] == pinned.model_dump(mode="json")
    # admit_run stores the continuation `_prepare_run` built, pin included.
    admitted, _ = await k.coordinator.admit_run(
        k.requester,
        "write standup note",
        k.scope,
        run_id="run_admitted",
        idempotency_key="pin-1",
        request_digest="d1",
    )
    assert (await _stored(k, admitted))["data"]["modes"] == pinned.model_dump(mode="json")

    # A profile flip after start (a restart with every toggle off) leaves the run's modes.
    flipped = make_kernel()
    for run_id in (run.run_id, admitted):
        cont = await flipped.coordinator._load_cont(TENANT, run_id)
        assert flipped.coordinator._run_modes(cont) == pinned
    # ... and the flipped profile's new runs pin nothing.
    fresh = await flipped.coordinator.start_run(k.requester, "write standup note", k.scope)
    assert "modes" not in (await _stored(flipped, fresh.run_id))["data"]

    # The evidence bundle reports the run's pinned modes, whatever the exporter's profile.
    bundle = await build_evidence(
        k.store, TENANT, run.run_id, environment="fixture", versions={}, features=Features()
    )
    assert bundle["modes"] == pinned.model_dump(mode="json")
    assert bundle["features"]["context_assembler"] == "off"


async def test_execution_ir_is_not_pinned(make_kernel: MakeKernel) -> None:
    """``execution_ir`` keeps reading the profile per call, as Phase 2 shipped (ADR 0032 §8)."""
    k = make_kernel(features=Features(execution_ir=FeatureMode.SHADOW))
    run = await k.coordinator.start_run(k.requester, "write standup note", k.scope)
    assert "modes" not in (await _stored(k, run.run_id))["data"]


async def test_off_run_writes_no_pin(make_kernel: MakeKernel) -> None:
    k = make_kernel()
    run = await k.coordinator.start_run(k.requester, "write standup note", k.scope)
    assert run.state is RunState.WAITING_APPROVAL
    admitted, _ = await k.coordinator.admit_run(
        k.requester,
        "write standup note",
        k.scope,
        run_id="run_admitted_off",
        idempotency_key="off-1",
        request_digest="d1",
    )
    checked = 0
    for run_id in (run.run_id, admitted):
        data = (await _stored(k, run_id))["data"]
        assert set(data) == OFF_CONTINUATION_KEYS, run_id
        # Byte for byte: the stored data is the model's own serialisation, with no pin key.
        assert _Continuation.model_validate(data).model_dump(mode="json") == data
        checked += 1
    assert checked == 2
    bundle = await build_evidence(
        k.store, TENANT, run.run_id, environment="fixture", versions={}, features=Features()
    )
    assert "modes" not in bundle


async def test_absent_pin_means_off(make_kernel: MakeKernel) -> None:
    k = make_kernel()
    run = await k.coordinator.start_run(k.requester, "write standup note", k.scope)
    all_on = Features(
        context_assembler=FeatureMode.ON,
        kernel_repeat=FeatureMode.ON,
        grounded_answers=FeatureMode.ON,
    )
    restarted = make_kernel(features=all_on)
    cont = await restarted.coordinator._load_cont(TENANT, run.run_id)
    assert cont.modes is None
    modes = restarted.coordinator._run_modes(cont)
    assert modes == RunModes() and modes.all_off


# -------------------------------------------------------------------------- route check
@pytest.mark.parametrize(
    ("route", "pinned_on", "refused", "start_route"),
    [
        (HOSTED_UNDECLARED, False, True, None),
        (HOSTED_DECLARED, False, False, None),
        (LOCAL, False, False, None),
        # masked by the pack (ADR 0032 §9, Task 3d.5), when the run's first call was on the
        # same route; from a local first call it is a stricter route (review D3-41)
        (HOSTED_UNDECLARED, True, False, HOSTED_UNDECLARED),
        (HOSTED_UNDECLARED, True, True, None),
    ],
)
async def test_route_check_reads_the_pin_and_the_route(
    make_kernel: MakeKernel,
    route: dict[str, Any],
    pinned_on: bool,
    refused: bool,
    start_route: dict[str, Any] | None,
) -> None:
    started = make_kernel(
        driver=ClarifyDriver(),
        features=Features(context_assembler=FeatureMode.ON) if pinned_on else None,
        route=start_route,
    )
    run = await started.coordinator.start_run(
        started.requester, "write standup note", started.scope
    )
    assert run.state is RunState.WAITING_INPUT
    driver = ClarifyDriver()
    resumed = make_kernel(driver=driver, route=route)
    run = await resumed.coordinator.resume_input(
        resumed.requester, run.run_id, "the standup", run.revision
    )
    if refused:
        assert (run.state, run.reason_code, driver.calls) == (
            RunState.FAILED,
            ReasonCode.ROUTE_BOUNDARY_UNMET,
            0,
        )
    else:
        assert (run.state, driver.calls) == (RunState.WAITING_INPUT, 1)


async def test_pinned_off_run_on_undeclared_hosted_route_fails_closed(
    make_kernel: MakeKernel,
) -> None:
    """T23, Review Focus 4: a run started on a local route resumes after a restart onto an
    undeclared hosted route whose profile has ``context_assembler: on``. The run is pinned
    ``off``, so it makes no model call and fails closed through an allowed transition."""
    local = make_kernel(driver=ClarifyDriver())
    run = await local.coordinator.start_run(local.requester, "write standup note", local.scope)
    assert run.state is RunState.WAITING_INPUT
    assert "modes" not in (await _stored(local, run.run_id))["data"]

    driver = ClarifyDriver()
    hosted = make_kernel(
        driver=driver,
        features=Features(context_assembler=FeatureMode.ON),
        route=HOSTED_UNDECLARED,
    )
    run = await hosted.coordinator.resume_input(
        hosted.requester, run.run_id, "the standup", run.revision
    )

    assert driver.calls == 0, "no model call on an undeclared hosted route"
    assert (run.state, run.reason_code, run.reason) == (
        RunState.FAILED,
        ReasonCode.ROUTE_BOUNDARY_UNMET,
        UNMET,
    )
    assert (
        classify(run.state, run.reason, "fixture", run.reason_code) == "fixture:blocked-by-design"
    )
    events = await hosted.store.list_events(TENANT, run.run_id)
    changes = [e.payload for e in events if e.type is RunEventType.RUN_STATE_CHANGED]
    assert changes[-1] == {
        "from": RunState.RUNNING,
        "to": RunState.FAILED,
        "reason": UNMET,
        "reason_code": ReasonCode.ROUTE_BOUNDARY_UNMET,
    }
    assert events[-1].type is RunEventType.RUN_TERMINAL
    assert RunEventType.MESSAGE_FINAL not in {e.type for e in events}


async def test_route_check_with_unresolved_reservation_goes_to_reconciliation(
    make_kernel: MakeKernel,
) -> None:
    """With an unresolved reservation the run goes to reconciliation, not FAILED, and no
    write is re-sent. No live path drives a run with an unresolved write today, so the
    driver loop is entered directly on the restarted coordinator (white box)."""
    local = make_kernel()
    run = await local.coordinator.start_run(local.requester, "write standup note", local.scope)
    local.backend.fail_mode = "timeout"  # the write may have committed: UNKNOWN
    run = await _approve(local, run.run_id)
    assert run.state is RunState.NEEDS_RECONCILIATION
    assert local.backend.create_calls == 1

    driver = ClarifyDriver()
    hosted = make_kernel(driver=driver, route=HOSTED_UNDECLARED)
    run = await hosted.coordinator._drive(run, DriverInput(task=run.task))

    assert driver.calls == 0
    assert (run.state, run.reason_code, run.reason) == (
        RunState.NEEDS_RECONCILIATION,
        ReasonCode.ROUTE_BOUNDARY_UNMET,
        UNMET,
    )
    actions = await hosted.store.list_actions(TENANT, run.run_id)
    assert [a.state for a in actions] == [ActionState.UNKNOWN]
    assert (local.backend.create_calls, hosted.backend.create_calls) == (1, 0)


async def test_route_check_skips_ack_turn_and_keeps_verified(make_kernel: MakeKernel) -> None:
    """The acknowledgement turn of a verified write on an undeclared hosted route makes no
    model call: it is skipped and recorded with ``context.failed``, and the run keeps its
    verified outcome with the kernel's fixed final text."""
    local = make_kernel()
    run = await local.coordinator.start_run(local.requester, "write standup note", local.scope)
    assert run.state is RunState.WAITING_APPROVAL
    calls_before = local.driver.calls

    hosted = make_kernel(route=HOSTED_UNDECLARED)
    run = await _approve(hosted, run.run_id)

    assert hosted.driver.calls == 0, "the acknowledgement turn made a model call"
    assert local.driver.calls == calls_before
    assert (run.state, run.reason_code) == (RunState.SUCCEEDED, ReasonCode.VERIFIED)
    actions = await hosted.store.list_actions(TENANT, run.run_id)
    assert [a.state for a in actions] == [ActionState.VERIFIED]
    events = await hosted.store.list_events(TENANT, run.run_id)
    failed = [e for e in events if e.type is RunEventType.CONTEXT_FAILED]
    assert [e.payload for e in failed] == [
        {
            "reason_code": ReasonCode.ROUTE_BOUNDARY_UNMET,
            "message": UNMET,
            "turn": "acknowledgement",
        }
    ]
    finals = [e.payload["text"] for e in events if e.type is RunEventType.MESSAGE_FINAL]
    assert finals == ["The approved action was independently verified."]
    assert RunEventType.BUDGET_EXHAUSTED not in {e.type for e in events}


async def test_ack_turn_on_a_local_route_is_unchanged(make_kernel: MakeKernel) -> None:
    """Control: the same approval on the local route makes the acknowledgement call and
    records no ``context.failed``."""
    k = make_kernel()
    run = await k.coordinator.start_run(k.requester, "write standup note", k.scope)
    calls = k.driver.calls
    run = await _approve(k, run.run_id)
    assert (run.state, k.driver.calls) == (RunState.SUCCEEDED, calls + 1)
    events = await k.store.list_events(TENANT, run.run_id)
    assert RunEventType.CONTEXT_FAILED not in {e.type for e in events}
    assert [e.payload["text"] for e in events if e.type is RunEventType.MESSAGE_FINAL] == ["done"]
