"""The explanation projection (ADR 0033 §6, Task 3c.3, Q5, G11).

The runs are recorded fixture runs of the notes domain, driven through the kernel; the
``run_store`` fixture runs them on both stores. ``explain`` reads only the progress ledger
and the reconstruction, so these tests also prove what it leaves out: observation values,
proposal arguments and model text (PR-26, PR-28), and guessed values (PR-24).
"""

from __future__ import annotations

import ast
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from e_agent.contracts.approval import ApprovalDecision
from e_agent.contracts.events import RunEvent, RunEventType
from e_agent.contracts.explain import Completeness, Explanation, ValueLabel
from e_agent.contracts.features import FeatureMode, Features
from e_agent.contracts.progress import RuleRef, StageStatus, TaskRefState
from e_agent.contracts.run import ReasonCode, RunRecord, RunState
from e_agent.kernel import explain as explain_module
from e_agent.kernel.explain import explain
from e_agent.kernel.progress import project_progress
from e_agent.kernel.reconstruct import reconstruct, without_reconstruction_keys
from e_agent.sdk.ports import AskClarification, DriverInput, DriverStep, FinalAnswer

from .conftest import (
    CONN,
    CREATE,
    NOTE_INPUT,
    NOTES_TASK,
    PLAN_BUDGETS,
    READ,
    TENANT,
    Kernel,
    NotesDriver,
    NotesPlanDriver,
)
from .test_grounded_answer import NOTES_QUESTION, GroundedDriver, _own
from .test_progress import WrongAnswerDriver

MakeKernel = Callable[..., Kernel]
SENTINEL = "SENTINEL-value-must-not-leak"
AT = datetime(2026, 10, 19, 9, 0, tzinfo=UTC)


def _explain(events: list[RunEvent], steps: list[Any] | None = None) -> Explanation:
    return explain(project_progress(events, steps or []), reconstruct(events))


async def _explained(k: Kernel, run_id: str) -> Explanation:
    events = await k.store.list_events(TENANT, run_id)
    steps = await k.store.list_steps(TENANT, run_id)
    return explain(project_progress(events, steps), reconstruct(events))


async def _approve(k: Kernel, run_id: str) -> RunRecord:
    pres = await k.coordinator.pending_approval(TENANT, run_id)
    return await k.coordinator.decide(
        actor=k.approver,
        run_id=run_id,
        action_id=pres.action_id,
        action_digest=pres.digest,
        expected_run_revision=pres.run_revision,
        decision=ApprovalDecision.APPROVED,
    )


async def _approved_run(make_kernel: MakeKernel, text: str = "standup notes") -> tuple[Kernel, str]:
    k = make_kernel([text])
    run = await k.coordinator.start_run(k.requester, "write standup note", k.scope)
    assert run.state is RunState.WAITING_APPROVAL
    run = await _approve(k, run.run_id)
    assert run.state is RunState.SUCCEEDED
    return k, run.run_id


@dataclass
class ClarifyingDriver:
    """Asks one question and stops there; the question is model text."""

    question: str = "which note?"
    driver_id: str = "notes-clarifying-driver"

    async def advance(self, ctx: Any, step_input: DriverInput) -> DriverStep:
        return AskClarification(question=self.question)


@dataclass
class FinalTextDriver(NotesDriver):
    """`NotesDriver` whose closing reply (``message.final``) is a sentinel."""

    final: str = SENTINEL

    async def advance(self, ctx: Any, step_input: DriverInput) -> DriverStep:
        if step_input.action_result is not None:
            self.calls += 1
            return FinalAnswer(text=self.final)
        return await super().advance(ctx, step_input)


# -- the competency questions (ADR 0033 §6, research 03 §5) ------------------------------------
async def _cq06_missing_data(make_kernel: MakeKernel) -> None:
    """Which missing data does the draft-creating action still need? The open findings by rule
    id, and the requests for input."""
    k = make_kernel([""], budgets=None)
    run = await k.coordinator.start_run(k.requester, "write standup note", k.scope)
    assert (run.state, run.reason_code) == (RunState.FAILED, ReasonCode.VALIDATION_FAILED)
    blocked = await _explained(k, run.run_id)
    assert [(f.rule_id, f.rule_version, f.status) for f in blocked.validation.open_findings] == [
        ("NOTE-001", "1", "FAIL")
    ]
    assert {s.status for s in blocked.validation.stages} == {StageStatus.BLOCKED}

    asking = make_kernel(driver=ClarifyingDriver())
    run = await asking.coordinator.start_run(asking.requester, "write a note", asking.scope)
    assert run.state is RunState.WAITING_INPUT
    events = await asking.store.list_events(TENANT, run.run_id)
    requested = [e.event_id for e in events if e.type is RunEventType.INPUT_REQUESTED]
    explained = await _explained(asking, run.run_id)
    assert [(r.event_id, r.status) for r in explained.validation.input_requests] == [
        (requested[0], StageStatus.WAITING)
    ]
    assert explained.validation.open_findings == ()


async def _cq07_basis(make_kernel: MakeKernel) -> None:
    """Which sources, and which tool, ontology and policy versions, was the decision based on?"""
    k, run_id = await _approved_run(make_kernel)
    events = await k.store.list_events(TENANT, run_id)
    reads = [e.payload for e in events if e.type is RunEventType.READ_RECORDED]
    explained = await _explained(k, run_id)
    assert [(s.evidence_id, s.contract_id, s.revision) for s in explained.sources] == [
        (p["evidence_id"], READ.contract_id, p["revision"]) for p in reads
    ]
    (action,) = await k.store.list_actions(TENANT, run_id)
    (proposal,) = explained.proposals
    assert (proposal.contract_id, proposal.binding_id) == (CREATE.contract_id, "notes-mem.create")
    assert (proposal.connection_id, proposal.connection_version) == (CONN, 1)
    assert proposal.credential_version == action.credential_version
    (record,) = await k.store.list_approvals(TENANT, action.action_id)
    (approval,) = explained.approvals
    assert approval.policy_version == record.policy_version
    assert [s.status for s in explained.validation.stages] == [StageStatus.SUCCEEDED]
    # the passed rules' versions, and the driver this run recorded (review C3-26, C3-27)
    assert explained.validation.rules_evaluated == (
        RuleRef(rule_id="NOTE-001", rule_version="1", status="PASS"),
    )
    assert explained.validation.open_findings == ()
    assert explained.run.driver_id == k.driver.driver_id == "notes-driver"


async def _cq08_withdrawn_source(make_kernel: MakeKernel) -> None:
    """If a source is withdrawn, which of this run's proposals and approvals are affected?"""
    k, run_id = await _approved_run(make_kernel)
    explained = await _explained(k, run_id)
    (proposal,) = explained.proposals
    assert proposal.evidence_ids is not None and len(proposal.evidence_ids) == 1
    (named,) = proposal.evidence_ids
    affected = [p.action_id for p in explained.proposals if named in (p.evidence_ids or ())]
    approvals = [a.approval_id for a in explained.approvals if a.action_id in affected]
    assert affected == [proposal.action_id]
    assert approvals == [explained.approvals[0].approval_id]
    # the verifier's read-back is a source of the run that names no proposal
    later = [s.evidence_id for s in explained.sources if s.evidence_id != named]
    assert later and not any(e in (proposal.evidence_ids or ()) for e in later)


async def _cq09_already_created(make_kernel: MakeKernel) -> None:
    """Has a draft already been created for this logical operation?"""
    k = make_kernel()
    run = await k.coordinator.start_run(k.requester, "write standup note", k.scope)
    waiting = await _explained(k, run.run_id)
    (proposal,) = waiting.proposals
    (action,) = await k.store.list_actions(TENANT, run.run_id)
    assert proposal.logical_operation_id == action.logical_operation_id
    assert (proposal.state, waiting.receipts, waiting.outcomes) == ("AWAITING_APPROVAL", (), ())

    run = await _approve(k, run.run_id)
    done = await _explained(k, run.run_id)
    (proposal,) = done.proposals
    assert proposal.logical_operation_id == action.logical_operation_id
    assert proposal.state == "VERIFIED"
    assert [(r.action_id, r.status) for r in done.receipts] == [(action.action_id, "COMMITTED")]
    assert [(o.action_id, o.status) for o in done.outcomes] == [
        (action.action_id, StageStatus.SUCCEEDED)
    ]


async def _cq10_labels(make_kernel: MakeKernel) -> None:
    """Is the value an extraction, an inference, a hypothesis or an authoritative record?"""
    k, run_id = await _approved_run(make_kernel)
    explained = await _explained(k, run_id)
    assert {s.label for s in explained.sources} == {ValueLabel.PROVIDER_READ}
    assert {p.label for p in explained.proposals} == {ValueLabel.MODEL_PROPOSAL}
    assert {a.label for a in explained.approvals} == {ValueLabel.APPROVER_DECISION}
    assert {r.label for r in explained.receipts} == {ValueLabel.PROVIDER_RECEIPT}
    assert {o.label for o in explained.outcomes} == {ValueLabel.VERIFIED_OUTCOME}

    wrong = make_kernel(driver=WrongAnswerDriver(), with_answer=True)
    run = await wrong.coordinator.start_run(wrong.requester, "count the notes", wrong.scope)
    assert run.reason_code is ReasonCode.VERIFICATION_FAILED
    refused = await _explained(wrong, run.run_id)
    assert refused.outcomes and {o.label for o in refused.outcomes} == {ValueLabel.NOT_VERIFIED}


CASES: tuple[tuple[str, Callable[[MakeKernel], Awaitable[None]]], ...] = (
    ("CQ06", _cq06_missing_data),
    ("CQ07", _cq07_basis),
    ("CQ08", _cq08_withdrawn_source),
    ("CQ09", _cq09_already_created),
    ("CQ10", _cq10_labels),
)
"""One case per research 03 question ADR 0033 §6 lists; CQ01-CQ05 need the knowledge layer."""


async def test_explanation_answers_competency_questions(make_kernel: MakeKernel) -> None:
    assert [cq for cq, _ in CASES] == ["CQ06", "CQ07", "CQ08", "CQ09", "CQ10"]
    ran = 0
    for _, case in CASES:
        await case(make_kernel)
        ran += 1
    assert ran == len(CASES) == 5  # zero cases is a failure (PR-31)


# -- purity -----------------------------------------------------------------------------------
async def test_explanation_makes_no_model_call(make_kernel: MakeKernel) -> None:
    k, run_id = await _approved_run(make_kernel)
    calls = k.driver.calls
    events = await k.store.list_events(TENANT, run_id)
    await _explained(k, run_id)
    assert k.driver.calls == calls
    assert await k.store.list_events(TENANT, run_id) == events  # nothing written either
    # the module reads only contracts and the two projections: no driver, store or adapter
    tree = ast.parse(Path(explain_module.__file__).read_text(encoding="utf-8"))
    imported = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    allowed = {"__future__", "collections.abc", "enum", "typing"}
    assert {m for m in imported if not m.startswith("e_agent.contracts")} - allowed == {
        "e_agent.kernel.reconstruct"
    }, imported
    assert not any(isinstance(node, ast.Import) for node in ast.walk(tree))


async def test_explanation_is_deterministic(make_kernel: MakeKernel) -> None:
    k, run_id = await _approved_run(make_kernel)
    events = await k.store.list_events(TENANT, run_id)
    steps = await k.store.list_steps(TENANT, run_id)
    first = explain(project_progress(events, steps), reconstruct(events))
    second = explain(project_progress(events, steps), reconstruct(events))
    shuffled = list(reversed(events))
    third = explain(project_progress(shuffled, steps), reconstruct(shuffled))
    assert first.model_dump_json() == second.model_dump_json() == third.model_dump_json()


async def test_explanation_holds_no_observation_values(make_kernel: MakeKernel) -> None:
    """The note text is the proposal's argument, the verifier's observed value and the
    read-back's data; the closing reply is model text. None reaches the explanation (PR-26,
    PR-28), though the events hold them."""
    k = make_kernel(driver=FinalTextDriver(texts=[SENTINEL]))
    run = await k.coordinator.start_run(k.requester, "write standup note", k.scope)
    run = await _approve(k, run.run_id)
    assert run.state is RunState.SUCCEEDED
    events = await k.store.list_events(TENANT, run.run_id)
    leaks = {e.type for e in events if SENTINEL in e.model_dump_json()}
    assert leaks >= {
        RunEventType.PROPOSAL_CREATED,
        RunEventType.OUTCOME_REPORTED,
        RunEventType.MESSAGE_FINAL,
    }
    assert SENTINEL not in (await _explained(k, run.run_id)).model_dump_json()

    asking = make_kernel(driver=ClarifyingDriver(question=SENTINEL))
    run = await asking.coordinator.start_run(asking.requester, "write a note", asking.scope)
    explained = await _explained(asking, run.run_id)
    assert explained.validation.input_requests  # the request is shown, by its event id
    assert SENTINEL not in explained.model_dump_json()

    # a failing validation: its finding's message and values stay out (review C3-29)
    finding = {
        "rule_id": "R-1",
        "rule_version": "2",
        "status": "FAIL",
        "message": f"value {SENTINEL} is not allowed",
        "expected": f"not {SENTINEL}",
        "observed": SENTINEL,
        "evidence_ids": [],
    }
    failing = [
        _event(1, RunEventType.RUN_CREATED, {"task": "t", "driver": "d"}),
        _event(2, RunEventType.VALIDATION_COMPLETED, {"status": "FAIL", "findings": [finding]}),
    ]
    blocked = _explain(failing)
    assert blocked.validation.open_findings == (
        RuleRef(rule_id="R-1", rule_version="2", status="FAIL"),
    )
    assert blocked.validation.rules_evaluated == blocked.validation.open_findings
    assert SENTINEL not in blocked.model_dump_json()


# -- partial and unknown (PR-24) --------------------------------------------------------------
def _phase2(event: RunEvent) -> RunEvent:
    """``event`` as written before Task 3c.2: the ADR 0031 §3 keys removed."""
    return event.model_copy(
        update={"payload": without_reconstruction_keys(event.type, event.payload)}
    )


async def test_explanation_of_old_run_marks_partial(make_kernel: MakeKernel) -> None:
    k, run_id = await _approved_run(make_kernel)
    events = await k.store.list_events(TENANT, run_id)
    current = _explain(events)
    assert current.completeness is Completeness.KNOWN
    assert current.run.unknown_fields == ()
    assert all(p.unknown_fields == () for p in current.proposals)

    old = _explain([_phase2(e) for e in events])
    assert old.completeness is Completeness.PARTIAL
    assert old.run.task_ref_state is TaskRefState.UNKNOWN
    assert old.run.requester_id is None and "requester_id" in old.run.unknown_fields
    (proposal,) = old.proposals
    # not recorded before the keys: unknown, never a guessed value
    assert proposal.evidence_ids is None and "evidence_ids" in proposal.unknown_fields
    assert proposal.binding_id is None and "binding_id" in proposal.unknown_fields
    # still recorded: the digest (from the approval request) and the reservation's operation id
    assert proposal.digest == current.proposals[0].digest
    assert proposal.logical_operation_id == current.proposals[0].logical_operation_id
    # `run.created` recorded the driver before the keys too, so it stays known
    assert old.run.driver_id == current.run.driver_id == "notes-driver"
    assert "driver_id" not in old.run.unknown_fields
    (approval,) = old.approvals
    assert approval.policy_version is None and "policy_version" in approval.unknown_fields
    assert approval.actor_id == current.approvals[0].actor_id
    # what the events always held is unchanged
    assert old.sources == current.sources
    assert old.receipts == current.receipts
    assert old.outcomes == current.outcomes


def _event(sequence: int, type_: RunEventType, payload: dict[str, Any]) -> RunEvent:
    return RunEvent(
        event_id=f"ev{sequence}",
        tenant_id=TENANT,
        run_id="run_x",
        sequence=sequence,
        type=type_,
        occurred_at=AT,
        payload=payload,
    )


async def test_explanation_of_a_two_step_plan_names_its_rules(make_kernel: MakeKernel) -> None:
    """The plan's later step revalidates with no findings at dispatch; the rules the run
    evaluated before it stay named (review C3-27)."""
    k = make_kernel(
        features=Features(execution_ir=FeatureMode.ON),
        budgets=PLAN_BUDGETS,
        driver=NotesPlanDriver(),
        input_schemas={"c": NOTE_INPUT, "p": NOTE_INPUT},
    )
    run = await k.coordinator.start_run(
        k.requester, "write standup note", k.scope, task_kind=NOTES_TASK.task_id
    )
    run = await _approve(k, run.run_id)
    assert run.state is RunState.SUCCEEDED
    events = await k.store.list_events(TENANT, run.run_id)
    validations = [e for e in events if e.type is RunEventType.VALIDATION_COMPLETED]
    assert validations[-1].payload["findings"] == []  # the case this test is about
    explained = await _explained(k, run.run_id)
    assert explained.validation.rules_evaluated == (
        RuleRef(rule_id="NOTE-001", rule_version="1", status="PASS"),
    )
    assert explained.validation.open_findings == ()


def test_rules_keep_first_seen_order_and_latest_status() -> None:
    def validation(sequence: int, *findings: tuple[str, str, str]) -> RunEvent:
        payload = [
            {"rule_id": r, "rule_version": v, "status": s, "message": SENTINEL}
            for r, v, s in findings
        ]
        return _event(sequence, RunEventType.VALIDATION_COMPLETED, {"findings": payload})

    events = [
        validation(1, ("A", "1", "FAIL"), ("B", "1", "PASS")),
        _event(2, RunEventType.PROPOSAL_CREATED, {}),
        validation(3, ("C", "1", "PASS"), ("A", "1", "PASS"), ("A", "2", "FAIL")),
    ]
    rules = _explain(events).validation.rules_evaluated
    assert [(r.rule_id, r.rule_version, r.status) for r in rules] == [
        ("A", "1", "PASS"),
        ("B", "1", "PASS"),
        ("C", "1", "PASS"),
        ("A", "2", "FAIL"),
    ]
    assert SENTINEL not in _explain(events).model_dump_json()


def test_explanation_of_no_events_is_unknown() -> None:
    explained = _explain([])
    assert explained.completeness is Completeness.UNKNOWN
    assert explained.run.run_id is None and explained.run.state is None
    assert (explained.sources, explained.proposals, explained.outcomes) == ((), (), ())


def test_a_known_null_is_not_an_unknown_field() -> None:
    """A run created without a task definition records ``task_id: null``: that is known."""
    created = {
        "task": "t",
        "driver": "d",
        "requester_id": "alice",
        "logical_operation_id": "op1",
        "created_at": AT.isoformat(),
        "task_id": None,
        "task_version": None,
    }
    explained = _explain([_event(1, RunEventType.RUN_CREATED, created)])
    assert explained.run.task_ref_state is TaskRefState.NONE
    assert explained.run.unknown_fields == ()
    assert explained.run.state == "CREATED"
    assert explained.run.driver_id == "d"


def test_an_unrecorded_driver_is_unknown() -> None:
    """A ``run.created`` without ``driver`` does not say which driver ran: unknown (PR-24)."""
    explained = _explain([_event(1, RunEventType.RUN_CREATED, {"task": "t"})])
    assert explained.run.driver_id is None
    assert "driver_id" in explained.run.unknown_fields
    assert _explain([]).run.driver_id is None
    assert "driver_id" in _explain([]).run.unknown_fields


async def test_explanation_of_a_grounded_run_names_a_grounded_outcome(
    make_kernel: MakeKernel,
) -> None:
    """ADR 0033 §6, 3e.2 review R1-6: a run that ended ``GROUNDED`` explains a grounded
    outcome, labelled ``grounded_answer``, never ``verified_outcome`` (PR-19); a verified
    run names no grounded outcome."""
    driver = GroundedDriver(_own(("/count", "0")))
    on = Features(grounded_answers=FeatureMode.ON)  # a run that cannot write (FA-1)
    k = make_kernel(features=on, driver=driver, read_only=True, task=NOTES_QUESTION)
    run = await k.coordinator.start_run(k.requester, "how many notes?", k.scope)
    assert (run.state, run.reason_code) == (RunState.SUCCEEDED, ReasonCode.GROUNDED)

    explained = await _explained(k, run.run_id)

    (outcome,) = explained.outcomes
    assert outcome.label is ValueLabel.GROUNDED_ANSWER
    assert (outcome.status, outcome.action_id) == (StageStatus.SUCCEEDED, None)
    assert ValueLabel.VERIFIED_OUTCOME not in {o.label for o in explained.outcomes}
    k, run_id = await _approved_run(make_kernel)
    labels = {o.label for o in (await _explained(k, run_id)).outcomes}
    assert labels == {ValueLabel.VERIFIED_OUTCOME}
