"""`ProposalRationale` on proposals and plans (ADR 0033 §4, §5, Task 3e.3, D6, Review Focus
5 and 7).

A write proposal or a plan may carry a rationale: the goal it serves, the evidence ids of
this run it rests on, the rule ids it considered, the alternatives it rejected and a short
summary. It is model output, a claim the kernel checks, never an approval input and never in
the approval digest (target §5.6). In ``on`` an evidence id that is not an observation of
this run, or a rule id that is neither a kernel finding id nor a rule the admitted
validators evaluated for the proposal, is the repair finding ``KERNEL-RATIONALE`` before an
action exists. In ``shadow`` the proposal takes today's path and the kernel records
``grounding.compared``. In ``off`` the rationale is dropped and nothing changes. At rest the
rationale is ids, codes and a digest of each model-authored text, never the text (owner,
G2, PR-26); the text lives only in the run's continuation. Runs over both stores through
the ``run_store`` fixture (ENG-STORE-1).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import pytest
from e_agent.contracts.action import ActionState
from e_agent.contracts.approval import ApprovalDecision
from e_agent.contracts.context import Budgets, TaskContext
from e_agent.contracts.digest import digest
from e_agent.contracts.events import RunEvent, RunEventType
from e_agent.contracts.evidence import EvidenceRef
from e_agent.contracts.features import FeatureMode, Features
from e_agent.contracts.grounding import Citation, ProposalRationale, RejectedAlternative
from e_agent.contracts.plan import ActionPlan, ActionProposal, plan_to_wire
from e_agent.contracts.run import ReasonCode, RunState
from e_agent.kernel import rationale
from e_agent.kernel.approval import compute_digest
from e_agent.kernel.continuation import _Continuation
from e_agent.kernel.evidence import run_explanation
from e_agent.kernel.features import FALLBACK_MESSAGES, TERMINAL_MESSAGES
from e_agent.kernel.ir import StepDigestContext, plan_digest_input
from e_agent.sdk.ports import (
    DriverInput,
    DriverStep,
    FinalAnswer,
    Observation,
    ProposeAction,
    ReadRequest,
    RequestReads,
)
from pydantic import ValidationError

from .conftest import (
    CONN,
    CREATE,
    FIRST,
    FOLLOW_UP,
    NOTE_INPUT,
    NOTES_TASK,
    PLAN_BUDGETS,
    READ,
    TENANT,
    Kernel,
    NotesPlanDriver,
    two_step_plan,
)
from .test_mode_pinning import OFF_CONTINUATION_KEYS

MakeKernel = Callable[..., Kernel]
ON = Features(grounded_answers=FeatureMode.ON)
SHADOW = Features(grounded_answers=FeatureMode.SHADOW)
PLAN_ON = Features(execution_ir=FeatureMode.ON, grounded_answers=FeatureMode.ON)
SCHEMAS = {"c": NOTE_INPUT, "p": NOTE_INPUT}
GROUNDING_EVENTS = {RunEventType.GROUNDING_COMPARED, RunEventType.GROUNDING_SHADOW_FAILED}
SUMMARY_TEXT = "SENTINEL-3e3-summary-text"
ALT_TEXT = "SENTINEL-3e3-alternative-line"
SECRETS = (SUMMARY_TEXT, ALT_TEXT)
OTHER_DIGEST = "jcs-sha256-v1:" + "0" * 64
AT_REST_KEYS = {"goal_ref", "cited_evidence", "rules_considered", "alternatives", "summary_digest"}

Make = Callable[[Observation, int], ProposalRationale | None]
"""Builds a proposal's rationale from the run's observation and the attempt (1, 2, ...)."""


def _rationale(
    evidence: tuple[str, ...] = (), rules: tuple[str, ...] = (), summary: str = SUMMARY_TEXT
) -> ProposalRationale:
    return ProposalRationale(
        goal_ref="run",
        cited_evidence=evidence,
        rules_considered=rules,
        alternatives=(
            RejectedAlternative(
                proposal_digest=OTHER_DIGEST,
                reason_code=ReasonCode.VALIDATION_FAILED,
                line=ALT_TEXT,
            ),
        ),
        summary=summary,
    )


def _own(*rules: str) -> Make:
    """A rationale citing the run's own observation and ``rules``."""

    def make(obs: Observation, attempt: int) -> ProposalRationale:
        return _rationale((obs.evidence.evidence_id,), rules)

    return make


def _wrong_then_right(evidence: str | None = "ev_unknown", rule: str = "NOTE-001") -> Make:
    """First a rationale naming ``evidence`` (None: the run's own) and ``rule``, then one
    that resolves."""

    def make(obs: Observation, attempt: int) -> ProposalRationale:
        if attempt == 1:
            return _rationale((evidence or obs.evidence.evidence_id,), (rule,))
        return _rationale((obs.evidence.evidence_id,), ("NOTE-001", "KERNEL-CITATION"))

    return make


@dataclass
class RationaleDriver:
    """Reads the notes summary, then proposes one note with the rationale ``make`` builds."""

    make: Make
    driver_id: str = "notes-rationale-driver"
    attempts: int = 0
    seen: list[DriverInput] = field(default_factory=list)

    async def advance(self, ctx: TaskContext, step_input: DriverInput) -> DriverStep:
        self.seen.append(step_input)
        if step_input.action_result is not None:
            return FinalAnswer(text="done")
        if not step_input.observations:
            request = ReadRequest(
                request_id="r1", contract_id=READ.contract_id, connection_id=CONN, arguments={}
            )
            return RequestReads(reads=(request,))
        self.attempts += 1
        proposal = ActionProposal(
            contract_id=CREATE.contract_id,
            connection_id=CONN,
            arguments={"text": "standup notes"},
            rationale=self.make(step_input.observations[0], self.attempts),
        )
        return ProposeAction(proposal=proposal)


@dataclass
class PlanRationaleDriver(NotesPlanDriver):
    """Proposes ``build(obs)``: a plan whose rationales need the run's evidence id."""

    build: Callable[[Observation], ActionPlan] = field(default=lambda obs: two_step_plan())

    async def advance(self, ctx: TaskContext, step_input: DriverInput) -> DriverStep:
        if step_input.observations and step_input.action_result is None:
            self.plan = self.build(step_input.observations[0])
        return await super().advance(ctx, step_input)


def _kernel(make_kernel: MakeKernel, make: Make, features: Features | None, **kw: Any) -> Kernel:
    return make_kernel(features=features, driver=RationaleDriver(make), **kw)


async def _start(k: Kernel, task_kind: str | None = None) -> Any:
    return await k.coordinator.start_run(
        k.requester, "write standup note", k.scope, task_kind=task_kind
    )


async def _events(k: Kernel, run_id: str) -> list[RunEvent]:
    return await k.store.list_events(TENANT, run_id)


def _of(events: list[RunEvent], kind: RunEventType) -> list[RunEvent]:
    return [e for e in events if e.type is kind]


def _repairs(events: list[RunEvent]) -> list[dict[str, Any]]:
    """The findings of the kernel's repair records: ``validation.completed`` with no action."""
    return [
        f
        for e in _of(events, RunEventType.VALIDATION_COMPLETED)
        if e.action_id is None
        for f in e.payload["findings"]
    ]


def _validated(k: Kernel) -> list[Any]:
    """Spy on the notes validator: every proposal it is given."""
    seen: list[Any] = []
    real = k.validator.validate

    async def validate(ctx: TaskContext, item: Any) -> Any:
        seen.append(item.proposal)
        return await real(ctx, item)

    k.validator.validate = validate  # type: ignore[method-assign]
    return seen


async def _stored(k: Kernel, run_id: str) -> dict[str, Any]:
    stored = await k.store.load_continuation(TENANT, run_id)
    assert stored is not None
    data: dict[str, Any] = stored[0]["data"]
    return data


def _broken_check(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError(f"rationale engine down {SUMMARY_TEXT}")

    monkeypatch.setattr(rationale, "check_rationale", broken)


def _no_text(events: list[RunEvent]) -> None:
    dumped = json.dumps([e.payload for e in events])
    for text in SECRETS:
        assert text not in dumped


# -- the check in `on` ---------------------------------------------------------------------
async def test_rationale_with_unknown_evidence_is_kernel_rationale(
    make_kernel: MakeKernel,
) -> None:
    """An evidence id that names no observation of this run is ``KERNEL-RATIONALE``, before
    an action exists, within the repair budget; the repaired proposal takes today's path."""
    k = _kernel(make_kernel, _wrong_then_right(), ON)

    run = await _start(k)

    assert run.state is RunState.WAITING_APPROVAL, run.reason
    events = await _events(k, run.run_id)
    (finding,) = _repairs(events)
    assert finding["rule_id"] == rationale.KERNEL_RATIONALE
    assert finding["observed"] == "ev_unknown"
    assert finding["evidence_ids"] == ["ev_unknown"]
    assert finding["message"] == rationale.RATIONALE_MESSAGES[rationale.RefKind.EVIDENCE]
    (created,) = _of(events, RunEventType.PROPOSAL_CREATED)  # the repaired proposal only
    assert len(await k.store.list_actions(TENANT, run.run_id)) == 1
    driver = k.driver
    assert [f.rule_id for f in driver.seen[2].findings] == [rationale.KERNEL_RATIONALE]
    cont = await k.coordinator._load_cont(TENANT, run.run_id)
    assert cont.repairs == 1
    obs = next(iter(cont.observations.values()))
    assert created.payload["rationale"]["cited_evidence"] == [obs.evidence.evidence_id]
    _no_text(events)


async def test_rationale_evidence_of_another_run_is_unresolved(make_kernel: MakeKernel) -> None:
    """Review Focus 5, T6: an evidence id of a second run of the same tenant does not
    resolve; the lookup is this run's continuation, never the tenant."""
    k = _kernel(make_kernel, _own(), ON)
    first = await _start(k)
    assert first.state is RunState.WAITING_APPROVAL
    other = await k.coordinator._load_cont(TENANT, first.run_id)
    foreign = next(iter(other.observations.values())).evidence.evidence_id
    k.driver.make = _wrong_then_right(evidence=foreign)
    k.driver.attempts = 0

    second = await _start(k)

    assert second.state is RunState.WAITING_APPROVAL
    (finding,) = _repairs(await _events(k, second.run_id))
    assert (finding["rule_id"], finding["observed"]) == (rationale.KERNEL_RATIONALE, foreign)


async def test_rationale_with_unknown_rule_is_kernel_rationale(make_kernel: MakeKernel) -> None:
    """A rule id the admitted validators did not evaluate for the proposal, and that is no
    kernel finding id, is ``KERNEL-RATIONALE``; ``NOTE-001`` (the notes validator's rule)
    and a ``KERNEL-*`` id resolve."""
    k = _kernel(make_kernel, _wrong_then_right(evidence=None, rule="NOTE-999"), ON)

    run = await _start(k)

    assert run.state is RunState.WAITING_APPROVAL, run.reason
    events = await _events(k, run.run_id)
    (finding,) = _repairs(events)
    assert (finding["rule_id"], finding["observed"]) == (rationale.KERNEL_RATIONALE, "NOTE-999")
    assert finding["message"] == rationale.RATIONALE_MESSAGES[rationale.RefKind.RULE]
    assert "evidence_ids" not in finding or not finding["evidence_ids"]
    (created,) = _of(events, RunEventType.PROPOSAL_CREATED)
    assert created.payload["rationale"]["rules_considered"] == ["NOTE-001", "KERNEL-CITATION"]
    _no_text(events)


async def test_rationale_repairs_count_against_the_budget(make_kernel: MakeKernel) -> None:
    """A rationale that never resolves exhausts ``max_validation_repairs``: the run fails
    ``VALIDATION_FAILED`` and no action is ever created."""
    k = _kernel(
        make_kernel,
        lambda obs, n: _rationale(("ev_unknown",)),
        ON,
        budgets=Budgets(max_validation_repairs=1),
    )

    run = await _start(k)

    assert (run.state, run.reason_code) == (RunState.FAILED, ReasonCode.VALIDATION_FAILED)
    assert await k.store.list_actions(TENANT, run.run_id) == []
    rules = {f["rule_id"] for f in _repairs(await _events(k, run.run_id))}
    assert rules == {rationale.KERNEL_RATIONALE}


async def test_resolved_rationale_changes_nothing(make_kernel: MakeKernel) -> None:
    """A rationale that resolves can only fail to add a finding: the proposal is validated,
    blocked or approved exactly as without it (ADR 0033 §4)."""
    k = _kernel(make_kernel, _own("NOTE-001"), ON)
    seen = _validated(k)

    run = await _start(k)

    assert run.state is RunState.WAITING_APPROVAL
    assert _repairs(await _events(k, run.run_id)) == []
    assert [(p.rationale, p.citations) for p in seen] == [(None, ())]


# -- the plan path -------------------------------------------------------------------------
def _plan(
    obs: Observation,
    *,
    plan: ProposalRationale | None,
    step: ProposalRationale | None,
    steps: int = 2,
) -> ActionPlan:
    base = two_step_plan()
    eid = obs.evidence.evidence_id
    cited = (Citation(evidence_id=eid, pointer="/topic", value="standup"),)
    planned = tuple(
        s.model_copy(
            update={
                "proposal": s.proposal.model_copy(update={"rationale": step, "citations": cited})
            }
        )
        for s in base.steps[:steps]
    )
    if steps == 1:
        planned = (planned[0].model_copy(update={"depends_on": ()}),)
    return base.model_copy(update={"steps": planned, "rationale": plan})


def _plan_kernel(make_kernel: MakeKernel, build: Callable[[Observation], ActionPlan]) -> Kernel:
    driver = PlanRationaleDriver(build=build)
    return make_kernel(features=PLAN_ON, budgets=PLAN_BUDGETS, driver=driver, input_schemas=SCHEMAS)


def _bad(obs: Observation) -> ProposalRationale:
    return _rationale(("ev_unknown",))


def _good(obs: Observation) -> ProposalRationale:
    return _rationale((obs.evidence.evidence_id,), ("NOTE-001",))


@pytest.mark.parametrize(
    ("case", "build"),
    [
        ("plan", lambda obs: _plan(obs, plan=_bad(obs), step=_good(obs))),
        ("step", lambda obs: _plan(obs, plan=_good(obs), step=_bad(obs))),
        ("one-step plan", lambda obs: _plan(obs, plan=_bad(obs), step=None, steps=1)),
        ("one-step both", lambda obs: _plan(obs, plan=_good(obs), step=_bad(obs), steps=1)),
    ],
)
async def test_plan_rationale_is_checked(
    make_kernel: MakeKernel, case: str, build: Callable[[Observation], ActionPlan]
) -> None:
    """A plan's own rationale and each step's are checked like a proposal's, a 1-step plan's
    too: an unresolved one is ``KERNEL-RATIONALE`` before the plan or an action is stored.
    The driver repeats the plan, so the run exhausts its repairs."""
    k = _plan_kernel(make_kernel, build)

    run = await _start(k, NOTES_TASK.task_id)

    assert (run.state, run.reason_code) == (RunState.FAILED, ReasonCode.VALIDATION_FAILED), case
    events = await _events(k, run.run_id)
    assert {f["rule_id"] for f in _repairs(events)} == {rationale.KERNEL_RATIONALE}
    assert await k.store.list_actions(TENANT, run.run_id) == []
    assert not _of(events, RunEventType.IR_PLAN_COMPILED)
    _no_text(events)


@pytest.mark.parametrize("steps", [1, 2])
async def test_plan_rationale_stays_out_of_validators_plan_and_digest(
    make_kernel: MakeKernel, steps: int
) -> None:
    """A resolved plan rationale (and the steps' rationales and citations, carried from 3e.1)
    never reaches a validator, the stored plan or the approval digest input; at rest it is
    the plan's and each step's ids and digests, the texts only in the continuation."""
    k = _plan_kernel(
        make_kernel, lambda obs: _plan(obs, plan=_good(obs), step=_good(obs), steps=steps)
    )
    seen = _validated(k)

    run = await _start(k, NOTES_TASK.task_id)

    assert run.state is RunState.WAITING_APPROVAL, run.reason
    assert seen and all((p.rationale, p.citations) == (None, ()) for p in seen)
    events = await _events(k, run.run_id)
    _no_text(events)
    (created,) = _of(events, RunEventType.PROPOSAL_CREATED)
    assert set(created.payload["rationale"]) == AT_REST_KEYS
    pres = await k.coordinator.pending_approval(TENANT, run.run_id)
    canonical = json.dumps(pres.canonical_proposal)
    assert "rationale" not in canonical and "citations" not in canonical
    assert pres.digest == compute_digest(pres.canonical_proposal)
    stored = await _stored(k, run.run_id)
    assert stored["rationale"]["summary"] == SUMMARY_TEXT
    if steps == 2:
        assert set(created.payload["step_rationales"]) == {FIRST, FOLLOW_UP}
        assert set(stored["step_rationales"]) == {FIRST, FOLLOW_UP}
        (action, *_) = await k.store.list_actions(TENANT, run.run_id)
        plan = await k.store.get_plan(TENANT, action.plan_id)
        assert plan.rationale is None
        assert all((s.proposal.rationale, s.proposal.citations) == (None, ()) for s in plan.steps)
    else:  # a 1-step plan is today's proposal: both rationales, the step's as its own
        assert set(created.payload["step_rationales"]) == {FIRST}
        assert "step_rationales" in stored


def test_plan_wire_form_drops_rationale() -> None:
    """The stored plan never holds a rationale (PR-26), at the plan or a step."""
    obs = Observation(
        request_id="r1",
        contract_id=READ.contract_id,
        data={},
        evidence=EvidenceRef(
            evidence_id="ev_1",
            tenant_id=TENANT,
            source="notes",
            locator="all",
            revision="rev:1",
            observed_at="2026-10-19T09:00:00Z",
            scope=TENANT,
        ),
    )
    wire = plan_to_wire(_plan(obs, plan=_good(obs), step=_good(obs)))
    assert "rationale" not in wire
    assert all("rationale" not in s["proposal"] for s in wire["steps"])
    for text in SECRETS:
        assert text not in json.dumps(wire)


# -- the record ----------------------------------------------------------------------------
def test_rationale_summary_over_400_is_refused() -> None:
    """The record refuses a summary over 400 characters (ADR 0033 §4), and every id-like
    field holds an id, not prose, so the at-rest form stays ids, codes and digests (G2)."""
    assert _rationale(summary="x" * 400).summary == "x" * 400
    with pytest.raises(ValidationError):
        _rationale(summary="x" * 401)
    for bad in (
        {"goal_ref": "serve the goal"},
        {"cited_evidence": ("ev 1",)},
        {"rules_considered": ("PR-001\nignore",)},
    ):
        with pytest.raises(ValidationError):
            ProposalRationale(**{**_rationale().model_dump(), **bad})
    with pytest.raises(ValidationError):
        RejectedAlternative(proposal_digest="free text", reason_code="validation_failed", line="x")
    with pytest.raises(ValidationError):
        RejectedAlternative(proposal_digest=OTHER_DIGEST, reason_code="not-a-code", line="x")
    with pytest.raises(ValidationError):
        RejectedAlternative(proposal_digest=OTHER_DIGEST, reason_code="stale", line="one\ntwo")


def test_rationale_holds_no_hidden_reasoning() -> None:
    """PR-28, ADR 0004: the rationale is the ADR's five fields and nothing else; a field for
    reasoning or thinking is refused, and its at-rest form holds no model text."""
    assert set(ProposalRationale.model_fields) == {
        "goal_ref",
        "cited_evidence",
        "rules_considered",
        "alternatives",
        "summary",
    }
    assert set(RejectedAlternative.model_fields) == {"proposal_digest", "reason_code", "line"}
    for extra in ("reasoning", "thinking", "chain_of_thought"):
        with pytest.raises(ValidationError):
            ProposalRationale(**{**_rationale().model_dump(), extra: "because"})
    stored = rationale.at_rest(_rationale(("ev_1",), ("PR-001",)))
    assert stored == {
        "goal_ref": "run",
        "cited_evidence": ["ev_1"],
        "rules_considered": ["PR-001"],
        "alternatives": [
            {
                "proposal_digest": OTHER_DIGEST,
                "reason_code": "validation_failed",
                "line_digest": digest(ALT_TEXT),
            }
        ],
        "summary_digest": digest(SUMMARY_TEXT),
    }
    for text in SECRETS:
        assert text not in json.dumps(stored)


async def test_rationale_is_absent_from_driver_snapshot_and_explanation(
    make_kernel: MakeKernel,
) -> None:
    """Hidden-reasoning hygiene end to end: the rationale text is in no event, no
    explanation and no field of the stored continuation but ``rationale`` itself."""
    k = _kernel(make_kernel, _own("NOTE-001"), ON)
    run = await _start(k)
    assert run.state is RunState.WAITING_APPROVAL
    _no_text(await _events(k, run.run_id))
    explanation = (await run_explanation(k.store, TENANT, run.run_id)).model_dump(mode="json")
    for text in SECRETS:
        assert text not in json.dumps(explanation)
    stored = await _stored(k, run.run_id)
    rest = {key: value for key, value in stored.items() if key != "rationale"}
    for text in SECRETS:
        assert text not in json.dumps(rest, default=str)


# -- the approval digest -------------------------------------------------------------------
def _normalized(canonical: dict[str, Any]) -> dict[str, Any]:
    """The digest input without its per-run ids (operation id, evidence ids)."""
    out = dict(canonical)
    out.pop("logical_operation_id")
    out["evidence"] = [{**e, "id": "-"} for e in out["evidence"]]
    return out


@pytest.mark.parametrize("features", [SHADOW, ON], ids=["shadow", "on"])
async def test_rationale_never_changes_the_approval_digest(
    make_kernel: MakeKernel, features: Features
) -> None:
    """Target §5.6: the approval digest covers the arguments, never the rationale. Two runs
    that differ only in a rationale bind the same digest input (less per-run ids), and the
    plan digest input of a plan with rationales equals the one without."""
    canonicals = []
    for make in (_own("NOTE-001"), lambda obs, n: None):
        k = _kernel(make_kernel, make, features)
        run = await _start(k)
        assert run.state is RunState.WAITING_APPROVAL
        pres = await k.coordinator.pending_approval(TENANT, run.run_id)
        assert pres.digest == compute_digest(pres.canonical_proposal)
        assert "rationale" not in json.dumps(pres.canonical_proposal)
        cont = await k.coordinator._load_cont(TENANT, run.run_id)
        assert cont.canonical_proposal == pres.canonical_proposal
        canonicals.append(_normalized(pres.canonical_proposal))
    assert canonicals[0] == canonicals[1]

    plain = two_step_plan()
    reasoned = plain.model_copy(
        update={
            "rationale": _rationale(("ev_1",)),
            "steps": tuple(
                s.model_copy(
                    update={"proposal": s.proposal.model_copy(update={"rationale": _rationale()})}
                )
                for s in plain.steps
            ),
        }
    )
    ctx = StepDigestContext(
        tenant_id=TENANT,
        requester_id="u",
        binding_id="b",
        connection_version=1,
        credential_subject="svc",
        credential_version="none",
        evidence=(),
        fact_digests={},
        rule_bundle_version="notes@1",
        policy_version="p",
    )
    contexts = {FIRST: ctx, FOLLOW_UP: ctx}
    assert plan_digest_input(reasoned, contexts, run_operation_id="op") == plan_digest_input(
        plain, contexts, run_operation_id="op"
    )


# -- off and shadow ------------------------------------------------------------------------
def _shape(events: list[RunEvent]) -> list[tuple[str, list[str]]]:
    return [(e.type.value, sorted(e.payload)) for e in events]


async def test_rationale_off_action_record_unchanged(make_kernel: MakeKernel) -> None:
    """``off`` is today: a rationale is dropped before validation, nothing checks, records or
    stores it, and the action record, the events and the continuation keys are those of the
    same run without one."""
    runs = []
    for make in (_own("NOTE-999"), lambda obs, n: None):
        k = _kernel(make_kernel, make, Features())
        seen = _validated(k)
        run = await _start(k)
        assert run.state is RunState.WAITING_APPROVAL
        assert [p.rationale for p in seen] == [None]
        events = await _events(k, run.run_id)
        (action,) = await k.store.list_actions(TENANT, run.run_id)
        stored = await _stored(k, run.run_id)
        assert set(stored) == OFF_CONTINUATION_KEYS
        assert _Continuation.model_validate(stored).model_dump(mode="json") == stored
        runs.append((events, action))
    (with_events, with_action), (without_events, without_action) = runs
    _no_text(with_events)
    assert not GROUNDING_EVENTS & {e.type for e in with_events}
    assert _shape(with_events) == _shape(without_events)
    ids = {"action_id", "run_id", "logical_operation_id", "approved_facts", "digest"}
    assert with_action.model_dump(exclude=ids) == without_action.model_dump(exclude=ids)
    assert not any("rationale" in e.payload for e in with_events)
    assert not any("step_rationales" in e.payload for e in with_events)


async def test_rationale_shadow_records_comparison(make_kernel: MakeKernel) -> None:
    """``shadow`` checks and records ``grounding.compared`` (counts only) with the proposal's
    own write, and acts on today's path: an unresolved rationale adds no finding."""
    k = _kernel(make_kernel, lambda obs, n: _rationale(("ev_unknown",), ("NOTE-999",)), SHADOW)

    run = await _start(k)

    assert run.state is RunState.WAITING_APPROVAL
    events = await _events(k, run.run_id)
    assert _repairs(events) == []
    (created,) = _of(events, RunEventType.PROPOSAL_CREATED)
    (compared,) = _of(events, RunEventType.GROUNDING_COMPARED)
    assert compared.action_id == created.action_id
    assert compared.payload == {
        "rationale": {
            "evidence": {"cited": 1, "resolved": 0, "unresolved": 1},
            "rules": {"cited": 1, "resolved": 0, "unresolved": 1},
        }
    }
    assert set(created.payload["rationale"]) == AT_REST_KEYS
    _no_text(events)


async def test_rationale_shadow_failure_changes_nothing(
    make_kernel: MakeKernel, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A shadow check that cannot run records ``grounding.shadow_failed`` with a fixed
    message and changes nothing else; no rationale is stored."""
    _broken_check(monkeypatch)
    k = _kernel(make_kernel, _own(), SHADOW)

    run = await _start(k)

    assert run.state is RunState.WAITING_APPROVAL
    events = await _events(k, run.run_id)
    (failed,) = _of(events, RunEventType.GROUNDING_SHADOW_FAILED)
    assert failed.payload == {"stage": "rationale", "message": rationale.RATIONALE_SHADOW_MESSAGE}
    assert "rationale" not in _of(events, RunEventType.PROPOSAL_CREATED)[0].payload
    assert "rationale" not in await _stored(k, run.run_id)
    _no_text(events)


# -- at rest -------------------------------------------------------------------------------
@pytest.mark.parametrize("features", [SHADOW, ON], ids=["shadow", "on"])
async def test_rationale_text_is_stored_as_digest_only(
    make_kernel: MakeKernel, features: Features
) -> None:
    """Owner, G2; PR-26: no event payload holds the summary or an alternative's line. At
    rest the rationale is its ids, codes and the digest of each text; the text is kept only
    in the run's continuation, where the approval card reads it."""
    k = _kernel(make_kernel, _own("NOTE-001"), features)

    run = await _start(k)

    assert run.state is RunState.WAITING_APPROVAL
    events = await _events(k, run.run_id)
    _no_text(events)
    (created,) = _of(events, RunEventType.PROPOSAL_CREATED)
    stored = created.payload["rationale"]
    assert stored["summary_digest"] == digest(SUMMARY_TEXT)
    assert stored["alternatives"] == [
        {
            "proposal_digest": OTHER_DIGEST,
            "reason_code": "validation_failed",
            "line_digest": digest(ALT_TEXT),
        }
    ]
    cont = await _stored(k, run.run_id)
    assert cont["rationale"]["summary"] == SUMMARY_TEXT
    assert cont["rationale"]["alternatives"][0]["line"] == ALT_TEXT
    loaded = await k.coordinator._load_cont(TENANT, run.run_id)
    assert loaded.rationale is not None and loaded.rationale.summary == SUMMARY_TEXT
    assert loaded.pending_action_id == created.action_id


# -- failure (ADR 0027, Review Focus 7) -----------------------------------------------------
async def test_rationale_failure_falls_back_before_reservation(
    make_kernel: MakeKernel, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Before the first reservation a check that cannot run records ``feature.fallback``
    ``GROUNDING_CHECK_FAILED`` and the proposal takes today's path with its rationale
    dropped; the code never ends the run and no exception text reaches an event."""
    _broken_check(monkeypatch)
    k = _kernel(make_kernel, _own(), ON)

    run = await _start(k)

    assert run.state is RunState.WAITING_APPROVAL, run.reason
    events = await _events(k, run.run_id)
    (fallback,) = _of(events, RunEventType.FEATURE_FALLBACK)
    assert fallback.payload == {
        "feature": "grounded_answers",
        "reason_code": ReasonCode.GROUNDING_CHECK_FAILED,
        "message": FALLBACK_MESSAGES[ReasonCode.GROUNDING_CHECK_FAILED],
    }
    assert "rationale" not in _of(events, RunEventType.PROPOSAL_CREATED)[0].payload
    assert "rationale" not in await _stored(k, run.run_id)
    assert rationale.KERNEL_RATIONALE not in str([e.payload for e in events])
    _no_text(events)


@pytest.mark.parametrize("reservation", ["unresolved", "resolved"])
async def test_rationale_failure_after_reservation_fails_closed(
    make_kernel: MakeKernel, monkeypatch: pytest.MonkeyPatch, reservation: str
) -> None:
    """Review Focus 7: after the run's first reservation there is no fallback. The run fails
    ``GROUNDING_UNAVAILABLE``, in reconciliation while the reservation is unresolved, and no
    second action exists. No live path proposes after a reservation in an unfinished run, so
    the proposal path is entered directly (white box), as 3e.1's test does."""
    k = make_kernel(features=ON, budgets=Budgets(max_admitted_writes=2))
    run = await k.coordinator.start_run(k.requester, "write standup note", k.scope)
    k.backend.fail_mode = "timeout"  # the write may have committed: UNKNOWN
    pres = await k.coordinator.pending_approval(TENANT, run.run_id)
    run = await k.coordinator.decide(
        actor=k.approver,
        run_id=run.run_id,
        action_id=pres.action_id,
        action_digest=pres.digest,
        expected_run_revision=pres.run_revision,
        decision=ApprovalDecision.APPROVED,
    )
    assert run.state is RunState.NEEDS_RECONCILIATION
    if reservation == "resolved":  # the provider said it had no effect (white box)
        (action,) = await k.store.list_actions(TENANT, run.run_id)
        await k.coordinator._transition(action, ActionState.FAILED)
    _broken_check(monkeypatch)
    cont = await k.coordinator._load_cont(TENANT, run.run_id)
    (obs,) = cont.observations.values()
    proposal = ActionProposal(
        contract_id=CREATE.contract_id,
        connection_id=CONN,
        arguments={"text": "second note"},
        rationale=_rationale((obs.evidence.evidence_id,)),
    )

    run = await k.coordinator._handle_proposal(run, cont, proposal)

    expected = RunState.NEEDS_RECONCILIATION if reservation == "unresolved" else RunState.FAILED
    assert (run.state, run.reason_code, run.reason) == (
        expected,
        ReasonCode.GROUNDING_UNAVAILABLE,
        TERMINAL_MESSAGES[ReasonCode.GROUNDING_UNAVAILABLE],
    )
    events = await _events(k, run.run_id)
    assert RunEventType.FEATURE_FALLBACK not in {e.type for e in events}
    assert len(await k.store.list_actions(TENANT, run.run_id)) == 1  # the first write only
    assert k.backend.create_calls == 1
    _no_text(events)
