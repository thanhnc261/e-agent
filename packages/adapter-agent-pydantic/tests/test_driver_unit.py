"""Driver unit behaviour: hygiene, coercion, tool exposure."""

import json
from datetime import UTC, datetime

import pytest
from e_agent.adapters.pydantic_ai import PydanticAiDriver, ToolSpec
from e_agent.adapters.pydantic_ai.driver import _coerce, strip_thinking
from e_agent.contracts.capability import EffectKind
from e_agent.contracts.context import Principal, TaskContext
from e_agent.sdk.ports import DriverInput, FinalAnswer, ProposeAction, RequestReads
from pydantic_ai import ModelMessage, ModelResponse, TextPart, ToolCallPart, models
from pydantic_ai.messages import ThinkingPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

models.ALLOW_MODEL_REQUESTS = False  # CI never calls a real model
CTX = TaskContext(
    run_id="run_u",
    tenant_id="t",
    principal=Principal(principal_id="p", tenant_id="t", roles=frozenset()),
    resource_scope=frozenset({"c"}),
    deadline=datetime(2030, 1, 1, tzinfo=UTC),
)
READ = ToolSpec(
    contract_id="notes.note.read.v1",
    effect=EffectKind.READ,
    description="read",
    parameters={"type": "object", "properties": {"topic": {"type": "string"}}},
    connection_id="c",
)
WRITE = ToolSpec(
    contract_id="notes.note.create.v1",
    effect=EffectKind.WRITE,
    description="w",
    parameters={
        "type": "object",
        "properties": {"text": {"type": "string"}, "count": {"type": "string"}},
    },
    connection_id="c",
)


def test_strip_thinking_removes_only_thinking_parts() -> None:
    msgs: list[ModelMessage] = [ModelResponse(parts=[ThinkingPart("hidden"), TextPart("shown")])]
    cleaned = strip_thinking(msgs)
    assert [type(p).__name__ for p in cleaned[0].parts] == ["TextPart"]  # type: ignore[union-attr]


def test_numbers_become_decimal_strings_only_for_string_fields() -> None:
    assert _coerce(7, {"type": "string"}) == "7"
    assert _coerce(7.50, {"type": "string"}) == "7.5"
    assert _coerce(True, {"type": "string"}) is True
    assert _coerce(7, {"type": "integer"}) == 7


@pytest.mark.asyncio
async def test_reads_then_write_then_final_with_no_thinking_in_snapshot() -> None:
    def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        assert {t.name for t in info.function_tools} == {READ.name, WRITE.name}
        turn = sum(isinstance(m, ModelResponse) for m in messages)
        if turn == 0:
            return ModelResponse(
                parts=[
                    ThinkingPart("SECRET-REASONING"),
                    ToolCallPart(READ.name, {"topic": "standup"}, "c1"),
                ]
            )
        if turn == 1:
            return ModelResponse(parts=[ToolCallPart(WRITE.name, {"text": "hi", "count": 3}, "c2")])
        return ModelResponse(parts=[TextPart("done")])

    driver = PydanticAiDriver(FunctionModel(model), [READ, WRITE])
    step = await driver.advance(CTX, DriverInput(task="write a note"))
    assert isinstance(step, RequestReads)
    assert step.reads[0].request_id == "c1" and step.reads[0].connection_id == "c"
    from e_agent.contracts.evidence import EvidenceRef
    from e_agent.sdk.ports import Observation

    obs = Observation(
        request_id="c1",
        contract_id=READ.contract_id,
        data={"n": "0"},
        evidence=EvidenceRef(
            evidence_id="e",
            tenant_id="t",
            source="s",
            locator="l",
            revision="1",
            observed_at=datetime(2026, 1, 1, tzinfo=UTC),
            scope="t",
        ),
    )
    step = await driver.advance(CTX, DriverInput(task="", observations=(obs,)))
    assert isinstance(step, ProposeAction)
    assert step.proposal.arguments == {"text": "hi", "count": "3"}
    snapshot = json.dumps(driver.snapshot(CTX.run_id))
    assert "SECRET-REASONING" not in snapshot
    step = await driver.advance(CTX, DriverInput(task="", action_result={"status": "VERIFIED"}))
    assert isinstance(step, FinalAnswer) and step.text == "done"


@pytest.mark.asyncio
async def test_snapshot_restore_resumes_in_a_new_driver() -> None:
    def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if len(messages) == 1:
            return ModelResponse(parts=[ToolCallPart(WRITE.name, {"text": "x"}, "w1")])
        return ModelResponse(parts=[TextPart("resumed")])

    first = PydanticAiDriver(FunctionModel(model), [READ, WRITE])
    assert isinstance(await first.advance(CTX, DriverInput(task="t")), ProposeAction)
    state = json.loads(json.dumps(first.snapshot(CTX.run_id)))
    second = PydanticAiDriver(FunctionModel(model), [READ, WRITE])
    second.restore(CTX.run_id, state)
    step = await second.advance(CTX, DriverInput(task="", action_result={"status": "VERIFIED"}))
    assert isinstance(step, FinalAnswer) and step.text == "resumed"


@pytest.mark.asyncio
async def test_mixed_read_and_write_defers_the_write() -> None:
    seen: list[object] = []

    def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if len(messages) == 1:
            return ModelResponse(
                parts=[
                    ToolCallPart(READ.name, {}, "r"),
                    ToolCallPart(WRITE.name, {"text": "x"}, "w"),
                ]
            )
        seen.append(messages[-1])
        return ModelResponse(parts=[TextPart("ok")])

    driver = PydanticAiDriver(FunctionModel(model), [READ, WRITE])
    step = await driver.advance(CTX, DriverInput(task="t"))
    assert isinstance(step, RequestReads) and len(step.reads) == 1
    await driver.advance(CTX, DriverInput(task=""))
    assert "read facts first" in str(seen[-1])
