"""The pydantic-ai driver's grounding offer (Task 3e.4, ADR 0033 §5, plan D4, D8).

``DriverInput.grounding`` is the kernel's offer for one call, derived from the run's pinned
``grounded_answers`` mode; the driver never reads the profile. With ``off`` every tool schema
and instruction is today's, pinned by both ``off`` model-request goldens (the notes pack's
``golden/off_model_request.json`` and the ERP ``off_model_request_erp.json``). Otherwise an
answer tool offers ``citations`` beside its arguments, a write tool and the plan tool offer
``rationale``, and ``cite_and_answer`` adds the generic grounded answer. The envelope leaves
the arguments before they reach a proposal; one the records refuse is a fixed refusal.
"""

from __future__ import annotations

import dataclasses
import json
from typing import Any

import pytest
from e_agent.adapters.pydantic_ai import PydanticAiDriver
from e_agent.adapters.pydantic_ai.driver import PLAN_SHAPE_REFUSAL, PLAN_TOOL, _RunState
from e_agent.adapters.pydantic_ai.grounding import (
    CITATION_REFUSAL,
    CITATIONS_SCHEMA,
    GROUNDED_REFUSAL,
    GROUNDED_TOOL,
    GROUNDING_INSTRUCTIONS,
    GROUNDING_REFUSALS,
    ID_PATTERN,
    RATIONALE_REFUSAL,
    RATIONALE_SCHEMA,
)
from e_agent.contracts.features import FeatureMode, Features
from e_agent.contracts.grounding import SUMMARY_MAX, Citation, ProposalRationale
from e_agent.contracts.run import RunState
from e_agent.contracts.task import GROUNDED_ANSWER
from e_agent.plugins.erp.simulator import fixture_profile_path
from e_agent.sdk.ports import (
    AskClarification,
    DriverInput,
    FinalAnswer,
    GroundingOffer,
    ProposeAction,
    ProposePlan,
    RequestReads,
)
from e_agent.server.bootstrap import build_runtime, tool_specs
from e_agent.server.profile import load_profile
from pydantic_ai import (
    DeferredToolRequests,
    ModelMessage,
    ModelResponse,
    TextPart,
    ToolCallPart,
    models,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

from tests.unit.plugins.erp.simulator import record_off_model_request_erp as erp_off

from .test_driver_plan import (
    ANSWER,
    GOLDEN,
    GUIDANCE,
    PIN,
    PLAN_ALLOWED,
    READ,
    SPECS,
    UNCHANGED_CASES,
    WRITE,
    _ctx,
    _rejections,
    _request_view,
)

models.ALLOW_MODEL_REQUESTS = False  # CI never calls a real model

EVIDENCE = "ev_one"
CITED = [{"evidence_id": EVIDENCE, "pointer": "/count", "value": "0"}]
RATIONALE = {
    "goal_ref": "notes-question@1",
    "cited_evidence": [EVIDENCE],
    "rules_considered": ["PR-003", "KERNEL-ARGS"],
    "summary": "The note the user asked for.",
}


def _seeing_driver() -> tuple[PydanticAiDriver, list[dict[str, Any]]]:
    """A driver whose model answers text and keeps each request's view."""
    seen: list[dict[str, Any]] = []

    def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        seen.append(_request_view(info))
        return ModelResponse(parts=[TextPart("done")])

    return PydanticAiDriver(FunctionModel(model), SPECS, guidance=GUIDANCE), seen


async def _first(
    grounding: GroundingOffer,
    *,
    allowed: tuple[str, ...] | None = None,
    writes: int = 1,
    seeing: tuple[PydanticAiDriver, list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    """The first model request of a new run's turn with this offer."""
    driver, seen = seeing or _seeing_driver()
    before = len(seen)
    step = await driver.advance(
        _ctx(f"run_{before}_{grounding.value}", writes),
        DriverInput(task="t", allowed_capabilities=allowed, grounding=grounding),
    )
    assert isinstance(step, FinalAnswer)
    assert len(seen) == before + 1
    return seen[-1]


async def _call(
    grounding: GroundingOffer,
    tool: str,
    args: dict[str, Any],
    *,
    run_id: str,
    allowed: tuple[str, ...] | None = None,
    writes: int = 1,
) -> tuple[Any, PydanticAiDriver]:
    """One turn whose model makes one call."""

    def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        return ModelResponse(parts=[ToolCallPart(tool, args, "call-1")])

    driver = PydanticAiDriver(FunctionModel(model), SPECS)
    step = await driver.advance(
        _ctx(run_id, writes),
        DriverInput(task="t", allowed_capabilities=allowed, grounding=grounding),
    )
    return step, driver


def _tools(view: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {t["name"]: t for t in view["function_tools"]}


# -- off: today's requests, both goldens -------------------------------------------------
async def test_off_tool_schemas_unchanged() -> None:
    """``off`` offers nothing new: the notes-pack golden (every unchanged case, the offer
    passed explicitly) and the ERP draft-po golden (through the real kernel, which sets the
    offer from the run's pin) are matched byte for byte."""
    assert DriverInput(task="t") == DriverInput(task="t", grounding=GroundingOffer.OFF)
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert set(golden) == set(UNCHANGED_CASES) and golden
    seeing = _seeing_driver()
    for name, (allowed, writes) in UNCHANGED_CASES.items():
        # One driver, a grounded call first: the `off` schemas never share its envelope.
        await _first(GroundingOffer.CITE_AND_ANSWER, allowed=allowed, writes=writes, seeing=seeing)
        view = await _first(GroundingOffer.OFF, allowed=allowed, writes=writes, seeing=seeing)
        assert json.dumps(view, sort_keys=True) == json.dumps(golden[name], sort_keys=True), name
    erp = json.loads(erp_off.GOLDEN.read_text("utf-8"))
    matched = erp_off.assert_matches(erp, await erp_off.record_requests())
    assert matched == 3
    print(f"off goldens matched: {len(UNCHANGED_CASES)} notes cases, {matched} ERP requests")


# -- cite and cite_and_answer: the offered envelope --------------------------------------
async def test_grounded_on_schema_offers_citations() -> None:
    off = _tools(await _first(GroundingOffer.OFF, allowed=PLAN_ALLOWED, writes=2))
    for offer in (GroundingOffer.CITE, GroundingOffer.CITE_AND_ANSWER):
        view = await _first(offer, allowed=(*PLAN_ALLOWED, ANSWER.contract_id), writes=2)
        tools = _tools(view)
        answer = tools[ANSWER.name]["parameters_json_schema"]
        assert answer["properties"]["citations"] == CITATIONS_SCHEMA
        assert answer["required"] == list(ANSWER.parameters["required"])  # optional sibling
        for write in (WRITE, PIN):
            schema = tools[write.name]["parameters_json_schema"]
            assert schema["properties"]["rationale"] == RATIONALE_SCHEMA
            assert "citations" not in schema["properties"]
        plan = tools[PLAN_TOOL]["parameters_json_schema"]
        assert plan["properties"]["rationale"] == RATIONALE_SCHEMA
        assert (
            plan["properties"]["steps"]
            == off[PLAN_TOOL]["parameters_json_schema"]["properties"]["steps"]
        )
        # Reads and the clarification tool are today's; no tool names a connection.
        for name in (READ.name, "request_clarification"):
            assert tools[name] == off[name], name
        assert view["instructions"].endswith(GROUNDING_INSTRUCTIONS)
        assert (GROUNDED_TOOL in tools) is (offer is GroundingOffer.CITE_AND_ANSWER), offer
    grounded = tools[GROUNDED_TOOL]["parameters_json_schema"]
    assert grounded["required"] == ["summary", "citations"]
    assert grounded["properties"]["citations"]["minItems"] == 1
    assert GROUNDED_TOOL not in off and "rationale" not in json.dumps(off)
    print("grounded schemas checked for 2 offers")


def test_rationale_schema_matches_the_record() -> None:
    """3e.3 open item: the offered schema carries the record's id pattern and summary bound,
    so a call that follows it is accepted and one that does not is refused by the record."""
    record = ProposalRationale.model_json_schema()
    assert record["properties"]["goal_ref"]["pattern"] == ID_PATTERN
    assert record["properties"]["summary"]["maxLength"] == SUMMARY_MAX
    props = RATIONALE_SCHEMA["properties"]
    assert props["goal_ref"]["pattern"] == ID_PATTERN
    assert props["cited_evidence"]["items"]["pattern"] == ID_PATTERN
    assert props["rules_considered"]["items"]["pattern"] == ID_PATTERN
    assert props["summary"]["maxLength"] == SUMMARY_MAX
    goals = ["run", "draft-po@1", "notes-question@1#answer", "open-pos@1"]
    for goal in goals:
        ProposalRationale(goal_ref=goal, summary="s")
    for bad in ["the draft po task", "", "x" * 129]:
        with pytest.raises(ValueError, match="goal_ref"):
            ProposalRationale(goal_ref=bad, summary="s")
    print(f"goal refs accepted: {len(goals)}")


async def test_grounded_calls_become_envelope_fields() -> None:
    step, _ = await _call(
        GroundingOffer.CITE, ANSWER.name, {"text": "0 notes", "citations": CITED}, run_id="r_a"
    )
    assert isinstance(step, ProposeAction)
    assert step.proposal.arguments == {"text": "0 notes"}
    assert step.proposal.citations == (Citation(evidence_id=EVIDENCE, pointer="/count", value="0"),)

    step, _ = await _call(
        GroundingOffer.CITE, WRITE.name, {"text": "a", "rationale": RATIONALE}, run_id="r_w"
    )
    assert isinstance(step, ProposeAction)
    assert step.proposal.arguments == {"text": "a"}
    assert step.proposal.rationale == ProposalRationale.model_validate(RATIONALE)
    assert step.proposal.connection_id == WRITE.connection_id

    args = {"summary": "There are 0 notes.", "citations": CITED}
    step, _ = await _call(GroundingOffer.CITE_AND_ANSWER, GROUNDED_TOOL, args, run_id="r_g")
    assert isinstance(step, ProposeAction)
    assert step.proposal.contract_id == GROUNDED_ANSWER
    assert step.proposal.arguments == {"summary": "There are 0 notes."}
    assert len(step.proposal.citations) == 1

    plan = {
        "steps": [
            {"step_id": "a", "tool": WRITE.name, "arguments": {"text": "a"}},
            {"step_id": "b", "tool": PIN.name, "arguments": {"text": "b"}},
        ],
        "rationale": RATIONALE,
    }
    step, _ = await _call(
        GroundingOffer.CITE, PLAN_TOOL, plan, run_id="r_p", allowed=PLAN_ALLOWED, writes=2
    )
    assert isinstance(step, ProposePlan)
    assert step.plan.rationale == ProposalRationale.model_validate(RATIONALE)
    assert all(s.proposal.rationale is None for s in step.plan.steps)


async def test_undeclared_envelope_keys_never_reach_arguments() -> None:
    """Fix round 1 (C1-1, PR-26): a top-level ``citations`` or ``rationale`` key that the
    tool's own schema does not declare is never forwarded as an argument, in any mode. In
    ``off`` it is dropped; otherwise it becomes the envelope only where that field is offered
    for the tool's kind (citations on an answer, rationale on a write), and is dropped
    elsewhere."""
    both = {"citations": CITED, "rationale": RATIONALE}
    cases = 0
    for offer in GroundingOffer:
        cited = offer is not GroundingOffer.OFF
        for spec in (ANSWER, WRITE):
            step, _ = await _call(
                offer, spec.name, {"text": "a", **both}, run_id=f"r_{offer}_{spec.name}"
            )
            assert isinstance(step, ProposeAction), (offer, spec.name)
            assert step.proposal.arguments == {"text": "a"}, (offer, spec.name)
            wants_cites = cited and spec is ANSWER
            wants_rationale = cited and spec is WRITE
            assert bool(step.proposal.citations) is wants_cites, (offer, spec.name)
            assert (step.proposal.rationale is not None) is wants_rationale, (offer, spec.name)
            cases += 1
        step, _ = await _call(offer, READ.name, {"text": "a", **both}, run_id=f"r_{offer}_read")
        assert isinstance(step, RequestReads)
        assert dict(step.reads[0].arguments) == {"text": "a"}, offer
        cases += 1
    print(f"undeclared envelope cases: {cases}")
    assert cases == 9


async def test_off_keeps_todays_parsing() -> None:
    """With ``off`` the generic answer is an unknown tool and a plan rationale is refused."""
    # Offered only for cite_and_answer: pydantic-ai refuses a tool it was not given, and the
    # driver's own parse refuses the call too if it ever arrives.
    for offer in (GroundingOffer.OFF, GroundingOffer.CITE):
        driver = PydanticAiDriver(FunctionModel(lambda m, i: ModelResponse([])), SPECS)
        state = driver._runs.setdefault(f"r_{offer}_g", _RunState())
        call = ToolCallPart(GROUNDED_TOOL, {"summary": "s", "citations": CITED}, "call-1")
        step = driver._plan_step(state, DeferredToolRequests(calls=[call]), (), offer)
        assert isinstance(step, AskClarification)
        assert state.rejected == {"call-1": "unknown tool"}
    plan = {
        "steps": [{"step_id": "a", "tool": WRITE.name, "arguments": {"text": "a"}}],
        "rationale": RATIONALE,
    }
    step, driver = await _call(
        GroundingOffer.OFF, PLAN_TOOL, plan, run_id="r_off_p", allowed=PLAN_ALLOWED, writes=2
    )
    assert isinstance(step, AskClarification)
    assert _rejections(driver, "r_off_p") == {"call-1": PLAN_SHAPE_REFUSAL}


REFUSED: dict[str, tuple[GroundingOffer, str, dict[str, Any], str]] = {
    "citations-not-a-list": (
        GroundingOffer.CITE,
        ANSWER.name,
        {"text": "a", "citations": {"evidence_id": EVIDENCE}},
        CITATION_REFUSAL,
    ),
    "citation-missing-pointer": (
        GroundingOffer.CITE,
        ANSWER.name,
        {"text": "a", "citations": [{"evidence_id": EVIDENCE, "value": 1}]},
        CITATION_REFUSAL,
    ),
    "rationale-prose-goal": (
        GroundingOffer.CITE,
        WRITE.name,
        {"text": "a", "rationale": {**RATIONALE, "goal_ref": "the user's goal"}},
        RATIONALE_REFUSAL,
    ),
    "rationale-long-summary": (
        GroundingOffer.CITE,
        WRITE.name,
        {"text": "a", "rationale": {**RATIONALE, "summary": "x" * (SUMMARY_MAX + 1)}},
        RATIONALE_REFUSAL,
    ),
    "rationale-not-an-object": (
        GroundingOffer.CITE,
        WRITE.name,
        {"text": "a", "rationale": "because"},
        RATIONALE_REFUSAL,
    ),
    "grounded-without-citation": (
        GroundingOffer.CITE_AND_ANSWER,
        GROUNDED_TOOL,
        {"summary": "s", "citations": []},
        GROUNDED_REFUSAL,
    ),
}


@pytest.mark.parametrize("name", sorted(REFUSED))
async def test_refused_envelope_returns_a_fixed_refusal(name: str) -> None:
    offer, tool, args, refusal = REFUSED[name]
    step, driver = await _call(offer, tool, args, run_id=f"r_{name}")
    assert isinstance(step, AskClarification)  # the turn had no usable request
    assert _rejections(driver, f"r_{name}") == {"call-1": refusal}
    assert refusal in GROUNDING_REFUSALS


def test_refusal_case_count() -> None:
    assert len(REFUSED) == 6
    print(f"refused envelopes: {len(REFUSED)}")


async def test_tool_declaring_an_envelope_name_keeps_it() -> None:
    """Fix round 1 (C1-2): a tool whose own schema declares ``citations`` (an answer) or
    ``rationale`` (a write) builds and works in ``off`` exactly as before, and is offered no
    grounding in ``on``: its schema is its own, and the key stays its domain argument."""
    own_cites = dataclasses.replace(
        ANSWER,
        contract_id="notes.cited.answer.v1",
        parameters={
            "type": "object",
            "properties": {"text": {"type": "string"}, "citations": {"type": "array"}},
            "required": ["text"],
        },
    )
    own_rationale = dataclasses.replace(
        WRITE,
        contract_id="notes.reasoned.create.v1",
        parameters={
            "type": "object",
            "properties": {"text": {"type": "string"}, "rationale": {"type": "string"}},
            "required": ["text"],
        },
    )
    specs = (READ, own_cites, own_rationale)
    seen: list[dict[str, Any]] = []

    def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        seen.append(_request_view(info))
        return ModelResponse(parts=[TextPart("done")])

    driver = PydanticAiDriver(FunctionModel(model), specs)  # builds, as before
    for index, offer in enumerate(GroundingOffer):
        await driver.advance(_ctx(f"r_own_{index}"), DriverInput(task="t", grounding=offer))
        tools = _tools(seen[-1])
        for spec in (own_cites, own_rationale):
            assert tools[spec.name]["parameters_json_schema"] == dict(spec.parameters), offer
    arguments = {"text": "a", "citations": ["mine"], "rationale": "mine"}
    for offer in GroundingOffer:
        for spec in (own_cites, own_rationale):

            def call(
                messages: list[ModelMessage], info: AgentInfo, name: str = spec.name
            ) -> ModelResponse:
                return ModelResponse(parts=[ToolCallPart(name, arguments, "call-1")])

            calling = PydanticAiDriver(FunctionModel(call), specs)
            step = await calling.advance(
                _ctx(f"r_own_call_{offer}"), DriverInput(task="t", grounding=offer)
            )
            assert isinstance(step, ProposeAction), (offer, spec.name)
            own = "citations" if spec is own_cites else "rationale"
            assert step.proposal.arguments == {"text": "a", own: arguments[own]}, offer
            assert step.proposal.citations == () and step.proposal.rationale is None


# -- the pin across a profile flip (D8) --------------------------------------------------
async def test_inflight_off_run_schema_unchanged_after_flip() -> None:
    """A run pinned ``off`` keeps the ``off`` tool schema after the profile flips
    ``grounded_answers`` on: its resumed call's tools equal its first call's and the ERP off
    golden's. A run started after the flip is offered citations."""
    seen: list[dict[str, Any]] = []

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        seen.append(erp_off._strip(erp_off._request_view(messages, info)["function_tools"], {}))
        if len(seen) in (1, 3):
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        "request_clarification", {"question": "Which demand?"}, f"c{len(seen)}"
                    )
                ]
            )
        return ModelResponse(parts=[TextPart("Noted.")])

    profile = load_profile(fixture_profile_path())
    rt = await build_runtime(
        profile,
        driver_factory=lambda registry: PydanticAiDriver(
            FunctionModel(respond), tool_specs(registry, profile), guidance=registry.agent_guidance
        ),
    )
    run = await rt.coordinator.start_run(rt.operator, "Restock widget-a.", rt.scope)
    assert run.state is RunState.WAITING_INPUT
    rt.coordinator._features = Features(grounded_answers=FeatureMode.ON)  # the profile flips
    run = await rt.coordinator.resume_input(rt.operator, run.run_id, "demand:d-001", run.revision)
    assert len(seen) == 2
    golden = json.loads(erp_off.GOLDEN.read_text("utf-8"))
    off_tools = golden["erp-draft-po"]["requests"][0]["function_tools"]
    assert seen[0] == seen[1] == off_tools
    assert "citations" not in json.dumps(seen[1]) and "rationale" not in json.dumps(seen[1])

    after = await rt.coordinator.start_run(rt.operator, "Restock widget-a.", rt.scope)
    assert after.state is RunState.WAITING_INPUT and len(seen) == 3
    assert seen[2] != off_tools  # pinned `on`: answers cite, writes carry a rationale
    tools = {t["name"]: t["parameters_json_schema"]["properties"] for t in seen[2]}
    assert "citations" in tools["procurement_shortage_answer_v1"]
    assert "rationale" in tools["procurement_purchase_order_create_draft_v1"]
    assert GROUNDED_TOOL not in tools  # the fixture's typed answers keep the generic one out


# -- no dropped key reaches the ledger or an export (fix round 1, C1-1, PR-26) ------------
CANARY = "CANARY-3e4"
READ_EXTRAS = {"citations": f"{CANARY}-read-citations", "rationale": f"{CANARY}-read-rationale"}
SHORTAGE_ARGS = {
    "demand_ref": "demand:d-001",
    "product_ref": "product:widget-a",
    "demand_quantity": "12",
    "available": "5",
    "inbound": "0",
    "shortage": "7",
}
PO_ARGS = {
    "demand_ref": "demand:d-001",
    "product_ref": "product:widget-a",
    "supplier_ref": "supplier:approved-co",
    "offer_ref": "offer:a",
    "quantity": "7",
    "unit": "Units",
    "currency": "VND",
    "unit_price": "100",
    "subtotal": "700",
    "requested_date": "2026-10-20",
}
CANARY_RUNS = {
    "shortage": [
        [
            ("procurement_demand_read_v1", {"demand_ref": "demand:d-001", **READ_EXTRAS}),
            ("inventory_availability_read_v1", {"product_ref": "product:widget-a", **READ_EXTRAS}),
        ],
        [
            (
                "procurement_shortage_answer_v1",
                {
                    **SHORTAGE_ARGS,
                    "citations": [
                        {"evidence_id": "ev-none", "pointer": "/quantity", "value": f"{CANARY}-v"}
                    ],
                    "rationale": {"goal_ref": "run", "summary": f"{CANARY}-answer-rationale"},
                },
            )
        ],
        [("procurement_shortage_answer_v1", dict(SHORTAGE_ARGS))],
    ],
    "draft-po": [
        [
            ("procurement_demand_read_v1", {"demand_ref": "demand:d-001", **READ_EXTRAS}),
            ("inventory_availability_read_v1", {"product_ref": "product:widget-a", **READ_EXTRAS}),
            ("procurement_offers_read_v1", {"product_ref": "product:widget-a", **READ_EXTRAS}),
        ],
        [
            (
                "procurement_purchase_order_create_draft_v1",
                {
                    **PO_ARGS,
                    "citations": f"{CANARY}-write-citations",
                    "rationale": {
                        "goal_ref": "run",
                        "rules_considered": ["PR-003"],
                        "summary": f"{CANARY}-write-rationale",
                    },
                },
            )
        ],
    ],
}


@pytest.mark.parametrize("mode", list(FeatureMode))
async def test_no_canary_reaches_events_or_evidence(mode: FeatureMode) -> None:
    """Canary text in envelope keys the tools do not declare (on reads, an answer's
    rationale, a write's citations, and the offered fields themselves) reaches no event, no
    action record and no evidence bundle, in ``off``, ``shadow`` and ``on``: dropped keys
    are dropped, and the offered ones are stored as ids and digests only."""
    from e_agent.contracts.approval import ApprovalDecision
    from e_agent.kernel.evidence import build_evidence

    searched = 0
    for task, turns in CANARY_RUNS.items():
        cursor = 0

        def respond(
            messages: list[ModelMessage], info: AgentInfo, turns: Any = turns
        ) -> ModelResponse:
            nonlocal cursor
            cursor += 1
            if cursor > len(turns):
                return ModelResponse(parts=[TextPart("Done.")])
            calls = turns[cursor - 1]
            return ModelResponse(
                parts=[
                    ToolCallPart(name, dict(args), f"c{cursor}-{i}")
                    for i, (name, args) in enumerate(calls)
                ]
            )

        profile = load_profile(fixture_profile_path())
        profile = profile.model_copy(
            update={"features": profile.features.model_copy(update={"grounded_answers": mode})}
        )
        rt = await build_runtime(
            profile,
            driver_factory=lambda registry, p=profile, r=respond: PydanticAiDriver(
                FunctionModel(r), tool_specs(registry, p), guidance=registry.agent_guidance
            ),
        )
        run = await rt.coordinator.start_run(rt.operator, f"canary {task}", rt.scope)
        if run.state is RunState.WAITING_APPROVAL:
            pres = await rt.coordinator.pending_approval(rt.operator.tenant_id, run.run_id)
            run = await rt.coordinator.decide(
                actor=rt.operator,
                run_id=run.run_id,
                action_id=pres.action_id,
                action_digest=pres.digest,
                expected_run_revision=pres.run_revision,
                decision=ApprovalDecision.APPROVED,
            )
        assert run.state is RunState.SUCCEEDED, (mode, task, run.reason)
        tenant = rt.operator.tenant_id
        events = await rt.store.list_events(tenant, run.run_id)
        actions = await rt.store.list_actions(tenant, run.run_id)
        bundle = await build_evidence(
            rt.store,
            tenant,
            run.run_id,
            environment="fixture",
            versions={},
            features=profile.features,
        )
        text = json.dumps(
            [
                [e.model_dump(mode="json") for e in events],
                [a.model_dump(mode="json") for a in actions],
                bundle,
            ],
            default=str,
        )
        assert events and actions
        assert CANARY not in text, (mode, task)
        assert "rationale" not in json.dumps([a.arguments for a in actions]), (mode, task)
        searched += len(events)
    print(f"{mode.value}: no canary in {searched} events and 2 bundles")
