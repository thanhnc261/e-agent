"""Accepted public model calls replay through the real host; no network/model/ERP access.

Two kinds of recording, kept in separate folders so neither is mistaken for the other
(PR-29): ``erp-model-calls`` holds parts captured from a local model, and
``erp-authored-plan-calls`` holds hand-authored parts (``provenance: "authored"``) that check
the driver's plan output (Task 2c.9) as a fixture. No live model produced an authored file.
"""

import json
from pathlib import Path

import pytest
from e_agent.adapters.pydantic_ai import PydanticAiDriver
from e_agent.adapters.pydantic_ai.driver import PLAN_TOOL
from e_agent.contracts.action import ActionState
from e_agent.contracts.approval import ApprovalDecision
from e_agent.contracts.events import RunEventType
from e_agent.contracts.features import Features
from e_agent.contracts.run import ReasonCode, RunState
from e_agent.plugins.erp.simulator import fixture_profile_path
from e_agent.server.bootstrap import build_runtime, tool_specs
from e_agent.server.profile import load_profile
from pydantic_ai import ModelMessagesTypeAdapter, TextPart, ToolCallPart
from pydantic_ai.models.function import FunctionModel

REPLAYS = Path(__file__).resolve().parents[3] / "tests/replays"
ROOT = REPLAYS / "erp-model-calls"
AUTHORED_ROOT = REPLAYS / "erp-authored-plan-calls"
AUTHORED = ["draft-po-plan"]
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


@pytest.mark.parametrize(("root", "names"), [(ROOT, TASKS), (AUTHORED_ROOT, AUTHORED)])
def test_every_recording_is_replayed(root, names):
    recorded = {path.stem for path in root.glob("*.json")}
    assert recorded, f"no recordings found in {root}"
    assert len(names) == len(set(names)), "a recording is listed twice"
    assert recorded == set(names), (
        f"recordings without a replay test: {sorted(recorded - set(names))}; "
        f"listed without a recording: {sorted(set(names) - recorded)}"
    )
    print(f"{root.name}: {len(recorded)} recordings")


def test_recording_provenance_is_explicit():
    """A captured recording names its model; an authored one says it is authored and claims
    no model, seed or temperature (PR-29)."""
    captured = [json.loads((ROOT / f"{t}.json").read_text()) for t in TASKS]
    authored = [json.loads((AUTHORED_ROOT / f"{t}.json").read_text()) for t in AUTHORED]
    assert captured and authored
    for recording in captured:
        assert recording["kind"] == "recorded-public-model-parts-fixture-replay"
        assert "provenance" not in recording and recording["model_digest"]
    for recording in authored:
        assert recording["provenance"] == "authored"
        assert recording["kind"] == "authored-model-parts-fixture-replay"
        assert not {"model_digest", "seed", "temperature", "context_length"} & set(recording)
    print(f"provenance checked: {len(captured)} captured, {len(authored)} authored")


async def replay(task, *, omit_late_order=False, root=ROOT, offered=None, context_assembler=None):
    """Replay one recording; ``context_assembler`` pins that mode for the run (Task 3d.3)."""
    recording = json.loads((root / f"{task}.json").read_text())
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
        if offered is not None:
            offered.append({tool.name for tool in info.function_tools})
        if cursor >= len(responses):
            # A mutated invalid trace cannot fabricate host verification with final text.
            assert omit_late_order
            from pydantic_ai import ModelResponse

            return ModelResponse(parts=[TextPart("The task is complete.")])
        response = responses[cursor]
        cursor += 1
        return response

    profile = load_profile(fixture_profile_path())
    if "features" in recording:  # authored plan recordings run in execution IR `on`
        profile = profile.model_copy(
            update={
                "features": Features.model_validate(recording["features"]),
                "budgets": profile.budgets.model_copy(update=recording["budgets"]),
            }
        )
    if context_assembler is not None:
        features = profile.features.model_copy(update={"context_assembler": context_assembler})
        profile = profile.model_copy(update={"features": features})
    runtime = await build_runtime(
        profile,
        driver_factory=lambda registry: PydanticAiDriver(
            FunctionModel(respond), tool_specs(registry, profile), guidance=registry.agent_guidance
        ),
    )
    run = await runtime.coordinator.start_run(
        runtime.operator, recording["prompt"], runtime.scope, task_kind=recording.get("task_kind")
    )
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
    assert (
        runtime.diagnostics()["fixture-erp"]["create_calls"] == recording["expected_fixture_writes"]
    )
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
    assert runtime.diagnostics()["fixture-erp"]["create_calls"] == 0
    actions = await runtime.store.list_actions(runtime.operator.tenant_id, run.run_id)
    assert not any(action.state is ActionState.VERIFIED for action in actions)


async def test_authored_plan_recording_replays_through_the_driver_plan_output():
    """The authored ``propose_plan`` call becomes one approved two-step plan: both draft POs
    are written once each and verified, the second with ``requested_date`` from the first's
    read-back. A fixture check of the driver against the host, not model evidence."""
    offered = []
    runtime, run, recording, cursor, response_count = await replay(
        "draft-po-plan", root=AUTHORED_ROOT, offered=offered
    )
    assert recording["provenance"] == "authored"
    assert (run.state, run.reason_code) == (RunState.SUCCEEDED, ReasonCode.VERIFIED)
    assert cursor == response_count
    assert PLAN_TOOL in offered[1]  # the plan call was answered by the plan tool on offer
    assert runtime.diagnostics()["fixture-erp"]["create_calls"] == 2
    actions = await runtime.store.list_actions(runtime.operator.tenant_id, run.run_id)
    assert sorted((a.step_index, a.contract_id, a.state) for a in actions) == [
        (0, recording["expected_contract"], ActionState.VERIFIED),
        (1, recording["expected_contract"], ActionState.VERIFIED),
    ]
    first, second = sorted(actions, key=lambda a: a.step_index)
    assert first.plan_id is not None and first.plan_id == second.plan_id
    tenant = runtime.operator.tenant_id
    assert len(await runtime.store.list_approvals(tenant, first.action_id)) == 1
    assert await runtime.store.list_approvals(tenant, second.action_id) == []
    events = await runtime.store.list_events(tenant, run.run_id)
    assert not [e for e in events if e.type is RunEventType.FEATURE_FALLBACK]
    (lineage,) = [e.payload for e in events if e.type is RunEventType.IR_LINEAGE_RESOLVED]
    (resolved,) = lineage["values"]
    assert (resolved["from_step"], resolved["path"]) == ("first-po", "/requested_date")
    assert second.arguments["requested_date"] == resolved["value"]
