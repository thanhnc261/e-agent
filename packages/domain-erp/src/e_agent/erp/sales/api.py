"""Public sales DTOs (portable; amounts and quantities are decimal strings)."""

from __future__ import annotations

from datetime import date
from typing import Literal

from e_agent.contracts.common import DecimalStr, Record


class PricingQuery(Record):
    """Read whether a customer may be quoted and the list price of a product."""

    customer_ref: str
    product_ref: str


class Pricing(Record):
    customer_ref: str
    customer_name: str
    customer_active: bool
    product_ref: str
    product_saleable: bool
    list_price: DecimalStr
    currency: str
    unit: str


class DraftQuotation(Record):
    """ERP-05 arguments: one draft quotation with one line; never confirmed or sent."""

    customer_ref: str
    product_ref: str
    quantity: DecimalStr
    unit: str
    unit_price: DecimalStr
    currency: str
    subtotal: DecimalStr


class QuotationQuery(Record):
    operation_key: str


class QuotationView(Record):
    external_ref: str
    operation_key: str
    state: str
    customer_ref: str
    product_ref: str
    quantity: DecimalStr
    unit: str
    unit_price: DecimalStr
    currency: str
    subtotal: DecimalStr
    sent: bool


DeliveryStatus = Literal["pending", "partial", "delivered"]


class OpenOrdersQuery(Record):
    """Read confirmed sales orders with their promised date and delivery status."""

    as_of: date


class OpenOrder(Record):
    order_ref: str
    external_ref: str
    customer_ref: str
    promised_date: date
    delivery_status: DeliveryStatus


class OpenOrders(Record):
    as_of: date
    orders: tuple[OpenOrder, ...]


class LateOrdersAnswer(Record):
    """ERP-06 answer: confirmed orders promised before ``as_of`` and not fully delivered."""

    as_of: date
    late_order_refs: tuple[str, ...]
    summary: str
