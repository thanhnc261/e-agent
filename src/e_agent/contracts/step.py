"""Step records: one kernel stage or driver turn of a run (ADR 0025, target §5.4)."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import Field

from .common import Record, UtcDatetime
from .evidence import EvidenceRef


class StepKind(StrEnum):
    DRIVER_TURN = "driver_turn"
    READ = "read"
    VALIDATE = "validate"
    APPROVAL_WAIT = "approval_wait"
    DISPATCH = "dispatch"
    VERIFY = "verify"
    RECONCILE = "reconcile"


class StepStatus(StrEnum):
    STARTED = "started"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    BLOCKED = "blocked"
    UNKNOWN = "unknown"
    SKIPPED = "skipped"


class StepUsage(Record):
    """Budget use attributed to one step."""

    model_tokens: int = Field(default=0, ge=0)
    provider_calls: int = Field(default=0, ge=0)
    active_seconds: float = Field(default=0, ge=0)


class StepRecord(Record):
    """Written in the same transaction as its run events; references, never raw payloads."""

    schema_version: Literal["step.v1"] = "step.v1"
    tenant_id: str
    run_id: str
    step_id: str
    sequence: int = Field(ge=0)
    """Monotonic per run."""
    kind: StepKind
    status: StepStatus
    parent_step_id: str | None = None
    """A repair links to the step it repairs."""
    action_id: str | None = None
    input_refs: tuple[EvidenceRef, ...] = ()
    output_ref: EvidenceRef | None = None
    finding_ids: tuple[str, ...] = ()
    usage: StepUsage = StepUsage()
    started_at: UtcDatetime
    finished_at: UtcDatetime | None = None
