"""Domain normalizer: typed facts and derived values (ADR 0009 'normalizer-derived').

PR-002 derived fact: required = max(demand - available - inbound, 0).
The formula and its version are recorded in the rule inventory.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from e_agent.contracts.common import format_decimal

from . import DEMAND_READ, INVENTORY_AVAILABILITY_READ, OFFERS_READ
from .api import Demand, Offers

SHORTAGE_FORMULA_VERSION = "pr-002-v1"


@dataclass(frozen=True)
class ProcurementFacts:
    demand: Demand | None
    available: Decimal | None
    inbound: Decimal | None
    offers: Offers | None
    evidence_ids: tuple[str, ...]

    @property
    def required_quantity(self) -> Decimal | None:
        if self.demand is None or self.available is None or self.inbound is None:
            return None
        return max(Decimal(self.demand.quantity) - self.available - self.inbound, Decimal(0))

    @property
    def required_quantity_str(self) -> str | None:
        value = self.required_quantity
        return None if value is None else format_decimal(value)


def collect_facts(observations: Iterable[tuple[str, Mapping[str, Any], str]]) -> ProcurementFacts:
    """Build facts from (contract_id, data, evidence_id) triples; missing stays None."""
    demand = offers = None
    available = inbound = None
    evidence: list[str] = []
    for contract_id, data, evidence_id in observations:
        if contract_id == DEMAND_READ:
            demand = Demand.model_validate(data)
        elif contract_id == OFFERS_READ:
            offers = Offers.model_validate(data)
        elif contract_id == INVENTORY_AVAILABILITY_READ:
            available = Decimal(str(data["available"]))
            inbound = Decimal(str(data["inbound"]))
        else:
            continue
        evidence.append(evidence_id)
    return ProcurementFacts(demand, available, inbound, offers, tuple(sorted(evidence)))
