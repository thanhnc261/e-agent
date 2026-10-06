"""Public procurement DTOs (portable; amounts and quantities are decimal strings)."""

from __future__ import annotations

from datetime import date

from e_agent.contracts.common import DecimalStr, Record


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


class PurchaseOrderView(Record):
    external_ref: str
    operation_key: str
    state: str
    product_ref: str
    supplier_ref: str
    quantity: DecimalStr
    unit: str
    currency: str
    unit_price: DecimalStr
    subtotal: DecimalStr
