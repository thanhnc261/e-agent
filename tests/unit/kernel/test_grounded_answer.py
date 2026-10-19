"""The generic grounded answer ``grounded.answer.v1`` (ADR 0033 §3, §5, plan D5, Task 3e.2).

A core answer owned by the kernel, not a registry capability: arguments ``{summary}`` and at
least one citation in the kernel envelope. The kernel recognizes it before the task-set check
and the capability lookup, and only in a run pinned ``grounded_answers: on``; in ``off`` and
``shadow`` the call takes today's path. It is admitted when the run's offered tool set holds
no typed answer contract and the run is unbound or its definition's acceptance spec sets
``grounded_answer``; a call that is not admitted is the repair finding
``KERNEL-GROUNDED-ANSWER``. When every citation resolves against this run's evidence the run
ends ``SUCCEEDED`` with ``GROUNDED``, which is never ``verified`` (PR-19): no action record,
no outcome report, and ``message.final`` carries the summary with ``contract_id`` and the
at-rest citations. The check failing fails the run closed with ``GROUNDING_UNAVAILABLE``:
there is no typed verifier to fall back to. Runs over both stores through the ``run_store``
fixture (ENG-STORE-1).
"""

from __future__ import annotations

import dataclasses
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
from e_agent.contracts.features import FeatureMode, Features
from e_agent.contracts.grounding import Citation
from e_agent.contracts.outcome import OutcomeCheck, OutcomeReport, OutcomeStatus
from e_agent.contracts.plan import ActionProposal
from e_agent.contracts.run import ReasonCode, RunState
from e_agent.contracts.task import (
    GROUNDED_ANSWER,
    AcceptanceSpec,
    RequiredEffect,
    TaskDefinition,
    acceptance_met,
    check_answer_condition,
)
from e_agent.kernel import grounded_answer
from e_agent.kernel.errors import KernelError
from e_agent.kernel.evidence import build_evidence
from e_agent.kernel.features import TERMINAL_MESSAGES
from e_agent.kernel.registry import PluginRegistry
from e_agent.sdk.manifest import BindingTemplate, TaskDeclaration
from e_agent.sdk.ports import (
    DriverInput,
    DriverStep,
    GroundingOffer,
    Observation,
    PluginContribution,
    ProposeAction,
    ReadRequest,
    RequestReads,
)
from pydantic import ValidationError

from .conftest import CONN, CREATE, NOTES_TASK, READ, SUMMARY, TENANT, Kernel
from .test_grounding import CLASSED_DATA, CLASSES, PINNED_ON, CitingDriver
from .test_mode_pinning import HOSTED_UNDECLARED

MakeKernel = Callable[..., Kernel]
ON = Features(grounded_answers=FeatureMode.ON)
SHADOW = Features(grounded_answers=FeatureMode.SHADOW)
BOUND_ON = Features(execution_ir=FeatureMode.ON, grounded_answers=FeatureMode.ON)
SUMMARY_TEXT = "There are 0 standup notes."
AT_REST_KEYS = {"evidence_id", "pointer", "value_digest"}
NOTES_QUESTION = TaskDefinition(
    task_id="notes-question",
    version="1",
    title="Answer a question about the notes",
    goal_template="answer a question about the notes",
    capabilities=(READ.contract_id,),
    acceptance=AcceptanceSpec(grounded_answer=True),
)
"""A read-only notes definition that admits a grounded answer (ADR 0033 §3)."""

Cite = Callable[[Observation, int], tuple[Citation, ...]]


def _own(*pointers: tuple[str, Any]) -> Cite:
    def cite(obs: Observation, attempt: int) -> tuple[Citation, ...]:
        eid = obs.evidence.evidence_id
        return tuple(Citation(evidence_id=eid, pointer=p, value=v) for p, v in pointers)

    return cite


def _wrong_then_right(obs: Observation, attempt: int) -> tuple[Citation, ...]:
    value = "7" if attempt == 1 else "0"  # the notes summary counts 0 notes
    return (Citation(evidence_id=obs.evidence.evidence_id, pointer="/count", value=value),)


@dataclass
class GroundedDriver:
    """Reads the notes summary, then answers with ``grounded.answer.v1`` and the citations
    ``cite`` builds. ``on_answer`` runs before each answer (a profile flip mid-run)."""

    cite: Cite
    connection_id: str = CONN
    on_answer: Callable[[], None] | None = None
    arguments: dict[str, Any] = field(default_factory=lambda: {"summary": SUMMARY_TEXT})
    driver_id: str = "notes-grounded-driver"
    attempts: int = 0
    seen: list[DriverInput] = field(default_factory=list)

    async def advance(self, ctx: TaskContext, step_input: DriverInput) -> DriverStep:
        self.seen.append(step_input)
        if not step_input.observations:
            request = ReadRequest(
                request_id="r1", contract_id=READ.contract_id, connection_id=CONN, arguments={}
            )
            return RequestReads(reads=(request,))
        if self.on_answer is not None:
            self.on_answer()
        self.attempts += 1
        obs = step_input.observations[0]
        proposal = ActionProposal(
            contract_id=GROUNDED_ANSWER,
            connection_id=self.connection_id,
            arguments=dict(self.arguments),
            citations=self.cite(obs, self.attempts),
        )
        return ProposeAction(proposal=proposal)


def _kernel(
    make_kernel: MakeKernel, cite: Cite, features: Features | None = ON, **kw: Any
) -> Kernel:
    driver = kw.pop("driver", None) or GroundedDriver(cite)
    return make_kernel(features=features, driver=driver, **kw)


async def _start(k: Kernel, task_kind: str | None = None) -> Any:
    return await k.coordinator.start_run(
        k.requester, "how many standup notes are there?", k.scope, task_kind=task_kind
    )


async def _events(k: Kernel, run_id: str) -> list[RunEvent]:
    return await k.store.list_events(TENANT, run_id)


def _of(events: list[RunEvent], kind: RunEventType) -> list[RunEvent]:
    return [e for e in events if e.type is kind]


def _rules(events: list[RunEvent]) -> list[str]:
    return [
        f["rule_id"]
        for e in _of(events, RunEventType.VALIDATION_COMPLETED)
        for f in e.payload["findings"]
    ]


async def _admits(k: Kernel, run_id: str) -> bool:
    run = await k.store.get_run(TENANT, run_id)
    cont = await k.coordinator._load_cont(TENANT, run_id)
    return k.coordinator._admits_grounded_answer(run, cont)


def _assert_grounded_end(run: Any, events: list[RunEvent]) -> RunEvent:
    assert (run.state, run.reason_code) == (RunState.SUCCEEDED, ReasonCode.GROUNDED), run.reason
    assert not _of(events, RunEventType.PROPOSAL_CREATED)  # no action record (ADR 0033 §3)
    assert not _of(events, RunEventType.OUTCOME_REPORTED)
    (final,) = _of(events, RunEventType.MESSAGE_FINAL)
    return final


# -- the grounded end ---------------------------------------------------------------------
async def test_read_only_question_ends_grounded_without_bespoke_contract(
    make_kernel: MakeKernel,
) -> None:
    """An unbound notes run with no typed answer: the generic answer, its connection
    ignored, ends ``GROUNDED`` with the summary and the at-rest citations in
    ``message.final``, and no action record."""
    driver = GroundedDriver(_own(("/count", "0"), ("/topic", "standup")), connection_id="none")
    k = _kernel(make_kernel, _own(), driver=driver)

    run = await _start(k)

    events = await _events(k, run.run_id)
    final = _assert_grounded_end(run, events)
    (read,) = _of(events, RunEventType.READ_RECORDED)
    eid = read.payload["evidence_id"]
    assert final.payload == {
        "text": SUMMARY_TEXT,
        "contract_id": GROUNDED_ANSWER,
        "citations": [
            {"evidence_id": eid, "pointer": "/count", "value_digest": digest("0")},
            {"evidence_id": eid, "pointer": "/topic", "value_digest": digest("standup")},
        ],
    }
    assert await k.store.list_actions(TENANT, run.run_id) == []
    assert not _rules(events)
    assert run.reason == grounded_answer.GROUNDED_REASON
    assert await _admits(k, run.run_id)
    print(f"grounded end: {len(final.payload['citations'])} citations")


async def test_grounded_is_never_reported_as_verified(make_kernel: MakeKernel) -> None:
    """PR-19: a grounded end has no verified action, no outcome report and its own reason
    code; a spec that requires a verified answer or effect is never met by it, and the
    flag alone admits it."""
    k = _kernel(make_kernel, _own(("/count", "0")))

    run = await _start(k)

    events = await _events(k, run.run_id)
    _assert_grounded_end(run, events)
    assert run.reason_code is not ReasonCode.VERIFIED
    bundle = await build_evidence(
        k.store, TENANT, run.run_id, environment="fixture", versions={}, features=ON
    )
    assert bundle["outcomes"] == [] and bundle["actions"] == []
    section = bundle["grounded_answer"]
    labels = {section["summary"]["label"], *(c["label"] for c in section["citations"])}
    assert labels == {"unverified", "grounded"}  # never "verified"
    report = OutcomeReport(
        run_id=run.run_id,
        action_id="a1",
        status=OutcomeStatus.VERIFIED,
        checks=(OutcomeCheck(name="count", passed=True, expected="0", observed="0"),),
        verifier_id="v",
        verifier_version="1",
        reported_at=run.created_at,
    )
    answer = AcceptanceSpec(required_answer=SUMMARY.contract_id)
    effects = AcceptanceSpec(required_effects=(RequiredEffect(contract_id=CREATE.contract_id),))
    grounded = AcceptanceSpec(grounded_answer=True)
    cases = [
        (answer, {}, [], True, False),
        (effects, {}, [], True, False),
        (AcceptanceSpec(), {}, [], True, False),  # without the flag a grounded end never meets
        (grounded, {}, [], True, True),
        (grounded, {}, [], False, False),
        (grounded, {CREATE.contract_id: 1}, [report], False, False),  # nothing else meets it
        (answer, {}, [report], False, True),  # today's rules unchanged
        (AcceptanceSpec(), {}, [], False, True),
    ]
    for spec, counts, reports, is_grounded, met in cases:
        assert acceptance_met(spec, counts, reports, grounded=is_grounded) is met, spec
    print(f"acceptance cases: {len(cases)}")


async def test_free_text_answer_is_labelled_unverified(make_kernel: MakeKernel) -> None:
    """The evidence bundle labels the summary ``unverified`` model text and each citation
    ``grounded`` (ADR 0033 §3); a bundle without a grounded end has no such key."""
    k = _kernel(make_kernel, _own(("/count", "0")))
    run = await _start(k)
    bundle = await build_evidence(
        k.store, TENANT, run.run_id, environment="fixture", versions={}, features=ON
    )
    (read,) = _of(await _events(k, run.run_id), RunEventType.READ_RECORDED)
    assert bundle["grounded_answer"] == {
        "contract_id": GROUNDED_ANSWER,
        "summary": {"text": SUMMARY_TEXT, "label": "unverified"},
        "citations": [
            {
                "evidence_id": read.payload["evidence_id"],
                "pointer": "/count",
                "value_digest": digest("0"),
                "label": "grounded",
            }
        ],
    }
    off = make_kernel()
    off_run = await off.coordinator.start_run(off.requester, "write standup note", off.scope)
    off_bundle = await build_evidence(
        off.store, TENANT, off_run.run_id, environment="fixture", versions={}, features=Features()
    )
    assert "grounded_answer" not in off_bundle


async def test_typed_answer_final_text_is_not_a_grounded_section(
    make_kernel: MakeKernel,
) -> None:
    """A typed answer's run ends ``ANSWERED`` with a text-only ``message.final``: the
    bundle's grounded section reads only the kernel's ``contract_id`` record, so it has none."""
    driver = CitingDriver(_own(("/count", "0")))
    k = make_kernel(features=ON, with_answer=True, driver=driver)
    run = await _start(k)
    assert (run.state, run.reason_code) == (RunState.SUCCEEDED, ReasonCode.ANSWERED)
    (final,) = _of(await _events(k, run.run_id), RunEventType.MESSAGE_FINAL)
    assert "contract_id" not in final.payload
    bundle = await build_evidence(
        k.store, TENANT, run.run_id, environment="fixture", versions={}, features=ON
    )
    assert "grounded_answer" not in bundle


# -- admission (ADR 0033 §3) --------------------------------------------------------------
async def test_grounded_answer_not_offered_beside_a_typed_answer(make_kernel: MakeKernel) -> None:
    """Where a typed answer exists its verifier decides: an unbound run whose tool set holds
    the notes answer does not admit the generic one, and a call to it anyway is the fixed
    repair finding ``KERNEL-GROUNDED-ANSWER`` with no action, until the repair budget."""
    k = _kernel(make_kernel, _own(("/count", "0")), with_answer=True)

    run = await _start(k)

    assert (run.state, run.reason_code) == (RunState.FAILED, ReasonCode.VALIDATION_FAILED)
    events = await _events(k, run.run_id)
    budget = Budgets().max_validation_repairs
    assert _rules(events) == [grounded_answer.KERNEL_GROUNDED_ANSWER] * (budget + 1)
    for event in _of(events, RunEventType.VALIDATION_COMPLETED):
        assert event.action_id is None
        assert event.payload["findings"][0]["message"] == grounded_answer.NOT_ADMITTED
    assert not _of(events, RunEventType.MESSAGE_FINAL)
    assert await k.store.list_actions(TENANT, run.run_id) == []
    assert not await _admits(k, run.run_id)


async def test_grounded_answer_refused_on_bound_run_without_admission(
    make_kernel: MakeKernel,
) -> None:
    """A run bound to a definition whose acceptance spec does not set ``grounded_answer``
    refuses it before the task-set check; a definition that sets it admits it, and the
    grounded end meets its acceptance from the kernel's own ``message.final``."""
    refused = _kernel(make_kernel, _own(("/count", "0")), BOUND_ON, task=NOTES_TASK)
    run = await _start(refused, NOTES_TASK.task_id)
    assert run.task_id == NOTES_TASK.task_id
    assert run.state is RunState.FAILED
    events = await _events(refused, run.run_id)
    assert set(_rules(events)) == {grounded_answer.KERNEL_GROUNDED_ANSWER}  # not the task set
    assert not await _admits(refused, run.run_id)

    admitted = _kernel(make_kernel, _own(("/count", "0")), BOUND_ON, task=NOTES_QUESTION)
    run = await _start(admitted, NOTES_QUESTION.task_id)
    assert run.task_id == NOTES_QUESTION.task_id
    events = await _events(admitted, run.run_id)
    _assert_grounded_end(run, events)
    assert "KERNEL-ACCEPTANCE" not in _rules(events)
    assert await _admits(admitted, run.run_id)


async def test_grounded_answer_on_bound_run_without_snapshot_is_refused(
    make_kernel: MakeKernel,
) -> None:
    """A bound run whose admitted definition is unavailable admits nothing (fail closed)."""
    k = _kernel(make_kernel, _own(("/count", "0")), BOUND_ON, task=NOTES_QUESTION)
    run = await _start(k, NOTES_QUESTION.task_id)
    cont = await k.coordinator._load_cont(TENANT, run.run_id)
    assert k.coordinator._admits_grounded_answer(run, cont)
    cont.task = None
    assert not k.coordinator._admits_grounded_answer(run, cont)


@pytest.mark.parametrize("pinned", [FeatureMode.OFF, FeatureMode.SHADOW])
async def test_grounded_answer_not_offered_unless_pinned_on(
    make_kernel: MakeKernel, pinned: FeatureMode
) -> None:
    """Admission reads the run's pinned mode, never the profile: a run pinned ``off`` or
    ``shadow`` keeps today's path for the call (``KERNEL-PROPOSAL-KIND``) after the profile
    flips to ``on`` mid-run, while a run started after the flip admits it; a run pinned
    ``on`` stays grounded after the profile flips back."""
    k = _kernel(make_kernel, _own(("/count", "0")), Features(grounded_answers=pinned))
    flips: list[Features] = [ON]

    def flip() -> None:
        if flips:
            k.coordinator._features = flips.pop(0)

    k.driver.on_answer = flip
    run = await _start(k)
    assert run.state is RunState.FAILED
    events = await _events(k, run.run_id)
    assert set(_rules(events)) == {"KERNEL-PROPOSAL-KIND"}  # today's path, as before 3e.2
    assert not _of(events, RunEventType.MESSAGE_FINAL)
    assert not await _admits(k, run.run_id)

    k.driver.attempts = 0
    after = await _start(k)  # pinned `on` at its start
    _assert_grounded_end(after, await _events(k, after.run_id))
    assert await _admits(k, after.run_id)

    flips.append(Features(grounded_answers=pinned))
    k.driver.attempts = 0
    pinned_on = await _start(k)  # pinned `on`; the profile flips back before its answer
    _assert_grounded_end(pinned_on, await _events(k, pinned_on.run_id))
    assert k.coordinator._features.grounded_answers is pinned
    assert await _admits(k, pinned_on.run_id)


# -- the driver's offer (Task 3e.4, ADR 0033 §5) -------------------------------------------
@pytest.mark.parametrize(
    ("features", "task", "offer"),
    [
        (None, None, GroundingOffer.OFF),
        (SHADOW, None, GroundingOffer.CITE),
        (ON, None, GroundingOffer.CITE_AND_ANSWER),
        (BOUND_ON, NOTES_TASK, GroundingOffer.CITE),
        (BOUND_ON, NOTES_QUESTION, GroundingOffer.CITE_AND_ANSWER),
    ],
    ids=["off", "shadow", "on-admitted", "on-bound-not-admitted", "on-bound-admitted"],
)
async def test_driver_input_carries_the_pinned_offer(
    make_kernel: MakeKernel,
    features: Features | None,
    task: TaskDefinition | None,
    offer: GroundingOffer,
) -> None:
    """Every run-loop call carries the offer derived from the run's pin and the generic
    answer's admission (D8): ``off`` is today's input, ``shadow`` cites, and ``on`` adds the
    generic answer only where the run admits it."""
    kw = {} if task is None else {"task": task}
    k = _kernel(make_kernel, _own(("/count", "0")), features, **kw)
    await _start(k, None if task is None else task.task_id)
    assert k.driver.seen, "the driver was never called"
    assert {step.grounding for step in k.driver.seen} == {offer}
    print(f"{offer.value}: {len(k.driver.seen)} driver calls")


async def test_profile_flip_keeps_the_offer_pinned(make_kernel: MakeKernel) -> None:
    """A run pinned ``off`` is offered nothing on the calls made after the profile flips
    ``on``, and a run pinned ``on`` keeps its offer on the repair call made after the profile
    flips back (D8). The flip runs inside the answer turn, so each assertion reads only the
    calls whose input was built after it."""
    k = _kernel(make_kernel, _wrong_then_right, None)
    flips: list[int] = []

    def flip(features: Features) -> Callable[[], None]:
        def apply() -> None:
            if not flips:
                flips.append(len(k.driver.seen))  # this call's input was built before the flip
                k.coordinator._features = features

        return apply

    k.driver.on_answer = flip(ON)
    await _start(k)  # pinned `off`
    after = k.driver.seen[flips[0] :]
    assert after, "no driver call after the flip"
    assert {step.grounding for step in after} == {GroundingOffer.OFF}

    k.driver.seen.clear()
    k.driver.attempts = 0
    flips.clear()
    k.driver.on_answer = flip(Features())
    run = await _start(k)  # pinned `on` at its start; the first answer is refused
    after = k.driver.seen[flips[0] :]
    assert after, "no driver call after the flip"
    assert {step.grounding for step in after} == {GroundingOffer.CITE_AND_ANSWER}
    assert run.reason_code is ReasonCode.GROUNDED  # the repaired answer, after the flip
    print(f"calls after the flip: pinned on {len(after)}")


# -- repair and failure -------------------------------------------------------------------
async def test_grounded_answer_with_unresolved_citation_is_repaired(
    make_kernel: MakeKernel,
) -> None:
    """A citation that does not resolve is ``KERNEL-CITATION`` with no action, within the
    repair budget; the repaired answer ends grounded."""
    k = _kernel(make_kernel, _wrong_then_right)

    run = await _start(k)

    events = await _events(k, run.run_id)
    final = _assert_grounded_end(run, events)
    assert _rules(events) == ["KERNEL-CITATION"]
    (refused,) = _of(events, RunEventType.VALIDATION_COMPLETED)
    assert refused.action_id is None
    assert "7" not in json.dumps(refused.payload["findings"][0]["observed"])
    assert [c["value_digest"] for c in final.payload["citations"]] == [digest("0")]
    assert k.driver.attempts == 2
    assert k.driver.seen[-1].findings[0].rule_id == "KERNEL-CITATION"


@pytest.mark.parametrize(
    ("cite", "arguments", "rule"),
    [
        (_own(), {"summary": SUMMARY_TEXT}, "KERNEL-CITATION"),  # at least one citation
        (_own(("/count", "0")), {"summary": "  "}, "KERNEL-ARGS"),
        (_own(("/count", "0")), {"summary": SUMMARY_TEXT, "extra": 1}, "KERNEL-ARGS"),
        (_own(("/count", "0")), {"text": SUMMARY_TEXT}, "KERNEL-ARGS"),
    ],
)
async def test_grounded_answer_shape_is_a_repair_finding(
    make_kernel: MakeKernel, cite: Cite, arguments: dict[str, Any], rule: str
) -> None:
    """``grounded.answer.v1`` takes one non-empty ``summary`` and at least one citation;
    anything else is a fixed repair finding, never a grounded end."""
    driver = GroundedDriver(cite, arguments=arguments)
    k = _kernel(make_kernel, cite, driver=driver)

    run = await _start(k)

    assert (run.state, run.reason_code) == (RunState.FAILED, ReasonCode.VALIDATION_FAILED)
    events = await _events(k, run.run_id)
    assert set(_rules(events)) == {rule}
    assert not _of(events, RunEventType.MESSAGE_FINAL)


def _broken_check(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(*_: Any, **__: Any) -> Any:
        raise RuntimeError("SENTINEL-3e2-check-error")

    monkeypatch.setattr(grounded_answer, "check_citations", broken)


async def test_grounding_failure_fails_closed_for_generic_answer(
    make_kernel: MakeKernel, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Before any reservation there is still no fallback: a generic answer has no typed
    verifier, so the run fails closed with ``GROUNDING_UNAVAILABLE`` and no
    ``feature.fallback``, ``message.final`` or exception text."""
    _broken_check(monkeypatch)
    k = _kernel(make_kernel, _own(("/count", "0")))

    run = await _start(k)

    assert (run.state, run.reason_code, run.reason) == (
        RunState.FAILED,
        ReasonCode.GROUNDING_UNAVAILABLE,
        TERMINAL_MESSAGES[ReasonCode.GROUNDING_UNAVAILABLE],
    )
    events = await _events(k, run.run_id)
    kinds = {e.type for e in events}
    assert RunEventType.FEATURE_FALLBACK not in kinds
    assert RunEventType.MESSAGE_FINAL not in kinds
    assert "SENTINEL-3e2" not in json.dumps([e.payload for e in events])


@pytest.mark.parametrize("reservation", ["unresolved", "resolved"])
async def test_grounding_failure_after_reservation_fails_closed_for_generic_answer(
    make_kernel: MakeKernel, monkeypatch: pytest.MonkeyPatch, reservation: str
) -> None:
    """Review Focus 7: after a reservation the run fails ``GROUNDING_UNAVAILABLE``, in
    reconciliation while the reservation is unresolved. Entered directly (white box), as
    3e.1's post-reservation test does."""
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
        contract_id=GROUNDED_ANSWER,
        connection_id=CONN,
        arguments={"summary": SUMMARY_TEXT},
        citations=(Citation(evidence_id=obs.evidence.evidence_id, pointer="/count", value="0"),),
    )

    run = await k.coordinator._handle_proposal(run, cont, proposal)

    expected = RunState.NEEDS_RECONCILIATION if reservation == "unresolved" else RunState.FAILED
    assert (run.state, run.reason_code) == (expected, ReasonCode.GROUNDING_UNAVAILABLE)
    events = await _events(k, run.run_id)
    assert RunEventType.FEATURE_FALLBACK not in {e.type for e in events}
    assert RunEventType.MESSAGE_FINAL not in {e.type for e in events}
    assert len(await k.store.list_actions(TENANT, run.run_id)) == 1  # the write only


async def test_grounded_answer_resolves_only_against_the_class_view(
    make_kernel: MakeKernel, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The same view rule as a typed answer's (3e.1 R1-1): in a run pinned
    ``context_assembler: on`` on a hosted route, a citation of a value the pack masked is
    ``KERNEL-CITATION`` like a missing key; the visible value then grounds the answer."""

    def cite(obs: Observation, attempt: int) -> tuple[Citation, ...]:
        pointer, value = ("/owner", "alice") if attempt == 1 else ("/count", "0")
        return (Citation(evidence_id=obs.evidence.evidence_id, pointer=pointer, value=value),)

    k = _kernel(make_kernel, cite, PINNED_ON, route=HOSTED_UNDECLARED)
    monkeypatch.setattr(k.coordinator._registry, "data_classes", lambda _cid: CLASSES)
    real = k.backend.read

    async def read(ctx: TaskContext, binding: Any, request: ReadRequest) -> Observation:
        obs = await real(ctx, binding, request)
        return dataclasses.replace(obs, data=dict(CLASSED_DATA))

    monkeypatch.setattr(k.backend, "read", read)

    run = await _start(k)

    events = await _events(k, run.run_id)
    final = _assert_grounded_end(run, events)
    (refused,) = _of(events, RunEventType.VALIDATION_COMPLETED)
    assert [f["observed"] for f in refused.payload["findings"]] == [digest("/owner")]  # 3.R1
    assert "alice" not in json.dumps(refused.payload)
    assert [c["pointer"] for c in final.payload["citations"]] == ["/count"]


# -- the acceptance spec (refines ADR 0028) ------------------------------------------------
def test_acceptance_spec_grounded_answer_requires_no_effects_or_answer() -> None:
    """``grounded_answer`` is valid only when ``required_effects`` and ``required_answer``
    are both empty: the record refuses it, and registry admission re-checks a built
    record, which skips validation."""
    assert AcceptanceSpec(grounded_answer=True).grounded_answer
    assert AcceptanceSpec().grounded_answer is False
    effect = (RequiredEffect(contract_id=CREATE.contract_id),)
    bad = [
        {"grounded_answer": True, "required_answer": SUMMARY.contract_id},
        {"grounded_answer": True, "required_effects": effect},
        {
            "grounded_answer": True,
            "required_answer": SUMMARY.contract_id,
            "required_effects": effect,
        },
    ]
    for fields in bad:
        with pytest.raises(ValidationError, match="grounded_answer"):
            AcceptanceSpec.model_validate(fields)
        built = AcceptanceSpec.model_construct(**fields)
        with pytest.raises(ValueError, match="grounded_answer"):
            check_answer_condition(built)
        task = NOTES_QUESTION.model_copy(update={"acceptance": built})
        registry = PluginRegistry({"notes-mem.read": (CONN,)})
        with pytest.raises(KernelError, match="grounded_answer"):
            registry.register(
                plugin_id="notes-fixture",
                plugin_version="0.1.0",
                declared_capabilities=(READ,),
                binding_templates=(
                    BindingTemplate(binding_id="notes-mem.read", contract_id=READ.contract_id),
                ),
                declared_task_definitions=(TaskDeclaration(task_id=task.task_id, version="1"),),
                contribution=PluginContribution(capabilities=(READ,), task_definitions=(task,)),
            )
    print(f"refused acceptance specs: {len(bad)}")


# -- fix round 1 ---------------------------------------------------------------------------
async def test_grounded_section_needs_the_grounded_end(make_kernel: MakeKernel) -> None:
    """R1-3: the bundle's grounded section is gated on the run's ``GROUNDED`` reason code,
    not only on a ``message.final`` that carries the contract id."""
    k = make_kernel(features=ON)
    run = await k.coordinator.start_run(k.requester, "write standup note", k.scope)
    assert run.reason_code is not ReasonCode.GROUNDED
    current = await k.store.get_run(TENANT, run.run_id)
    forged = {"text": "x", "contract_id": GROUNDED_ANSWER, "citations": []}  # white box
    await k.store.update_run(
        current.model_copy(update={"revision": current.revision + 1}),
        current.revision,
        [(RunEventType.MESSAGE_FINAL, forged, None)],
    )
    bundle = await build_evidence(
        k.store, TENANT, run.run_id, environment="fixture", versions={}, features=ON
    )
    assert "grounded_answer" not in bundle


def test_plugin_capability_named_grounded_answer_is_refused() -> None:
    """R1-4 (PR-09): ``grounded.answer.v1`` is the kernel's own contract, so admission
    refuses a plugin capability that declares that id, before registering anything."""
    impostor = SUMMARY.model_copy(update={"contract_id": GROUNDED_ANSWER})
    registry = PluginRegistry({})
    with pytest.raises(KernelError, match=r"grounded\.answer\.v1 is the kernel's own"):
        registry.register(
            plugin_id="impostor",
            plugin_version="0.1.0",
            declared_capabilities=(READ, impostor),
            binding_templates=(),
            contribution=PluginContribution(capabilities=(READ, impostor)),
        )
    assert registry.capabilities == {}


def test_acceptance_spec_omits_a_false_grounded_answer() -> None:
    """R1-5: a definition without the flag serializes as before ADR 0033 (its stored form,
    its continuation snapshot and the context pack's task layer), and both forms
    round-trip."""
    cases = 0
    for task in (NOTES_TASK, NOTES_QUESTION):
        dumped = task.model_dump(mode="json")
        assert ("grounded_answer" in dumped["acceptance"]) is task.acceptance.grounded_answer
        assert TaskDefinition.model_validate(dumped) == task
        assert TaskDefinition.model_validate_json(task.model_dump_json()) == task
        cases += 1
    assert NOTES_TASK.acceptance.model_dump(mode="json") == {
        "required_effects": [{"contract_id": CREATE.contract_id, "min_verified": 1}],
        "required_answer": None,
        "answer_condition": None,
    }
    assert NOTES_QUESTION.acceptance.model_dump()["grounded_answer"] is True
    print(f"acceptance round trips: {cases}")


async def test_bound_snapshot_without_the_flag_is_stored_as_before(
    make_kernel: MakeKernel,
) -> None:
    """R1-5: the continuation's task snapshot of a definition without the flag has no
    ``grounded_answer`` key."""
    k = make_kernel(features=Features(execution_ir=FeatureMode.ON), task=NOTES_TASK)
    run = await _start(k, NOTES_TASK.task_id)
    stored = await k.store.load_continuation(TENANT, run.run_id)
    assert stored is not None
    assert "grounded_answer" not in stored[0]["data"]["task"]["acceptance"]
