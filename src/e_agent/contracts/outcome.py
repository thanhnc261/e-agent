"""Outcome reports produced only by the independent verifier."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import SerializerFunctionWrapHandler, model_serializer

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
    verified_values: dict[str, Any] | None = None
    """The values the verifier read back, as a JSON-mode mapping, when its read-back found
    the one record it checks; None otherwise. The only source a later plan step's lineage
    placeholder copies from (ADR 0025): never a receipt or model output. The kernel keeps
    them out of the ``outcome.reported`` event, so they never reach an export (PR-26), and
    stores them only in execution IR ``on``."""

    @model_serializer(mode="wrap")
    def _omit_unset_values(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        """Leave ``verified_values`` out when None, so a report without read-back values is
        stored exactly as before Task 2c.7."""
        data: dict[str, Any] = handler(self)
        if self.verified_values is None:
            data.pop("verified_values", None)
        return data
