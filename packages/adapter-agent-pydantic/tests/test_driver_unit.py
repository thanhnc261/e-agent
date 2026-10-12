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
        assert {t.name for t in info.function_tools} == {
            READ.name,
            WRITE.name,
            "request_clarification",
        }
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


@pytest.mark.asyncio
async def test_streaming_emits_only_public_text_not_thinking_or_tool_arguments() -> None:
    from pydantic_ai.models.function import DeltaThinkingPart

    async def stream_model(messages, info):
        yield {0: DeltaThinkingPart(content="HIDDEN-REASONING")}
        yield "Public "
        yield "answer"

    emitted = []

    class Sink:
        async def emit(self, ctx, text, *, new_message=False):
            emitted.append((text, new_message))

    driver = PydanticAiDriver(FunctionModel(stream_function=stream_model), [])
    driver.set_text_sink(Sink())
    result = await driver.advance(CTX, DriverInput(task="answer"))
    assert isinstance(result, FinalAnswer)
    assert "".join(text for text, _ in emitted) == "Public answer"
    assert emitted[0][1] is True
    assert "HIDDEN-REASONING" not in json.dumps(driver.snapshot(CTX.run_id))


async def test_token_usage_is_cumulative_across_restored_continuation() -> None:
    from e_agent.contracts.context import Budgets
    from e_agent.sdk.errors import DriverBudgetExceeded
    from pydantic_ai.usage import RequestUsage

    def model(messages, info):
        return ModelResponse(
            parts=[ToolCallPart(READ.name, {}, "r1")],
            usage=RequestUsage(input_tokens=10, output_tokens=5),
        )

    ctx = CTX.model_copy(update={"budgets": Budgets(max_model_tokens=20)})
    first = PydanticAiDriver(FunctionModel(model), [READ])
    assert isinstance(await first.advance(ctx, DriverInput(task="answer")), RequestReads)
    assert first.tokens_used(ctx.run_id) == 15
    state = json.loads(json.dumps(first.snapshot(ctx.run_id)))
    restored = PydanticAiDriver(FunctionModel(model), [READ])
    restored.restore(ctx.run_id, state)
    with pytest.raises(DriverBudgetExceeded, match="model usage"):
        await restored.advance(ctx, DriverInput(task="answer", user_input="next question"))
    assert restored.tokens_used(ctx.run_id) == 30


async def test_clarification_tool_resumes_after_restore_without_granting_authority():
    from e_agent.sdk.ports import AskClarification

    def model(messages, info):
        if len(messages) == 1:
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        "request_clarification", {"question": "Which customer?"}, "input-1"
                    )
                ]
            )
        assert "customer:acme" in str(messages[-1])
        return ModelResponse(parts=[TextPart("Received your customer reference.")])

    driver = PydanticAiDriver(FunctionModel(model), [READ, WRITE])
    result = await driver.advance(CTX, DriverInput(task="create a quotation"))
    assert isinstance(result, AskClarification) and result.question == "Which customer?"
    snapshot = json.loads(json.dumps(driver.snapshot(CTX.run_id)))
    restored = PydanticAiDriver(FunctionModel(model), [READ, WRITE])
    restored.restore(CTX.run_id, snapshot)
    resumed = await restored.advance(
        CTX, DriverInput(task="create a quotation", user_input="customer:acme")
    )
    assert isinstance(resumed, FinalAnswer)
    assert CTX.resource_scope == frozenset({"c"})


async def test_reasoning_tags_split_across_text_deltas_never_escape_or_persist():
    async def stream(messages, info):
        for fragment in ["<thi", "nk>HIDDEN-TEXT-REASONING</th", "ink>Public ", "answer"]:
            yield fragment

    emitted = []

    class Sink:
        async def emit(self, ctx, text, *, new_message=False):
            emitted.append(text)

    driver = PydanticAiDriver(FunctionModel(stream_function=stream), [])
    driver.set_text_sink(Sink())
    result = await driver.advance(CTX, DriverInput(task="answer"))
    assert isinstance(result, FinalAnswer) and result.text == "Public answer"
    assert "".join(emitted) == "Public answer"
    assert "HIDDEN-TEXT-REASONING" not in json.dumps(driver.snapshot(CTX.run_id))


def test_reasoning_split_between_text_parts_is_removed_from_history():
    response = ModelResponse(
        parts=[TextPart("<think>"), TextPart("HIDDEN-MULTIPART</think>Public answer")],
        provider_details={"reasoning": "HIDDEN-PROVIDER-METADATA"},
    )
    clean = strip_thinking([response])
    assert "HIDDEN" not in str(clean)
    assert "Public answer" in str(clean)


# --- LiteLLM provider (ADR 0021) ---


@pytest.mark.parametrize(
    "base_url", ["http://localhost:4000", "https://127.0.0.1:4000/v1", "http://[::1]:4000"]
)
def test_litellm_model_accepts_loopback_proxy(base_url: str) -> None:
    from e_agent.adapters.pydantic_ai import litellm_model

    model = litellm_model("ollama/qwen3", base_url)
    assert model.model_name == "ollama/qwen3"
    provider = model._provider  # type: ignore[attr-defined]
    assert provider.name == "litellm"
    assert str(provider.base_url).rstrip("/") == base_url.rstrip("/")


@pytest.mark.parametrize(
    ("base_url", "model_name"),
    [
        ("http://10.0.0.5:4000", "m"),
        ("https://proxy.example.com", "m"),
        ("http://user:pw@localhost:4000", "m"),
        ("http://localhost:4000/?x=1", "m"),
        ("http://localhost:4000/#frag", "m"),
        ("ftp://localhost:4000", "m"),
        ("http://localhost:4000", ""),
    ],
)
def test_litellm_model_refuses_non_loopback_or_malformed(base_url: str, model_name: str) -> None:
    from e_agent.adapters.pydantic_ai import litellm_model

    with pytest.raises(ValueError, match="loopback proxy endpoint"):
        litellm_model(model_name, base_url, "sk-secret-value")


def test_litellm_api_key_reaches_client_but_never_the_error() -> None:
    from e_agent.adapters.pydantic_ai import litellm_model

    model = litellm_model("m", "http://localhost:4000", "sk-secret-value")
    assert model.client.api_key == "sk-secret-value"  # type: ignore[attr-defined]
    with pytest.raises(ValueError, match="loopback") as caught:
        litellm_model("m", "https://proxy.example.com", "sk-secret-value")
    assert "sk-secret-value" not in str(caught.value)


def test_litellm_without_a_key_never_falls_back_to_the_process_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from e_agent.adapters.pydantic_ai import litellm_model

    monkeypatch.setenv("OPENAI_API_KEY", "should-not-be-read")
    model = litellm_model("m", "http://localhost:4000")
    assert model.client.api_key == "not-required"  # type: ignore[attr-defined]
    assert "should-not-be-read" not in repr(model.client.api_key)  # type: ignore[attr-defined]


def test_ollama_model_endpoint_guard_is_unchanged() -> None:
    from e_agent.adapters.pydantic_ai import ollama_model

    ollama_model("qwen3", "http://localhost:11434/v1")
    for url, name in [
        ("https://localhost:11434/v1", "qwen3"),  # ollama stays http-only
        ("http://10.0.0.5:11434/v1", "qwen3"),
        ("http://localhost:11434/v1", "qwen3:cloud"),
    ]:
        with pytest.raises(ValueError, match="local Ollama endpoint"):
            ollama_model(name, url)
