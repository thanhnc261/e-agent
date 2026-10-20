"""The explanation projection (ADR 0033 §6, Task 3c.3).

``explain(ledger, reconstructed)`` is a pure function over a run's progress ledger
(`kernel/progress.py`) and its reconstruction (`kernel/reconstruct.py`). It reads nothing
else, writes nothing and calls no model. It renders goal → source facts → validation
findings → proposals → approvals → receipts → outcomes, as ids, versions, digests and
statuses (`contracts/explain.py`). Each proposal shows its rationale second, after its
facts, as the evidence ids, rule ids, codes and text digests ``proposal.created`` stored
(ADR 0033 §4); the texts were never stored. A run that ended ``GROUNDED`` names a grounded
outcome, never a verified one (PR-19, ADR 0033 §6).

What it leaves out is a rule, not an omission: the proposal's arguments and the receipt's
provider error text (they can carry read data), each finding's message and its expected and
observed values, the outcome's checks (observed values, PR-26) and every model text (PR-28;
the ledger holds none). A field the events do not record is None and named in
``unknown_fields`` (PR-24).
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import Enum
from typing import Any

from e_agent.contracts.explain import (
    AlternativeRef,
    ApprovalRef,
    Completeness,
    Explanation,
    InputRequest,
    OutcomeRef,
    ProposalRef,
    RationaleRef,
    ReceiptRef,
    RunHeader,
    SourceFact,
    Validation,
    ValueLabel,
)
from e_agent.contracts.progress import ProgressLedger, RuleRef, StageKind, StageStatus
from e_agent.contracts.run import ReasonCode
from e_agent.kernel.reconstruct import (
    BY_DESIGN_PARTIAL,
    UNKNOWN_SLOT,
    FieldState,
    Rebuilt,
    Reconstructed,
)

# Each entry's fields by the reconstructed row field they come from. Fields not named here
# stay out of the explanation (arguments, credential subject, timestamps, error text).
_RUN = {
    "run_id": "run_id",
    "goal": "task",  # the operator's task text, not model text
    "requester_id": "requester_id",
    "state": "state",
    "reason_code": "reason_code",
}
_PROPOSAL = {
    "action_id": "action_id",
    "contract_id": "contract_id",
    "binding_id": "binding_id",
    "connection_id": "connection_id",
    "connection_version": "connection_version",
    "credential_version": "credential_version",
    "logical_operation_id": "logical_operation_id",
    "plan_id": "plan_id",
    "step_index": "step_index",
    "supersedes_action_id": "supersedes_action_id",
    "digest": "digest",
    "evidence_ids": "approved_facts",  # the evidence ids only (ADR 0031 §2)
    "state": "state",
}
_APPROVAL = {
    "approval_id": "approval_id",
    "action_id": "action_id",
    "decision": "decision",
    "actor_id": "actor_id",
    "policy_version": "policy_version",
    "action_digest": "action_digest",
}
_RECEIPT = {
    "action_id": "action_id",
    "attempt": "attempt",
    "status": "status",
    "external_refs": "external_refs",
}


def explain(ledger: ProgressLedger, reconstructed: Reconstructed) -> Explanation:
    """The run's explanation; the same inputs always give the same record."""
    return Explanation(
        completeness=Completeness(reconstructed.state.value),
        run=_header(ledger, reconstructed),
        sources=tuple(SourceFact.of(f) for f in ledger.facts),
        validation=_validation(ledger),
        proposals=tuple(_proposal(row, reconstructed.rationales) for row in reconstructed.actions),
        approvals=tuple(_entry(ApprovalRef, row, _APPROVAL) for row in reconstructed.approvals),
        receipts=tuple(_entry(ReceiptRef, row, _RECEIPT) for row in reconstructed.receipts),
        outcomes=_outcomes(ledger, reconstructed),
    )


def _header(ledger: ProgressLedger, reconstructed: Reconstructed) -> RunHeader:
    values, _, unknown = _flatten(reconstructed.run, _RUN)
    driver = reconstructed.driver
    driver_known = driver.state is not FieldState.UNKNOWN
    return RunHeader(
        **values,
        driver_id=driver.value if driver_known else None,
        task_ref=ledger.task_ref,
        task_ref_state=ledger.task_ref_state,
        unknown_fields=unknown if driver_known else (*unknown, "driver_id"),
    )


def _validation(ledger: ProgressLedger) -> Validation:
    stages = (*ledger.done, *ledger.pending)
    return Validation(
        stages=tuple(s for s in stages if s.kind is StageKind.VALIDATE),
        open_findings=tuple(
            RuleRef(rule_id=f.rule_id, rule_version=f.rule_version, status=f.status)
            for f in ledger.open_findings
        ),  # without the message (PR-26)
        rules_evaluated=ledger.rules_evaluated,
        input_requests=tuple(
            InputRequest(event_id=s.event_id, status=s.status)
            for s in stages
            if s.kind is StageKind.INPUT
        ),
    )


def _proposal(row: Rebuilt, rationales: Mapping[str, Mapping[str, Any]]) -> ProposalRef:
    values, partial, unknown = _flatten(row, _PROPOSAL)
    stored = rationales.get(str(values["action_id"]), {})
    try:
        refs = _rationales(stored)
    except (ValueError, AttributeError, KeyError, TypeError):  # not as the kernel wrote it
        refs, unknown = (), (*unknown, "rationales")
    return ProposalRef(**values, partial_fields=partial, unknown_fields=unknown, rationales=refs)


def _rationales(stored: Mapping[str, Any]) -> tuple[RationaleRef, ...]:
    """The at-rest rationale (ADR 0033 §4) as refs: the proposal's or plan's own, then each
    step's. Ids, codes and digests only; the texts were never stored. A ref stored as a
    digest (Task 3.R1) is shown as that digest, in its digest field, never as an id."""
    entries = [(None, stored["rationale"])] if "rationale" in stored else []
    entries.extend((step, r) for step, r in (stored.get("step_rationales") or {}).items())
    return tuple(
        RationaleRef(
            step_id=step,
            goal_ref=r.get("goal_ref"),
            goal_ref_digest=r.get("goal_ref_digest"),
            cited_evidence=tuple(r["cited_evidence"]),
            unresolved_evidence_digests=tuple(r.get("unresolved_evidence_digests", ())),
            rules_considered=tuple(r["rules_considered"]),
            unresolved_rule_digests=tuple(r.get("unresolved_rule_digests", ())),
            alternatives=tuple(AlternativeRef.model_validate(a) for a in r["alternatives"]),
            summary_digest=r["summary_digest"],
        )
        for step, r in entries
    )


def _entry(model: type[Any], row: Rebuilt, names: Mapping[str, str]) -> Any:
    values, _, unknown = _flatten(row, names)
    return model(**values, unknown_fields=unknown)


def _outcomes(ledger: ProgressLedger, reconstructed: Reconstructed) -> tuple[OutcomeRef, ...]:
    verified = tuple(
        OutcomeRef(
            action_id=s.action_id,
            status=s.status,
            event_id=s.event_id,
            step_id=s.step_id,
            label=ValueLabel.VERIFIED_OUTCOME
            if s.status is StageStatus.SUCCEEDED
            else ValueLabel.NOT_VERIFIED,
        )
        for s in (*ledger.done, *ledger.pending)
        if s.kind is StageKind.VERIFY
    )
    code = reconstructed.run.fields.get("reason_code", UNKNOWN_SLOT)
    if code.state is FieldState.UNKNOWN or code.value != ReasonCode.GROUNDED:
        return verified
    grounded = OutcomeRef(
        action_id=None,
        status=StageStatus.SUCCEEDED,
        event_id=None,
        step_id=None,
        label=ValueLabel.GROUNDED_ANSWER,
    )  # a grounded end has no verify stage and is never `verified_outcome` (PR-19)
    return (*verified, grounded)


def _flatten(
    row: Rebuilt, names: Mapping[str, str]
) -> tuple[dict[str, Any], tuple[str, ...], tuple[str, ...]]:
    """The entry's values by its field names, with the names that are partial and unknown.
    An unknown slot gives None, never a default (PR-24)."""
    values: dict[str, Any] = {}
    partial: list[str] = []
    unknown: list[str] = []
    for name, field in names.items():
        slot = row.fields.get(field, UNKNOWN_SLOT)
        if slot.state is FieldState.UNKNOWN:
            values[name] = None
            unknown.append(name)
            continue
        values[name] = _plain(slot.value)
        if slot.state is FieldState.PARTIAL and field not in BY_DESIGN_PARTIAL:
            partial.append(name)
    return values, tuple(partial), tuple(unknown)


def _plain(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, list):
        return tuple(value)
    return value
