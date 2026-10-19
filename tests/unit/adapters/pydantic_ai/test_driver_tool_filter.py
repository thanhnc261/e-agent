"""The driver offers only the run's allowed tools on a turn (Task 2c.6, owner decision D6).

One driver serves every task kind, so the run's tool set reaches it per turn through
`DriverInput.allowed_capabilities`; ``None`` offers today's full set. The kernel is the
boundary; this filter only shapes what the model sees.
"""

from datetime import UTC, datetime

import pytest
from e_agent.adapters.pydantic_ai import PydanticAiDriver, ToolSpec
from e_agent.contracts.capability import EffectKind
from e_agent.contracts.context import Principal, TaskContext
from e_agent.sdk.ports import DriverInput, FinalAnswer, ProposeAction, RequestReads
from pydantic_ai import ModelMessage, ModelResponse, TextPart, ToolCallPart, models
from pydantic_ai.models.function import AgentInfo, FunctionModel

models.ALLOW_MODEL_REQUESTS = False  # CI never calls a real model


def _ctx(run_id: str) -> TaskContext:
    return TaskContext(
        run_id=run_id,
        tenant_id="t",
        principal=Principal(principal_id="p", tenant_id="t", roles=frozenset()),
        resource_scope=frozenset({"c"}),
        deadline=datetime(2030, 1, 1, tzinfo=UTC),
    )


def _spec(contract_id: str, effect: EffectKind) -> ToolSpec:
    return ToolSpec(
        contract_id=contract_id,
        effect=effect,
        description=contract_id,
        parameters={"type": "object", "properties": {"text": {"type": "string"}}},
        connection_id="c",
    )


READ = _spec("notes.note.read.v1", EffectKind.READ)
WRITE = _spec("notes.note.create.v1", EffectKind.WRITE)
OTHER = _spec("notes.note.delete.v1", EffectKind.WRITE)
CLARIFY = "request_clarification"


@pytest.mark.asyncio
async def test_driver_offers_only_allowed_tools() -> None:
    offered: list[set[str]] = []

    def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        names = {t.name for t in info.function_tools}
        offered.append(names)
        for spec in (READ, WRITE):  # call the first business tool on offer
            if spec.name in names:
                return ModelResponse(parts=[ToolCallPart(spec.name, {"text": "x"}, "c1")])
        return ModelResponse(parts=[TextPart("no tool")])

    driver = PydanticAiDriver(FunctionModel(model), [READ, WRITE, OTHER])
    cases = [
        (None, {READ.name, WRITE.name, OTHER.name, CLARIFY}),  # today's set
        ((READ.contract_id, WRITE.contract_id), {READ.name, WRITE.name, CLARIFY}),
        ((WRITE.contract_id, "notes.unknown.v1"), {WRITE.name, CLARIFY}),
        ((), {CLARIFY}),
    ]
    for index, (allowed, expected) in enumerate(cases):
        offered.clear()
        ctx = _ctx(f"run_{index}")
        step = await driver.advance(ctx, DriverInput(task="t", allowed_capabilities=allowed))
        assert offered == [expected], allowed
        # Deferred semantics survive the filter: the call comes back to the kernel.
        if allowed is None or READ.contract_id in allowed:
            assert isinstance(step, RequestReads)
            assert step.reads[0].contract_id == READ.contract_id
        elif WRITE.contract_id in allowed:
            assert isinstance(step, ProposeAction)
            assert step.proposal.contract_id == WRITE.contract_id
        else:
            assert isinstance(step, FinalAnswer)
    print(f"tool filter cases: {len(cases)}")
    assert len(cases) == 4


@pytest.mark.asyncio
async def test_driver_filter_refuses_a_call_to_a_tool_not_on_offer() -> None:
    """A call to a tool outside the turn's set never reaches the kernel: the framework
    answers it as an unknown tool and the model retries with the offered set."""
    offered: list[set[str]] = []

    def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        offered.append({t.name for t in info.function_tools})
        if len(offered) == 1:  # ignores the offer and calls the read anyway
            return ModelResponse(parts=[ToolCallPart(READ.name, {"text": "x"}, "c1")])
        return ModelResponse(parts=[ToolCallPart(WRITE.name, {"text": "hi"}, "c2")])

    driver = PydanticAiDriver(FunctionModel(model), [READ, WRITE])
    step = await driver.advance(
        _ctx("run_refused"), DriverInput(task="t", allowed_capabilities=(WRITE.contract_id,))
    )
    assert isinstance(step, ProposeAction)
    assert step.proposal.contract_id == WRITE.contract_id
    assert offered == [{WRITE.name, CLARIFY}] * 2


@pytest.mark.asyncio
async def test_driver_filter_applies_per_turn() -> None:
    """The set is read on every turn; a later turn with another set offers that set."""
    offered: list[set[str]] = []

    def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        offered.append({t.name for t in info.function_tools})
        turn = sum(isinstance(m, ModelResponse) for m in messages)
        if turn == 0:
            return ModelResponse(parts=[ToolCallPart(READ.name, {"text": "x"}, "c1")])
        return ModelResponse(parts=[ToolCallPart(WRITE.name, {"text": "hi"}, "c2")])

    driver = PydanticAiDriver(FunctionModel(model), [READ, WRITE, OTHER])
    ctx = _ctx("run_turns")
    allowed = (READ.contract_id, WRITE.contract_id)
    first = await driver.advance(ctx, DriverInput(task="t", allowed_capabilities=allowed))
    assert isinstance(first, RequestReads)
    second = await driver.advance(
        ctx, DriverInput(task="t", allowed_capabilities=(WRITE.contract_id,))
    )
    assert isinstance(second, ProposeAction)
    assert offered == [{READ.name, WRITE.name, CLARIFY}, {WRITE.name, CLARIFY}]
