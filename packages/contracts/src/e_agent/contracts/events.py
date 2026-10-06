"""Durable run events (MVP design §4.1, ADR 0007)."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import Field

from .common import Record, UtcDatetime


class RunEventType(StrEnum):
    RUN_CREATED = "run.created"
    RUN_STATE_CHANGED = "run.state_changed"
    READ_RECORDED = "read.recorded"
    PROPOSAL_CREATED = "proposal.created"
    VALIDATION_COMPLETED = "validation.completed"
    APPROVAL_REQUESTED = "approval.requested"
    APPROVAL_DECIDED = "approval.decided"
    CONNECT_REQUIRED = "connect.required"
    INPUT_REQUESTED = "input.requested"
    INPUT_RECEIVED = "input.received"
    ACTION_RESERVED = "action.reserved"
    ACTION_DISPATCHING = "action.dispatching"
    ACTION_RECEIPT_RECORDED = "action.receipt_recorded"
    ACTION_UNKNOWN = "action.unknown"
    RECONCILIATION_COMPLETED = "reconciliation.completed"
    OUTCOME_REPORTED = "outcome.reported"
    MESSAGE_FINAL = "message.final"
    BUDGET_EXHAUSTED = "budget.exhausted"
    RUN_CANCEL_REQUESTED = "run.cancel_requested"
    RUN_TERMINAL = "run.terminal"


class RunEvent(Record):
    event_id: str
    schema_version: str = "1"
    tenant_id: str
    run_id: str
    sequence: int
    type: RunEventType
    occurred_at: UtcDatetime
    action_id: str | None = None
    correlation_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
