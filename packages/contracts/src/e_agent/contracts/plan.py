"""Model proposals. A proposal is never an approval or an executed action."""

from __future__ import annotations

from typing import Any

from .common import Record


class ActionProposal(Record):
    """One proposed capability invocation, payload validated by the capability schema."""

    contract_id: str
    connection_id: str
    arguments: dict[str, Any]
    expected_effects: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
