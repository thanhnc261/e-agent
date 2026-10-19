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
    """Every rule that validation evaluated, ``PASS`` included (research 03 CQ07)."""
    input_requests: tuple[InputRequest, ...]


class ProposalRef(Record):
    """One proposed action. The rationale of ADR 0033 §4 (Task 3e.3) joins this record as
    its evidence ids, rule ids and text digests; the arguments never do."""

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
    """A verification stage: its status, never the checked values."""

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
