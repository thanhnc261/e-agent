"""Validation findings from the authoritative rule inventory (ADR 0009)."""

from __future__ import annotations

from enum import StrEnum

from .common import Record


class ValidationStatus(StrEnum):
    PASS = "PASS"  # noqa: S105 - validation status, not a credential
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"
    ERROR = "ERROR"


class Finding(Record):
    rule_id: str
    rule_version: str
    status: ValidationStatus
    message: str
    expected: str | None = None
    observed: str | None = None
    evidence_ids: tuple[str, ...] = ()


class ValidationResult(Record):
    status: ValidationStatus
    findings: tuple[Finding, ...]
    rule_bundle_version: str
    validator_id: str

    @property
    def blocks_write(self) -> bool:
        return self.status is not ValidationStatus.PASS
