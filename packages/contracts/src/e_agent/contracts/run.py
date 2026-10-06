"""Runs and run states (MVP design §7)."""

from __future__ import annotations

from enum import StrEnum

from .common import Record, UtcDatetime


class RunState(StrEnum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    WAITING_INPUT = "WAITING_INPUT"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    VERIFYING = "VERIFYING"
    NEEDS_RECONCILIATION = "NEEDS_RECONCILIATION"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


TERMINAL_RUN_STATES = frozenset({RunState.SUCCEEDED, RunState.FAILED, RunState.CANCELLED})


class RunRecord(Record):
    run_id: str
    tenant_id: str
    requester_id: str
    task: str
    state: RunState
    revision: int
    logical_operation_id: str
    created_at: UtcDatetime
    reason: str | None = None
