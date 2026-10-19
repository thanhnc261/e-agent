"""`features.context_assembler: on` in the kernel (ADR 0032 §7-§9, Task 3d.5).

Every driver call of a run pinned ``on`` (each run-loop turn and the post-write
acknowledgement turn) passes the turn's context pack in ``DriverInput.context``, and the
kernel records ``context.assembled`` (ids, counts and a digest) after the turn. An
assembly failure falls back to the driver history only before the run's first write
reservation, on a route that is ``local`` or declares ``data_processing``; otherwise the
acknowledgement turn is skipped with ``context.failed`` and any other call ends the run
``CONTEXT_UNAVAILABLE`` (or in reconciliation while a reservation is unresolved). A run
pinned ``on`` keeps the loosest route boundary a call of it has used, and a later call on a
stricter one fails closed with ``ROUTE_BOUNDARY_UNMET`` (review D3-41). A restored driver
state whose ``rendering`` marker disagrees with the pin is refused before ``restore`` (D8).
Runs over both stores through the ``run_store`` fixture (ENG-STORE-1).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from e_agent.contracts.action import ActionState
from e_agent.contracts.approval import ApprovalDecision
from e_agent.contracts.context import TaskContext
from e_agent.contracts.context_pack import (
    ContextLayer,
    ContextPack,
    DroppedReason,
    tool_return_text,
)
from e_agent.contracts.events import RunEvent, RunEventType
from e_agent.contracts.features import FeatureMode, Features
from e_agent.contracts.plan import ActionProposal
from e_agent.contracts.run import ReasonCode, RunState
from e_agent.kernel import context_on
from e_agent.kernel.continuation import _Continuation
from e_agent.kernel.errors import ErrorCode, KernelError
from e_agent.kernel.evidence import classify
from e_agent.kernel.features import FALLBACK_MESSAGES, TERMINAL_MESSAGES
from e_agent.sdk.errors import ContextNotRendered
from e_agent.sdk.ports import (
    AskClarification,
    DriverInput,
    DriverStep,
    FinalAnswer,
    ProposeAction,
    ReadRequest,
    RequestReads,
)

from .conftest import CONN, CREATE, READ, TENANT, Kernel, NotesDriver
from .test_mode_pinning import HOSTED_DECLARED, HOSTED_UNDECLARED, LOCAL, OFF_CONTINUATION_KEYS

MakeKernel = Callable[..., Kernel]
ON = Features(context_assembler=FeatureMode.ON)
UNAVAILABLE = TERMINAL_MESSAGES[ReasonCode.CONTEXT_UNAVAILABLE]
UNMET = TERMINAL_MESSAGES[ReasonCode.ROUTE_BOUNDARY_UNMET]
MISMATCH = TERMINAL_MESSAGES[ReasonCode.DRIVER_STATE_MISMATCH]
VERIFIED_TEXT = "The approved action was independently verified."
INJECTION = Path(__file__).parent / "fixtures" / "injection"
TURN_MARKERS = {
    RunEventType.CONTEXT_ASSEMBLED,
    RunEventType.CONTEXT_COMPARED,
    RunEventType.CONTEXT_SHADOW_FAILED,
}


@dataclass
class PackNotesDriver(NotesDriver):
    """The notes driver, keeping every driver input it was given."""

    seen: list[DriverInput] = field(default_factory=list)

    async def advance(self, ctx: TaskContext, step_input: DriverInput) -> DriverStep:
        self.seen.append(step_input)
        return await super().advance(ctx, step_input)


@dataclass
class StatefulDriver:
    """Asks a question per turn (or runs the notes flow) and keeps a history it snapshots;
    ``marker`` is the ``rendering`` value its snapshot writes, as a pack-rendering driver
    does (ADR 0032 §6)."""

    notes: bool = False
    marker: str | None = None
    driver_id: str = "stateful-driver"
    calls: int = 0
    history: dict[str, list[str]] = field(default_factory=dict)
    restored: list[str] = field(default_factory=list)
    seen: list[DriverInput] = field(default_factory=list)

    async def advance(self, ctx: TaskContext, step_input: DriverInput) -> DriverStep:
        self.calls += 1
        self.seen.append(step_input)
        self.history.setdefault(ctx.run_id, []).append(f"turn-{self.calls}")
        if not self.notes:
            return AskClarification(question="Which note?")
        if step_input.action_result is not None:
            return FinalAnswer(text="done")
        if not step_input.observations:
            read = ReadRequest(
                request_id="r1", contract_id=READ.contract_id, connection_id=CONN, arguments={}
            )
            return RequestReads(reads=(read,))
        proposal = ActionProposal(
            contract_id=CREATE.contract_id, connection_id=CONN, arguments={"text": "standup"}
        )
        return ProposeAction(proposal=proposal)

    def snapshot(self, run_id: str) -> dict[str, Any] | None:
        if run_id not in self.history:
            return None
        state: dict[str, Any] = {"schema": "stateful-v1", "history": self.history[run_id]}
        if self.marker is not None:
            state["rendering"] = self.marker
        return state

    def restore(self, run_id: str, state: dict[str, Any]) -> None:
        self.restored.append(run_id)
        self.history[run_id] = list(state["history"])


async def _events(k: Kernel, run_id: str) -> list[RunEvent]:
    return await k.store.list_events(TENANT, run_id)


def _types(events: list[RunEvent]) -> list[RunEventType]:
    return [e.type for e in events]


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


async def _complete(k: Kernel) -> Any:
    run = await k.coordinator.start_run(k.requester, "write standup note", k.scope)
    assert run.state is RunState.WAITING_APPROVAL, run.reason
    return await _approve(k, run.run_id)


async def _stored_data(k: Kernel, run_id: str) -> dict[str, Any]:
    stored = await k.store.load_continuation(TENANT, run_id)
    assert stored is not None
    data: dict[str, Any] = stored[0]["data"]
    return data


def _failing_assemble(monkeypatch: pytest.MonkeyPatch, fail_on: Callable[[int], bool]) -> list[int]:
    """Patch `context_on.assemble` to raise on the calls ``fail_on`` selects (1-based)."""
    real = context_on.assemble
    calls: list[int] = []

    def patched(*args: Any, **kwargs: Any) -> ContextPack:
        calls.append(1)
        if fail_on(len(calls)):
            raise RuntimeError("SENTINEL-3d5-assembly-text")
        return real(*args, **kwargs)

    monkeypatch.setattr(context_on, "assemble", patched)
    return calls


# -- every call carries the pack --------------------------------------------------------
async def test_on_passes_pack_on_every_call(make_kernel: MakeKernel) -> None:
    driver = PackNotesDriver(texts=["standup notes"])
    k = make_kernel(features=ON, driver=driver)
    run = await _complete(k)
    assert (run.state, run.reason_code) == (RunState.SUCCEEDED, ReasonCode.VERIFIED)

    # the read turn, the proposal turn and the acknowledgement turn
    assert len(driver.seen) == 3
    packs = [step.context for step in driver.seen]
    assert all(pack is not None for pack in packs), "a driver call without the pack"
    assert len({json.dumps(dict(p.stable_prefix), sort_keys=True) for p in packs if p}) == 1
    first, second, ack = packs
    assert first is not None and second is not None and ack is not None
    assert (len(first.observations), len(second.observations), len(ack.observations)) == (0, 1, 1)
    # D3-43: the acknowledgement's tool return is ids, status and external refs only
    ack_input = driver.seen[-1]
    assert ack_input.action_result is not None
    assert set(ack_input.action_result) == {"status", "external_refs"}

    events = await _events(k, run.run_id)
    assembled = [e.payload for e in events if e.type is RunEventType.CONTEXT_ASSEMBLED]
    assert [(p["turn"], p["acknowledgement"]) for p in assembled] == [
        (1, False),
        (2, False),
        (3, True),
    ]
    assert [p["pack_digest"] for p in assembled] == [p.digest for p in packs if p]
    assert "standup" not in json.dumps(assembled)  # ids, counts, digests: no value
    types = set(_types(events))
    assert RunEventType.FEATURE_FALLBACK not in types
    assert RunEventType.CONTEXT_COMPARED not in types
    assert RunEventType.CONTEXT_FAILED not in types
    data = await _stored_data(k, run.run_id)
    assert data["context_boundary"] == "local"


async def test_off_and_shadow_runs_pass_no_pack(make_kernel: MakeKernel) -> None:
    checked = 0
    for features in (None, Features(context_assembler=FeatureMode.SHADOW)):
        driver = PackNotesDriver(texts=["standup notes"])
        k = make_kernel(features=features, driver=driver)
        run = await _complete(k)
        assert run.state is RunState.SUCCEEDED
        assert [step.context for step in driver.seen] == [None, None, None]
        events = await _events(k, run.run_id)
        assert RunEventType.CONTEXT_ASSEMBLED not in set(_types(events))
        assert "context_boundary" not in await _stored_data(k, run.run_id)
        checked += 1
    assert checked == 2


async def test_on_masks_personal_values_on_undeclared_hosted_route(
    make_kernel: MakeKernel,
) -> None:
    """The ``on`` exemption of the route rules rests on masking (ADR 0030, ADR 0032 §9): on
    an undeclared hosted route the note text (unmarked, so ``personal``) reaches the driver
    only masked, while the continuation keeps it for validation and verification."""

    @dataclass
    class KeyedDriver(PackNotesDriver):
        async def advance(self, ctx: TaskContext, step_input: DriverInput) -> DriverStep:
            if not step_input.observations and step_input.action_result is None:
                self.seen.append(step_input)
                read = ReadRequest(
                    request_id="r1",
                    contract_id=READ.contract_id,
                    connection_id=CONN,
                    arguments={"operation_key": "k1"},
                )
                return RequestReads(reads=(read,))
            return await super().advance(ctx, step_input)

    driver = KeyedDriver(texts=["standup notes"])
    k = make_kernel(features=ON, route=HOSTED_UNDECLARED, driver=driver)
    k.backend.notes["k1"] = {"key": "k1", "text": "SEEDED-PERSONAL-alice@example.com"}
    run = await k.coordinator.start_run(k.requester, "write standup note", k.scope)
    assert run.state is RunState.WAITING_APPROVAL, run.reason
    pack = driver.seen[1].context
    assert pack is not None
    returned = "".join(tool_return_text(o) for o in pack.observations)
    assert "SEEDED-PERSONAL" not in returned
    assert any(o.masked and o.partial for o in pack.observations)
    assert any(d.reason is DroppedReason.CLASS_ROUTE for d in pack.dropped)
    cont = await k.coordinator._peek_cont(TENANT, run.run_id)
    assert "SEEDED-PERSONAL" in json.dumps([o.data for o in cont.observations.values()])


# -- failure handling (ADR 0032 §7, ADR 0027) ---------------------------------------------
@pytest.mark.parametrize("route", [LOCAL, HOSTED_DECLARED], ids=["local", "declared"])
async def test_assembly_failure_before_reservation_falls_back_on_local_route(
    make_kernel: MakeKernel, monkeypatch: pytest.MonkeyPatch, route: dict[str, Any]
) -> None:
    calls = _failing_assemble(monkeypatch, lambda n: n == 1)
    driver = PackNotesDriver(texts=["standup notes"])
    k = make_kernel(features=ON, driver=driver, route=route)
    run = await _complete(k)
    assert (run.state, run.reason_code) == (RunState.SUCCEEDED, ReasonCode.VERIFIED)
    assert len(calls) == 3
    # the failed turn used the driver history; every later turn has its pack
    assert [step.context is None for step in driver.seen] == [True, False, False]

    events = await _events(k, run.run_id)
    fallbacks = [e for e in events if e.type is RunEventType.FEATURE_FALLBACK]
    assert [e.payload for e in fallbacks] == [
        {
            "feature": "context_assembler",
            "reason_code": ReasonCode.CONTEXT_ASSEMBLY_FAILED,
            "message": FALLBACK_MESSAGES[ReasonCode.CONTEXT_ASSEMBLY_FAILED],
        }
    ]
    types = _types(events)
    assert types.index(RunEventType.FEATURE_FALLBACK) < types.index(RunEventType.ACTION_RESERVED)
    assert "SENTINEL-3d5" not in json.dumps([e.payload for e in events])


async def test_assembly_failure_on_undeclared_hosted_route_fails_closed(
    make_kernel: MakeKernel, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T23: a fallback would send the unmasked history to a route that may not receive it."""
    _failing_assemble(monkeypatch, lambda _: True)
    driver = PackNotesDriver(texts=["standup notes"])
    k = make_kernel(features=ON, driver=driver, route=HOSTED_UNDECLARED)
    run = await k.coordinator.start_run(k.requester, "write standup note", k.scope)

    assert driver.calls == 0, "a model call on an undeclared hosted route without its pack"
    assert (run.state, run.reason_code, run.reason) == (
        RunState.FAILED,
        ReasonCode.CONTEXT_UNAVAILABLE,
        UNAVAILABLE,
    )
    assert classify(run.state, run.reason, "fixture", run.reason_code) == (
        "fixture:infrastructure-or-budget"
    )
    events = await _events(k, run.run_id)
    assert RunEventType.FEATURE_FALLBACK not in set(_types(events))
    assert "SENTINEL-3d5" not in json.dumps([e.payload for e in events])


async def test_assembly_failure_after_reservation_has_no_fallback(
    make_kernel: MakeKernel, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Review Focus 7: after the first reservation nothing falls back, even on a local route
    where a fallback is otherwise allowed. No live path drives a run with an unresolved
    write, so the loop is entered directly (white box), as the route-check test does."""
    driver = PackNotesDriver(texts=["standup notes"])
    k = make_kernel(features=ON, driver=driver)
    run = await k.coordinator.start_run(k.requester, "write standup note", k.scope)
    k.backend.fail_mode = "timeout"  # the write may have committed: UNKNOWN
    run = await _approve(k, run.run_id)
    assert run.state is RunState.NEEDS_RECONCILIATION
    calls_before = driver.calls

    _failing_assemble(monkeypatch, lambda _: True)
    run = await k.coordinator._drive(run, DriverInput(task=run.task))

    assert driver.calls == calls_before
    assert (run.state, run.reason_code, run.reason) == (
        RunState.NEEDS_RECONCILIATION,
        ReasonCode.CONTEXT_UNAVAILABLE,
        UNAVAILABLE,
    )
    events = await _events(k, run.run_id)
    assert RunEventType.FEATURE_FALLBACK not in set(_types(events))
    actions = await k.store.list_actions(TENANT, run.run_id)
    assert [a.state for a in actions] == [ActionState.UNKNOWN]
    assert k.backend.create_calls == 1


@pytest.mark.parametrize("failure", ["assemble", "driver"])
async def test_ack_turn_assembly_failure_skips_turn_and_keeps_verified(
    make_kernel: MakeKernel, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    """The acknowledgement turn follows a reservation: a failed pack (or a driver that
    cannot render it, D3-42) skips the turn, records ``context.failed`` and keeps the
    verified outcome with the kernel's fixed final text."""

    @dataclass
    class RefusingAckDriver(PackNotesDriver):
        async def advance(self, ctx: TaskContext, step_input: DriverInput) -> DriverStep:
            if step_input.action_result is not None:
                self.seen.append(step_input)
                raise ContextNotRendered
            return await super().advance(ctx, step_input)

    if failure == "assemble":
        _failing_assemble(monkeypatch, lambda n: n == 3)
        driver: PackNotesDriver = PackNotesDriver(texts=["standup notes"])
    else:
        driver = RefusingAckDriver(texts=["standup notes"])
    k = make_kernel(features=ON, driver=driver)
    run = await _complete(k)

    assert (run.state, run.reason_code) == (RunState.SUCCEEDED, ReasonCode.VERIFIED)
    assert driver.calls == 2
    actions = await k.store.list_actions(TENANT, run.run_id)
    assert [a.state for a in actions] == [ActionState.VERIFIED]
    events = await _events(k, run.run_id)
    failed = [e.payload for e in events if e.type is RunEventType.CONTEXT_FAILED]
    assert failed == [
        {
            "reason_code": ReasonCode.CONTEXT_UNAVAILABLE,
            "message": UNAVAILABLE,
            "turn": "acknowledgement",
        }
    ]
    finals = [e.payload["text"] for e in events if e.type is RunEventType.MESSAGE_FINAL]
    assert finals == [VERIFIED_TEXT]
    types = set(_types(events))
    assert RunEventType.FEATURE_FALLBACK not in types
    assert RunEventType.BUDGET_EXHAUSTED not in types
    acknowledged = [e for e in events if e.type is RunEventType.CONTEXT_ASSEMBLED]
    assert [e.payload["acknowledgement"] for e in acknowledged] == [False, False]


async def test_driver_missing_rendering_fails_closed(make_kernel: MakeKernel) -> None:
    """D3-42: a driver that cannot render a pending read from the pack refuses the turn
    with the typed error; the kernel ends the run ``CONTEXT_UNAVAILABLE``, never retrying
    it without the pack."""

    @dataclass
    class RefusingDriver(PackNotesDriver):
        async def advance(self, ctx: TaskContext, step_input: DriverInput) -> DriverStep:
            if step_input.observations:
                self.seen.append(step_input)
                raise ContextNotRendered
            return await super().advance(ctx, step_input)

    driver = RefusingDriver(texts=["standup notes"])
    k = make_kernel(features=ON, driver=driver)
    run = await k.coordinator.start_run(k.requester, "write standup note", k.scope)
    assert (run.state, run.reason_code, run.reason) == (
        RunState.FAILED,
        ReasonCode.CONTEXT_UNAVAILABLE,
        UNAVAILABLE,
    )
    assert len(driver.seen) == 2 and all(s.context is not None for s in driver.seen)
    events = await _events(k, run.run_id)
    assert RunEventType.FEATURE_FALLBACK not in set(_types(events))


# -- the first-call boundary (review D3-41) --------------------------------------------
async def _waiting_on(make_kernel: MakeKernel, route: dict[str, Any]) -> tuple[Kernel, Any]:
    k = make_kernel(features=ON, driver=StatefulDriver(), route=route)
    run = await k.coordinator.start_run(k.requester, "write standup note", k.scope)
    assert run.state is RunState.WAITING_INPUT
    return k, run


async def _resume_on(
    make_kernel: MakeKernel, run: Any, route: dict[str, Any], features: Features | None = ON
) -> tuple[Any, StatefulDriver]:
    driver = StatefulDriver()
    resumed = make_kernel(features=features, driver=driver, route=route)
    run = await resumed.coordinator.resume_input(
        resumed.requester, run.run_id, "the standup", run.revision
    )
    return run, driver


async def test_on_refuses_a_stricter_route_than_an_earlier_turn(make_kernel: MakeKernel) -> None:
    """The persisted driver history is masked only for the route it was built on (pack-less
    fallback turns and the model's own arguments echo values), so a pinned-``on`` run whose
    first call ran on a local route makes no call on a hosted one."""
    checked = 0
    for stricter in (HOSTED_DECLARED, HOSTED_UNDECLARED):
        k, run = await _waiting_on(make_kernel, LOCAL)
        assert (await _stored_data(k, run.run_id))["context_boundary"] == "local"
        run, driver = await _resume_on(make_kernel, run, stricter)
        assert driver.calls == 0, stricter
        assert (run.state, run.reason_code, run.reason) == (
            RunState.FAILED,
            ReasonCode.ROUTE_BOUNDARY_UNMET,
            UNMET,
        )
        checked += 1
    # the same or a looser route is allowed; a looser call lowers the recorded boundary
    k, run = await _waiting_on(make_kernel, HOSTED_UNDECLARED)
    run, driver = await _resume_on(make_kernel, run, HOSTED_UNDECLARED)
    assert (run.state, driver.calls) == (RunState.WAITING_INPUT, 1)
    run, driver = await _resume_on(make_kernel, run, LOCAL)
    assert (run.state, driver.calls) == (RunState.WAITING_INPUT, 1)
    assert (await _stored_data(k, run.run_id))["context_boundary"] == "local"
    run, driver = await _resume_on(make_kernel, run, HOSTED_UNDECLARED)
    assert (run.state, run.reason_code, driver.calls) == (
        RunState.FAILED,
        ReasonCode.ROUTE_BOUNDARY_UNMET,
        0,
    )
    checked += 1
    assert checked == 3


async def test_on_ack_turn_on_a_stricter_route_is_skipped(make_kernel: MakeKernel) -> None:
    local = make_kernel(features=ON)
    run = await local.coordinator.start_run(local.requester, "write standup note", local.scope)
    assert run.state is RunState.WAITING_APPROVAL
    hosted = make_kernel(features=ON, route=HOSTED_DECLARED)
    run = await _approve(hosted, run.run_id)
    assert hosted.driver.calls == 0
    assert (run.state, run.reason_code) == (RunState.SUCCEEDED, ReasonCode.VERIFIED)
    events = await _events(hosted, run.run_id)
    failed = [e.payload for e in events if e.type is RunEventType.CONTEXT_FAILED]
    assert failed == [
        {
            "reason_code": ReasonCode.ROUTE_BOUNDARY_UNMET,
            "message": UNMET,
            "turn": "acknowledgement",
        }
    ]


# -- per-run pinning across a profile flip (D8) ------------------------------------------
async def test_off_to_on_flip_keeps_inflight_run_on_history(make_kernel: MakeKernel) -> None:
    started = make_kernel(driver=StatefulDriver())
    run = await started.coordinator.start_run(
        started.requester, "write standup note", started.scope
    )
    assert run.state is RunState.WAITING_INPUT
    run, driver = await _resume_on(make_kernel, run, LOCAL, features=ON)

    assert run.state is RunState.WAITING_INPUT
    assert driver.restored == [run.run_id], "the history continuation was not restored"
    assert [step.context for step in driver.seen] == [None]
    assert driver.history[run.run_id] == ["turn-1", "turn-1"]
    data = await _stored_data(started, run.run_id)
    assert set(data) == OFF_CONTINUATION_KEYS
    assert _Continuation.model_validate(data).model_dump(mode="json") == data
    events = await _events(started, run.run_id)
    types = set(_types(events))
    assert not types & TURN_MARKERS
    assert RunEventType.FEATURE_FALLBACK not in types


async def test_on_to_off_flip_keeps_inflight_run_on_pack(make_kernel: MakeKernel) -> None:
    started = make_kernel(features=ON, driver=StatefulDriver(marker="pack"))
    run = await started.coordinator.start_run(
        started.requester, "write standup note", started.scope
    )
    assert run.state is RunState.WAITING_INPUT
    driver = StatefulDriver(marker="pack")
    flipped = make_kernel(driver=driver)
    run = await flipped.coordinator.resume_input(
        flipped.requester, run.run_id, "the standup", run.revision
    )
    assert run.state is RunState.WAITING_INPUT
    assert driver.restored == [run.run_id]
    assert [step.context is not None for step in driver.seen] == [True]


# -- the restore check (D8) ----------------------------------------------------------------
@pytest.mark.parametrize(
    ("features", "marker"),
    [(None, "pack"), (Features(context_assembler=FeatureMode.SHADOW), "pack"), (ON, "summary")],
    ids=["off-with-pack", "shadow-with-pack", "on-with-unknown"],
)
async def test_restore_rendering_mismatch_fails_closed(
    make_kernel: MakeKernel, features: Features | None, marker: str
) -> None:
    started = make_kernel(features=features, driver=StatefulDriver(marker=marker))
    run = await started.coordinator.start_run(
        started.requester, "write standup note", started.scope
    )
    assert run.state is RunState.WAITING_INPUT
    stored_before = await started.store.load_continuation(TENANT, run.run_id)

    driver = StatefulDriver()
    restarted = make_kernel(features=features, driver=driver)
    with pytest.raises(KernelError) as err:  # the handler's conflict, not a ValueError
        await restarted.coordinator.resume_input(
            restarted.requester, run.run_id, "the standup", run.revision
        )
    assert err.value.code is ErrorCode.CONFLICT
    assert (driver.restored, driver.calls) == ([], 0)
    run = await restarted.store.get_run(TENANT, run.run_id)
    assert (run.state, run.reason_code, run.reason) == (
        RunState.FAILED,
        ReasonCode.DRIVER_STATE_MISMATCH,
        MISMATCH,
    )
    assert classify(run.state, run.reason, "fixture", run.reason_code) == "fixture:failed"
    # the stored continuation is left as it was: nothing restored, nothing rewritten
    assert await restarted.store.load_continuation(TENANT, run.run_id) == stored_before


async def test_restore_rendering_mismatch_with_unresolved_reservation_reconciles(
    make_kernel: MakeKernel,
) -> None:
    started = make_kernel(driver=StatefulDriver(notes=True, marker="pack"))
    run = await started.coordinator.start_run(
        started.requester, "write standup note", started.scope
    )
    assert run.state is RunState.WAITING_APPROVAL
    started.backend.fail_mode = "timeout"
    run = await _approve(started, run.run_id)
    assert run.state is RunState.NEEDS_RECONCILIATION

    driver = StatefulDriver(notes=True)
    restarted = make_kernel(driver=driver)
    with pytest.raises(KernelError) as err:
        await restarted.coordinator.reconcile(restarted.approver, run.run_id)
    assert err.value.code is ErrorCode.CONFLICT
    run = await restarted.store.get_run(TENANT, run.run_id)
    assert (run.state, run.reason_code, run.reason) == (
        RunState.NEEDS_RECONCILIATION,
        ReasonCode.DRIVER_STATE_MISMATCH,
        MISMATCH,
    )
    assert (driver.restored, driver.calls) == ([], 0)
    actions = await restarted.store.list_actions(TENANT, run.run_id)
    assert [a.state for a in actions] == [ActionState.UNKNOWN]
    assert (started.backend.create_calls, restarted.backend.create_calls) == (1, 0)


async def test_pinned_on_run_without_marker_restores(make_kernel: MakeKernel) -> None:
    """No pack turn yet, or every turn so far fell back: valid (ADR 0032 §8)."""
    started = make_kernel(features=ON, driver=StatefulDriver())
    run = await started.coordinator.start_run(
        started.requester, "write standup note", started.scope
    )
    run, driver = await _resume_on(make_kernel, run, LOCAL)
    assert run.state is RunState.WAITING_INPUT
    assert driver.restored == [run.run_id]


# -- injected fixtures (T1, Review Focus 1) ----------------------------------------------
@dataclass
class NaiveDriver:
    """Decides only from what the pack shows it: reads one operation's notes, then proposes
    a note naming how many it saw and the tools its stable prefix lists."""

    driver_id: str = "naive-driver"
    calls: int = 0
    seen: list[DriverInput] = field(default_factory=list)

    async def advance(self, ctx: TaskContext, step_input: DriverInput) -> DriverStep:
        self.calls += 1
        self.seen.append(step_input)
        pack = step_input.context
        assert pack is not None
        if step_input.action_result is not None:
            return FinalAnswer(text="done")
        if not pack.observations:
            read = ReadRequest(
                request_id="r1",
                contract_id=READ.contract_id,
                connection_id=CONN,
                arguments={"operation_key": "inj"},
            )
            return RequestReads(reads=(read,))
        [observation] = pack.observations
        notes = json.loads(tool_return_text(observation))["data"]["notes"]
        tools = pack.stable_prefix[ContextLayer.TOOLS]
        text = f"standup: {len(notes)} notes; tools {len(tools)}"
        proposal = ActionProposal(
            contract_id=CREATE.contract_id, connection_id=CONN, arguments={"text": text}
        )
        return ProposeAction(proposal=proposal)


def _injected_texts() -> list[str]:
    texts: list[str] = []
    for name in ("partners.json", "products.json", "leads.json"):
        data = json.loads((INJECTION / name).read_text("utf-8"))["data"]
        records = next(iter(data.values())) if len(data) == 1 else [data]
        for record in records:
            texts += [str(v) for v in record.values()]
    return texts


async def test_injected_fixture_run_proposes_the_same_action(make_kernel: MakeKernel) -> None:
    """A run whose observations hold values that read as instructions proposes the same
    action, over the same tool set, as a run over clean values: the values reach the driver
    only inside tool returns, fenced as data, and change nothing the kernel decides."""
    injected = _injected_texts()
    outcomes: list[tuple[Any, ...]] = []
    for texts in (["clean note"] * len(injected), injected):
        driver = NaiveDriver()
        k = make_kernel(features=ON, driver=driver)
        for i, text in enumerate(texts):
            k.backend.notes[f"n{i}"] = {"key": "inj", "text": text}
        run = await k.coordinator.start_run(k.requester, "write standup note", k.scope)
        assert run.state is RunState.WAITING_APPROVAL, run.reason
        [action] = await k.store.list_actions(TENANT, run.run_id)
        prefixes = {json.dumps(dict(s.context.stable_prefix)) for s in driver.seen if s.context}
        tool_sets = {s.allowed_capabilities for s in driver.seen}
        outcomes.append((action.contract_id, action.arguments, prefixes, tool_sets))
        if texts is injected:
            pack = driver.seen[-1].context
            assert pack is not None
            returned = tool_return_text(pack.observations[0])
            assert "</untrusted-data>" not in returned  # escaped, so no fence can close
            suffix = "".join(pack.dynamic_suffix.values())
            assert not any(t in suffix for t in injected if len(t) > 12)
    clean, dirty = outcomes
    assert clean[:2] == dirty[:2]
    assert clean[2:] == dirty[2:]
    print(f"injected values checked: {len(injected)}")
    assert len(injected) >= 10
