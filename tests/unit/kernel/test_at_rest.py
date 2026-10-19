"""Model-authored refs at rest (Task 3.R1, phase review P-1, P-2, PR-26).

A ref the model names is stored verbatim only when the kernel resolved it against something
it already knows: a rationale's ``goal_ref`` when it is ``"run"`` or the run's task
definition ``id@version``, an evidence id or rule id the check resolved, a citation's
evidence id and pointer when they named a value of this run's evidence. Anything else is
stored as its ``jcs-sha256-v1`` digest under a key that says so. The repair finding sent
back to the model keeps the raw ref; the finding as recorded (``validation.completed`` and
the stored continuation) holds its digest and only evidence ids that resolved. Value-shaped
tokens (an email, a phone number, an order number) stand in for what a model could copy
into a ref. Runs over both stores through the ``run_store`` fixture (ENG-STORE-1).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import pytest
from e_agent.adapters.pydantic_ai.grounding import CITATIONS_SCHEMA
from e_agent.contracts.digest import digest
from e_agent.contracts.events import RunEvent, RunEventType
from e_agent.contracts.explain import RationaleRef
from e_agent.contracts.features import FeatureMode, Features
from e_agent.contracts.grounding import (
    EVIDENCE_ID_MAX,
    POINTER_MAX,
    Citation,
    ProposalRationale,
)
from e_agent.contracts.run import RunState
from e_agent.contracts.validation import Finding, ValidationStatus
from e_agent.kernel import at_rest, grounding, rationale
from e_agent.kernel.evidence import build_evidence, run_explanation
from e_agent.kernel.explain import explain
from e_agent.kernel.progress import project_progress
from e_agent.kernel.reconstruct import reconstruct
from e_agent.sdk.ports import Observation
from pydantic import ValidationError

from .conftest import READ, TENANT, Kernel
from .test_grounded_answer import GroundedDriver
from .test_grounding import CitingDriver, _evidence
from .test_rationale import RationaleDriver

MakeKernel = Callable[..., Kernel]
ON = Features(grounded_answers=FeatureMode.ON)
SHADOW = Features(grounded_answers=FeatureMode.SHADOW)
BOUND = Features(execution_ir=FeatureMode.SHADOW, grounded_answers=FeatureMode.ON)
EMAIL = "buyer@example.com"
PHONE = "+84901234567"
ORDER = "S00042"
TOKENS = (EMAIL, PHONE, ORDER)
PATH = "/" + PHONE  # a pointer that names nothing in the notes summary


def _rationale(goal: str, evidence: tuple[str, ...], rules: tuple[str, ...]) -> ProposalRationale:
    return ProposalRationale(
        goal_ref=goal, cited_evidence=evidence, rules_considered=rules, summary="why"
    )


async def _events(k: Kernel, run_id: str) -> list[RunEvent]:
    events: list[RunEvent] = await k.store.list_events(TENANT, run_id)
    return events


def _of(events: list[RunEvent], kind: RunEventType) -> list[RunEvent]:
    return [e for e in events if e.type is kind]


def _repairs(events: list[RunEvent]) -> list[dict[str, Any]]:
    return [
        f
        for e in _of(events, RunEventType.VALIDATION_COMPLETED)
        if e.action_id is None
        for f in e.payload["findings"]
    ]


async def _persisted(k: Kernel, run_id: str, features: Features) -> dict[str, str]:
    """Every persisted form a raw ref must be absent from, as JSON text: the run's event
    payloads, the evidence bundle, the explanation and the stored continuation without the
    rationale texts it keeps by design for the approval card (3.R1 ruling 8)."""
    events = await _events(k, run_id)
    bundle = await build_evidence(
        k.store, TENANT, run_id, environment="fixture", versions={}, features=features
    )
    explained = (await run_explanation(k.store, TENANT, run_id)).model_dump(mode="json")
    stored = await k.store.load_continuation(TENANT, run_id)
    assert stored is not None
    kernel = {
        key: value
        for key, value in stored[0]["data"].items()
        if key not in {"rationale", "step_rationales"}
    }
    return {
        "events": json.dumps([e.payload for e in events]),
        "bundle": json.dumps(bundle, default=str),
        "explanation": json.dumps(explained),
        "continuation": json.dumps(kernel, default=str),
    }


def _absent(persisted: dict[str, str], *raw: str) -> None:
    print(f"at rest: {len(persisted)} sinks x {len(raw)} refs")
    assert persisted and raw
    for sink, text in persisted.items():
        for ref in raw:
            assert ref not in text, (sink, ref)


# -- the helpers (pure) --------------------------------------------------------------------
def test_goal_ref_is_verbatim_only_in_the_closed_set() -> None:
    """3.R1 ruling 1, coordinator ruling 3: ``"run"`` and the run's ``id@version`` only. A
    value-shaped ref that a pattern would admit (``so00042@1``) is a digest."""
    goals = at_rest.known_goals("standup-note", "1")
    assert goals == frozenset({"run", "standup-note@1"})
    assert at_rest.known_goals(None, None) == frozenset({"run"})
    assert at_rest.goal_at_rest("run", goals) == {"goal_ref": "run"}
    assert at_rest.goal_at_rest("standup-note@1", goals) == {"goal_ref": "standup-note@1"}
    cases = (EMAIL, "so00042@1", "standup-note@2", "standup-note@1#create")
    for value in cases:
        assert at_rest.goal_at_rest(value, goals) == {"goal_ref_digest": digest(value)}
    print(f"goal refs: {len(cases)} digested cases")


def test_refs_split_resolved_ids_from_digests() -> None:
    """Ruling 2: resolved ids in order under the id key; unresolved only as digests under
    their own key, left out when empty; never mixed."""
    out = at_rest.refs_at_rest("ids", "digests", ("a", PHONE, "b", ORDER), {"a", "b"})
    assert out == {"ids": ["a", "b"], "digests": [digest(PHONE), digest(ORDER)]}
    assert at_rest.refs_at_rest("ids", "digests", ("a",), {"a"}) == {"ids": ["a"]}
    assert at_rest.refs_at_rest("ids", "digests", (), set()) == {"ids": []}


def test_citation_at_rest_is_verbatim_only_when_named() -> None:
    value = digest("0")
    named = at_rest.citation_at_rest("ev-1", "/count", value, named=True)
    assert named == {"evidence_id": "ev-1", "pointer": "/count", "value_digest": value}
    unnamed = at_rest.citation_at_rest(EMAIL, PATH, value, named=False)
    assert unnamed == {
        "evidence_id_digest": digest(EMAIL),
        "pointer_digest": digest(PATH),
        "value_digest": value,
    }


def test_finding_at_rest_keeps_only_a_digest() -> None:
    finding = Finding(
        rule_id="KERNEL-RATIONALE",
        rule_version="1",
        status=ValidationStatus.FAIL,
        message="fixed",
        observed=PHONE,
        evidence_ids=(PHONE,),
    )
    stored = at_rest.finding_at_rest(finding)
    assert (stored.observed, stored.evidence_ids) == (digest(PHONE), ())
    assert stored.model_copy(update={"observed": PHONE, "evidence_ids": (PHONE,)}) == finding


def test_rationale_at_rest_takes_the_check_result() -> None:
    r = _rationale(EMAIL, ("ev_1", PHONE), ("NOTE-001", ORDER))
    result = rationale.check_rationale([r], {"ev_1"}, {"NOTE-001"}, frozenset({"run"}))
    stored = rationale.at_rest(r, result)
    assert stored == {
        "goal_ref_digest": digest(EMAIL),
        "cited_evidence": ["ev_1"],
        "unresolved_evidence_digests": [digest(PHONE)],
        "rules_considered": ["NOTE-001"],
        "unresolved_rule_digests": [digest(ORDER)],
        "alternatives": [],
        "summary_digest": digest("why"),
    }
    _absent({"stored": json.dumps(stored)}, *TOKENS)


# -- the length caps (ruling 5) ------------------------------------------------------------
def test_citation_caps_and_the_offered_schema() -> None:
    Citation(evidence_id="e" * EVIDENCE_ID_MAX, pointer="/" * POINTER_MAX, value=1)
    with pytest.raises(ValidationError):
        Citation(evidence_id="e" * (EVIDENCE_ID_MAX + 1), pointer="", value=1)
    with pytest.raises(ValidationError):
        Citation(evidence_id="e", pointer="/" * (POINTER_MAX + 1), value=1)
    assert (EVIDENCE_ID_MAX, POINTER_MAX) == (128, 1024)
    props = CITATIONS_SCHEMA["items"]["properties"]
    assert props["evidence_id"]["maxLength"] == EVIDENCE_ID_MAX
    assert props["pointer"]["maxLength"] == POINTER_MAX


# -- the explanation record ----------------------------------------------------------------
def test_rationale_ref_has_exactly_one_goal_form() -> None:
    base = {"step_id": None, "cited_evidence": (), "rules_considered": ()}
    extra = {"alternatives": (), "summary_digest": digest("why")}
    with pytest.raises(ValidationError):
        RationaleRef(**base, **extra)
    with pytest.raises(ValidationError):
        RationaleRef(**base, **extra, goal_ref="run", goal_ref_digest=digest(EMAIL))
    plain = RationaleRef(**base, **extra, goal_ref="run").model_dump(mode="json")
    assert not {"goal_ref_digest", "unresolved_evidence_digests", "unresolved_rule_digests"} & (
        set(plain)
    )
    hidden = RationaleRef(**base, **extra, goal_ref_digest=digest(EMAIL)).model_dump(mode="json")
    assert "goal_ref" not in hidden and hidden["goal_ref_digest"] == digest(EMAIL)


# -- rationale end to end (shadow and on, both stores) -------------------------------------
def _unresolved_first(obs: Observation, attempt: int) -> ProposalRationale:
    """First an email goal, a phone-number evidence id and an order-number rule; then the
    run's own evidence and an inventory rule, the goal still value-shaped."""
    if attempt == 1:
        return _rationale(EMAIL, (PHONE,), (ORDER,))
    return _rationale(EMAIL, (obs.evidence.evidence_id,), ("NOTE-001",))


@pytest.mark.parametrize("features", [SHADOW, ON], ids=["shadow", "on"])
async def test_unresolved_rationale_refs_are_digests_at_rest(
    make_kernel: MakeKernel, features: Features
) -> None:
    k = make_kernel(features=features, driver=RationaleDriver(_unresolved_first))

    run = await k.coordinator.start_run(k.requester, "write standup note", k.scope)

    assert run.state is RunState.WAITING_APPROVAL, run.reason
    events = await _events(k, run.run_id)
    (created,) = _of(events, RunEventType.PROPOSAL_CREATED)
    stored = created.payload["rationale"]
    assert stored["goal_ref_digest"] == digest(EMAIL) and "goal_ref" not in stored
    if features is SHADOW:  # the unresolved proposal is today's path, stored at rest
        assert _repairs(events) == []
        assert stored["cited_evidence"] == [] and stored["rules_considered"] == []
        assert stored["unresolved_evidence_digests"] == [digest(PHONE)]
        assert stored["unresolved_rule_digests"] == [digest(ORDER)]
    else:  # `on`: the repair is recorded as digests; the model got the raw refs
        evidence, rule = _repairs(events)
        assert (evidence["observed"], evidence["evidence_ids"]) == (digest(PHONE), [])
        assert (rule["observed"], rule["evidence_ids"]) == (digest(ORDER), [])
        sent = k.driver.seen[2].findings
        assert [(f.observed, f.evidence_ids) for f in sent] == [(PHONE, (PHONE,)), (ORDER, ())]
        assert "unresolved_evidence_digests" not in stored
        assert "unresolved_rule_digests" not in stored
    explained = await run_explanation(k.store, TENANT, run.run_id)
    (ref,) = explained.proposals[0].rationales
    assert (ref.goal_ref, ref.goal_ref_digest) == (None, digest(EMAIL))
    if features is SHADOW:
        assert ref.unresolved_evidence_digests == (digest(PHONE),)
        assert ref.unresolved_rule_digests == (digest(ORDER),)
    _absent(await _persisted(k, run.run_id, features), *TOKENS)


async def test_resolved_rationale_refs_stay_verbatim(make_kernel: MakeKernel) -> None:
    """A goal equal to the run's task definition ``id@version`` (a run bound in execution
    IR ``shadow``), a resolved evidence id and an inventory rule are stored and explained
    verbatim, with no digest key."""

    def make(obs: Observation, attempt: int) -> ProposalRationale:
        return _rationale("standup-note@1", (obs.evidence.evidence_id,), ("NOTE-001",))

    k = make_kernel(features=BOUND, driver=RationaleDriver(make))
    run = await k.coordinator.start_run(
        k.requester, "write standup note", k.scope, task_kind="standup-note"
    )

    assert run.state is RunState.WAITING_APPROVAL, run.reason
    assert (run.task_id, run.task_version) == ("standup-note", "1")
    cont = await k.coordinator._load_cont(TENANT, run.run_id)
    evidence_id = next(iter(cont.observations.values())).evidence.evidence_id
    (created,) = _of(await _events(k, run.run_id), RunEventType.PROPOSAL_CREATED)
    stored = created.payload["rationale"]
    assert stored["goal_ref"] == "standup-note@1"
    assert stored["cited_evidence"] == [evidence_id]
    assert stored["rules_considered"] == ["NOTE-001"]
    assert not {"goal_ref_digest", "unresolved_evidence_digests", "unresolved_rule_digests"} & (
        set(stored)
    )
    (ref,) = (await run_explanation(k.store, TENANT, run.run_id)).proposals[0].rationales
    assert (ref.goal_ref, ref.goal_ref_digest) == ("standup-note@1", None)
    assert (ref.cited_evidence, ref.rules_considered) == ((evidence_id,), ("NOTE-001",))


async def test_task_goal_of_an_unbound_run_is_a_digest(make_kernel: MakeKernel) -> None:
    """``standup-note@1`` is known only to a run bound to that definition."""

    def make(obs: Observation, attempt: int) -> ProposalRationale:
        return _rationale("standup-note@1", (obs.evidence.evidence_id,), ())

    k = make_kernel(features=ON, driver=RationaleDriver(make))
    run = await k.coordinator.start_run(k.requester, "write standup note", k.scope)
    (created,) = _of(await _events(k, run.run_id), RunEventType.PROPOSAL_CREATED)
    assert created.payload["rationale"]["goal_ref_digest"] == digest("standup-note@1")


async def test_reconstruct_round_trip_on_the_new_shape(make_kernel: MakeKernel) -> None:
    """Ruling 7: the reconstruction carries the stored keys as recorded (no schema version
    keys them), and the explanation built from it renders each digest as a digest."""
    k = make_kernel(features=SHADOW, driver=RationaleDriver(_unresolved_first))
    run = await k.coordinator.start_run(k.requester, "write standup note", k.scope)
    events = await _events(k, run.run_id)
    (created,) = _of(events, RunEventType.PROPOSAL_CREATED)

    rebuilt = reconstruct(events)

    assert rebuilt.rationales[str(created.action_id)] == {"rationale": created.payload["rationale"]}
    wire = json.loads(json.dumps([e.model_dump(mode="json") for e in events]))
    again = reconstruct(RunEvent.model_validate(e) for e in wire)
    assert again.rationales == rebuilt.rationales
    steps = await k.store.list_steps(TENANT, run.run_id)
    (ref,) = explain(project_progress(events, steps), rebuilt).proposals[0].rationales
    assert ref.goal_ref_digest == digest(EMAIL)
    assert ref.unresolved_evidence_digests == (digest(PHONE),)
    assert ref.unresolved_rule_digests == (digest(ORDER),)
    assert (ref.cited_evidence, ref.rules_considered) == ((), ())


# -- citations end to end ------------------------------------------------------------------
def _cite_unnamed_first(obs: Observation, attempt: int) -> tuple[Citation, ...]:
    """First an email evidence id, then the run's evidence at a phone-number pointer that
    names nothing, then citations that resolve."""
    eid = obs.evidence.evidence_id
    if attempt == 1:
        return (Citation(evidence_id=EMAIL, pointer="/count", value="0"),)
    if attempt == 2:
        return (Citation(evidence_id=eid, pointer=PATH, value="0"),)
    return (Citation(evidence_id=eid, pointer="/count", value="0"),)


@pytest.mark.parametrize("features", [SHADOW, ON], ids=["shadow", "on"])
async def test_unnamed_citation_refs_are_digests_at_rest(
    make_kernel: MakeKernel, features: Features
) -> None:
    driver = CitingDriver(_cite_unnamed_first)
    k = make_kernel(features=features, with_answer=True, driver=driver)

    run = await k.coordinator.start_run(k.requester, "summarise the notes", k.scope)

    assert run.state is RunState.SUCCEEDED, run.reason
    events = await _events(k, run.run_id)
    created = _of(events, RunEventType.PROPOSAL_CREATED)
    if features is SHADOW:  # the answer took today's path; its citation is at rest
        (answer,) = created
        assert answer.payload["citations"] == [
            {
                "evidence_id_digest": digest(EMAIL),
                "pointer_digest": digest("/count"),
                "value_digest": digest("0"),
            }
        ]
    else:
        first, second = _repairs(events)
        assert (first["observed"], first["evidence_ids"]) == (digest("/count"), [])
        assert (second["observed"], second["evidence_ids"]) == (digest(PATH), [])
        sent = [f for s in driver.seen for f in s.findings]
        assert [(f.observed, f.evidence_ids[0]) for f in sent][:1] == [("/count", EMAIL)]
        assert sent[1].observed == PATH
        (answer,) = created
        (resolved,) = answer.payload["citations"]
        assert (resolved["pointer"], resolved["value_digest"]) == ("/count", digest("0"))
    _absent(await _persisted(k, run.run_id, features), EMAIL, PHONE)


async def test_mismatched_citation_that_named_a_value_stays_verbatim(
    make_kernel: MakeKernel,
) -> None:
    """Coordinator ruling 4: a citation naming a real evidence id and pointer is verbatim
    whatever its status; a mismatch keeps its pointer and evidence id."""

    def cite(obs: Observation, attempt: int) -> tuple[Citation, ...]:
        value = "7" if attempt == 1 else "0"
        return (Citation(evidence_id=obs.evidence.evidence_id, pointer="/count", value=value),)

    k = make_kernel(features=SHADOW, with_answer=True, driver=CitingDriver(cite))
    run = await k.coordinator.start_run(k.requester, "summarise the notes", k.scope)
    events = await _events(k, run.run_id)
    read = _of(events, RunEventType.READ_RECORDED)[0]
    (answer,) = _of(events, RunEventType.PROPOSAL_CREATED)
    assert answer.payload["citations"] == [
        {
            "evidence_id": read.payload["evidence_id"],
            "pointer": "/count",
            "value_digest": digest("7"),
        }
    ]


def test_invalid_value_naming_nothing_is_a_digest() -> None:
    """A value outside the digest profile is ``mismatched`` before any lookup: when its
    evidence id and pointer name nothing, they are still digests at rest."""
    obs = Observation(
        request_id="r1", contract_id=READ.contract_id, data={"count": "0"}, evidence=_evidence()
    )
    bad = Citation(evidence_id=EMAIL, pointer=PATH, value="\ud800")  # a lone surrogate
    (verdict,) = grounding.check_citations([obs], [bad]).verdicts
    assert verdict.status is grounding.CitationStatus.MISMATCHED and not verdict.named
    assert verdict.at_rest()["evidence_id_digest"] == digest(EMAIL)


async def test_grounded_answer_unresolved_citation_is_a_digest(make_kernel: MakeKernel) -> None:
    """``grounded.answer.v1`` in ``on``: its ``KERNEL-CITATION`` repair is recorded as a
    digest, and the model got the raw pointer."""

    def cite(obs: Observation, attempt: int) -> tuple[Citation, ...]:
        pointer = PATH if attempt == 1 else "/count"
        return (Citation(evidence_id=obs.evidence.evidence_id, pointer=pointer, value="0"),)

    driver = GroundedDriver(cite)
    k = make_kernel(features=ON, driver=driver)
    run = await k.coordinator.start_run(k.requester, "how many standup notes are there?", k.scope)

    assert run.state is RunState.SUCCEEDED, run.reason
    events = await _events(k, run.run_id)
    (finding,) = _repairs(events)
    assert (finding["observed"], finding["evidence_ids"]) == (digest(PATH), [])
    assert driver.seen[2].findings[0].observed == PATH
    (final,) = _of(events, RunEventType.MESSAGE_FINAL)
    assert [c["pointer"] for c in final.payload["citations"]] == ["/count"]
    _absent(await _persisted(k, run.run_id, ON), PHONE)
