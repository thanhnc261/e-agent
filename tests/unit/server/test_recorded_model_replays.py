"""Accepted public model calls replay through the real host; no network/model/ERP access.

Two kinds of recording, kept in separate folders so neither is mistaken for the other
(PR-29): ``erp-model-calls`` holds parts captured from a local model, and
``erp-authored-plan-calls`` holds hand-authored parts (``provenance: "authored"``) that check
the driver's plan output (Task 2c.9) as a fixture. ``erp-authored-grounded-calls`` holds
hand-authored parts that check the driver's grounding envelope (Task 3e.4, ADR 0033 §5): it
names its own reads' evidence as ``<<evidence:CALL_ID>>``, which the replay resolves from
that call's tool return. No live model produced an authored file.
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path

import pytest
from e_agent.adapters.pydantic_ai import PydanticAiDriver
from e_agent.adapters.pydantic_ai.driver import PLAN_TOOL
from e_agent.adapters.pydantic_ai.grounding import GROUNDED_TOOL
from e_agent.contracts.action import ActionState
from e_agent.contracts.approval import ApprovalDecision
from e_agent.contracts.events import RunEventType
from e_agent.contracts.features import FeatureMode, Features
from e_agent.contracts.run import ReasonCode, RunState
from e_agent.contracts.task import GROUNDED_ANSWER
from e_agent.kernel.grounding import CITATION_MESSAGES, KERNEL_CITATION, CitationStatus
from e_agent.kernel.rationale import KERNEL_RATIONALE, RATIONALE_MESSAGES, RefKind
from e_agent.plugins.erp.simulator import fixture_profile_path
from e_agent.server.bootstrap import build_runtime, tool_specs
from e_agent.server.profile import load_profile
from pydantic_ai import ModelMessagesTypeAdapter, ModelRequest, TextPart, ToolCallPart
from pydantic_ai.messages import ToolReturnPart
from pydantic_ai.models.function import FunctionModel

REPLAYS = Path(__file__).resolve().parents[3] / "tests/replays"
ROOT = REPLAYS / "erp-model-calls"
AUTHORED_ROOT = REPLAYS / "erp-authored-plan-calls"
AUTHORED = ["draft-po-plan"]
GROUNDED_ROOT = REPLAYS / "erp-authored-grounded-calls"
GROUNDED = [
    "shortage-cited",
    "shortage-miscited",
    "draft-po-rationale",
    "draft-po-misruled",
    "open-pos-grounded",
]
EVIDENCE_PLACEHOLDER = re.compile(r"<<evidence:([^>]+)>>")
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


@pytest.mark.parametrize(
    ("root", "names"),
    [(ROOT, TASKS), (AUTHORED_ROOT, AUTHORED), (GROUNDED_ROOT, GROUNDED)],
)
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
    authored += [json.loads((GROUNDED_ROOT / f"{t}.json").read_text()) for t in GROUNDED]
    assert captured and authored
    for recording in captured:
        assert recording["kind"] == "recorded-public-model-parts-fixture-replay"
        assert "provenance" not in recording and recording["model_digest"]
    for recording in authored:
        assert recording["provenance"] == "authored"
        assert recording["kind"] == "authored-model-parts-fixture-replay"
        assert not {"model_digest", "seed", "temperature", "context_length"} & set(recording)
    print(f"provenance checked: {len(captured)} captured, {len(authored)} authored")


def _resolve_evidence(response, messages):
    """Replace each ``<<evidence:CALL_ID>>`` in an authored call with the evidence id of
    that call's tool return; a placeholder naming no returned read fails the replay."""
    returned = {
        part.tool_call_id: part.content["evidence_id"]
        for message in messages
        if isinstance(message, ModelRequest)
        for part in message.parts
        if isinstance(part, ToolReturnPart)
        and isinstance(part.content, dict)
        and "evidence_id" in part.content
    }
    for part in response.parts:
        if isinstance(part, ToolCallPart) and isinstance(part.args, str):
            part.args = EVIDENCE_PLACEHOLDER.sub(lambda m: returned[m.group(1)], part.args)
    return response


async def replay(
    task,
    *,
    omit_late_order=False,
    root=ROOT,
    offered=None,
    context_assembler=None,
    grounded_answers=None,
):
    """Replay one recording; ``context_assembler`` (Task 3d.3) and ``grounded_answers``
    (Task 3e.4) pin that mode for the run."""
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
        return _resolve_evidence(response, messages)

    profile = load_profile(fixture_profile_path())
    if "features" in recording:  # authored recordings pin their own toggles
        profile = profile.model_copy(
            update={
                "features": Features.model_validate(recording["features"]),
                "budgets": profile.budgets.model_copy(update=recording.get("budgets", {})),
            }
        )
    for name, mode in (
        ("context_assembler", context_assembler),
        ("grounded_answers", grounded_answers),
    ):
        if mode is not None:
            features = profile.features.model_copy(update={name: mode})
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


# -- Task 3e.4: the authored grounded replays (ADR 0033 §5) ---------------------------------
@pytest.mark.parametrize("task", GROUNDED)
async def test_authored_grounded_replay_verifies(task):
    """Each authored grounded recording replays through the driver's grounding envelope in
    ``on``: a typed answer or write ends verified by its verifier, the generic answer ends
    ``GROUNDED`` and is never verified (PR-19). A fixture check, not model evidence."""
    offered = []
    runtime, run, recording, cursor, response_count = await replay(
        task, root=GROUNDED_ROOT, offered=offered
    )
    assert recording["provenance"] == "authored"
    expected = ReasonCode(recording["expected_reason_code"])
    assert (run.state, run.reason_code) == (RunState.SUCCEEDED, expected), run.reason
    assert cursor == response_count
    assert (
        runtime.diagnostics()["fixture-erp"]["create_calls"] == recording["expected_fixture_writes"]
    )
    tenant = runtime.operator.tenant_id
    events = await runtime.store.list_events(tenant, run.run_id)
    assert not [e for e in events if e.type is RunEventType.FEATURE_FALLBACK]
    actions = await runtime.store.list_actions(tenant, run.run_id)
    if expected is ReasonCode.GROUNDED:
        assert actions == []  # no action record, no outcome report (ADR 0033 §3)
        assert not [e for e in events if e.type is RunEventType.OUTCOME_REPORTED]
        (final,) = [e for e in events if e.type is RunEventType.MESSAGE_FINAL]
        assert final.payload["contract_id"] == GROUNDED_ANSWER
        assert len(final.payload["citations"]) == 5
        assert all(GROUNDED_TOOL in names for names in offered)
        return
    assert any(
        a.contract_id == recording["expected_contract"] and a.state is ActionState.VERIFIED
        for a in actions
    )
    assert not any(GROUNDED_TOOL in names for names in offered)  # typed answers exist
    stored = [
        e.payload
        for e in events
        if e.type is RunEventType.PROPOSAL_CREATED
        and e.payload.get("contract_id") == recording["expected_contract"]
    ]
    assert stored and all("citations" in p or "rationale" in p for p in stored)
    for payload in stored:  # at rest: ids, pointers and digests only (PR-26)
        for citation in payload.get("citations", []):
            assert set(citation) == {"evidence_id", "pointer", "value_digest"}
        if "rationale" in payload:
            assert "summary" not in payload["rationale"]


@dataclass(frozen=True)
class Verdict:
    """What the grounding check decided about one proposal: its unresolved and mismatched
    citations, their (read, pointer) when known, and its unresolved rationale refs."""

    unresolved: int
    mismatched: int
    pointers: frozenset[tuple[str, str]] | None
    evidence_refs: int
    rule_refs: int

    @property
    def grounded(self) -> bool:
        return not (self.unresolved or self.mismatched or self.evidence_refs or self.rule_refs)


def _reads(events):
    """Evidence id to ``read#n``: runs differ in evidence ids, never in read order."""
    ids = [e.payload["evidence_id"] for e in events if e.type is RunEventType.READ_RECORDED]
    return {eid: f"read#{index}" for index, eid in enumerate(ids, start=1)}


def _on_verdicts(events):
    """``on``: a stored proposal with citations or a rationale passed the check; a
    ``validation.completed`` with ``KERNEL-CITATION`` or ``KERNEL-RATIONALE`` refused it."""
    reads, verdicts = _reads(events), []
    for event in events:
        if event.type is RunEventType.PROPOSAL_CREATED and (
            "citations" in event.payload or "rationale" in event.payload
        ):
            verdicts.append(Verdict(0, 0, frozenset(), 0, 0))
        elif event.type is RunEventType.VALIDATION_COMPLETED:
            found = event.payload["findings"]
            cites = [f for f in found if f["rule_id"] == KERNEL_CITATION]
            refs = [f for f in found if f["rule_id"] == KERNEL_RATIONALE]
            if not cites and not refs:
                continue
            status = {CITATION_MESSAGES[s]: s for s in CITATION_MESSAGES}
            kinds = [
                next(k for k in RefKind if RATIONALE_MESSAGES[k] == f["message"]) for f in refs
            ]
            verdicts.append(
                Verdict(
                    sum(status[f["message"]] is CitationStatus.UNRESOLVED for f in cites),
                    sum(status[f["message"]] is CitationStatus.MISMATCHED for f in cites),
                    frozenset((reads[f["evidence_ids"][0]], f["observed"]) for f in cites),
                    kinds.count(RefKind.EVIDENCE),
                    kinds.count(RefKind.RULE),
                )
            )
    return verdicts


def _shadow_verdicts(events):
    """``shadow``: each ``grounding.compared``, with the pointers of the citations it did not
    resolve read from its proposal's at-rest citations (same order as its verdicts)."""
    reads, verdicts = _reads(events), []
    stored = {
        e.action_id: e.payload.get("citations", [])
        for e in events
        if e.type is RunEventType.PROPOSAL_CREATED
    }
    for event in events:
        if event.type is not RunEventType.GROUNDING_COMPARED:
            continue
        cited, rationale = event.payload["citations"], event.payload["rationale"]
        pointers = frozenset()
        if cited["unresolved"] or cited["mismatched"]:
            at_rest = stored.get(event.action_id)
            pointers = (
                None
                if at_rest is None
                else frozenset(
                    (reads[c["evidence_id"]], c["pointer"])
                    for c, verdict in zip(at_rest, cited["verdicts"], strict=True)
                    if verdict != CitationStatus.RESOLVED
                )
            )
        verdicts.append(
            Verdict(
                cited["unresolved"],
                cited["mismatched"],
                pointers,
                rationale["evidence"]["unresolved"],
                rationale["rules"]["unresolved"],
            )
        )
    return verdicts


async def test_grounding_shadow_agrees_with_on():
    """The real consumer of ``grounded_answers: shadow`` (plan, Toggles; ADR 0033 §5): over
    the authored grounded replays, shadow's ``grounding.compared`` verdicts equal what ``on``
    decided, check by check, up to and including the first check ``on`` refused. After it the
    runs diverge by design: ``on`` sends a repair, ``shadow`` acts on nothing and the verifier
    or validation decides as today. Shadow never refuses, never falls back and ends as
    today."""
    compared = refused = 0
    replays = [
        t
        for t in GROUNDED
        if json.loads((GROUNDED_ROOT / f"{t}.json").read_text())["shadow_compared"]
    ]
    assert replays
    for task in replays:
        on = await replay(task, root=GROUNDED_ROOT)
        shadow = await replay(task, root=GROUNDED_ROOT, grounded_answers=FeatureMode.SHADOW)
        runs = {}
        for name, (runtime, run, *_rest) in (("on", on), ("shadow", shadow)):
            runs[name] = (
                run,
                await runtime.store.list_events(runtime.operator.tenant_id, run.run_id),
            )
        on_verdicts = _on_verdicts(runs["on"][1])
        shadow_verdicts = _shadow_verdicts(runs["shadow"][1])
        assert on_verdicts and shadow_verdicts, task
        first_refused = next((i for i, v in enumerate(on_verdicts) if not v.grounded), None)
        if first_refused is None:
            assert shadow_verdicts == on_verdicts, task
            n = len(on_verdicts)
        else:
            n = first_refused + 1
            assert shadow_verdicts[:n] == on_verdicts[:n], task
            refused += 1
        compared += n
        shadow_run, shadow_events = runs["shadow"]
        on_run = runs["on"][0]
        assert shadow_run.state is RunState.SUCCEEDED, task  # decided as today
        if first_refused is None:  # nothing refused: the runs are the same run
            assert shadow_run.reason_code is on_run.reason_code, task
        kinds = {e.type for e in shadow_events}
        assert RunEventType.GROUNDING_SHADOW_FAILED not in kinds
        assert RunEventType.FEATURE_FALLBACK not in kinds
        rules = {
            f["rule_id"]
            for e in shadow_events
            if e.type is RunEventType.VALIDATION_COMPLETED
            for f in e.payload["findings"]
        }
        assert not rules & {KERNEL_CITATION, KERNEL_RATIONALE}, task
    print(f"grounding shadow agrees with on: {compared} checks, {len(replays)} replays")
    print(f"checks on refused: {refused}")
    assert compared > 0 and refused > 0  # zero cases or no refusal would be vacuous (PR-31)
