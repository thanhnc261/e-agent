"""Public procurement DTOs (portable; amounts and quantities are decimal strings)."""

from __future__ import annotations

from datetime import date

from e_agent.contracts.common import DecimalStr, Record


class DemandQuery(Record):
    """Read one procurement demand (quantity, unit, requested date, budget)."""

    demand_ref: str


class OfferQuery(Record):
    """Read supplier offers for a product, including approval status."""

    product_ref: str


class PurchaseOrderQuery(Record):
    operation_key: str


class Demand(Record):
    demand_ref: str
    product_ref: str
    quantity: DecimalStr
    unit: str
    requested_date: date
    budget: DecimalStr
    currency: str


class Offer(Record):
    offer_ref: str
    supplier_ref: str
    product_ref: str
    unit_price: DecimalStr
    currency: str
    unit: str
    approved: bool
    delivery_date: date


class Offers(Record):
    product_ref: str
    offers: tuple[Offer, ...]


class DraftPurchaseOrder(Record):
    """Arguments of procurement.purchase-order.create-draft.v1."""

    demand_ref: str
    product_ref: str
    supplier_ref: str
    offer_ref: str
    quantity: DecimalStr
    unit: str
    currency: str
    unit_price: DecimalStr
    subtotal: DecimalStr
    requested_date: date


class ShortageAnswer(Record):
    """ERP-01 answer: availability for a demand and the resulting shortage."""

    demand_ref: str
    product_ref: str
    demand_quantity: DecimalStr
    available: DecimalStr
    inbound: DecimalStr
    shortage: DecimalStr


class OfferRecommendation(Record):
    """ERP-02 answer: the eligible offer to use, or none (offer_ref null)."""

    demand_ref: str
    product_ref: str
    offer_ref: str | None
    supplier_ref: str | None
    unit_price: DecimalStr | None
    explanation: str


class DraftRfqQuery(Record):
    """Read one draft request for quotation (draft purchase order) by reference."""

    purchase_order_ref: str


class DraftRfq(Record):
    """Current values of a draft RFQ; ``revision`` is its optimistic version."""

    purchase_order_ref: str
    external_ref: str
    state: str
    revision: str
    supplier_ref: str
    product_ref: str
    quantity: DecimalStr
    unit: str
    unit_price: DecimalStr
    currency: str
    requested_date: date


class AmendDraftRfq(Record):
    """ERP-04 arguments: change only quantity and/or requested date of a draft RFQ.

    ``expected_revision`` is the revision that was read; the provider rejects the
    change if the RFQ moved on since (optimistic concurrency).
    """

    purchase_order_ref: str
    expected_revision: str
    quantity: DecimalStr
    requested_date: date


class PurchaseOrderView(Record):
    external_ref: str
    operation_key: str
    state: str
    purchase_order_ref: str | None = None
    requested_date: date | None = None
    product_ref: str
    supplier_ref: str
    quantity: DecimalStr
    unit: str
    currency: str
    unit_price: DecimalStr
    subtotal: DecimalStr
