"""Execution receipts. COMMITTED means provider-confirmed, not business-verified."""

from __future__ import annotations

from enum import StrEnum

from .common import Record, UtcDatetime


class ReceiptStatus(StrEnum):
    COMMITTED = "COMMITTED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


class ExecutionReceipt(Record):
    action_id: str
    attempt: int
    status: ReceiptStatus
    external_refs: tuple[str, ...] = ()
    provider_correlation: str | None = None
    sanitized_error: str | None = None
    started_at: UtcDatetime
    finished_at: UtcDatetime
