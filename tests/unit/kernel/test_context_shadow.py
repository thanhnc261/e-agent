"""`features.context_assembler: shadow` (ADR 0032 §7, Task 3d.3, Review Focus 8).

Before each run-loop driver turn of a run pinned ``shadow``, the kernel builds the context
pack; after the turn it records ``context.compared``: per-layer estimates of the pack and of
the same inputs unbounded, the driver's ``tokens_used`` delta, drop counts and the pack
digest. The driver keeps its own history, and shadow adds no model call, provider read or
budget use. A shadow error records ``context.shadow_failed`` with a stage and a fixed
message and changes nothing else. Runs over both stores through the ``run_store`` fixture
(ENG-STORE-1).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import pytest
from e_agent.contracts.approval import ApprovalDecision
from e_agent.contracts.context import TaskContext
from e_agent.contracts.context_pack import ContextLayer, DroppedKind, DroppedReason
from e_agent.contracts.events import RunEvent, RunEventType
from e_agent.contracts.evidence import EvidenceRef
from e_agent.contracts.features import FeatureMode, Features
from e_agent.contracts.plan import ActionProposal
from e_agent.contracts.run import RunState
from e_agent.kernel import context_shadow
from e_agent.kernel.context_shadow import observation_turns, referenced_evidence
from e_agent.kernel.features import CONTEXT_SHADOW_MESSAGES
from e_agent.sdk.ports import (
    DriverInput,
    DriverStep,
    FinalAnswer,
    Observation,
    ProposeAction,
    ReadRequest,
    RequestReads,
)

from .conftest import CONN, CREATE, READ, TENANT, Kernel, NotesDriver

MakeKernel = Callable[..., Kernel]
OFF = Features()
SHADOW = Features(context_assembler=FeatureMode.SHADOW)
CONTEXT_EVENTS = {RunEventType.CONTEXT_COMPARED, RunEventType.CONTEXT_SHADOW_FAILED}
SENTINEL = "SENTINEL-3d3-shadow-exception-text"
COMPARED_KEYS = {
    "turn",
    "pack_digest",
    "pack_tokens",
    "unbounded_tokens",
    "tokens_used_delta",
    "observations",
    "dropped",
    "drop_reasons",
    "omitted_evidence",
    "truncated_evidence",
    "masked_evidence",
}
LAYERS = {layer.value for layer in ContextLayer}


@dataclass
class TokenNotesDriver(NotesDriver):
    """The notes driver, reporting a fixed token use per model call."""

    per_call: int = 7
    tokens: dict[str, int] = field(default_factory=dict)

    async def advance(self, ctx: TaskContext, step_input: DriverInput) -> DriverStep:
        self.tokens[ctx.run_id] = self.tokens.get(ctx.run_id, 0) + self.per_call
        return await super().advance(ctx, step_input)

    def tokens_used(self, run_id: str) -> int:
        return self.tokens.get(run_id, 0)


@dataclass
class ReadingDriver:
    """Reads the notes once per turn for ``reads`` turns, then proposes the note."""

    reads: int = 5
    driver_id: str = "reading-driver"
    calls: int = 0

    async def advance(self, ctx: TaskContext, step_input: DriverInput) -> DriverStep:
        self.calls += 1
        if step_input.action_result is not None:
            return FinalAnswer(text="done")
        if self.calls <= self.reads:
            request = ReadRequest(
                request_id=f"r{self.calls}",
                contract_id=READ.contract_id,
                connection_id=CONN,
                arguments={},
            )
            return RequestReads(reads=(request,))
        proposal = ActionProposal(
            contract_id=CREATE.contract_id, connection_id=CONN, arguments={"text": "standup notes"}
        )
        return ProposeAction(proposal=proposal)


async def _events(k: Kernel, run_id: str) -> list[RunEvent]:
    return await k.store.list_events(TENANT, run_id)


async def _of(k: Kernel, run_id: str, kind: RunEventType) -> list[dict[str, Any]]:
    return [e.payload for e in await _events(k, run_id) if e.type is kind]


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
    """Start the notes run and approve its write: read, propose, approve, verify."""
    run = await k.coordinator.start_run(k.requester, "write standup note", k.scope)
    assert run.state is RunState.WAITING_APPROVAL
    return await _approve(k, run.run_id)


def _without_context(types: list[RunEventType]) -> list[RunEventType]:
    return [t for t in types if t not in CONTEXT_EVENTS]


def _counted_timed(k: Kernel) -> list[int]:
    """Count the coordinator's budgeted calls (`_timed`: model, provider, verifier)."""
    calls: list[int] = []
    inner = k.coordinator._timed

    async def counted(*args: Any, **kwargs: Any) -> Any:
        calls.append(1)
        return await inner(*args, **kwargs)

    k.coordinator._timed = counted  # type: ignore[method-assign]
    return calls


# -- shadow records one comparison per driver turn ------------------------------------------
async def test_shadow_records_context_compared_per_turn(make_kernel: MakeKernel) -> None:
    driver = TokenNotesDriver(texts=["standup notes"])
    k = make_kernel(features=SHADOW, driver=driver)
    run = await _complete(k)
    assert run.state is RunState.SUCCEEDED

    events = await _events(k, run.run_id)
    compared = [e for e in events if e.type is RunEventType.CONTEXT_COMPARED]
    cont = await k.coordinator._peek_cont(TENANT, run.run_id)
    # one per run-loop turn: the read turn and the proposal turn (the post-write
    # acknowledgement turn is in verification.py, outside the run loop)
    assert [e.payload["turn"] for e in compared] == [1, 2] == list(range(1, cont.turns + 1))
    assert not [e for e in events if e.type is RunEventType.CONTEXT_SHADOW_FAILED]
    for event in compared:
        payload = event.payload
        assert set(payload) == COMPARED_KEYS
        assert payload["pack_digest"].startswith("jcs-sha256-v1:")
        assert set(payload["pack_tokens"]) <= LAYERS
        assert set(payload["pack_tokens"]) == set(payload["unbounded_tokens"])
        assert all(isinstance(v, int) and v >= 0 for v in payload["pack_tokens"].values())
        for layer, tokens in payload["pack_tokens"].items():
            assert tokens <= payload["unbounded_tokens"][layer], layer
        assert payload["tokens_used_delta"] == driver.per_call
        assert set(payload["dropped"]) == {kind.value for kind in DroppedKind}
        assert set(payload["drop_reasons"]) == {reason.value for reason in DroppedReason}
        assert event.action_id is None
    first, second = (e.payload for e in compared)
    assert (first["observations"], second["observations"]) == (0, 1)
    assert "evidence" not in first["pack_tokens"]
    assert second["pack_tokens"]["evidence"] > 0
    # each comparison is recorded right after its turn, before the step's own events
    types = [e.type for e in events]
    assert types.index(RunEventType.CONTEXT_COMPARED) < types.index(RunEventType.READ_RECORDED)
    second_at = [i for i, t in enumerate(types) if t is RunEventType.CONTEXT_COMPARED][1]
    assert types.index(RunEventType.READ_RECORDED) < second_at
    assert second_at < types.index(RunEventType.PROPOSAL_CREATED)
    # ids, counts and digests only: no observation value or task text reaches the event
    text = json.dumps([e.payload for e in compared])
    assert "standup" not in text


async def test_shadow_clears_old_observations_by_their_recorded_turn(
    make_kernel: MakeKernel,
) -> None:
    """``observation_turns`` comes from the run's events: a read recorded after turn N's
    comparison returned on turn N, so on turn 6 the reads of turns 1 and 2 are older than
    the retention (3 turns) and are cleared in the pack, never in the unbounded estimate. No
    write is in flight, so no deferred call holds clearing back."""
    k = make_kernel(features=SHADOW, driver=ReadingDriver(reads=5))
    run = await k.coordinator.start_run(k.requester, "write standup note", k.scope)
    assert run.state is RunState.WAITING_APPROVAL
    compared = await _of(k, run.run_id, RunEventType.CONTEXT_COMPARED)
    assert [p["turn"] for p in compared] == [1, 2, 3, 4, 5, 6]
    reads = {
        p["request_id"]: p["evidence_id"]
        for p in await _of(k, run.run_id, RunEventType.READ_RECORDED)
    }
    last = compared[-1]
    assert last["observations"] == 5
    assert last["omitted_evidence"] == [reads["r1"], reads["r2"]]
    assert last["drop_reasons"]["cleared"] == 2
    assert last["dropped"]["observation"] == 2
    assert last["pack_tokens"]["evidence"] < last["unbounded_tokens"]["evidence"]
    # turn 5 clears the read of turn 1 (5 - 1 > 3); turn 4 clears nothing (4 - 1 is not)
    assert compared[4]["omitted_evidence"] == [reads["r1"]]
    assert all(p["omitted_evidence"] == [] for p in compared[:4])


# -- Review Focus 8: no model call, read or budget ---------------------------------------
async def test_shadow_adds_no_model_call_read_or_budget(make_kernel: MakeKernel) -> None:
    seen: dict[str, dict[str, Any]] = {}
    for name, features in (("off", OFF), ("shadow", SHADOW)):
        driver = TokenNotesDriver(texts=["standup notes"])
        k = make_kernel(features=features, driver=driver)
        timed = _counted_timed(k)
        run = await _complete(k)
        cont = await k.coordinator._peek_cont(TENANT, run.run_id)
        events = await _events(k, run.run_id)
        seen[name] = {
            "state": (run.state, run.reason_code),
            "model_calls": driver.calls,
            "provider_reads": k.backend.read_calls,
            "provider_writes": k.backend.create_calls,
            "timed_calls": len(timed),
            "tokens": driver.tokens_used(run.run_id),
            "counters": (cont.turns, cont.read_calls, cont.repairs, cont.writes),
            "types": _without_context([e.type for e in events]),
            "context_events": len([e for e in events if e.type in CONTEXT_EVENTS]),
            "revision": run.revision,
        }
    off, shadow = seen["off"], seen["shadow"]
    assert off["context_events"] == 0
    assert shadow["context_events"] == 2
    # one more revision per comparison and nothing else
    assert shadow.pop("revision") - off.pop("revision") == 2
    shadow.pop("context_events"), off.pop("context_events")
    assert shadow == off


# -- failure: a fixed record, nothing else changes -------------------------------------------
@pytest.mark.parametrize(
    ("stage", "target"),
    [("inputs", "project_progress"), ("assemble", "assemble"), ("compare", "compared_payload")],
)
async def test_shadow_failure_records_context_shadow_failed_and_changes_nothing(
    make_kernel: MakeKernel, monkeypatch: pytest.MonkeyPatch, stage: str, target: str
) -> None:
    off = make_kernel(features=OFF)
    off_run = await _complete(off)
    off_types = [e.type for e in await _events(off, off_run.run_id)]

    def boom(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError(SENTINEL)

    monkeypatch.setattr(context_shadow, target, boom)
    k = make_kernel(features=SHADOW)
    run = await _complete(k)
    assert (run.state, run.reason_code) == (off_run.state, off_run.reason_code)
    events = await _events(k, run.run_id)
    failed = [e.payload for e in events if e.type is RunEventType.CONTEXT_SHADOW_FAILED]
    assert failed == [
        {"stage": stage, "message": CONTEXT_SHADOW_MESSAGES[stage], "turn": turn} for turn in (1, 2)
    ]
    assert not [e for e in events if e.type is RunEventType.CONTEXT_COMPARED]
    assert _without_context([e.type for e in events]) == off_types
    assert SENTINEL not in json.dumps([e.payload for e in events])
    assert (k.backend.read_calls, k.backend.create_calls) == (
        off.backend.read_calls,
        off.backend.create_calls,
    )


# -- off: today -----------------------------------------------------------------------------
async def test_off_records_no_context_event(
    make_kernel: MakeKernel, monkeypatch: pytest.MonkeyPatch
) -> None:
    def never(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("off builds no context pack")

    monkeypatch.setattr(context_shadow, "assemble", never)
    monkeypatch.setattr(context_shadow, "project_progress", never)
    k = make_kernel(features=OFF)
    run = await _complete(k)
    assert run.state is RunState.SUCCEEDED
    events = await _events(k, run.run_id)
    assert not [e for e in events if e.type in CONTEXT_EVENTS]
    stored = await k.store.load_continuation(TENANT, run.run_id)
    assert stored is not None and "modes" not in stored[0]["data"]


async def test_execution_ir_shadow_alone_records_no_context_event(
    make_kernel: MakeKernel,
) -> None:
    """Only the pinned ``context_assembler`` mode builds a pack, not another feature."""
    k = make_kernel(features=Features(execution_ir=FeatureMode.SHADOW))
    run = await _complete(k)
    assert not [e for e in await _events(k, run.run_id) if e.type in CONTEXT_EVENTS]


# -- the pure sources ------------------------------------------------------------------------
def _event(sequence: int, kind: RunEventType, payload: dict[str, Any]) -> RunEvent:
    return RunEvent(
        event_id=f"e{sequence}",
        tenant_id=TENANT,
        run_id="run-1",
        sequence=sequence,
        type=kind,
        occurred_at=datetime(2026, 10, 19, tzinfo=UTC),
        payload=payload,
    )


def test_observation_turns_come_from_the_turn_markers() -> None:
    read = RunEventType.READ_RECORDED
    events = [
        _event(1, read, {"request_id": "r0", "evidence_id": "ev0"}),  # before any marker
        _event(2, RunEventType.CONTEXT_COMPARED, {"turn": 1}),
        _event(3, read, {"request_id": "r1", "evidence_id": "ev1"}),
        _event(4, RunEventType.CONTEXT_COMPARED, {"turn": 2}),
        _event(5, read, {"request_id": "r2", "evidence_id": "ev2"}),
        _event(6, read, {"request_id": "vread_x", "evidence_id": "ev9"}),  # a verifier read
        _event(7, RunEventType.CONTEXT_SHADOW_FAILED, {"turn": 3, "stage": "assemble"}),
        _event(8, read, {"request_id": "r3", "evidence_id": "ev3"}),
        _event(9, RunEventType.CONTEXT_COMPARED, {"turn": 4}),
        _event(10, read, {"request_id": "r1", "evidence_id": "ev1b"}),  # re-read before dispatch
    ]
    turns = observation_turns(reversed(events), {"r0", "r1", "r2", "r3"})
    # unknown ages are absent, never guessed; a re-read keeps the turn the model saw it
    assert turns == {"r1": 1, "r2": 2, "r3": 3}


def _observation(request_id: str, evidence_id: str) -> Observation:
    evidence = EvidenceRef(
        evidence_id=evidence_id,
        tenant_id=TENANT,
        source="notes",
        locator="all",
        revision="rev:1",
        observed_at=datetime(2026, 10, 19, tzinfo=UTC),
        scope=TENANT,
    )
    return Observation(
        request_id=request_id, contract_id=READ.contract_id, data={}, evidence=evidence
    )


def test_referenced_evidence_is_what_proposals_bound() -> None:
    created, read = RunEventType.PROPOSAL_CREATED, RunEventType.READ_RECORDED
    events = [
        _event(1, read, {"request_id": "r1", "evidence_id": "ev1"}),
        _event(2, read, {"request_id": "r2", "evidence_id": "ev2"}),
        _event(3, read, {"request_id": "r3", "evidence_id": "ev3"}),
        _event(4, created, {"contract_id": "c", "evidence_ids": ["ev1", "ev2"]}),
        _event(5, created, {"contract_id": "c", "kind": "answer", "evidence_ids": []}),
        _event(6, created, {"contract_id": "c"}),  # a pre-ADR-0031 row: no key
        _event(7, read, {"request_id": "r1", "evidence_id": "ev1b"}),  # re-read before dispatch
    ]
    observations = {
        "r1": _observation("r1", "ev1b"),
        "r2": _observation("r2", "ev2"),
        "r3": _observation("r3", "ev3"),
    }
    assert referenced_evidence(events, observations) == frozenset({"ev1", "ev1b", "ev2"})
