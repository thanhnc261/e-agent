"""Synthetic procurement scenarios (MVP design §2)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass
class FixtureOffer:
    offer_ref: str
    supplier_ref: str
    unit_price: str
    approved: bool
    delivery_date: date


@dataclass
class FixtureScenario:
    name: str
    demand_quantity: str = "12"
    available: str = "5"
    inbound: str = "0"
    requested_date: date = date(2026, 10, 20)
    budget: str = "1000"
    currency: str = "VND"
    unit: str = "Units"
    product_ref: str = "product:widget-a"
    demand_ref: str = "demand:d-001"
    offers: list[FixtureOffer] = field(
        default_factory=lambda: [
            FixtureOffer("offer:a", "supplier:approved-co", "100", True, date(2026, 10, 15)),
            FixtureOffer("offer:b", "supplier:unvetted-co", "80", False, date(2026, 10, 14)),
        ]
    )


SCENARIOS: dict[str, FixtureScenario] = {
    "valid": FixtureScenario("valid"),
    "zero-shortage": FixtureScenario("zero-shortage", available="12"),
    "over-budget": FixtureScenario("over-budget", budget="500"),
}
