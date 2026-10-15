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
class FixtureRfq:
    purchase_order_ref: str = "rfq:po-100"
    external_ref: str = "PO/FIXTURE/RFQ-100"
    state: str = "draft"
    revision: str = "rev-1"
    supplier_ref: str = "supplier:approved-co"
    product_ref: str = "product:widget-a"
    quantity: str = "10"
    unit_price: str = "100"
    requested_date: date = date(2026, 10, 20)


def _orders() -> list[dict[str, str]]:
    # (ref, promised, status): so-1 and so-4 are late as of 2026-10-06
    rows = [
        ("so-1", "2026-10-01", "pending"),
        ("so-2", "2026-10-03", "delivered"),
        ("so-3", "2026-10-10", "partial"),
        ("so-4", "2026-09-30", "partial"),
    ]
    return [
        {
            "order_ref": f"order:{r}",
            "external_ref": f"S/FIXTURE/{r}",
            "customer_ref": "customer:acme",
            "promised_date": d,
            "delivery_status": st,
        }
        for r, d, st in rows
    ]


def _invoices() -> list[dict[str, str]]:
    rows = [
        ("inv-1", "2026-09-20", "500", "VND"),
        ("inv-2", "2026-10-20", "300", "VND"),
        ("inv-3", "2026-09-01", "0", "VND"),
        ("inv-4", "2026-09-25", "120.5", "USD"),
        ("inv-5", "2026-09-28", "250", "VND"),
    ]
    return [
        {
            "invoice_ref": f"invoice:{r}",
            "external_ref": f"INV/FIXTURE/{r}",
            "customer_ref": "customer:acme",
            "due_date": d,
            "residual": amt,
            "currency": cur,
        }
        for r, d, amt, cur in rows
    ]


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
    rfq: FixtureRfq = field(default_factory=FixtureRfq)
    customers: dict[str, bool] = field(
        default_factory=lambda: {"customer:acme": True, "customer:archived": False}
    )
    list_price: str = "150"
    product_saleable: bool = True
    as_of: date = date(2026, 10, 6)
    orders: list[dict[str, str]] = field(default_factory=_orders)
    contacts: dict[str, bool] = field(
        default_factory=lambda: {"contact:jane": True, "contact:old": False}
    )
    teams: dict[str, list[str]] = field(
        default_factory=lambda: {
            "team:direct": ["user:alice", "user:bob"],
            "team:partners": ["user:carol"],
        }
    )
    sources: list[str] = field(default_factory=lambda: ["source:website", "source:referral"])
    invoices: list[dict[str, str]] = field(default_factory=_invoices)


SCENARIOS: dict[str, FixtureScenario] = {
    "valid": FixtureScenario("valid"),
    "zero-shortage": FixtureScenario("zero-shortage", available="12"),
    "over-budget": FixtureScenario("over-budget", budget="500"),
    "rfq-confirmed": FixtureScenario("rfq-confirmed", rfq=FixtureRfq(state="purchase")),
    "unsaleable-product": FixtureScenario("unsaleable-product", product_saleable=False),
}
