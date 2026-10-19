"""`features.grounded_answers` for typed answers (ADR 0033 §1, §2, §5, Task 3e.1, Review Focus
5 and 7).

A typed answer may carry citations in the kernel envelope (`ActionProposal.citations`). A
citation resolves when its evidence id names an observation of **this run's** continuation,
its RFC 6901 pointer exists in that observation's data, and the value there equals the cited
value under ADR 0006's ``jcs-sha256-v1`` (numbers as canonical decimal strings). In ``on`` an
unresolved or mismatched citation is the repair finding ``KERNEL-CITATION`` before the
answer's action exists; when every citation resolves the verifier still decides. In
``shadow`` the answer goes to its verifier as today and the kernel records
``grounding.compared``. In ``off`` citations are dropped and nothing changes. At rest a
citation is its evidence id, pointer and value digest, never the value (PR-26). A check that
cannot run falls back before the run's first reservation and fails closed after it. Runs over
both stores through the ``run_store`` fixture (ENG-STORE-1).
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
from e_agent.contracts.common import utc_now
from e_agent.contracts.context import Budgets, TaskContext
from e_agent.contracts.context_pack import masked_marker
from e_agent.contracts.data_classes import DataClass
from e_agent.contracts.digest import digest
from e_agent.contracts.events import RunEvent, RunEventType
from e_agent.contracts.evidence import EvidenceRef
from e_agent.contracts.features import FeatureMode, Features
from e_agent.contracts.grounding import Citation, GroundingCompared
from e_agent.contracts.plan import ActionPlan, ActionProposal, PlannedStep, plan_to_wire
from e_agent.contracts.run import ReasonCode, RunState
from e_agent.kernel import grounding
from e_agent.kernel.approval import digest_input
from e_agent.kernel.features import FALLBACK_MESSAGES, TERMINAL_MESSAGES
from e_agent.sdk.ports import (
    DriverInput,
    DriverStep,
    FinalAnswer,
    Observation,
    ProposeAction,
    ReadRequest,
    RequestReads,
)

from .conftest import CONN, CREATE, READ, SUMMARY, TENANT, Kernel
from .test_mode_pinning import HOSTED_UNDECLARED, LOCAL, OFF_CONTINUATION_KEYS

MakeKernel = Callable[..., Kernel]
ON = Features(grounded_answers=FeatureMode.ON)
SHADOW = Features(grounded_answers=FeatureMode.SHADOW)
GROUNDING_EVENTS = {RunEventType.GROUNDING_COMPARED, RunEventType.GROUNDING_SHADOW_FAILED}
NO_RATIONALE_COUNTS = {
    "evidence": {"cited": 0, "resolved": 0, "unresolved": 0},
    "rules": {"cited": 0, "resolved": 0, "unresolved": 0},
}
SENTINEL = "SENTINEL-3e1-cited-value"
AT_REST_KEYS = {"evidence_id", "pointer", "value_digest"}

Cite = Callable[[Observation, int], tuple[Citation, ...]]
"""Builds a proposal's citations from the run's observation and the attempt (1, 2, ...)."""


def _own(*pointers: tuple[str, Any]) -> Cite:
    def cite(obs: Observation, attempt: int) -> tuple[Citation, ...]:
        eid = obs.evidence.evidence_id
        return tuple(Citation(evidence_id=eid, pointer=p, value=v) for p, v in pointers)

    return cite


def _none(obs: Observation, attempt: int) -> tuple[Citation, ...]:
    return ()


@dataclass
class CitingDriver:
    """Reads the notes summary, then proposes the notes answer (``count`` from ``counts``,
    else the observed one) with the citations ``cite`` builds; answers after the verified
    result."""

    cite: Cite
    counts: list[str] = field(default_factory=list)
    driver_id: str = "notes-citing-driver"
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
        obs = step_input.observations[0]
        count = self.counts.pop(0) if self.counts else str(obs.data["count"])
        proposal = ActionProposal(
            contract_id=SUMMARY.contract_id,
            connection_id=CONN,
            arguments={"count": count},
            citations=self.cite(obs, self.attempts),
        )
        return ProposeAction(proposal=proposal)


def _kernel(
    make_kernel: MakeKernel, cite: Cite, features: Features | None = None, **kw: Any
) -> Kernel:
    return make_kernel(features=features, with_answer=True, driver=CitingDriver(cite), **kw)


async def _start(k: Kernel) -> Any:
    return await k.coordinator.start_run(k.requester, "summarise the notes", k.scope)


async def _events(k: Kernel, run_id: str) -> list[RunEvent]:
    return await k.store.list_events(TENANT, run_id)


def _of(events: list[RunEvent], kind: RunEventType) -> list[RunEvent]:
    return [e for e in events if e.type is kind]


def _rules(event: RunEvent) -> list[str]:
    return [f["rule_id"] for f in event.payload["findings"]]


def _verifier(k: Kernel) -> Any:
    return k.coordinator._registry.verifier_for(SUMMARY.contract_id)


def _evidence(evidence_id: str = "ev-1") -> EvidenceRef:
    return EvidenceRef(
        evidence_id=evidence_id,
        tenant_id=TENANT,
        source="notes",
        locator="all",
        revision="rev:1",
        observed_at=utc_now(),
        scope=TENANT,
    )


def _observation(data: dict[str, Any], evidence_id: str = "ev-1") -> Observation:
    return Observation(
        request_id="r1", contract_id=READ.contract_id, data=data, evidence=_evidence(evidence_id)
    )


# -- the check (pure) ---------------------------------------------------------------------
def test_check_compares_canonical_values() -> None:
    """Numbers compare as canonical decimal strings (ADR 0006), so a cited ``"3"`` or
    ``3.0`` is the observed ``3``; nested values and the whole-document pointer resolve."""
    obs = _observation({"count": 3, "lines": [{"qty": "1.50"}], "a/b": True, "m~n": None})
    citations = (
        Citation(evidence_id="ev-1", pointer="/count", value="3"),
        Citation(evidence_id="ev-1", pointer="/count", value=3.0),
        Citation(evidence_id="ev-1", pointer="/lines/0/qty", value="1.50"),
        Citation(evidence_id="ev-1", pointer="/a~1b", value=True),
        Citation(evidence_id="ev-1", pointer="/m~0n", value=None),
        Citation(evidence_id="ev-1", pointer="/lines", value=[{"qty": "1.50"}]),
        Citation(evidence_id="ev-1", pointer="/count", value="4"),
        Citation(evidence_id="ev-1", pointer="/lines/0/qty", value="1.5"),
    )
    result = grounding.check_citations([obs], citations)
    statuses = [v.status for v in result.verdicts]
    print(f"grounding check: {len(statuses)} citations")
    assert (
        statuses
        == [grounding.CitationStatus.RESOLVED] * 6 + [grounding.CitationStatus.MISMATCHED] * 2
    )
    assert not result.grounded
    assert result.counts() == {"cited": 8, "resolved": 6, "unresolved": 0, "mismatched": 2}
    assert grounding.check_citations([obs], citations[:6]).grounded
    assert grounding.check_citations([obs], ()).grounded  # nothing cited, nothing refused


# -- `on` ---------------------------------------------------------------------------------
async def test_citation_resolves_to_this_run_evidence(make_kernel: MakeKernel) -> None:
    k = _kernel(make_kernel, _own(("/count", "0"), ("/topic", "standup")), ON)

    run = await _start(k)

    assert run.state is RunState.SUCCEEDED, (run.state, run.reason)
    assert _verifier(k).calls == 1
    events = await _events(k, run.run_id)
    read = _of(events, RunEventType.READ_RECORDED)[0]  # the driver's; the verifier reads again
    (created,) = _of(events, RunEventType.PROPOSAL_CREATED)
    assert created.payload["kind"] == "answer"
    assert created.payload["citations"] == [
        {
            "evidence_id": read.payload["evidence_id"],
            "pointer": "/count",
            "value_digest": digest("0"),
        },
        {
            "evidence_id": read.payload["evidence_id"],
            "pointer": "/topic",
            "value_digest": digest("standup"),
        },
    ]
    assert "KERNEL-CITATION" not in str([e.payload for e in events])
    assert not GROUNDING_EVENTS & {e.type for e in events}  # `on` records no comparison
    (action,) = await k.store.list_actions(TENANT, run.run_id)
    assert action.state is ActionState.VERIFIED
    assert action.arguments == {"count": "0"}  # the domain answer never sees `citations`


async def test_citation_to_another_run_is_unresolved(make_kernel: MakeKernel) -> None:
    """Review Focus 5: a second run of the same tenant cites the first run's evidence id, at
    a pointer and value that are right there. The lookup is this run's continuation, so the
    citation does not resolve: ``KERNEL-CITATION``, no action, no verifier call. The repair
    that cites its own evidence is verified."""
    k = _kernel(make_kernel, _own(("/count", "0")), ON)
    first = await _start(k)
    assert first.state is RunState.SUCCEEDED, first.reason
    read = _of(await _events(k, first.run_id), RunEventType.READ_RECORDED)[0]
    foreign = read.payload["evidence_id"]

    def cite(obs: Observation, attempt: int) -> tuple[Citation, ...]:
        eid = foreign if attempt == 1 else obs.evidence.evidence_id
        return (Citation(evidence_id=eid, pointer="/count", value="0"),)

    k.coordinator._driver = CitingDriver(cite)
    second = await _start(k)

    assert second.state is RunState.SUCCEEDED, second.reason
    assert second.tenant_id == first.tenant_id
    events = await _events(k, second.run_id)
    validation = _of(events, RunEventType.VALIDATION_COMPLETED)[0]
    assert validation.action_id is None
    assert _rules(validation) == ["KERNEL-CITATION"]
    (finding,) = validation.payload["findings"]
    assert finding["evidence_ids"] == [foreign]
    assert finding["observed"] == "/count"
    assert finding["message"] == grounding.CITATION_MESSAGES[grounding.CitationStatus.UNRESOLVED]
    assert len(_of(events, RunEventType.PROPOSAL_CREATED)) == 1  # only the repaired answer
    assert _verifier(k).calls == 2  # one per run: never for the foreign citation


async def test_mismatched_value_is_kernel_citation(make_kernel: MakeKernel) -> None:
    def cite(obs: Observation, attempt: int) -> tuple[Citation, ...]:
        value = "7" if attempt == 1 else "0"
        return (Citation(evidence_id=obs.evidence.evidence_id, pointer="/count", value=value),)

    k = _kernel(make_kernel, cite, ON)

    run = await _start(k)

    assert run.state is RunState.SUCCEEDED, run.reason
    events = await _events(k, run.run_id)
    validations = _of(events, RunEventType.VALIDATION_COMPLETED)
    assert _rules(validations[0]) == ["KERNEL-CITATION"]
    (finding,) = validations[0].payload["findings"]
    assert finding["status"] == "FAIL"
    assert finding["message"] == grounding.CITATION_MESSAGES[grounding.CitationStatus.MISMATCHED]
    assert finding["expected"] is None  # ids and pointers only, never a value (ADR 0032 §5)
    assert finding["observed"] == "/count"
    assert _verifier(k).calls == 1  # only the repaired answer reached the verifier
    driver = k.coordinator._driver
    assert driver.seen[2].findings[0].rule_id == "KERNEL-CITATION"  # the repair reached it


async def test_mismatched_citation_counts_against_repairs(make_kernel: MakeKernel) -> None:
    """``KERNEL-CITATION`` is within ``max_validation_repairs``: past it the run fails
    ``VALIDATION_FAILED``, and no answer action was ever created."""
    k = _kernel(make_kernel, _own(("/count", "7")), ON)

    run = await _start(k)

    assert (run.state, run.reason_code) == (RunState.FAILED, ReasonCode.VALIDATION_FAILED)
    validations = _of(await _events(k, run.run_id), RunEventType.VALIDATION_COMPLETED)
    assert [_rules(e) for e in validations] == [["KERNEL-CITATION"]] * 3
    assert await k.store.list_actions(TENANT, run.run_id) == []
    assert _verifier(k).calls == 0


BAD_POINTERS = ["/missing", "/count/0", "/topic/x", "count", "/~2", "/notes/-"]


def test_bad_pointer_is_unresolved_in_the_check() -> None:
    """A pointer with no value in the data, or that is not RFC 6901 at all, is unresolved;
    the record accepts it, so a bad pointer is a repair, never a refused proposal."""
    obs = _observation({"count": "0", "topic": "standup", "notes": []})
    citations = tuple(Citation(evidence_id="ev-1", pointer=p, value="0") for p in BAD_POINTERS)
    result = grounding.check_citations([obs], citations)
    print(f"bad pointers: {len(result.verdicts)} cases")
    assert len(result.verdicts) == len(BAD_POINTERS) == 6
    assert {v.status for v in result.verdicts} == {grounding.CitationStatus.UNRESOLVED}


async def test_bad_pointer_is_kernel_citation(make_kernel: MakeKernel) -> None:
    def cite(obs: Observation, attempt: int) -> tuple[Citation, ...]:
        pointer = "/missing" if attempt == 1 else "/count"
        return (Citation(evidence_id=obs.evidence.evidence_id, pointer=pointer, value="0"),)

    k = _kernel(make_kernel, cite, ON)

    run = await _start(k)

    assert run.state is RunState.SUCCEEDED, run.reason
    validation = _of(await _events(k, run.run_id), RunEventType.VALIDATION_COMPLETED)[0]
    (finding,) = validation.payload["findings"]
    assert (finding["rule_id"], finding["observed"]) == ("KERNEL-CITATION", "/missing")
    assert finding["message"] == grounding.CITATION_MESSAGES[grounding.CitationStatus.UNRESOLVED]


# -- at rest ------------------------------------------------------------------------------
@pytest.mark.parametrize("features", [SHADOW, ON], ids=["shadow", "on"])
async def test_citation_value_is_not_stored(make_kernel: MakeKernel, features: Features) -> None:
    """PR-26: a cited value that is not in the evidence is nowhere in the ledger, the actions
    or the continuation. In ``shadow`` the stored form is the evidence id, the pointer and
    the value's ``jcs-sha256-v1`` digest; in ``on`` the mismatch is a repair whose finding
    names the pointer only."""

    def cite(obs: Observation, attempt: int) -> tuple[Citation, ...]:
        value = SENTINEL if attempt == 1 else "standup"
        return (Citation(evidence_id=obs.evidence.evidence_id, pointer="/topic", value=value),)

    k = _kernel(make_kernel, cite, features)

    run = await _start(k)

    assert run.state is RunState.SUCCEEDED, run.reason
    events = await _events(k, run.run_id)
    assert SENTINEL not in json.dumps([e.payload for e in events])
    actions = await k.store.list_actions(TENANT, run.run_id)
    assert SENTINEL not in json.dumps([a.model_dump(mode="json") for a in actions])
    stored = await k.store.load_continuation(TENANT, run.run_id)
    assert stored is not None
    assert SENTINEL not in json.dumps(stored[0])
    created = _of(events, RunEventType.PROPOSAL_CREATED)
    stored_forms = [c for e in created for c in e.payload.get("citations", [])]
    assert stored_forms, "at least one citation is stored"
    assert all(set(c) == AT_REST_KEYS for c in stored_forms)
    if features is SHADOW:
        first = _of(events, RunEventType.PROPOSAL_CREATED)[0].payload["citations"][0]
        assert first["value_digest"] == digest(SENTINEL)
        assert first["value_digest"].startswith("jcs-sha256-v1:")


def test_citations_stay_outside_serialization_and_the_digest() -> None:
    """An empty envelope is left out of a proposal's dump, so a stored plan is today's; the
    approval digest input enumerates its fields, so no citation reaches it."""
    plain = ActionProposal(contract_id=CREATE.contract_id, connection_id=CONN, arguments={})
    cited = plain.model_copy(
        update={"citations": (Citation(evidence_id="ev-1", pointer="/x", value=SENTINEL),)}
    )
    assert "citations" not in plain.model_dump(mode="json")
    assert cited.model_dump(mode="json")["citations"][0]["value"] == SENTINEL
    plan = ActionPlan(
        plan_id="p",
        task_id="t",
        task_version="1",
        steps=(PlannedStep(step_id="s1", proposal=cited),),
    )
    wire = plan_to_wire(plan)
    assert SENTINEL not in json.dumps(wire)  # a plan step's citations are never stored
    assert "citations" not in wire["steps"][0]["proposal"]
    assert "citations" not in digest_input.__code__.co_varnames


# -- `off` --------------------------------------------------------------------------------
_IDS = ("action_id", "run_id", "logical_operation_id", "supersedes_action_id", "created_at")


async def test_grounded_off_drops_citations_and_action_record_unchanged(
    make_kernel: MakeKernel,
) -> None:
    """``off``: a driver that sends citations anyway gets exactly the run, events, actions
    and continuation of one that sends none; the citations are dropped, never stored."""
    runs = {}
    for name, cite in (("plain", _none), ("cited", _own(("/count", SENTINEL)))):
        k = _kernel(make_kernel, cite)
        run = await _start(k)
        events = await _events(k, run.run_id)
        actions = await k.store.list_actions(TENANT, run.run_id)
        stored = await k.store.load_continuation(TENANT, run.run_id)
        runs[name] = (k, run, events, actions, stored)

    _, plain_run, plain_events, plain_actions, plain_stored = runs["plain"]
    k, run, events, actions, stored = runs["cited"]
    assert (run.state, run.revision, run.reason_code) == (
        plain_run.state,
        plain_run.revision,
        plain_run.reason_code,
    )
    assert run.state is RunState.SUCCEEDED
    assert [(e.type, sorted(e.payload)) for e in events] == [
        (e.type, sorted(e.payload)) for e in plain_events
    ]
    created, plain_created = (
        _of(es, RunEventType.PROPOSAL_CREATED)[0] for es in (events, plain_events)
    )
    assert "citations" not in created.payload
    assert created.payload["arguments"] == plain_created.payload["arguments"]
    assert created.payload["digest"] == plain_created.payload["digest"]
    assert not GROUNDING_EVENTS & {e.type for e in events}
    assert RunEventType.FEATURE_FALLBACK not in {e.type for e in events}
    assert SENTINEL not in json.dumps([e.payload for e in events])
    assert [a.model_dump(mode="json", exclude=set(_IDS)) for a in actions] == [
        a.model_dump(mode="json", exclude=set(_IDS)) for a in plain_actions
    ]
    assert stored is not None and plain_stored is not None
    assert set(stored[0]["data"]) == set(plain_stored[0]["data"]) == OFF_CONTINUATION_KEYS
    assert SENTINEL not in json.dumps(stored[0])
    assert _verifier(k).calls == 1  # the verifier decided, as today


# -- `shadow` -----------------------------------------------------------------------------
async def test_grounded_shadow_records_comparison(make_kernel: MakeKernel) -> None:
    """The answer goes to its verifier as today; its own write carries
    ``grounding.compared`` with the counts and verdicts, and the stored citations. The run,
    its actions and its other events are ``off``'s."""

    def cite(obs: Observation, attempt: int) -> tuple[Citation, ...]:
        eid = obs.evidence.evidence_id
        return (
            Citation(evidence_id=eid, pointer="/count", value="0"),
            Citation(evidence_id=eid, pointer="/topic", value="retro"),
            Citation(evidence_id="ev-not-this-run", pointer="/count", value="0"),
        )

    runs = {}
    for features in (Features(), SHADOW):
        k = _kernel(make_kernel, cite, features)
        run = await _start(k)
        runs[features.grounded_answers] = (k, run, await _events(k, run.run_id))

    _, off_run, off_events = runs[FeatureMode.OFF]
    k, run, events = runs[FeatureMode.SHADOW]
    assert (run.state, run.revision) == (off_run.state, off_run.revision)
    assert run.state is RunState.SUCCEEDED
    assert [e.type for e in events if e.type not in GROUNDING_EVENTS] == [
        e.type for e in off_events
    ]
    assert _verifier(k).calls == 1  # the mismatch did not stop the verifier
    (compared,) = _of(events, RunEventType.GROUNDING_COMPARED)
    assert compared.payload == {  # the one shape for answers and proposals (3e.3)
        "citations": {
            "cited": 3,
            "resolved": 1,
            "unresolved": 1,
            "mismatched": 1,
            "verdicts": ["resolved", "mismatched", "unresolved"],
        },
        "rationale": NO_RATIONALE_COUNTS,
    }
    index = events.index(compared)  # the comparison follows its proposal in the same write
    created = events[index - 1]
    assert created.type is RunEventType.PROPOSAL_CREATED
    assert created.action_id == compared.action_id is not None
    assert [c["pointer"] for c in created.payload["citations"]] == ["/count", "/topic", "/count"]
    assert "KERNEL-CITATION" not in str([e.payload for e in events])


async def test_grounded_shadow_without_citations_records_zero(make_kernel: MakeKernel) -> None:
    k = _kernel(make_kernel, _none, SHADOW)
    run = await _start(k)
    events = await _events(k, run.run_id)
    (compared,) = _of(events, RunEventType.GROUNDING_COMPARED)
    assert compared.payload["citations"]["cited"] == 0
    assert compared.payload == GroundingCompared().model_dump(mode="json")
    assert "citations" not in _of(events, RunEventType.PROPOSAL_CREATED)[0].payload


def _broken_check(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(*_: Any, **__: Any) -> Any:
        raise RuntimeError(SENTINEL)

    monkeypatch.setattr(grounding, "check_citations", broken)


async def test_grounded_shadow_failure_changes_nothing(
    make_kernel: MakeKernel, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A shadow error records ``grounding.shadow_failed`` with its stage and fixed message,
    never the exception text, and the run is ``off``'s."""
    _broken_check(monkeypatch)
    runs = {}
    for features in (Features(), SHADOW):
        k = _kernel(make_kernel, _own(("/count", "0")), features)
        run = await _start(k)
        runs[features.grounded_answers] = (run, await _events(k, run.run_id))

    off_run, off_events = runs[FeatureMode.OFF]
    run, events = runs[FeatureMode.SHADOW]
    assert (run.state, run.revision) == (off_run.state, off_run.revision)
    assert [e.type for e in events if e.type not in GROUNDING_EVENTS] == [
        e.type for e in off_events
    ]
    (failed,) = _of(events, RunEventType.GROUNDING_SHADOW_FAILED)
    assert failed.payload == {"stage": "check", "message": grounding.GROUNDING_SHADOW_MESSAGE}
    assert SENTINEL not in json.dumps([e.payload for e in events])
    assert "citations" not in _of(events, RunEventType.PROPOSAL_CREATED)[0].payload


# -- the verifier decides -----------------------------------------------------------------
async def test_verifier_still_decides(make_kernel: MakeKernel) -> None:
    """Resolved citations never make an answer verified (PR-19): an answer whose citations
    all resolve but whose count is wrong fails its verifier, and the repair is verified."""
    k = make_kernel(
        features=ON,
        with_answer=True,
        driver=CitingDriver(_own(("/count", "0"), ("/topic", "standup")), counts=["5"]),
    )

    run = await _start(k)

    assert run.state is RunState.SUCCEEDED, run.reason
    assert _verifier(k).calls == 2
    events = await _events(k, run.run_id)
    outcomes = _of(events, RunEventType.OUTCOME_REPORTED)
    assert [e.payload["status"] for e in outcomes] == ["FAILED", "VERIFIED"]
    assert "KERNEL-CITATION" not in str([e.payload for e in events])
    actions = sorted(
        await k.store.list_actions(TENANT, run.run_id), key=lambda a: a.arguments["count"]
    )
    assert [(a.arguments["count"], a.state) for a in actions] == [
        ("0", ActionState.VERIFIED),
        ("5", ActionState.VERIFICATION_FAILED),
    ]


# -- failure handling (ADR 0027) ----------------------------------------------------------
async def test_grounding_failure_falls_back_before_reservation(
    make_kernel: MakeKernel, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Before the first reservation a check that cannot run records ``feature.fallback``
    ``GROUNDING_CHECK_FAILED`` and the typed answer goes to its verifier as today; the code
    never ends the run, and the unchecked citations are not stored."""
    _broken_check(monkeypatch)
    k = _kernel(make_kernel, _own(("/count", "7")), ON)

    run = await _start(k)

    assert (run.state, run.reason_code) == (RunState.SUCCEEDED, ReasonCode.ANSWERED)
    assert _verifier(k).calls == 1
    events = await _events(k, run.run_id)
    (fallback,) = _of(events, RunEventType.FEATURE_FALLBACK)
    assert fallback.payload == {
        "feature": "grounded_answers",
        "reason_code": ReasonCode.GROUNDING_CHECK_FAILED,
        "message": FALLBACK_MESSAGES[ReasonCode.GROUNDING_CHECK_FAILED],
    }
    assert SENTINEL not in json.dumps([e.payload for e in events])
    assert "citations" not in _of(events, RunEventType.PROPOSAL_CREATED)[0].payload
    assert "KERNEL-CITATION" not in str([e.payload for e in events])


@pytest.mark.parametrize("reservation", ["unresolved", "resolved"])
async def test_grounding_failure_after_reservation_fails_closed(
    make_kernel: MakeKernel, monkeypatch: pytest.MonkeyPatch, reservation: str
) -> None:
    """Review Focus 7: after the run's first reservation there is no fallback. The run fails
    ``GROUNDING_UNAVAILABLE``, in reconciliation while the reservation is unresolved, and
    the answer is neither stored nor verified. No live path proposes an answer after a
    reservation in a run that has not finished, so the proposal path is entered directly
    (white box), as 3d.6's post-reservation test does."""
    k = make_kernel(features=ON, with_answer=True, budgets=Budgets(max_admitted_writes=2))
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
        contract_id=SUMMARY.contract_id,
        connection_id=CONN,
        arguments={"count": "1"},
        citations=(Citation(evidence_id=obs.evidence.evidence_id, pointer="/count", value="1"),),
    )

    run = await k.coordinator._handle_proposal(run, cont, proposal)

    expected = RunState.NEEDS_RECONCILIATION if reservation == "unresolved" else RunState.FAILED
    assert (run.state, run.reason_code, run.reason) == (
        expected,
        ReasonCode.GROUNDING_UNAVAILABLE,
        TERMINAL_MESSAGES[ReasonCode.GROUNDING_UNAVAILABLE],
    )
    assert _verifier(k).calls == 0
    events = await _events(k, run.run_id)
    assert RunEventType.FEATURE_FALLBACK not in {e.type for e in events}
    assert len(await k.store.list_actions(TENANT, run.run_id)) == 1  # the write only
    assert SENTINEL not in json.dumps([e.payload for e in events])
    assert k.backend.create_calls == 1


async def test_write_proposal_citations_are_dropped(make_kernel: MakeKernel) -> None:
    """Citations belong to answers (ADR 0033 §2); on a write proposal the validators never
    see them and nothing stores them, in every mode."""
    seen: list[Any] = []
    for features in (Features(), SHADOW, ON):
        k = make_kernel(features=features)
        real = k.validator.validate

        async def validate(ctx: TaskContext, item: Any, real: Any = real) -> Any:
            seen.append(item.proposal.citations)
            return await real(ctx, item)

        k.validator.validate = validate  # type: ignore[method-assign]
        driver = k.driver
        original = driver.advance

        async def advance(
            ctx: TaskContext, step_input: DriverInput, original: Any = original
        ) -> Any:
            step = await original(ctx, step_input)
            if isinstance(step, ProposeAction) and step_input.observations:
                eid = step_input.observations[0].evidence.evidence_id
                cited = Citation(evidence_id=eid, pointer="/topic", value=SENTINEL)
                return ProposeAction(
                    proposal=step.proposal.model_copy(update={"citations": (cited,)})
                )
            return step

        driver.advance = advance
        run = await k.coordinator.start_run(k.requester, "write standup note", k.scope)
        assert run.state is RunState.WAITING_APPROVAL, run.reason
        events = await _events(k, run.run_id)
        assert SENTINEL not in json.dumps([e.payload for e in events])
        assert not GROUNDING_EVENTS & {e.type for e in events}
    assert seen == [(), (), ()]


# -- fix round 1 (R1-1): with `context_assembler: on`, only what the model was shown -------
CLASSED_DATA = {
    "topic": "standup",
    "count": "0",
    "owner": "alice",
    "token": "s3cret",
    "notes": [{"key": "k1"}, {"key": "k2"}],
}
CLASSES = {
    "/output/topic": DataClass.INTERNAL,
    "/output/count": DataClass.INTERNAL,
    "/output/owner": DataClass.PERSONAL,
    "/output/token": DataClass.SECRET,
    "/output/notes/items/key": DataClass.INTERNAL,
}
"""On a hosted, undeclared route the pack masks ``owner`` and removes ``token``."""
PINNED_ON = Features(context_assembler=FeatureMode.ON, grounded_answers=FeatureMode.ON)
MARKER = masked_marker(DataClass.PERSONAL)


def _view(route: dict[str, Any] = HOSTED_UNDECLARED) -> Any:
    return grounding.ClassView(lambda _cid: CLASSES, route)


def _verdicts(cited: list[tuple[str, Any]], view: Any) -> list[grounding.CitationStatus]:
    obs = _observation(dict(CLASSED_DATA))
    citations = [Citation(evidence_id="ev-1", pointer=p, value=v) for p, v in cited]
    return [v.status for v in grounding.check_citations([obs], citations, view).verdicts]


U, R, M = (
    grounding.CitationStatus.UNRESOLVED,
    grounding.CitationStatus.RESOLVED,
    grounding.CitationStatus.MISMATCHED,
)


def test_masked_pointer_is_unresolved_never_mismatched() -> None:
    """A masked value is not evidence: the right value and a wrong guess get the same
    verdict, so the check is no oracle on what the pack withheld (PR-26)."""
    assert _verdicts([("/owner", "alice"), ("/owner", "bob")], _view()) == [U, U]
    # a container holding a masked value is no evidence either
    assert _verdicts([("", dict(CLASSED_DATA))], _view()) == [U]


def test_secret_removed_pointer_is_like_a_missing_key() -> None:
    assert _verdicts(
        [("/token", "s3cret"), ("/token", "guess"), ("/nonexistent", "s3cret")], _view()
    ) == [U, U, U]


def test_visible_value_still_resolves_or_mismatches() -> None:
    cited = [("/topic", "standup"), ("/topic", "retro"), ("/notes/1/key", "k2")]
    assert _verdicts(cited, _view()) == [R, M, R]
    # on a local route nothing personal is masked; a secret is still removed
    assert _verdicts([("/owner", "alice"), ("/token", "s3cret")], _view(LOCAL)) == [R, U]


def test_marker_as_cited_value_is_unresolved() -> None:
    """Citing the marker itself, alone or inside a container, never resolves."""
    cited = [("/owner", MARKER), ("/notes/0", {"key": MARKER})]
    assert _verdicts(cited, _view()) == [U, U]


def test_raw_check_without_view_is_unchanged() -> None:
    """``context_assembler`` not ``on``: the driver sent the raw data, compared as before."""
    cited = [("/owner", "alice"), ("/owner", "bob"), ("/token", "s3cret"), ("/x", "1")]
    assert _verdicts(cited, None) == [R, M, R, U]


def _classed(
    make_kernel: MakeKernel,
    monkeypatch: pytest.MonkeyPatch,
    cite: Cite,
    features: Features,
    route: dict[str, Any],
) -> Kernel:
    k = _kernel(make_kernel, cite, features, route=route)
    monkeypatch.setattr(k.coordinator._registry, "data_classes", lambda _cid: CLASSES)
    real = k.backend.read

    async def read(ctx: TaskContext, binding: Any, request: ReadRequest) -> Observation:
        obs = await real(ctx, binding, request)
        return dataclasses.replace(obs, data=dict(CLASSED_DATA))

    monkeypatch.setattr(k.backend, "read", read)
    return k


async def test_masked_and_removed_citations_give_one_finding_text(
    make_kernel: MakeKernel, monkeypatch: pytest.MonkeyPatch
) -> None:
    """In a run pinned ``context_assembler: on`` on a hosted route, a masked pointer, a
    removed secret and a nonexistent key give the same ``KERNEL-CITATION`` text, and no
    finding names a data class or a value. The visible repair is verified."""
    pointers = ["/owner", "/token", "/nonexistent"]

    def cite(obs: Observation, attempt: int) -> tuple[Citation, ...]:
        eid = obs.evidence.evidence_id
        if attempt > 1:
            return (Citation(evidence_id=eid, pointer="/count", value="0"),)
        values = ["alice", "s3cret", "alice"]
        return tuple(
            Citation(evidence_id=eid, pointer=p, value=v)
            for p, v in zip(pointers, values, strict=True)
        )

    k = _classed(make_kernel, monkeypatch, cite, PINNED_ON, HOSTED_UNDECLARED)

    run = await _start(k)

    assert run.state is RunState.SUCCEEDED, run.reason
    validation = _of(await _events(k, run.run_id), RunEventType.VALIDATION_COMPLETED)[0]
    findings = validation.payload["findings"]
    assert [f["observed"] for f in findings] == pointers
    unresolved = grounding.CITATION_MESSAGES[grounding.CitationStatus.UNRESOLVED]
    assert {f["message"] for f in findings} == {unresolved}
    text = json.dumps(findings)
    for leaked in ("personal", "secret", "masked", "alice", "s3cret"):
        assert leaked not in text, leaked
    assert _verifier(k).calls == 1


async def test_context_assembler_off_with_grounded_on_is_unchanged(
    make_kernel: MakeKernel, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without the pack the model saw the raw values: they resolve as before."""

    def cite(obs: Observation, attempt: int) -> tuple[Citation, ...]:
        eid = obs.evidence.evidence_id
        return (
            Citation(evidence_id=eid, pointer="/owner", value="alice"),
            Citation(evidence_id=eid, pointer="/token", value="s3cret"),
        )

    k = _classed(make_kernel, monkeypatch, cite, ON, LOCAL)

    run = await _start(k)

    assert run.state is RunState.SUCCEEDED, run.reason
    events = await _events(k, run.run_id)
    assert "KERNEL-CITATION" not in str([e.payload for e in events])
    created = _of(events, RunEventType.PROPOSAL_CREATED)[0]
    assert [c["pointer"] for c in created.payload["citations"]] == ["/owner", "/token"]


async def test_class_walk_failure_takes_the_failure_path(
    make_kernel: MakeKernel, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A walk that cannot run is a check that cannot run: before a reservation it falls
    back with ``GROUNDING_CHECK_FAILED`` and the verifier decides."""

    def broken(*_: Any, **__: Any) -> Any:
        raise RuntimeError(SENTINEL)

    k = _classed(make_kernel, monkeypatch, _own(("/count", "0")), PINNED_ON, HOSTED_UNDECLARED)
    monkeypatch.setattr(grounding, "Walker", broken)

    run = await _start(k)

    assert (run.state, run.reason_code) == (RunState.SUCCEEDED, ReasonCode.ANSWERED)
    events = await _events(k, run.run_id)
    (fallback,) = _of(events, RunEventType.FEATURE_FALLBACK)
    assert fallback.payload["reason_code"] == ReasonCode.GROUNDING_CHECK_FAILED
    assert SENTINEL not in json.dumps([e.payload for e in events])
    assert _verifier(k).calls == 1


# -- fix round 2 (R2-1): a container the class walk removed something from is no value ---
REMOVAL_DATA = {
    "s": ["a", "b"],
    "box": {"visible": "v", "token": "x"},
    "open": {"named": "n", "extra": "e"},
}
REMOVAL_CLASSES = {
    "/output/s/items": DataClass.SECRET,
    "/output/box/visible": DataClass.INTERNAL,
    "/output/box/token": DataClass.SECRET,
    "/output/open/named": DataClass.INTERNAL,
}
"""Secret list members, a box's secret key, and an unnamed key the hosted-undeclared row
leaves out (``open/extra``): each removal leaves a reduced container behind."""


def _removal_verdicts(cited: list[tuple[str, Any]]) -> list[grounding.CitationStatus]:
    obs = _observation(dict(REMOVAL_DATA))
    view = grounding.ClassView(lambda _cid: REMOVAL_CLASSES, HOSTED_UNDECLARED)
    citations = [Citation(evidence_id="ev-1", pointer=p, value=v) for p, v in cited]
    return [v.status for v in grounding.check_citations([obs], citations, view).verdicts]


def test_list_that_lost_secret_members_is_unresolved() -> None:
    assert _removal_verdicts([("/s", []), ("/s", ["a", "b"])]) == [U, U]


def test_box_that_lost_a_secret_key_is_unresolved() -> None:
    assert _removal_verdicts([("/box", {"visible": "v"}), ("/box/token", "x")]) == [U, U]


def test_box_that_lost_an_unnamed_key_is_unresolved() -> None:
    assert _removal_verdicts([("/open", {"named": "n"}), ("", {})]) == [U, U]


def test_value_beside_a_removal_still_resolves() -> None:
    cited = [("/box/visible", "v"), ("/open/named", "n"), ("/box/visible", "w")]
    assert _removal_verdicts(cited) == [R, R, M]


def test_markers_are_the_ones_the_walker_writes() -> None:
    """A secret is never masked, only removed (`ContextPolicy`), so its marker is not one."""
    assert masked_marker(DataClass.SECRET) not in grounding.MARKERS
    assert MARKER in grounding.MARKERS
