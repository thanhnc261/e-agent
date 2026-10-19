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
    READ_REJECTED = "read.rejected"
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
    # A feature in `on` mode returned to the existing path before a write (ADR 0027).
    FEATURE_FALLBACK = "feature.fallback"
    # Execution IR (ADR 0025, target architecture §6.4.5, §6.4.6).
    IR_PLAN_COMPILED = "ir.plan_compiled"
    IR_SHADOW_FAILED = "ir.shadow_failed"
    IR_LINEAGE_RESOLVED = "ir.lineage_resolved"
    IR_STEP_VERIFIED = "ir.step_verified"
    # Context assembly (ADR 0032 §11): an acknowledgement turn skipped, with its code.
    CONTEXT_FAILED = "context.failed"
    # `context_assembler: shadow` (ADR 0032 §7, Task 3d.3): the pack built for a driver turn
    # compared with the same inputs unbounded, or the stage at which building it failed.
    CONTEXT_COMPARED = "context.compared"
    CONTEXT_SHADOW_FAILED = "context.shadow_failed"
    # `context_assembler: on` (Task 3d.5): the pack a driver turn was given, by digest and
    # counts, for ADR 0032 §13's record; it marks the turn as `context.compared` does.
    CONTEXT_ASSEMBLED = "context.assembled"


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
    actor: str | None = None
    """Who caused the event (ADR 0018). None on rows written before the field existed."""
    payload: dict[str, Any] = Field(default_factory=dict)
