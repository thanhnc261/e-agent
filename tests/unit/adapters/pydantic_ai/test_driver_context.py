"""The pydantic-ai driver renders the kernel's context pack (Task 3d.4, target §7.4, ADR 0032).

When ``DriverInput.context`` is set, the stable prefix becomes the run's instructions, the
dynamic suffix is a per-turn message that is never written to the persisted history, and every
observation reaches the model only as the pack's ``tool_return_text`` (Review Focus 4).
Clearing keeps every tool call and return pair (Review Focus 2) and does not run while a
deferred write is pending (§7.4 rule 4). A pack-rendered run marks its snapshot
``rendering: "pack"`` (D8); a run without a pack is exactly today's.
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import AsyncIterator
from typing import Any

import pytest
from e_agent.adapters.pydantic_ai.driver import BASE_INSTRUCTIONS, STATE_SCHEMA, PydanticAiDriver
from e_agent.contracts.context_pack import (
    ContextLayer,
    Dropped,
    DroppedKind,
    DroppedReason,
    tool_return_text,
)
from e_agent.kernel.context import INSTRUCTIONS
from e_agent.sdk.errors import ContextNotRendered
from e_agent.sdk.ports import DriverInput, FinalAnswer, ProposeAction, RequestReads
from pydantic_ai import (
    ModelMessage,
    ModelMessagesTypeAdapter,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
)
from pydantic_ai.messages import ToolReturnPart, UserPromptPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from .record_on_model_request import (
    GOLDEN,
    GUIDANCE,
    NOTE,
    READ,
    RUNS,
    SPECS,
    UNDECLARED,
    WRITE,
    Script,
    assert_matches,
    call,
    ctx,
    finding,
    observation,
    pack,
    record_requests,
)

TASK = "Write a note"
OFF_SNAPSHOT_KEYS = {
    "schema",
    "pydantic_ai_version",
    "messages",
    "pending_reads",
    "pending_write",
    "pending_input",
    "rejected",
    "tokens",
}


def _returns(messages: list[ModelMessage]) -> dict[str, ToolReturnPart]:
    return {
        p.tool_call_id: p
        for m in messages
        if isinstance(m, ModelRequest)
        for p in m.parts
        if isinstance(p, ToolReturnPart)
    }


def _call_ids(messages: list[ModelMessage]) -> list[str]:
    return [
        p.tool_call_id
        for m in messages
        if isinstance(m, ModelResponse)
        for p in m.parts
        if isinstance(p, ToolCallPart)
    ]


def _return_ids(messages: list[ModelMessage]) -> list[str]:
    return [
        p.tool_call_id
        for m in messages
        if isinstance(m, ModelRequest)
        for p in m.parts
        if isinstance(p, ToolReturnPart)
    ]


def _prompts(messages: list[ModelMessage]) -> list[str]:
    return [
        str(p.content)
        for m in messages
        if isinstance(m, ModelRequest)
        for p in m.parts
        if isinstance(p, UserPromptPart)
    ]


def _persisted_prompts(snapshot: dict[str, Any]) -> list[str]:
    return _prompts(list(ModelMessagesTypeAdapter.validate_python(snapshot["messages"])))


def _snapshot(driver: PydanticAiDriver, run_id: str) -> dict[str, Any]:
    snapshot = driver.snapshot(run_id)
    assert snapshot is not None
    return snapshot


# -------------------------------------------------------------------------- rendering
async def test_driver_renders_pack() -> None:
    script = Script(
        [
            ModelResponse(parts=[call(READ, {"note_ref": "note:1"}, "c1")]),
            ModelResponse(parts=[call(WRITE, {"text": "standup"}, "w1")]),
            ModelResponse(parts=[TextPart("stopped")]),
        ]
    )
    driver = script.driver()
    run = ctx("run_render")
    first = pack()
    step = await driver.advance(run, DriverInput(task=TASK, context=first))
    assert isinstance(step, RequestReads)

    # The stable prefix is the run's instructions, after the driver's own.
    instructions = script.infos[0].instructions or ""
    assert instructions.startswith(BASE_INSTRUCTIONS)
    assert GUIDANCE[0] in instructions
    for layer in (ContextLayer.INSTRUCTIONS, ContextLayer.TASK, ContextLayer.TOOLS):
        assert first.stable_prefix[layer] in instructions
    assert INSTRUCTIONS in instructions
    # The dynamic suffix is the last part of the request, after the task prompt.
    last = script.requests[0][-1]
    assert isinstance(last, ModelRequest)
    assert isinstance(last.parts[0], UserPromptPart) and last.parts[0].content == TASK
    assert isinstance(last.parts[-1], UserPromptPart)
    assert first.dynamic_suffix[ContextLayer.LEDGER] in str(last.parts[-1].content)
    assert first.dynamic_suffix[ContextLayer.LEDGER] not in instructions

    # The read returns as the pack's rendering: numbers as strings, markup escaped.
    note = observation("c1", NOTE)
    second = pack((note,), turn=1)
    step = await driver.advance(run, DriverInput(task=TASK, observations=(note,), context=second))
    assert isinstance(step, ProposeAction)
    [rendered] = second.observations
    returned = _returns(script.requests[1])["c1"]
    assert returned.content == tool_return_text(rendered)
    payload = json.loads(returned.content)
    assert payload["evidence_id"] == "ev-c1"
    assert payload["data"]["notes"][0]["count"] == "3"
    assert "<9>" not in returned.content and "\\u003c9\\u003e" in returned.content
    # The instructions are the same on every turn of the run (§7.4 rule 2).
    assert script.infos[1].instructions == instructions

    # A blocked write returns rule ids only; the findings are in the suffix, not a prompt.
    blocked = (finding(observed="212 characters"),)
    third = pack((note,), findings=blocked, deferred_pending=True)
    step = await driver.advance(
        run,
        DriverInput(task=TASK, observations=(note,), findings=blocked, context=third),
    )
    assert isinstance(step, FinalAnswer)
    write_return = _returns(script.requests[2])["w1"].content
    assert write_return == {
        "status": "BLOCKED",
        "findings": [{"rule_id": "NOTE-001", "status": "FAIL"}],
        "details": "this turn's host context",
    }
    prompts = _prompts(script.requests[2])
    assert not any(p.startswith("Host validation feedback") for p in prompts)
    assert third.dynamic_suffix[ContextLayer.FINDINGS] in prompts[-1]
    assert "212 characters" in prompts[-1]  # local route: fenced, not masked


async def test_findings_without_pending_call_get_a_fixed_prompt() -> None:
    """Findings with no deferred call to return them on (an unverified text answer) reach the
    model through the suffix, behind a fixed prompt that holds no finding text."""
    script = Script([ModelResponse(parts=[TextPart("42")]), ModelResponse(parts=[TextPart("4")])])
    driver = script.driver()
    run = ctx("run_feedback")
    await driver.advance(run, DriverInput(task=TASK, context=pack()))
    feedback = (finding(message="the answer is not 42", observed="42"),)
    step = await driver.advance(
        run, DriverInput(task=TASK, findings=feedback, context=pack(findings=feedback))
    )
    assert isinstance(step, FinalAnswer)
    snapshot = json.dumps(_snapshot(driver, run.run_id)["messages"])
    assert "the answer is not 42" not in snapshot
    assert "the answer is not 42" in script.sent(1)


async def test_dynamic_suffix_is_not_persisted() -> None:
    script = Script(
        [
            ModelResponse(parts=[call(READ, {"note_ref": "note:1"}, "c1")]),
            ModelResponse(parts=[TextPart("done")]),
        ]
    )
    driver = script.driver()
    run = ctx("run_suffix")
    first = pack(turns=1)
    await driver.advance(run, DriverInput(task=TASK, context=first))
    suffix_one = first.dynamic_suffix[ContextLayer.LEDGER]
    assert any(suffix_one in p for p in _prompts(script.requests[0]))
    snapshot = _snapshot(driver, run.run_id)
    assert _persisted_prompts(snapshot) == [TASK]

    # A resumed driver gets the next turn's suffix only, never a stale copy.
    resumed = script.driver()
    resumed.restore(run.run_id, snapshot)
    note = observation("c1", NOTE)
    second = pack((note,), turn=1, turns=2)
    suffix_two = second.dynamic_suffix[ContextLayer.LEDGER]
    assert suffix_two != suffix_one
    step = await resumed.advance(run, DriverInput(task=TASK, observations=(note,), context=second))
    assert isinstance(step, FinalAnswer)
    prompts = _prompts(script.requests[1])
    assert sum(suffix_two in p for p in prompts) == 1
    assert not any(suffix_one in p for p in prompts)
    assert _persisted_prompts(_snapshot(resumed, run.run_id)) == [TASK]


# --------------------------------------------------------------------------- clearing
async def test_clearing_keeps_call_return_pairs() -> None:
    """Two parallel reads, cleared three turns later: both calls and both returns stay, with
    the same ids in the same order, their content the pack's stub with its evidence id."""
    script = Script(
        [
            ModelResponse(
                parts=[
                    call(READ, {"note_ref": "note:1"}, "c1"),
                    call(READ, {"note_ref": "note:2"}, "c2"),
                ]
            ),
            ModelResponse(parts=[call(READ, {"note_ref": "note:3"}, "c3")]),
            ModelResponse(parts=[call(WRITE, {"text": "standup"}, "w1")]),
            ModelResponse(parts=[TextPart("done")]),
        ]
    )
    driver = script.driver()
    run = ctx("run_clear")
    one, two = observation("c1", NOTE), observation("c2", NOTE)
    three = observation("c3", {"notes": []})
    await driver.advance(run, DriverInput(task=TASK, context=pack()))
    step = await driver.advance(
        run,
        DriverInput(
            task=TASK,
            observations=(one, two),
            context=pack((one, two), turn=1, observation_turns={"c1": 1, "c2": 1}),
        ),
    )
    assert isinstance(step, RequestReads)
    turns = {"c1": 1, "c2": 1, "c3": 5}
    clearing = pack((one, two, three), turn=5, observation_turns=turns)
    assert {
        Dropped(kind=DroppedKind.OBSERVATION, ref=f"ev-{c}", reason=DroppedReason.CLEARED)
        for c in ("c1", "c2")
    } <= set(clearing.dropped)
    step = await driver.advance(
        run, DriverInput(task=TASK, observations=(one, two, three), context=clearing)
    )
    assert isinstance(step, ProposeAction)

    sent = script.requests[2]
    assert _call_ids(sent) == ["c1", "c2", "c3"]
    assert _return_ids(sent) == ["c1", "c2", "c3"]
    stubs = {o.evidence.evidence_id: tool_return_text(o) for o in clearing.observations}
    returns = _returns(sent)
    for c in ("c1", "c2"):
        assert returns[c].content == stubs[f"ev-{c}"]
        assert returns[c].tool_name == READ.name
        stub = json.loads(returns[c].content)
        assert stub["evidence_id"] == f"ev-{c}"
        assert stub["data"] == {"omitted": "cleared"}
        assert stub["truncated"] is True
    assert json.loads(returns["c3"].content)["data"] == {"notes": []}
    # The cleared form is what is kept, so a resume sees the same pairs.
    snapshot = _snapshot(driver, run.run_id)
    resumed = script.driver()
    resumed.restore(run.run_id, snapshot)
    step = await resumed.advance(
        run,
        DriverInput(
            task=TASK,
            observations=(one, two, three),
            action_result={"status": "VERIFIED"},
            context=pack((one, two, three), turn=6, observation_turns=turns),
        ),
    )
    assert isinstance(step, FinalAnswer)
    resent = script.requests[3]
    assert _call_ids(resent) == ["c1", "c2", "c3", "w1"]
    assert _return_ids(resent) == ["c1", "c2", "c3", "w1"]
    assert _returns(resent)["c1"].content == stubs["ev-c1"]


async def test_no_clearing_with_pending_deferred_call() -> None:
    """While a write is pending (the kernel's ``pending_action_id``), the driver clears
    nothing, even when a pack asks for it (§7.4 rule 4). The write's result ends the wait:
    the acknowledgement turn, which carries ``action_result``, applies the stub, so it never
    shows an earlier turn's rendering (review D3-40)."""
    script = Script(
        [
            ModelResponse(parts=[call(READ, {"note_ref": "note:1"}, "c1")]),
            ModelResponse(parts=[call(WRITE, {"text": "standup"}, "w1")]),
            ModelResponse(parts=[call(WRITE, {"text": "short"}, "w2")]),
            ModelResponse(parts=[TextPart("done")]),
        ]
    )
    driver = script.driver()
    run = ctx("run_pending")
    note = observation("c1", NOTE)
    await driver.advance(run, DriverInput(task=TASK, context=pack()))
    before = pack((note,), turn=1, observation_turns={"c1": 1})
    step = await driver.advance(run, DriverInput(task=TASK, observations=(note,), context=before))
    assert isinstance(step, ProposeAction)
    assert _snapshot(driver, run.run_id)["pending_write"] == "w1"

    asks_to_clear = pack((note,), turn=9, observation_turns={"c1": 1})
    assert json.loads(tool_return_text(asks_to_clear.observations[0]))["data"] == {
        "omitted": "cleared"
    }
    blocked = (finding(),)
    step = await driver.advance(
        run,
        DriverInput(task=TASK, observations=(note,), findings=blocked, context=asks_to_clear),
    )
    assert isinstance(step, ProposeAction)
    sent = script.requests[2]
    assert _returns(sent)["c1"].content == tool_return_text(before.observations[0])
    assert _call_ids(sent) == ["c1", "w1"] and _return_ids(sent) == ["c1", "w1"]

    step = await driver.advance(
        run,
        DriverInput(
            task=TASK,
            observations=(note,),
            action_result={"status": "VERIFIED"},
            context=asks_to_clear,
        ),
    )
    assert isinstance(step, FinalAnswer)
    acknowledged = script.requests[3]
    assert _returns(acknowledged)["c1"].content == tool_return_text(asks_to_clear.observations[0])
    assert _call_ids(acknowledged) == ["c1", "w1", "w2"]
    assert _return_ids(acknowledged) == ["c1", "w1", "w2"]
    assert _returns(acknowledged)["w2"].content == {"status": "VERIFIED"}


async def test_pending_read_without_a_rendering_fails_closed() -> None:
    """A read the pack does not render never falls back to ``Observation.data``."""
    script = Script([ModelResponse(parts=[call(READ, {"note_ref": "note:1"}, "c1")])])
    driver = script.driver()
    run = ctx("run_missing")
    await driver.advance(run, DriverInput(task=TASK, context=pack()))
    note = observation("c1", NOTE)
    with pytest.raises(ContextNotRendered):  # typed (D3-42), never a plain ValueError
        await driver.advance(run, DriverInput(task=TASK, observations=(note,), context=pack()))
    assert len(script.requests) == 1


# ----------------------------------------------------------------------------- masking
SEEDED = "Jane Roe"


async def test_masked_value_absent_from_model_request() -> None:
    """Hosted route without ``data_processing``: a seeded ``personal`` value in a read, a
    read error and a finding never reaches the model request, and each mask is in
    ``dropped`` (T23, Review Focus 4)."""
    note = observation(
        "c1", {"notes": [{"note_ref": "note:1", "author": SEEDED, "text": "standup"}]}
    )
    read_errors = {"c2": f"NOT_FOUND: no note written by {SEEDED}"}
    blocked = (finding(message=f"{SEEDED} may not write notes", observed=f"author {SEEDED}"),)

    async def drive(*, with_pack: bool) -> tuple[Script, list[Any]]:
        script = Script(
            [
                ModelResponse(
                    parts=[
                        call(READ, {"note_ref": "note:1"}, "c1"),
                        call(READ, {"note_ref": "note:2"}, "c2"),
                    ]
                ),
                ModelResponse(parts=[call(WRITE, {"text": "standup"}, "w1")]),
                ModelResponse(parts=[call(WRITE, {"text": "standup again"}, "w2")]),
                ModelResponse(parts=[TextPart("done")]),
            ]
        )
        driver = script.driver()
        run = ctx(f"run_masked_{with_pack}")
        packs: list[Any] = [
            pack(route=UNDECLARED),
            pack((note,), route=UNDECLARED, read_errors=read_errors, turn=1),
            pack((note,), route=UNDECLARED, findings=blocked, deferred_pending=True),
            pack((note,), route=UNDECLARED),
        ]
        inputs = [
            DriverInput(task=TASK),
            DriverInput(task=TASK, observations=(note,), read_errors=read_errors),
            DriverInput(task=TASK, observations=(note,), findings=blocked),
            DriverInput(task=TASK, observations=(note,), action_result={"status": "VERIFIED"}),
        ]
        for step_input, turn_pack in zip(inputs, packs, strict=True):
            if with_pack:
                step_input = dataclasses.replace(step_input, context=turn_pack)
            await driver.advance(run, step_input)
        assert len(script.requests) == 4
        return script, packs

    # Control: without a pack the value reaches the model, so the check below can see it.
    control, _ = await drive(with_pack=False)
    assert SEEDED in control.sent(1) and SEEDED in control.sent(2)

    script, packs = await drive(with_pack=True)
    for index in range(4):
        assert SEEDED not in script.sent(index), f"request {index} carries the personal value"
    rendered = json.loads(_returns(script.requests[1])["c1"].content)
    assert rendered["data"]["notes"][0]["author"] == "[masked:personal]"
    assert rendered["masked"] is True and rendered["partial"] is True
    mask = DroppedReason.CLASS_ROUTE
    assert Dropped(kind=DroppedKind.VALUE, ref="ev-c1#/notes/0/author", reason=mask) in set(
        packs[1].dropped
    )
    assert Dropped(kind=DroppedKind.VALUE, ref="read_error:c2", reason=mask) in set(
        packs[1].dropped
    )
    assert {
        Dropped(kind=DroppedKind.VALUE, ref=f"finding:0#/{name}", reason=mask)
        for name in ("message", "expected", "observed")
    } <= set(packs[2].dropped)


# ---------------------------------------------------------------------------- snapshot
async def test_snapshot_without_context_is_unchanged() -> None:
    script = Script(
        [
            ModelResponse(parts=[call(READ, {"note_ref": "note:1"}, "c1")]),
            ModelResponse(parts=[call(WRITE, {"text": "standup"}, "w1")]),
            ModelResponse(parts=[TextPart("done")]),
            ModelResponse(parts=[TextPart("again")]),
        ]
    )
    driver = script.driver()
    run = ctx("run_off")
    note = observation("c1", NOTE)
    await driver.advance(run, DriverInput(task=TASK))
    await driver.advance(run, DriverInput(task=TASK, observations=(note,)))
    blocked = (finding(),)
    await driver.advance(run, DriverInput(task=TASK, observations=(note,), findings=blocked))
    snapshot = _snapshot(driver, run.run_id)
    assert set(snapshot) == OFF_SNAPSHOT_KEYS
    assert snapshot["schema"] == STATE_SCHEMA
    # Today's renderings: the full observation and the findings verbatim.
    assert _returns(script.requests[1])["c1"].content == {
        "data": NOTE,
        "evidence_id": "ev-c1",
    }
    assert _returns(script.requests[2])["w1"].content["findings"][0]["observed"] == (
        "212 characters"
    )
    assert script.infos[0].instructions == "\n\n".join([BASE_INSTRUCTIONS, *GUIDANCE])
    assert all(len(r[-1].parts) == 1 for r in script.requests[:1])

    # A pack turn marks the snapshot, and the marker survives a later turn without a pack
    # and a restore (D8).
    await driver.advance(run, DriverInput(task=TASK, user_input="more", context=pack()))
    marked = _snapshot(driver, run.run_id)
    assert marked["rendering"] == "pack"
    resumed = script.driver()
    resumed.restore(run.run_id, marked)
    assert _snapshot(resumed, run.run_id)["rendering"] == "pack"
    assert set(marked) == OFF_SNAPSHOT_KEYS | {"rendering"}


async def test_marker_survives_a_turn_without_a_pack() -> None:
    script = Script([ModelResponse(parts=[TextPart("a")]), ModelResponse(parts=[TextPart("b")])])
    driver = script.driver()
    run = ctx("run_marker")
    await driver.advance(run, DriverInput(task=TASK, context=pack()))
    await driver.advance(run, DriverInput(task=TASK, user_input="and then?"))
    assert _snapshot(driver, run.run_id)["rendering"] == "pack"


def test_restore_without_marker_has_none() -> None:
    driver = Script([]).driver(SPECS)
    run = ctx("run_plain")
    state = {
        "schema": STATE_SCHEMA,
        "pydantic_ai_version": __import__("pydantic_ai").__version__,
        "messages": [],
        "pending_reads": {},
        "pending_write": None,
        "pending_input": None,
        "rejected": {},
        "tokens": 0,
    }
    driver.restore(run.run_id, state)
    assert "rendering" not in _snapshot(driver, run.run_id)


# ------------------------------------------------------------------------------ golden
def _golden() -> dict[str, Any]:
    golden: dict[str, Any] = json.loads(GOLDEN.read_text("utf-8"))
    return golden


async def test_on_model_request_golden() -> None:
    golden = _golden()
    assert tuple(golden) == RUNS
    # The task, the read's return, the blocked write and the acknowledgement.
    assert assert_matches(golden, await record_requests()) == 4
    run = golden["notes-on"]
    assert run["rendering"] == "pack"
    for request in run["requests"]:
        assert request["function_tools"] and request["instructions"] and request["messages"]
    with pytest.raises(AssertionError, match="0 cases"):
        assert_matches({}, {})
    with pytest.raises(AssertionError, match="0 cases"):
        assert_matches({"notes-on": {"rendering": "pack", "requests": []}}, {})


async def test_streamed_turn_gets_the_suffix_and_does_not_persist_it() -> None:
    """With a text sink the driver streams; the suffix still reaches the request only."""
    seen: list[list[ModelMessage]] = []

    async def stream(messages: list[ModelMessage], info: AgentInfo) -> AsyncIterator[str]:
        seen.append(list(messages))
        yield "streamed answer"

    emitted: list[str] = []

    class Sink:
        async def emit(self, ctx: Any, text: str, *, new_message: bool = False) -> None:
            emitted.append(text)

    driver = PydanticAiDriver(FunctionModel(stream_function=stream), SPECS, guidance=GUIDANCE)
    driver.set_text_sink(Sink())
    run = ctx("run_stream")
    turn = pack()
    step = await driver.advance(run, DriverInput(task=TASK, context=turn))
    assert isinstance(step, FinalAnswer) and "".join(emitted) == "streamed answer"
    suffix = turn.dynamic_suffix[ContextLayer.LEDGER]
    assert len(seen) == 1 and any(suffix in p for p in _prompts(seen[0]))
    assert _persisted_prompts(_snapshot(driver, run.run_id)) == [TASK]
