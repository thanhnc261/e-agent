"""The explanation of one run: a read-only projection (ADR 0033 §6, Task 3c.3).

It is computed from the progress ledger and the reconstruction, never stored, and renders
the run in order: goal, source facts, validation findings, proposals, approvals, receipts
and outcomes. It holds ids, versions, digests and statuses only: no observation values
(PR-26), no proposal arguments, no provider error text and no model text (PR-28). Every
entry carries the label of what kind of record it is (research 03 CQ10).

A fact the events do not record stays unknown (PR-24): a field is None and its name is
listed in the entry's ``unknown_fields``, so a known None (no plan link) and an unrecorded
value never look alike.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import SerializerFunctionWrapHandler, model_serializer

from .common import Record
from .progress import FactRef, RuleRef, Stage, StageStatus, TaskRefState


class Completeness(StrEnum):
    """How much of the run its events show (ADR 0031 §2)."""

    KNOWN = "known"
    PARTIAL = "partial"
    """Some field is not recorded or may be behind its row: a run whose events predate the
    ADR 0031 §3 keys is partial."""
    UNKNOWN = "unknown"
    """The events show no run at all."""


class ValueLabel(StrEnum):
    """What kind of record an explained value is (research 03 CQ10)."""

    PROVIDER_READ = "provider_read"
    """A read the action gateway recorded: an authoritative provider record at a revision."""
    MODEL_PROPOSAL = "model_proposal"
    """A proposed action, shown by its digest; model output is a proposal (PR-13)."""
    APPROVER_DECISION = "approver_decision"
    PROVIDER_RECEIPT = "provider_receipt"
    """A committed effect as the provider reported it, not a verified outcome (PR-19)."""
    VERIFIED_OUTCOME = "verified_outcome"
    """An outcome an independent read-back verified."""
    NOT_VERIFIED = "not_verified"
    """An outcome the read-back did not verify: failed, unknown or not finished."""
    MODEL_AUTHORED = "model_authored"
    """Model-authored text, shown only by its digest (a rationale, ADR 0033 §4)."""
    GROUNDED_ANSWER = "grounded_answer"
    """A ``grounded.answer.v1`` end: every citation resolved against this run's evidence.
    Grounded, never verified: no independent read-back took place (PR-19, ADR 0033 §3)."""


class RunHeader(Record):
    run_id: str | None
    goal: str | None
    """The operator's task text from ``run.created``; None when the events do not hold it."""
    task_ref: str | None
    task_ref_state: TaskRefState
    requester_id: str | None
    driver_id: str | None
    """The driver ``run.created`` records for this run, not the exporting runtime's."""
    state: str | None
    reason_code: str | None
    unknown_fields: tuple[str, ...] = ()


class SourceFact(Record):
    """One recorded read: its evidence id and revision, never its data."""

    evidence_id: str
    contract_id: str | None
    revision: str | None
    label: ValueLabel = ValueLabel.PROVIDER_READ

    @classmethod
    def of(cls, fact: FactRef) -> SourceFact:
        return cls(
            evidence_id=fact.evidence_id, contract_id=fact.contract_id, revision=fact.revision
        )


class InputRequest(Record):
    """A request for input, by its event; the question text stays out (PR-28)."""

    event_id: str | None
    status: StageStatus


class Validation(Record):
    stages: tuple[Stage, ...]
    """Each validation the run recorded, in order."""
    open_findings: tuple[RuleRef, ...]
    """The non-``PASS`` findings of the latest validation that no later proposal superseded,
    by rule id, version and status. Their message is validator free text and their
    ``expected`` and ``observed`` values are read data; all stay out (PR-26)."""
    rules_evaluated: tuple[RuleRef, ...]
    """Every rule evaluated in this run (across every validation), latest status per rule
    version (research 03 CQ07)."""
    input_requests: tuple[InputRequest, ...]


class AlternativeRef(Record):
    proposal_digest: str
    reason_code: str
    line_digest: str
    """The digest of the model's one line, never the line."""


class RationaleRef(Record):
    """A proposal's rationale as stored (ADR 0033 §4, §6): the goal, evidence ids, rule ids
    and codes it names and the digest of each model-authored text, never the text. It is a
    model's claim the kernel checked, shown after the facts it names."""

    step_id: str | None
    """The plan step it belongs to; None for the proposal's or the plan's own."""
    goal_ref: str
    cited_evidence: tuple[str, ...]
    rules_considered: tuple[str, ...]
    alternatives: tuple[AlternativeRef, ...]
    summary_digest: str
    label: ValueLabel = ValueLabel.MODEL_AUTHORED


class ProposalRef(Record):
    """One proposed action: its facts, then its rationale (ADR 0033 §4) as evidence ids,
    rule ids and text digests; the arguments never appear."""

    action_id: str | None
    contract_id: str | None
    binding_id: str | None
    connection_id: str | None
    connection_version: int | None
    credential_version: str | None
    logical_operation_id: str | None
    plan_id: str | None
    step_index: int | None
    supersedes_action_id: str | None
    digest: str | None
    evidence_ids: tuple[str, ...] | None
    """The evidence ids of the facts the proposal was made on; None when not recorded."""
    state: str | None
    label: ValueLabel = ValueLabel.MODEL_PROPOSAL
    partial_fields: tuple[str, ...] = ()
    """Fields whose value is only what the events show and may be behind the row."""
    unknown_fields: tuple[str, ...] = ()
    rationales: tuple[RationaleRef, ...] = ()
    """Shown after the facts: the proposal's or plan's own rationale first, then each step's.
    Left out when empty, so a run without one explains as before Task 3e.3."""

    @model_serializer(mode="wrap")
    def _omit_no_rationale(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        if not self.rationales:
            data.pop("rationales", None)
        return data


class ApprovalRef(Record):
    approval_id: str | None
    action_id: str | None
    decision: str | None
    actor_id: str | None
    policy_version: str | None
    action_digest: str | None
    label: ValueLabel = ValueLabel.APPROVER_DECISION
    unknown_fields: tuple[str, ...] = ()


class ReceiptRef(Record):
    """A receipt: status and provider references; the provider's error text stays out."""

    action_id: str | None
    attempt: int | None
    status: str | None
    external_refs: tuple[str, ...] | None
    label: ValueLabel = ValueLabel.PROVIDER_RECEIPT
    unknown_fields: tuple[str, ...] = ()


class OutcomeRef(Record):
    """A verification stage, or a run's grounded end (ADR 0033 §6): its status, never the
    checked values. A grounded end has no action, event or step id."""

    action_id: str | None
    status: StageStatus
    event_id: str | None
    step_id: str | None
    label: ValueLabel


class Explanation(Record):
    completeness: Completeness
    run: RunHeader
    sources: tuple[SourceFact, ...]
    validation: Validation
    proposals: tuple[ProposalRef, ...]
    """In the order of their ``proposal.created``."""
    approvals: tuple[ApprovalRef, ...]
    receipts: tuple[ReceiptRef, ...]
    outcomes: tuple[OutcomeRef, ...]
