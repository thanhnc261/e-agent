"""Approval records bound to an exact digest (ADR 0006)."""

from __future__ import annotations

from enum import StrEnum

from .common import Record, UtcDatetime


class ApprovalDecision(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"


class ApprovalRecord(Record):
    approval_id: str
    tenant_id: str
    run_id: str
    action_id: str
    action_digest: str
    actor_id: str
    decision: ApprovalDecision
    policy_version: str
    issued_at: UtcDatetime
    expires_at: UtcDatetime
