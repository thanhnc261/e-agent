"""Outcome reports produced only by the independent verifier."""

from __future__ import annotations

from enum import StrEnum

from .common import Record, UtcDatetime


class OutcomeStatus(StrEnum):
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


class OutcomeCheck(Record):
    name: str
    passed: bool
    expected: str
    observed: str


class OutcomeReport(Record):
    run_id: str
    action_id: str | None
    status: OutcomeStatus
    checks: tuple[OutcomeCheck, ...]
    verifier_id: str
    verifier_version: str
    observed_refs: tuple[str, ...] = ()
    reported_at: UtcDatetime
