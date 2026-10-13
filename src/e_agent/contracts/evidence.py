"""Evidence references with provenance and completeness."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

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


class ApprovedFact(Record):
    """Host-retained, authorized facts bound to the action's input evidence.

    Domain verifiers interpret the opaque data through their public DTOs.
    These records are captured by the host, never accepted from model output.
    """

    contract_id: str
    data: dict[str, Any]
    evidence: EvidenceRef
