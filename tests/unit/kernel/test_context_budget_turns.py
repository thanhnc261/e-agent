"""12- and 20-turn conversations stay within the context budget (core plan exit evidence;
ADR 0032 §2, §3; Task 3d.5).

A scripted conversation pinned ``context_assembler: on``: three read turns, each fetching a
large note set, then a question to the user, repeated until the run has used every driver
turn. Each turn's pack must fit ``max_input_tokens`` and the evidence layer budget, old
results must be cleared after ``tool_result_retention_turns`` (their call and evidence id
kept), and the same inputs unbounded must exceed the budget, so the bound is what keeps the
conversation inside it. Runs over both stores through the ``run_store`` fixture.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import pytest
from e_agent.contracts.context import Budgets, TaskContext
from e_agent.contracts.context_pack import (
    ContextLayer,
    ContextPack,
    ContextPolicy,
    DroppedKind,
    DroppedReason,
    json_text,
    tool_return_text,
)
from e_agent.contracts.events import RunEventType
from e_agent.contracts.features import FeatureMode, Features
from e_agent.contracts.run import RunState
from e_agent.kernel.context import estimate_tokens
from e_agent.kernel.context_shadow import layer_tokens
from e_agent.sdk.ports import AskClarification, DriverInput, DriverStep, ReadRequest, RequestReads

from .conftest import CONN, READ, TENANT, Kernel

MakeKernel = Callable[..., Kernel]
POLICY = ContextPolicy()
NOTES_PER_READ = 50
NOTE_TEXT = "standup detail " * 30  # about 450 bytes per note


@dataclass
class ConversationDriver:
    """Reads on three turns, then asks the user; every fourth turn and the last ask."""

    turns: int
    driver_id: str = "conversation-driver"
    calls: int = 0
    packs: list[ContextPack | None] = field(default_factory=list)

    async def advance(self, ctx: TaskContext, step_input: DriverInput) -> DriverStep:
        self.calls += 1
        self.packs.append(step_input.context)
        if self.calls % 4 == 0 or self.calls >= self.turns:
            return AskClarification(question=f"Anything else after turn {self.calls}?")
        read = ReadRequest(
            request_id=f"r{self.calls}",
            contract_id=READ.contract_id,
            connection_id=CONN,
            arguments={"operation_key": "big"},
        )
        return RequestReads(reads=(read,))


def live_tokens(pack: ContextPack) -> int:
    """The tokens of the observations rendered with their data, not cleared."""
    stubs = {d.ref for d in pack.dropped if d.reason is DroppedReason.CLEARED}
    return sum(
        estimate_tokens(tool_return_text(o))
        for o in pack.observations
        if o.evidence.evidence_id not in stubs
    )


def _total(pack: ContextPack) -> int:
    return sum(layer_tokens(pack).values())


async def _converse(make_kernel: MakeKernel, turns: int) -> tuple[ConversationDriver, Kernel]:
    driver = ConversationDriver(turns=turns)
    k = make_kernel(
        features=Features(context_assembler=FeatureMode.ON),
        driver=driver,
        budgets=Budgets(max_driver_turns=turns, max_read_calls=turns),
    )
    for i in range(NOTES_PER_READ):
        k.backend.notes[f"n{i}"] = {"key": "big", "text": f"{i}: {NOTE_TEXT}"}
    run = await k.coordinator.start_run(k.requester, "write standup note", k.scope)
    while driver.calls < turns:
        assert run.state is RunState.WAITING_INPUT, run.reason
        run = await k.coordinator.resume_input(
            k.requester, run.run_id, f"continue after {driver.calls}", run.revision
        )
    assert run.state is RunState.WAITING_INPUT, run.reason
    assert driver.calls == turns
    return driver, k


def _check_budget(driver: ConversationDriver, turns: int) -> dict[str, int]:
    packs = [p for p in driver.packs if p is not None]
    assert len(packs) == turns, "a turn without its pack"
    cleared = 0
    largest = 0
    rendered: list[int] = []
    for turn, pack in enumerate(packs, start=1):
        tokens = layer_tokens(pack)
        total = _total(pack)
        largest = max(largest, total)
        assert total <= POLICY.max_input_tokens, (turn, total)
        assert (
            tokens.get(ContextLayer.EVIDENCE.value, 0)
            <= POLICY.layer_budgets[ContextLayer.EVIDENCE]
        ), (turn, tokens)
        stubs = {
            d.ref
            for d in pack.dropped
            if d.kind is DroppedKind.OBSERVATION and d.reason is DroppedReason.CLEARED
        }
        live = [o for o in pack.observations if o.evidence.evidence_id not in stubs]
        cleared = max(cleared, len(stubs))
        # every observation keeps its place and evidence id, cleared or not (§7.4 rule 3)
        assert {o.evidence.evidence_id for o in pack.observations} >= stubs
        # only the reads of the last `tool_result_retention_turns` turns are rendered
        assert len(live) <= POLICY.tool_result_retention_turns, (turn, len(live))
        rendered.append(live_tokens(pack))
    return {
        "turns": len(packs),
        "cleared": cleared,
        "largest": largest,
        "live_last": rendered[-1],
        "live_max": max(rendered),
    }


@pytest.mark.parametrize("turns", [12])
async def test_twelve_turn_conversation_respects_budget(
    make_kernel: MakeKernel, turns: int
) -> None:
    driver, k = await _converse(make_kernel, turns)
    counts = _check_budget(driver, turns)
    print(f"budget turns checked: {counts}")
    assert counts["turns"] == 12
    assert counts["cleared"] > 0, "nothing was cleared: the retention rule did not run"
    await _check_unbounded_exceeds(k, driver)


@pytest.mark.parametrize("turns", [20])
async def test_twenty_turn_conversation_stays_under_budget(
    make_kernel: MakeKernel, turns: int
) -> None:
    driver, k = await _converse(make_kernel, turns)
    counts = _check_budget(driver, turns)
    print(f"budget turns checked: {counts}")
    assert counts["turns"] == 20
    # the rendered observations plateau: what grows after twelve turns is stubs and the
    # ledger's ids, not observation data
    packs = [p for p in driver.packs if p is not None]
    print(f"pack tokens per turn: {[_total(p) for p in packs]}")
    # turns 12 and 20 both follow a question and hold the last three reads: the same size
    assert live_tokens(packs[-1]) == live_tokens(packs[11])
    assert _total(packs[-1]) <= POLICY.max_input_tokens
    await _check_unbounded_exceeds(k, driver)


async def _check_unbounded_exceeds(k: Kernel, driver: ConversationDriver) -> None:
    """Non-vacuous: the run's observations, unbounded, do not fit the budget, and every
    turn recorded its ``context.assembled``."""
    [run_id] = list(k.coordinator._runs)
    cont = await k.coordinator._peek_cont(TENANT, run_id)
    raw = sum(estimate_tokens(json_text(o.data)) for o in cont.observations.values())
    print(f"unbounded observation tokens: {raw}, observations: {len(cont.observations)}")
    assert raw > POLICY.max_input_tokens
    events = await k.store.list_events(TENANT, run_id)
    assembled = [e for e in events if e.type is RunEventType.CONTEXT_ASSEMBLED]
    assert len(assembled) == driver.calls
