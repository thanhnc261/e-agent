"""Evidence references with provenance and completeness."""

from __future__ import annotations

from enum import StrEnum

from .common import Record, UtcDatetime


class Completeness(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    UNKNOWN = "unknown"


class EvidenceRef(Record):
    evidence_id: str
    tenant_id: str
    source: str
    locator: str
    revision: str | None
    observed_at: UtcDatetime
    scope: str
    completeness: Completeness = Completeness.COMPLETE
    environment: str = "fixture"
