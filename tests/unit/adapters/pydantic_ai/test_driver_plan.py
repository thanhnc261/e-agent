"""The pydantic-ai driver emits action plans in execution IR ``on`` (Task 2c.9, ADR 0025).

The plan tool (`propose_plan`) is offered only on a turn whose run is bound to a task
definition (``DriverInput.allowed_capabilities`` is set, which the kernel does only in
``on``) and whose effective write budget (``ctx.budgets.max_admitted_writes``, the same
value the kernel's plan refusal reads) is above one. Everywhere else the model request is
byte-identical to the one before this task, pinned by ``golden/off_model_request.json``,
which was captured from the driver at the task's base commit (ENG-TOGGLE-1, ENG-EVID-5).

The driver only builds `ProposePlan` (PR-13): connections come from the host's tool specs,
never from the model (PR-11, PR-12), and a lineage placeholder is built only from the
plan tool's typed ``lineage`` field, never from a literal ``$lineage`` key (ADR 0025).
"""

import dataclasses
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from e_agent.adapters.pydantic_ai import PydanticAiDriver, ToolSpec
from e_agent.adapters.pydantic_ai.driver import (
    CONNECTION_REFUSAL,
    PLAN_LINEAGE_REFUSAL,
    PLAN_REFUSALS,
    PLAN_SHAPE_REFUSAL,
    PLAN_STRUCTURE_REFUSAL,
    PLAN_TOOL,
    PLAN_TOOL_REFUSAL,
)
from e_agent.contracts.capability import EffectKind
from e_agent.contracts.context import Budgets, Principal, TaskContext
from e_agent.contracts.plan import LineageRef
from e_agent.sdk.ports import (
    AskClarification,
    DriverInput,
    FinalAnswer,
    ProposeAction,
    ProposePlan,
)
from pydantic_ai import ModelMessage, ModelRequest, ModelResponse, TextPart, ToolCallPart, models
from pydantic_ai.messages import ToolReturnPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

models.ALLOW_MODEL_REQUESTS = False  # CI never calls a real model

GOLDEN = Path(__file__).parent / "golden" / "off_model_request.json"
GUIDANCE = ("Domain guidance: write notes briefly.",)
CLARIFY = "request_clarification"


def _spec(contract_id: str, effect: EffectKind, connection_id: str = "conn-host") -> ToolSpec:
    return ToolSpec(
        contract_id=contract_id,
        effect=effect,
        description=f"{contract_id} tool",
        parameters={
            "type": "object",
            "properties": {"text": {"type": "string"}, "parent": {"type": "string"}},
            "required": ["text"],
        },
        connection_id=connection_id,
    )


READ = _spec("notes.note.read.v1", EffectKind.READ)
WRITE = _spec("notes.note.create.v1", EffectKind.WRITE)
PIN = _spec("notes.note.pin.v1", EffectKind.WRITE, connection_id="conn-pin")
ANSWER = _spec("notes.summary.answer.v1", EffectKind.ANSWER)
SPECS = (READ, WRITE, PIN, ANSWER)
ALL = tuple(s.contract_id for s in SPECS)


def _ctx(run_id: str, writes: int = 1) -> TaskContext:
    return TaskContext(
        run_id=run_id,
        tenant_id="t",
        principal=Principal(principal_id="p", tenant_id="t", roles=frozenset()),
        resource_scope=frozenset({"conn-host", "conn-pin"}),
        deadline=datetime(2030, 1, 1, tzinfo=UTC),
        budgets=Budgets(max_admitted_writes=writes),
    )


def _request_view(info: AgentInfo) -> dict[str, Any]:
    """Everything the driver decides about a model request: tools, outputs, instructions."""
    return {
        "function_tools": [dataclasses.asdict(t) for t in info.function_tools],
        "output_tools": [dataclasses.asdict(t) for t in info.output_tools],
        "allow_text_output": info.allow_text_output,
        "instructions": info.instructions,
    }


async def _first_request(
    allowed: tuple[str, ...] | None, writes: int, run_id: str
) -> dict[str, Any]:
    seen: list[dict[str, Any]] = []

    def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        seen.append(_request_view(info))
        return ModelResponse(parts=[TextPart("done")])

    driver = PydanticAiDriver(FunctionModel(model), SPECS, guidance=GUIDANCE)
    step = await driver.advance(
        _ctx(run_id, writes), DriverInput(task="t", allowed_capabilities=allowed)
    )
    assert isinstance(step, FinalAnswer)
    assert len(seen) == 1
    return seen[0]


# The model requests that must stay as they were before plan output existed: `off` and
# `shadow` (no tool set reaches the driver) at either budget, and `on` with one write.
UNCHANGED_CASES = {
    "off-one-write": (None, 1),
    "off-two-writes": (None, 2),
    "on-one-write": ((READ.contract_id, WRITE.contract_id), 1),
    "on-no-write-tool": ((READ.contract_id, ANSWER.contract_id), 2),
}


async def capture_golden() -> dict[str, Any]:
    """Regenerate the golden; run only at a commit whose driver is the accepted baseline."""
    return {
        name: await _first_request(allowed, writes, f"golden_{name}")
        for name, (allowed, writes) in UNCHANGED_CASES.items()
    }


def _plan_call(steps: Any, call_id: str = "plan-1") -> ModelResponse:
    return ModelResponse(parts=[ToolCallPart(PLAN_TOOL, {"steps": steps}, call_id)])


def _two_steps() -> list[dict[str, Any]]:
    return [
        {"step_id": "first", "tool": WRITE.name, "arguments": {"text": "standup", "parent": 7}},
        {
            "step_id": "follow-up",
            "tool": PIN.name,
            "arguments": {"text": "follow-up"},
            "lineage": {"parent": {"step": "first", "path": "/key"}},
        },
    ]


PLAN_ALLOWED = (READ.contract_id, WRITE.contract_id, PIN.contract_id)


async def _drive(
    response: ModelResponse, run_id: str
) -> tuple[Any, PydanticAiDriver, list[list[ModelMessage]]]:
    """One plan-eligible turn whose model returns ``response``; later turns answer text."""
    requests: list[list[ModelMessage]] = []

    def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        requests.append(list(messages))
        if len(requests) == 1:
            return response
        return ModelResponse(parts=[TextPart("stopped")])

    driver = PydanticAiDriver(FunctionModel(model), SPECS)
    step = await driver.advance(
        _ctx(run_id, writes=2), DriverInput(task="t", allowed_capabilities=PLAN_ALLOWED)
    )
    return step, driver, requests


def _rejections(driver: PydanticAiDriver, run_id: str) -> dict[str, str]:
    snapshot = driver.snapshot(run_id)
    assert snapshot is not None
    return dict(snapshot["rejected"])


def _tool_returns(messages: list[ModelMessage]) -> list[ToolReturnPart]:
    return [
        p
        for m in messages
        if isinstance(m, ModelRequest)
        for p in m.parts
        if isinstance(p, ToolReturnPart)
    ]


# -- the four task tests ------------------------------------------------------------------
async def test_function_model_plan_output_becomes_propose_plan() -> None:
    step, driver, _ = await _drive(_plan_call(_two_steps()), "run_plan")
    assert isinstance(step, ProposePlan)
    first, second = step.plan.steps
    assert (first.step_id, second.step_id) == ("first", "follow-up")
    assert (first.proposal.contract_id, second.proposal.contract_id) == (
        WRITE.contract_id,
        PIN.contract_id,
    )
    # Each step's connection is the host's binding for its tool, never the model's.
    assert (first.proposal.connection_id, second.proposal.connection_id) == (
        "conn-host",
        "conn-pin",
    )
    # Schema-guided coercion applies per step, as for a single write.
    assert first.proposal.arguments == {"text": "standup", "parent": "7"}
    assert first.depends_on == ()
    parent = second.proposal.arguments["parent"]
    assert isinstance(parent, LineageRef)
    assert (parent.step_id, parent.path) == ("first", "/key")
    assert second.proposal.arguments["text"] == "follow-up"
    assert second.depends_on == ("first",)  # a lineage source is a dependency
    assert first.proposal.expected_effects == (WRITE.description,)
    # The plan call is the pending write: its result or findings return to that call.
    snapshot = driver.snapshot("run_plan")
    assert snapshot is not None
    assert (snapshot["pending_write"], snapshot["rejected"]) == ("plan-1", {})


async def test_driver_offers_plan_output_only_when_task_allows_multiple_writes() -> None:
    bound = (READ.contract_id, WRITE.contract_id, PIN.contract_id)
    cases = [
        (None, 1, False),  # off / shadow
        (None, 2, False),  # off / shadow: the budget alone never offers a plan
        (bound, 1, False),  # on, one write
        (bound, 0, False),  # on, a read-only task
        ((READ.contract_id, ANSWER.contract_id), 2, False),  # on, no write tool on offer
        (bound, 2, True),
        (ALL, 3, True),
    ]
    for index, (allowed, writes, offered) in enumerate(cases):
        view = await _first_request(allowed, writes, f"run_offer_{index}")
        names = [t["name"] for t in view["function_tools"]]
        assert (PLAN_TOOL in names) is offered, (allowed, writes)
        if not offered:
            continue
        assert allowed is not None
        (plan_tool,) = [t for t in view["function_tools"] if t["name"] == PLAN_TOOL]
        assert plan_tool["kind"] == "external"
        step_schema = plan_tool["parameters_json_schema"]["properties"]["steps"]
        # Only the write tools on offer can be plan steps; no connection field exists.
        assert step_schema["items"]["properties"]["tool"]["enum"] == sorted(
            s.name for s in SPECS if s.effect is EffectKind.WRITE and s.contract_id in allowed
        )
        assert "connection_id" not in json.dumps(plan_tool["parameters_json_schema"])
        assert step_schema["maxItems"] == writes
        # The base instructions say "exactly one write tool"; the plan addendum follows them.
        assert view["instructions"].startswith(_golden()["off-one-write"]["instructions"])
        assert PLAN_TOOL in view["instructions"]
    print(f"plan offer cases: {len(cases)}")
    assert len(cases) == 7


def _golden() -> dict[str, Any]:
    views: dict[str, Any] = json.loads(GOLDEN.read_text(encoding="utf-8"))
    return views


async def test_driver_off_mode_outputs_unchanged() -> None:
    golden = _golden()
    assert set(golden) == set(UNCHANGED_CASES), "golden cases drifted from UNCHANGED_CASES"
    current = await capture_golden()
    for name in UNCHANGED_CASES:
        assert current[name] == golden[name], f"model request changed for {name}"
    # Byte for byte: the serialised request equals the golden file's entry.
    for name in UNCHANGED_CASES:
        assert json.dumps(current[name], sort_keys=True) == json.dumps(golden[name], sort_keys=True)
    print(f"unchanged request cases: {len(UNCHANGED_CASES)}")
    assert len(UNCHANGED_CASES) == 4


async def test_plan_with_model_chosen_connection_is_rejected() -> None:
    """A plan step that names a connection never becomes a `ProposePlan`; the call returns
    to the model with a fixed refusal (PR-11, PR-12). The kernel half, a plan step on a
    connection with no binding, is `tests/unit/kernel/test_action_plan_guards.py::
    test_plan_step_on_a_connection_without_binding_is_refused`."""
    keys = ("connection_id", "connection", "connection_ref")
    for index, key in enumerate(keys):
        steps = _two_steps()
        steps[1][key] = "conn-model-picked"
        run_id = f"run_conn_{index}"
        step, driver, requests = await _drive(_plan_call(steps), run_id)
        assert isinstance(step, AskClarification)  # the turn had no usable request
        assert _rejections(driver, run_id) == {"plan-1": CONNECTION_REFUSAL}
        snapshot = driver.snapshot(run_id)
        assert snapshot is not None and snapshot["pending_write"] is None
        # On the next turn the model sees the refusal as the plan call's result.
        final = await driver.advance(
            _ctx(run_id, writes=2),
            DriverInput(task="t", user_input="continue", allowed_capabilities=PLAN_ALLOWED),
        )
        assert isinstance(final, FinalAnswer)
        (returned,) = _tool_returns(requests[1])
        assert (returned.tool_call_id, returned.content) == (
            "plan-1",
            {"error": CONNECTION_REFUSAL},
        )
    print(f"connection keys refused: {len(keys)}")
    assert len(keys) == 3


# -- the rest of the plan tool's refusals ------------------------------------------------
REFUSED_PLANS: dict[str, Any] = {
    "literal-lineage-key": [
        {"step_id": "first", "tool": WRITE.name, "arguments": {"text": "a"}},
        {
            "step_id": "second",
            "tool": WRITE.name,
            "arguments": {"text": "b", "parent": {"$lineage": {"step": "first", "path": "/k"}}},
            "depends_on": ["first"],
        },
    ],
    "top-level-lineage-key": [
        {"step_id": "first", "tool": WRITE.name, "arguments": {"$lineage": "x", "text": "a"}},
    ],
    "read-step": [{"step_id": "first", "tool": READ.name, "arguments": {"text": "a"}}],
    "answer-step": [{"step_id": "first", "tool": ANSWER.name, "arguments": {"text": "a"}}],
    "unknown-tool": [{"step_id": "first", "tool": "notes_note_drop_v1", "arguments": {}}],
    "bad-pointer": [
        {"step_id": "first", "tool": WRITE.name, "arguments": {"text": "a"}},
        {
            "step_id": "second",
            "tool": WRITE.name,
            "arguments": {"text": "b"},
            "lineage": {"parent": {"step": "first", "path": "key"}},
        },
    ],
    "later-dependency": [
        {
            "step_id": "first",
            "tool": WRITE.name,
            "arguments": {"text": "a"},
            "lineage": {"parent": {"step": "second", "path": "/key"}},
        },
        {"step_id": "second", "tool": WRITE.name, "arguments": {"text": "b"}},
    ],
    "value-and-lineage": [
        {"step_id": "first", "tool": WRITE.name, "arguments": {"text": "a"}},
        {
            "step_id": "second",
            "tool": WRITE.name,
            "arguments": {"text": "b", "parent": "literal"},
            "lineage": {"parent": {"step": "first", "path": "/key"}},
        },
    ],
    "no-steps": [],
    "steps-not-a-list": {"first": {}},
    "arguments-not-an-object": [{"step_id": "first", "tool": WRITE.name, "arguments": []}],
    "duplicate-step-id": [
        {"step_id": "first", "tool": WRITE.name, "arguments": {"text": "a"}},
        {"step_id": "first", "tool": WRITE.name, "arguments": {"text": "b"}},
    ],
}


REFUSED_BY = {
    "literal-lineage-key": PLAN_STRUCTURE_REFUSAL,  # the records refuse it (ADR 0025)
    "top-level-lineage-key": PLAN_STRUCTURE_REFUSAL,
    "read-step": PLAN_TOOL_REFUSAL,
    "answer-step": PLAN_TOOL_REFUSAL,
    "unknown-tool": PLAN_TOOL_REFUSAL,
    "bad-pointer": PLAN_LINEAGE_REFUSAL,
    "later-dependency": PLAN_STRUCTURE_REFUSAL,
    "value-and-lineage": PLAN_LINEAGE_REFUSAL,
    "no-steps": PLAN_SHAPE_REFUSAL,
    "steps-not-a-list": PLAN_SHAPE_REFUSAL,
    "arguments-not-an-object": PLAN_SHAPE_REFUSAL,
    "duplicate-step-id": PLAN_STRUCTURE_REFUSAL,
}


def test_every_refused_plan_names_its_refusal() -> None:
    assert REFUSED_PLANS, "no refused plan cases"
    assert set(REFUSED_BY) == set(REFUSED_PLANS)
    assert set(REFUSED_BY.values()) | {CONNECTION_REFUSAL} == PLAN_REFUSALS
    print(f"refused plan cases: {len(REFUSED_PLANS)}")


@pytest.mark.parametrize("case", sorted(REFUSED_PLANS))
async def test_malformed_plan_call_returns_to_the_model(case: str) -> None:
    run_id = f"run_bad_{case}"
    step, driver, _ = await _drive(_plan_call(REFUSED_PLANS[case]), run_id)
    assert isinstance(step, AskClarification)
    rejected = _rejections(driver, run_id)
    assert rejected == {"plan-1": REFUSED_BY[case]}  # a fixed message, never model text


async def test_plan_call_beside_reads_or_writes_is_refused() -> None:
    """A plan is the turn's one write: beside reads it waits for the facts; beside a write
    the first proposal in the response wins and the rest return to the model."""
    read = ToolCallPart(READ.name, {"text": "x"}, "read-1")
    plan = ToolCallPart(PLAN_TOOL, {"steps": _two_steps()}, "plan-1")
    write = ToolCallPart(WRITE.name, {"text": "x"}, "write-1")

    step, driver, _ = await _drive(ModelResponse(parts=[read, plan]), "run_mixed_read")
    assert type(step).__name__ == "RequestReads"
    assert set(_rejections(driver, "run_mixed_read")) == {"plan-1"}

    step, driver, _ = await _drive(ModelResponse(parts=[plan, write]), "run_mixed_write")
    assert isinstance(step, ProposePlan)
    assert set(_rejections(driver, "run_mixed_write")) == {"write-1"}

    step, driver, _ = await _drive(ModelResponse(parts=[write, plan]), "run_write_first")
    assert isinstance(step, ProposeAction)
    assert set(_rejections(driver, "run_write_first")) == {"plan-1"}


async def test_plan_result_and_findings_return_to_the_plan_call() -> None:
    """The kernel's refusal of a plan (or its verified result) is the plan call's result."""
    calls: list[list[ModelMessage]] = []

    def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        calls.append(list(messages))
        if len(calls) == 1:
            return _plan_call(_two_steps())
        return ModelResponse(parts=[TextPart("ok")])

    driver = PydanticAiDriver(FunctionModel(model), SPECS)
    allowed = (WRITE.contract_id, PIN.contract_id)
    ctx = _ctx("run_result", writes=2)
    first = await driver.advance(ctx, DriverInput(task="t", allowed_capabilities=allowed))
    assert isinstance(first, ProposePlan)
    final = await driver.advance(
        ctx,
        DriverInput(
            task="t",
            allowed_capabilities=allowed,
            action_result={"status": "VERIFIED", "external_refs": ["note:1", "note:2"]},
        ),
    )
    assert isinstance(final, FinalAnswer)
    (returned,) = _tool_returns(calls[1])
    assert returned.tool_call_id == "plan-1"
    assert returned.content == {"status": "VERIFIED", "external_refs": ["note:1", "note:2"]}
