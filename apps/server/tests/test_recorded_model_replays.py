"""Accepted public model calls replay through the real host; no network/model/ERP access."""

import json
from pathlib import Path

import pytest
from e_agent.adapters.pydantic_ai import PydanticAiDriver
from e_agent.contracts.action import ActionState
from e_agent.contracts.approval import ApprovalDecision
from e_agent.contracts.run import RunState
from e_agent.server.bootstrap import build_runtime, tool_specs
from e_agent.server.profile import load_profile
from pydantic_ai import ModelMessagesTypeAdapter, TextPart, ToolCallPart
from pydantic_ai.models.function import FunctionModel

ROOT = Path(__file__).resolve().parents[3] / "tests/replays/erp-model-calls"
TASKS = [
    "draft-po",
    "shortage",
    "recommend",
    "amend-rfq",
    "quotation",
    "late-orders",
    "crm-lead",
    "overdue-invoices",
]


async def replay(task, *, omit_late_order=False):
    recording = json.loads((ROOT / f"{task}.json").read_text())
    responses = ModelMessagesTypeAdapter.validate_python(recording["responses"])
    if omit_late_order:
        for response in responses:
            for part in response.parts:
                if isinstance(part, ToolCallPart) and "late_orders_answer" in part.tool_name:
                    args = part.args_as_dict()
                    args["late_order_refs"] = ["order:so-1"]
                    part.args = args
    cursor = 0

    def respond(messages, info):
        nonlocal cursor
        if cursor >= len(responses):
            # A mutated invalid trace cannot fabricate host verification with final text.
            assert omit_late_order
            from pydantic_ai import ModelResponse

            return ModelResponse(parts=[TextPart("The task is complete.")])
        response = responses[cursor]
        cursor += 1
        return response

    profile = load_profile()
    runtime = await build_runtime(
        profile,
        driver_factory=lambda registry: PydanticAiDriver(
            FunctionModel(respond), tool_specs(registry, profile), guidance=registry.agent_guidance
        ),
    )
    run = await runtime.coordinator.start_run(runtime.operator, recording["prompt"], runtime.scope)
    if run.state is RunState.WAITING_APPROVAL:
        approval = await runtime.coordinator.pending_approval(
            runtime.operator.tenant_id, run.run_id
        )
        run = await runtime.coordinator.decide(
            actor=runtime.operator,
            run_id=run.run_id,
            action_id=approval.action_id,
            action_digest=approval.digest,
            expected_run_revision=approval.run_revision,
            decision=ApprovalDecision.APPROVED,
        )
    return runtime, run, recording, cursor, len(responses)


@pytest.mark.parametrize("task", TASKS)
async def test_accepted_public_model_calls_pass_independent_fixture_verification(task):
    runtime, run, recording, cursor, response_count = await replay(task)
    assert run.state is RunState.SUCCEEDED
    assert cursor == response_count
    assert runtime.fake_erp.create_calls == recording["expected_fixture_writes"]
    actions = await runtime.store.list_actions(runtime.operator.tenant_id, run.run_id)
    assert any(
        action.contract_id == recording["expected_contract"]
        and action.state is ActionState.VERIFIED
        for action in actions
    )
    assert all(
        part.get("part_kind") in {"text", "tool-call"} and not part.get("provider_details")
        for response in recording["responses"]
        for part in response["parts"]
    )


async def test_recorded_late_order_trace_cannot_verify_a_missing_order():
    runtime, run, _, _, _ = await replay("late-orders", omit_late_order=True)
    assert run.state is RunState.FAILED
    assert runtime.fake_erp.create_calls == 0
    actions = await runtime.store.list_actions(runtime.operator.tenant_id, run.run_id)
    assert not any(action.state is ActionState.VERIFIED for action in actions)
