"""`features.kernel_repeat` in the kernel (ADR 0031 §5, Task 3d.6, Review Focus 6 and 7).

A write proposal is a repeat when an earlier write proposal of the same run was blocked by
validation in `_handle_proposal`, its approval digest recomputed with that revision's rule
bundle version equals the earlier digest (so every fact's evidence id, source, revision,
completeness and fact digest is unchanged), and the registry surface is the run's. In ``on``
a repeat makes no action and gets ``KERNEL-REPEAT`` plus the earlier findings as a repair
within ``max_validation_repairs``; in ``shadow`` validation runs as today and the kernel
records ``repeat.compared``; in ``off`` nothing is recorded or kept. A block by a validator
that raised (the ``error`` bundle) is never a repeat. A check that cannot run falls back
before the run's first reservation and fails closed after it. Runs over both stores through
the ``run_store`` fixture (ENG-STORE-1).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from functools import partial
from typing import Any

import pytest
from e_agent.contracts.action import ActionState
from e_agent.contracts.approval import ApprovalDecision
from e_agent.contracts.common import utc_now
from e_agent.contracts.context import Budgets, TaskContext
from e_agent.contracts.events import RunEvent, RunEventType
from e_agent.contracts.evidence import Completeness, EvidenceRef
from e_agent.contracts.features import FeatureMode, Features
from e_agent.contracts.plan import ActionProposal
from e_agent.contracts.run import ReasonCode, RunState
from e_agent.contracts.validation import Finding, ValidationStatus
from e_agent.kernel import repeat
from e_agent.kernel.approval import compute_digest, digest_input
from e_agent.kernel.continuation import BlockedRevision
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

from .conftest import CONN, CREATE, READ, TENANT, Kernel
from .test_mode_pinning import OFF_CONTINUATION_KEYS

MakeKernel = Callable[..., Kernel]
ON = Features(kernel_repeat=FeatureMode.ON)
SHADOW = Features(kernel_repeat=FeatureMode.SHADOW)
REPEAT_EVENTS = {RunEventType.REPEAT_COMPARED, RunEventType.REPEAT_SHADOW_FAILED}
SENTINEL = "SENTINEL-3d6-check-text"


def _counting(k: Kernel, *, explode_first: bool = False) -> list[str]:
    """Count the notes validator's calls (the text it judged); optionally raise on the
    first call, as an engine that is down would."""
    real = k.validator.validate
    calls: list[str] = []

    async def validate(ctx: TaskContext, item: Any) -> Any:
        calls.append(str(item.proposal.arguments.get("text")))
        if explode_first and len(calls) == 1:
            raise RuntimeError("engine down")
        return await real(ctx, item)

    k.validator.validate = validate  # type: ignore[method-assign]
    return calls


async def _events(k: Kernel, run_id: str) -> list[RunEvent]:
    return await k.store.list_events(TENANT, run_id)


def _of(events: list[RunEvent], kind: RunEventType) -> list[RunEvent]:
    return [e for e in events if e.type is kind]


def _rules(event: RunEvent) -> list[str]:
    return [f["rule_id"] for f in event.payload["findings"]]


async def _stored(k: Kernel, run_id: str) -> dict[str, Any]:
    stored = await k.store.load_continuation(TENANT, run_id)
    assert stored is not None
    data: dict[str, Any] = stored[0]["data"]
    return data


async def _actions(k: Kernel, run_id: str) -> list[Any]:
    """The run's actions in proposal order (a store may list them in another)."""
    order = [e.action_id for e in _of(await _events(k, run_id), RunEventType.PROPOSAL_CREATED)]
    actions = await k.store.list_actions(TENANT, run_id)
    return sorted(actions, key=lambda a: order.index(a.action_id))


async def _start(k: Kernel) -> Any:
    return await k.coordinator.start_run(k.requester, "write standup note", k.scope)


# -- `on` ---------------------------------------------------------------------------------
async def test_repeat_of_blocked_digest_short_circuits(make_kernel: MakeKernel) -> None:
    k = make_kernel(["", "", "standup notes"], features=ON)
    calls = _counting(k)

    run = await _start(k)

    assert run.state is RunState.WAITING_APPROVAL, run.reason
    assert calls == ["", "standup notes"]  # the repeat was never validated again
    actions = await _actions(k, run.run_id)
    assert [a.state for a in actions] == [ActionState.BLOCKED, ActionState.AWAITING_APPROVAL]
    events = await _events(k, run.run_id)
    validations = _of(events, RunEventType.VALIDATION_COMPLETED)
    assert [e.action_id for e in validations] == [actions[0].action_id, None, actions[1].action_id]
    repeated = validations[1].payload
    assert repeated["status"] == "FAIL"
    assert _rules(validations[1]) == ["KERNEL-REPEAT", "NOTE-001"]
    kernel_finding = repeated["findings"][0]
    assert kernel_finding["observed"] == actions[0].action_id
    assert kernel_finding["message"] == repeat.REPEAT_MESSAGE
    assert repeated["findings"][1:] == validations[0].payload["findings"]
    assert "action_state" not in repeated  # no action id, so no reconstruction key
    assert not REPEAT_EVENTS & {e.type for e in events}  # `on` records no comparison
    assert len(_of(events, RunEventType.PROPOSAL_CREATED)) == 2
    data = await _stored(k, run.run_id)
    assert [b["action_id"] for b in data["blocked"]] == [actions[0].action_id]
    assert data["repairs"] == 2


async def test_repeat_counts_against_repairs(make_kernel: MakeKernel) -> None:
    """The budget is the blocked path's: two repairs, then FAILED ``VALIDATION_FAILED``,
    exactly where ``off`` ends the same script, with one validation instead of three."""
    outcomes = {}
    for features in (Features(), ON):
        k = make_kernel(["", "", "", ""], features=features)
        calls = _counting(k)
        run = await _start(k)
        events = await _events(k, run.run_id)
        actions = await k.store.list_actions(TENANT, run.run_id)
        outcomes[features.kernel_repeat] = (run, calls, events, actions)

    off_run, off_calls, off_events, off_actions = outcomes[FeatureMode.OFF]
    on_run, on_calls, on_events, on_actions = outcomes[FeatureMode.ON]
    for run in (off_run, on_run):
        assert (run.state, run.reason_code) == (RunState.FAILED, ReasonCode.VALIDATION_FAILED)
    assert (len(off_calls), len(on_calls)) == (3, 1)
    assert (len(off_actions), len(on_actions)) == (3, 1)
    off_validations = _of(off_events, RunEventType.VALIDATION_COMPLETED)
    on_validations = _of(on_events, RunEventType.VALIDATION_COMPLETED)
    assert len(off_validations) == len(on_validations) == 3
    assert [_rules(e)[0] for e in on_validations] == ["NOTE-001", "KERNEL-REPEAT", "KERNEL-REPEAT"]


@dataclass
class RereadDriver:
    """Reads, proposes an empty note, then on the finding re-reads the same request (the
    test decides whether the source's revision moved) and proposes the same empty note;
    then a valid one."""

    k: Kernel
    bump: bool
    driver_id: str = "reread-driver"
    calls: int = 0
    seen: list[DriverInput] = field(default_factory=list)

    async def advance(self, ctx: TaskContext, step_input: DriverInput) -> DriverStep:
        self.calls += 1
        self.seen.append(step_input)
        if step_input.action_result is not None:
            return FinalAnswer(text="done")
        read = ReadRequest(
            request_id="r1", contract_id=READ.contract_id, connection_id=CONN, arguments={}
        )
        if self.calls == 1:
            return RequestReads(reads=(read,))
        if self.calls == 3:  # after the first finding: read the same fact again
            if self.bump:
                self.k.backend.revision += 1
            return RequestReads(reads=(read,))
        text = "standup notes" if self.calls >= 5 else ""
        proposal = ActionProposal(
            contract_id=CREATE.contract_id, connection_id=CONN, arguments={"text": text}
        )
        return ProposeAction(proposal=proposal)


def _fixed_evidence_reads(k: Kernel, monkeypatch: pytest.MonkeyPatch) -> None:
    """Every read returns the same evidence id and data: a re-read differs only in the
    source revision, so the test isolates the revision (Review Focus 6)."""
    backend = k.backend

    async def read(ctx: TaskContext, binding: Any, request: ReadRequest) -> Observation:
        evidence = EvidenceRef(
            evidence_id="ev-fixed",
            tenant_id=ctx.tenant_id,
            source="notes",
            locator="all",
            revision=f"rev:{backend.revision}",
            observed_at=utc_now(),
            scope=ctx.tenant_id,
        )
        return Observation(
            request_id=request.request_id,
            contract_id=request.contract_id,
            data={"topic": "standup", "count": "0"},
            evidence=evidence,
        )

    monkeypatch.setattr(backend, "read", read)


@pytest.mark.parametrize("bump", [True, False], ids=["revision-changed", "revision-same"])
async def test_changed_fact_revision_revalidates(
    make_kernel: MakeKernel, monkeypatch: pytest.MonkeyPatch, bump: bool
) -> None:
    """Review Focus 6: the same proposal after a re-read whose revision moved is validated
    again; with the revision unchanged (same evidence id and data) it is the repeat."""
    k = make_kernel(features=ON)
    k.coordinator._driver = driver = RereadDriver(k, bump)
    _fixed_evidence_reads(k, monkeypatch)
    calls = _counting(k)

    run = await _start(k)

    assert run.state is RunState.WAITING_APPROVAL, run.reason
    validations = _of(await _events(k, run.run_id), RunEventType.VALIDATION_COMPLETED)
    assert len(validations) == 3
    if bump:
        assert calls == ["", "", "standup notes"]
        assert [_rules(e)[0] for e in validations] == ["NOTE-001", "NOTE-001", "NOTE-001"]
    else:
        assert calls == ["", "standup notes"]
        assert _rules(validations[1])[0] == "KERNEL-REPEAT"
    assert driver.calls == 5


def _canonical(evidence: EvidenceRef, fact: str = "") -> Any:
    return partial(
        digest_input,
        tenant_id=TENANT,
        requester_id="alice",
        logical_operation_id="op-1",
        contract_id=CREATE.contract_id,
        binding_id="notes-mem.create",
        connection_id=CONN,
        connection_version=1,
        credential_subject="svc",
        arguments={"text": ""},
        expected_effects=(),
        evidence=[evidence],
        policy_version="p1",
        credential_version="none",
        fact_digests={evidence.evidence_id: fact} if fact else {},
    )


def test_repeat_compares_every_fact_field() -> None:
    """The compared set is the full digest input the original validation was bound to: a
    change in any fact field (revision, completeness, source, a revision-less fact's
    digest) or a changed surface is not a repeat."""
    evidence = EvidenceRef(
        evidence_id="ev-1",
        tenant_id=TENANT,
        source="notes",
        locator="all",
        revision=None,
        observed_at=utc_now(),
        scope=TENANT,
    )
    earlier = _canonical(evidence, fact="facts-json-v1:a")
    blocked = (
        BlockedRevision(
            action_id="act-1",
            digest=compute_digest(earlier(rule_bundle_version="notes@1")),
            rule_bundle_version="notes@1",
            findings=(),
        ),
    )
    assert repeat.find_repeat(blocked, earlier, surface_unchanged=True) == blocked[0]
    assert repeat.find_repeat(blocked, earlier, surface_unchanged=False) is None
    changed = [
        _canonical(evidence.model_copy(update={"revision": "rev:2"}), fact="facts-json-v1:a"),
        _canonical(
            evidence.model_copy(update={"completeness": Completeness.PARTIAL}),
            fact="facts-json-v1:a",
        ),
        _canonical(evidence.model_copy(update={"source": "other"}), fact="facts-json-v1:a"),
        _canonical(evidence, fact="facts-json-v1:b"),
        _canonical(evidence.model_copy(update={"evidence_id": "ev-2"}), fact="facts-json-v1:a"),
    ]
    for canonical in changed:
        assert repeat.find_repeat(blocked, canonical, surface_unchanged=True) is None
    print(f"repeat rule refuses {len(changed)} changed fact fields")
    assert len(changed) == 5


def test_invalid_digest_is_never_a_repeat() -> None:
    """A proposal outside the digest profile (``KERNEL-ARGS``) is never a repeat."""

    def unencodable(**_: Any) -> dict[str, Any]:
        return {"arguments": {"value": float("nan")}}

    blocked = (BlockedRevision(action_id="a", digest="invalid", rule_bundle_version="r"),)
    assert repeat.find_repeat(blocked, unencodable, surface_unchanged=True) is None


async def test_validator_error_block_is_not_a_repeat(make_kernel: MakeKernel) -> None:
    """A validator that raised has not judged the facts: its ``error`` bundle block is not
    kept, so the same proposal is validated again (ruling on 3d.6 concern 1)."""
    k = make_kernel(["standup notes", "standup notes"], features=ON)
    calls = _counting(k, explode_first=True)

    run = await _start(k)

    assert run.state is RunState.WAITING_APPROVAL, run.reason
    assert calls == ["standup notes", "standup notes"]
    validations = _of(await _events(k, run.run_id), RunEventType.VALIDATION_COMPLETED)
    assert [_rules(e)[0] for e in validations] == ["KERNEL-VALIDATOR-ERROR", "NOTE-001"]
    assert "blocked" not in await _stored(k, run.run_id)


async def test_changed_surface_revalidates(make_kernel: MakeKernel) -> None:
    """A registry surface that is no longer the run's may hold other validators: the same
    proposal is validated again."""
    k = make_kernel(["", ""], features=ON)
    calls = _counting(k)
    registry = k.coordinator._registry
    real = registry.surface_digest

    def surface() -> str:  # the run's surface until the first proposal is validated
        return real() if not calls else "sha256:other"

    registry.surface_digest = surface  # type: ignore[method-assign]
    run = await _start(k)

    assert (run.state, run.reason_code) == (RunState.FAILED, ReasonCode.VALIDATION_FAILED)
    assert calls == ["", "", ""]
    validations = _of(await _events(k, run.run_id), RunEventType.VALIDATION_COMPLETED)
    assert "KERNEL-REPEAT" not in {r for e in validations for r in _rules(e)}


# -- `shadow` -----------------------------------------------------------------------------
async def test_repeat_shadow_records_comparison(make_kernel: MakeKernel) -> None:
    """Validation runs as today; each write proposal's ``repeat.compared`` is in the
    proposal's own write, so the run, its actions and its other events are ``off``'s."""
    runs = {}
    for features in (Features(), SHADOW):
        k = make_kernel(["", "", "standup notes"], features=features)
        calls = _counting(k)
        run = await _start(k)
        runs[features.kernel_repeat] = (k, run, calls, await _events(k, run.run_id))

    _, off_run, off_calls, off_events = runs[FeatureMode.OFF]
    k, run, calls, events = runs[FeatureMode.SHADOW]
    assert calls == off_calls == ["", "", "standup notes"]
    assert (run.state, run.revision) == (off_run.state, off_run.revision)
    assert [e.type for e in events if e.type not in REPEAT_EVENTS] == [e.type for e in off_events]
    actions = await _actions(k, run.run_id)
    compared = _of(events, RunEventType.REPEAT_COMPARED)
    assert [e.action_id for e in compared] == [a.action_id for a in actions]
    assert [e.payload for e in compared] == [
        {"would_repeat": False, "repeat_of": None, "same_findings": None},
        {"would_repeat": True, "repeat_of": actions[0].action_id, "same_findings": True},
        {"would_repeat": False, "repeat_of": None, "same_findings": None},
    ]
    for event in compared:  # the comparison follows its proposal in the same write
        index = events.index(event)
        assert events[index - 1].type is RunEventType.PROPOSAL_CREATED
        assert events[index - 1].action_id == event.action_id
    data = await _stored(k, run.run_id)
    assert [b["action_id"] for b in data["blocked"]] == [a.action_id for a in actions[:2]]


async def test_repeat_shadow_disagreement_is_recorded(make_kernel: MakeKernel) -> None:
    """A validator that is not a function of its input (the ADR's assumption broken) shows
    as ``same_findings: false``: what the release report counts."""
    k = make_kernel(["", ""], features=SHADOW)
    real = k.validator.validate
    seen: list[int] = []

    async def drifting(ctx: TaskContext, item: Any) -> Any:
        seen.append(1)
        result = await real(ctx, item)
        if len(seen) == 1:
            return result
        moved = Finding(
            rule_id="NOTE-002", rule_version="1", status=ValidationStatus.FAIL, message="m"
        )
        return result.model_copy(update={"findings": (moved,)})

    k.validator.validate = drifting  # type: ignore[method-assign]
    run = await _start(k)
    compared = _of(await _events(k, run.run_id), RunEventType.REPEAT_COMPARED)
    assert compared[1].payload["would_repeat"] is True
    assert compared[1].payload["same_findings"] is False


@pytest.mark.parametrize("stage", ["check", "compare"])
async def test_repeat_shadow_failure_changes_nothing(
    make_kernel: MakeKernel, monkeypatch: pytest.MonkeyPatch, stage: str
) -> None:
    """A shadow error records ``repeat.shadow_failed`` with its stage and fixed message,
    never the exception text, and leaves validation and the run as ``off`` (D3-30)."""

    def broken(*_: Any, **__: Any) -> Any:
        raise RuntimeError(SENTINEL)

    monkeypatch.setattr(repeat, "find_repeat" if stage == "check" else "same_findings", broken)
    runs = {}
    for features in (Features(), SHADOW):
        k = make_kernel(["", "", "standup notes"], features=features)
        calls = _counting(k)
        run = await _start(k)
        runs[features.kernel_repeat] = (run, calls, await _events(k, run.run_id))

    off_run, off_calls, off_events = runs[FeatureMode.OFF]
    run, calls, events = runs[FeatureMode.SHADOW]
    assert calls == off_calls
    assert (run.state, run.revision) == (off_run.state, off_run.revision)
    assert [e.type for e in events if e.type not in REPEAT_EVENTS] == [e.type for e in off_events]
    failed = _of(events, RunEventType.REPEAT_SHADOW_FAILED)
    # `compare` runs only where a match was found: the second proposal
    expected = 3 if stage == "check" else 1
    assert [e.payload for e in failed] == [
        {"stage": stage, "message": repeat.REPEAT_SHADOW_MESSAGES[stage]}
    ] * expected
    assert SENTINEL not in str([e.payload for e in events])
    assert len(_of(events, RunEventType.REPEAT_COMPARED)) == 3 - expected


# -- `off` --------------------------------------------------------------------------------
async def test_repeat_off_unchanged(make_kernel: MakeKernel) -> None:
    """``off`` validates every repeat again, records nothing and keeps nothing: the stored
    continuation has exactly the pre-Phase 3 keys."""
    k = make_kernel(["", "", "standup notes"])
    calls = _counting(k)

    run = await _start(k)

    assert run.state is RunState.WAITING_APPROVAL
    assert calls == ["", "", "standup notes"]
    events = await _events(k, run.run_id)
    assert not REPEAT_EVENTS & {e.type for e in events}
    assert RunEventType.FEATURE_FALLBACK not in {e.type for e in events}
    assert "KERNEL-REPEAT" not in str([e.payload for e in events])
    assert set(await _stored(k, run.run_id)) == OFF_CONTINUATION_KEYS


# -- failure handling (ADR 0027) ----------------------------------------------------------
def _broken_check(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(*_: Any, **__: Any) -> Any:
        raise RuntimeError(SENTINEL)

    monkeypatch.setattr(repeat, "find_repeat", broken)


async def test_repeat_check_failure_falls_back_before_reservation(
    make_kernel: MakeKernel, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Before the first reservation a check that cannot run records ``feature.fallback``
    ``REPEAT_CHECK_FAILED`` and the proposal is validated as today; the code never ends
    the run."""
    _broken_check(monkeypatch)
    k = make_kernel(["", "", "standup notes"], features=ON)
    calls = _counting(k)

    run = await _start(k)

    assert (run.state, run.reason_code) == (RunState.WAITING_APPROVAL, None)
    assert calls == ["", "", "standup notes"]  # every proposal validated as today
    events = await _events(k, run.run_id)
    fallbacks = _of(events, RunEventType.FEATURE_FALLBACK)
    assert [e.payload for e in fallbacks] == [
        {
            "feature": "kernel_repeat",
            "reason_code": ReasonCode.REPEAT_CHECK_FAILED,
            "message": FALLBACK_MESSAGES[ReasonCode.REPEAT_CHECK_FAILED],
        }
    ] * 3
    assert SENTINEL not in str([e.payload for e in events])
    validations = _of(events, RunEventType.VALIDATION_COMPLETED)
    assert [_rules(e)[0] for e in validations] == ["NOTE-001", "NOTE-001", "NOTE-001"]


@pytest.mark.parametrize("reservation", ["unresolved", "resolved"])
async def test_repeat_check_failure_after_reservation_fails_closed(
    make_kernel: MakeKernel, monkeypatch: pytest.MonkeyPatch, reservation: str
) -> None:
    """Review Focus 7: after the run's first reservation there is no fallback. The run fails
    ``REPEAT_UNAVAILABLE``, in reconciliation while the reservation is unresolved, and the
    proposal is neither validated nor stored. No live path proposes a write after a
    reservation in a run that has not finished (a verified write ends the run; a plan's
    later steps dispatch through `_start_step`), so the proposal path is entered directly
    (white box), as 3d.5's post-reservation test does."""
    k = make_kernel(features=ON, budgets=Budgets(max_admitted_writes=2))
    run = await _start(k)
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
    calls = _counting(k)
    _broken_check(monkeypatch)
    cont = await k.coordinator._load_cont(TENANT, run.run_id)
    proposal = ActionProposal(
        contract_id=CREATE.contract_id, connection_id=CONN, arguments={"text": "again"}
    )

    run = await k.coordinator._handle_proposal(run, cont, proposal)

    expected = RunState.NEEDS_RECONCILIATION if reservation == "unresolved" else RunState.FAILED
    assert (run.state, run.reason_code, run.reason) == (
        expected,
        ReasonCode.REPEAT_UNAVAILABLE,
        TERMINAL_MESSAGES[ReasonCode.REPEAT_UNAVAILABLE],
    )
    assert calls == []
    events = await _events(k, run.run_id)
    assert RunEventType.FEATURE_FALLBACK not in {e.type for e in events}
    assert len(await k.store.list_actions(TENANT, run.run_id)) == 1
    assert SENTINEL not in str([e.payload for e in events])
    assert k.backend.create_calls == 1
