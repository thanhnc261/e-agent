"""Pydantic AI driver through the real kernel, SHACL engine and fixture ERP (I04).

A FunctionModel plays the LLM deterministically; no real model is called in CI.
"""

import json

import pytest
from e_agent.adapters.pydantic_ai import PydanticAiDriver
from e_agent.contracts.approval import ApprovalDecision
from e_agent.contracts.run import RunState
from e_agent.plugins.erp.simulator import fixture_profile_path
from e_agent.server.bootstrap import build_runtime, tool_specs
from e_agent.server.profile import Profile, load_profile
from pydantic_ai import ModelMessage, ModelResponse, TextPart, ToolCallPart, models
from pydantic_ai.messages import ThinkingPart, ToolReturnPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

models.ALLOW_MODEL_REQUESTS = False
SECRET = "HIDDEN-CHAIN-OF-THOUGHT-7f3a"


def scripted_llm(first_offer: str) -> FunctionModel:
    def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        names = {t.name for t in info.function_tools}
        assert "procurement_purchase_order_read_v1" not in names  # host-only capability
        assert "procurement_open_demands_read_v1" in names  # discovery read is offered
        last = messages[-1]
        returns = [p for p in getattr(last, "parts", []) if isinstance(p, ToolReturnPart)]
        if len(messages) == 1:
            return ModelResponse(
                parts=[
                    ThinkingPart(SECRET),
                    ToolCallPart(
                        "procurement_demand_read_v1", {"demand_ref": "demand:d-001"}, "r1"
                    ),
                    ToolCallPart(
                        "inventory_availability_read_v1", {"product_ref": "product:widget-a"}, "r2"
                    ),
                    ToolCallPart(
                        "procurement_offers_read_v1", {"product_ref": "product:widget-a"}, "r3"
                    ),
                ]
            )
        content = returns[0].content if returns else {}
        if isinstance(content, dict) and content.get("status") == "VERIFIED":
            return ModelResponse(parts=[TextPart("Đã tạo đơn mua nháp và đã xác minh.")])
        blocked = isinstance(content, dict) and content.get("status") == "BLOCKED"
        offer, supplier, price = (
            ("offer:a", "supplier:approved-co", "100")
            if blocked or first_offer == "a"
            else ("offer:b", "supplier:unvetted-co", "80")
        )
        qty = 7
        return ModelResponse(
            parts=[
                ThinkingPart(SECRET),
                ToolCallPart(
                    "procurement_purchase_order_create_draft_v1",
                    {
                        "demand_ref": "demand:d-001",
                        "product_ref": "product:widget-a",
                        "supplier_ref": supplier,
                        "offer_ref": offer,
                        "quantity": qty,
                        "unit": "Units",
                        "currency": "VND",
                        "unit_price": price,
                        "subtotal": str(qty * int(price)),
                        "requested_date": "2026-10-20",
                    },
                    f"w{len(messages)}",
                ),
            ]
        )

    return FunctionModel(model)


async def _run(first_offer: str):  # type: ignore[no-untyped-def]
    profile = load_profile(fixture_profile_path())
    rt = await build_runtime(
        profile,
        driver_factory=lambda reg: PydanticAiDriver(
            scripted_llm(first_offer), tool_specs(reg, profile), guidance=reg.agent_guidance
        ),
    )
    run = await rt.coordinator.start_run(rt.operator, "Bổ sung hàng widget-a", rt.scope)
    return rt, run


@pytest.mark.asyncio
async def test_model_proposal_is_approved_executed_and_verified() -> None:
    rt, run = await _run("a")
    assert run.state is RunState.WAITING_APPROVAL
    pres = await rt.coordinator.pending_approval(rt.operator.tenant_id, run.run_id)
    assert pres.canonical_proposal["arguments"]["quantity"] == "7"  # coerced to a string
    run = await rt.coordinator.decide(
        actor=rt.operator,
        run_id=run.run_id,
        action_id=pres.action_id,
        action_digest=pres.digest,
        expected_run_revision=pres.run_revision,
        decision=ApprovalDecision.APPROVED,
    )
    assert run.state is RunState.SUCCEEDED
    assert rt.diagnostics()["fixture-erp"]["create_calls"] == 1
    events = await rt.store.list_events(rt.operator.tenant_id, run.run_id)
    assert events[-3].type == "message.final"


@pytest.mark.asyncio
async def test_rule_findings_reach_the_model_which_repairs() -> None:
    rt, run = await _run("b")
    assert run.state is RunState.WAITING_APPROVAL
    pres = await rt.coordinator.pending_approval(rt.operator.tenant_id, run.run_id)
    assert pres.canonical_proposal["arguments"]["offer_ref"] == "offer:a"
    events = await rt.store.list_events(rt.operator.tenant_id, run.run_id)
    statuses = [e.payload["status"] for e in events if e.type == "validation.completed"]
    assert statuses == ["FAIL", "PASS"]


@pytest.mark.asyncio
async def test_no_hidden_reasoning_reaches_the_ledger() -> None:
    rt, run = await _run("b")
    blob = json.dumps(
        {
            "events": [
                e.model_dump(mode="json")
                for e in await rt.store.list_events(rt.operator.tenant_id, run.run_id)
            ],
            "continuation": await rt.store.load_continuation(rt.operator.tenant_id, run.run_id),
            "actions": [
                a.model_dump(mode="json")
                for a in await rt.store.list_actions(rt.operator.tenant_id, run.run_id)
            ],
        },
        ensure_ascii=False,
    )
    assert SECRET not in blob
    assert "procurement_purchase_order_create_draft_v1" in blob  # history itself is stored


# --- Model provider selection (ADR 0021): Ollama default, LiteLLM explicit, no fallback ---

LITELLM_KEY = "sk-test-123"


def _with_driver(**driver: object):  # type: ignore[no-untyped-def]
    profile = load_profile(fixture_profile_path())
    raw = profile.model_dump(mode="json")
    raw["driver"] = {**raw["driver"], "kind": "pydantic-ai", **driver}
    return Profile.model_validate(raw)  # validates, so the provider literal is exercised


def _inner_model(rt) -> object:  # type: ignore[no-untyped-def]
    return rt.coordinator._driver._agent.model


@pytest.fixture(autouse=True)
def _clean_model_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("E_AGENT_OLLAMA_URL", "E_AGENT_LITELLM_URL", "E_AGENT_TEST_LITELLM_KEY"):
        monkeypatch.delenv(name, raising=False)


@pytest.mark.asyncio
async def test_litellm_profile_builds_driver_and_reports_provider() -> None:
    rt = await build_runtime(_with_driver(provider="litellm", model="ollama/qwen3"))
    assert isinstance(rt.coordinator._driver, PydanticAiDriver)
    assert rt.versions["model_provider"] == "litellm"
    assert rt.versions["model"] == "ollama/qwen3"


@pytest.mark.asyncio
async def test_default_provider_is_ollama_and_unchanged() -> None:
    rt = await build_runtime(_with_driver(model="qwen3"))
    assert rt.versions["model_provider"] == "ollama"
    assert rt.versions["model"] == "qwen3"
    scripted = await build_runtime(load_profile(fixture_profile_path()))
    assert scripted.versions["model_provider"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["ollama", "litellm"])
async def test_pydantic_ai_profile_without_a_model_is_rejected(provider: str) -> None:
    from e_agent.kernel.errors import ErrorCode, KernelError

    with pytest.raises(KernelError) as caught:
        await build_runtime(_with_driver(provider=provider))
    assert caught.value.code is ErrorCode.STARTUP_REJECTED


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider", "env", "url"),
    [
        ("litellm", "E_AGENT_LITELLM_URL", "https://proxy.example.com"),
        ("ollama", "E_AGENT_OLLAMA_URL", "http://10.0.0.5:11434/v1"),
    ],
)
async def test_remote_model_endpoint_rejects_startup(
    monkeypatch: pytest.MonkeyPatch, provider: str, env: str, url: str
) -> None:
    from e_agent.kernel.errors import ErrorCode, KernelError

    monkeypatch.setenv(env, url)
    with pytest.raises(KernelError) as caught:
        await build_runtime(_with_driver(provider=provider, model="m"))
    assert caught.value.code is ErrorCode.STARTUP_REJECTED


@pytest.mark.asyncio
async def test_base_url_env_names_the_endpoint_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    from e_agent.kernel.errors import ErrorCode, KernelError

    monkeypatch.setenv("E_AGENT_TEST_PROXY_URL", "https://proxy.example.com")
    with pytest.raises(KernelError) as caught:
        await build_runtime(
            _with_driver(provider="litellm", model="m", base_url_env="E_AGENT_TEST_PROXY_URL")
        )
    assert caught.value.code is ErrorCode.STARTUP_REJECTED


@pytest.mark.asyncio
async def test_missing_api_key_variable_rejects_startup_naming_only_the_variable() -> None:
    from e_agent.kernel.errors import ErrorCode, KernelError

    with pytest.raises(KernelError) as caught:
        await build_runtime(
            _with_driver(provider="litellm", model="m", api_key_env="E_AGENT_TEST_LITELLM_KEY")
        )
    assert caught.value.code is ErrorCode.STARTUP_REJECTED
    assert "E_AGENT_TEST_LITELLM_KEY" in str(caught.value)


@pytest.mark.asyncio
async def test_api_key_comes_from_the_named_variable_and_is_never_echoed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from e_agent.kernel.errors import KernelError

    monkeypatch.setenv("E_AGENT_TEST_LITELLM_KEY", LITELLM_KEY)
    profile = _with_driver(provider="litellm", model="m", api_key_env="E_AGENT_TEST_LITELLM_KEY")
    rt = await build_runtime(profile)
    assert _inner_model(rt).client.api_key == LITELLM_KEY  # type: ignore[attr-defined]
    assert LITELLM_KEY not in json.dumps(rt.versions)
    assert LITELLM_KEY not in profile.model_dump_json()
    # a refused endpoint with a key set must not leak the key in the error either
    monkeypatch.setenv("E_AGENT_LITELLM_URL", "https://proxy.example.com")
    with pytest.raises(KernelError) as caught:
        await build_runtime(profile)
    assert LITELLM_KEY not in str(caught.value)


@pytest.mark.asyncio
async def test_litellm_without_api_key_env_ignores_the_process_openai_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "should-not-be-read")
    rt = await build_runtime(_with_driver(provider="litellm", model="m"))
    assert _inner_model(rt).client.api_key == "not-required"  # type: ignore[attr-defined]
