"""Pydantic AI driver through the real kernel, SHACL engine and fixture ERP (I04).

A FunctionModel plays the LLM deterministically; no real model is called in CI.
"""

import json

import pytest
from e_agent.adapters.pydantic_ai import PydanticAiDriver
from e_agent.contracts.approval import ApprovalDecision
from e_agent.contracts.run import RunState
from e_agent.server.bootstrap import build_runtime, tool_specs
from e_agent.server.profile import load_profile
from pydantic_ai import ModelMessage, ModelResponse, TextPart, ToolCallPart, models
from pydantic_ai.messages import ThinkingPart, ToolReturnPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

models.ALLOW_MODEL_REQUESTS = False
SECRET = "HIDDEN-CHAIN-OF-THOUGHT-7f3a"


def scripted_llm(first_offer: str) -> FunctionModel:
    def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        names = {t.name for t in info.function_tools}
        assert "procurement_purchase_order_read_v1" not in names  # host-only capability
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
    profile = load_profile()
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
    assert rt.fake_erp is not None and rt.fake_erp.create_calls == 1
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
