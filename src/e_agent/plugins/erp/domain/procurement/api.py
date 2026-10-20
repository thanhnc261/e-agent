"""Public procurement DTOs (portable; amounts and quantities are decimal strings)."""

from __future__ import annotations

from datetime import date

from e_agent.contracts.common import DecimalStr, Record
from pydantic import ConfigDict, Field

_REFERENCE_DESCRIPTION = (
    "Opaque resource identifier; copy the complete exact reference, including its prefix, "
    "from authorized read data or user input."
)


class DemandQuery(Record):
    """Read one procurement demand (quantity, unit, requested date, budget)."""

    demand_ref: str = Field(description=_REFERENCE_DESCRIPTION)


class OpenDemandsQuery(Record):
    """List open procurement demands; takes no arguments."""


class OfferQuery(Record):
    """Read supplier offers for a product, including approval status."""

    product_ref: str = Field(description=_REFERENCE_DESCRIPTION)


class PurchaseOrderQuery(Record):
    operation_key: str


class Demand(Record):
    demand_ref: str = Field(description=_REFERENCE_DESCRIPTION)
    product_ref: str = Field(description=_REFERENCE_DESCRIPTION)
    quantity: DecimalStr
    unit: str
    requested_date: date
    budget: DecimalStr
    currency: str


class OpenDemand(Record):
    demand_ref: str = Field(description=_REFERENCE_DESCRIPTION)
    product_ref: str = Field(description=_REFERENCE_DESCRIPTION)
    product_name: str
    quantity: DecimalStr
    unit: str
    requested_date: date


class OpenDemands(Record):
    demands: tuple[OpenDemand, ...]
    complete: bool


class Offer(Record):
    offer_ref: str = Field(description=_REFERENCE_DESCRIPTION)
    supplier_ref: str = Field(description=_REFERENCE_DESCRIPTION)
    product_ref: str = Field(description=_REFERENCE_DESCRIPTION)
    unit_price: DecimalStr
    currency: str
    unit: str
    approved: bool
    delivery_date: date


class Offers(Record):
    product_ref: str = Field(description=_REFERENCE_DESCRIPTION)
    offers: tuple[Offer, ...]


class DraftPurchaseOrder(Record):
    """Arguments of procurement.purchase-order.create-draft.v1."""

    demand_ref: str = Field(description=_REFERENCE_DESCRIPTION)
    product_ref: str = Field(description=_REFERENCE_DESCRIPTION)
    supplier_ref: str = Field(description=_REFERENCE_DESCRIPTION)
    offer_ref: str = Field(description=_REFERENCE_DESCRIPTION)
    quantity: DecimalStr
    unit: str
    currency: str
    unit_price: DecimalStr
    subtotal: DecimalStr
    requested_date: date


class ShortageAnswer(Record):
    """ERP-01 answer: availability for a demand and the resulting shortage."""

    demand_ref: str = Field(description=_REFERENCE_DESCRIPTION)
    product_ref: str = Field(description=_REFERENCE_DESCRIPTION)
    demand_quantity: DecimalStr
    available: DecimalStr
    inbound: DecimalStr
    shortage: DecimalStr


class OfferRecommendation(Record):
    """ERP-02 answer: the eligible offer to use, or none (offer_ref null)."""

    demand_ref: str = Field(description=_REFERENCE_DESCRIPTION)
    product_ref: str = Field(description=_REFERENCE_DESCRIPTION)
    offer_ref: str | None = Field(description=_REFERENCE_DESCRIPTION)
    supplier_ref: str | None = Field(description=_REFERENCE_DESCRIPTION)
    unit_price: DecimalStr | None
    explanation: str


class DraftRfqQuery(Record):
    """Read one draft request for quotation (draft purchase order) by reference."""

    purchase_order_ref: str = Field(description=_REFERENCE_DESCRIPTION)


class DraftRfq(Record):
    """Current values of a draft RFQ; ``revision`` is its optimistic version."""

    purchase_order_ref: str = Field(description=_REFERENCE_DESCRIPTION)
    external_ref: str = Field(description=_REFERENCE_DESCRIPTION)
    state: str
    revision: str
    supplier_ref: str = Field(description=_REFERENCE_DESCRIPTION)
    product_ref: str = Field(description=_REFERENCE_DESCRIPTION)
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

    model_config = ConfigDict(
        json_schema_extra={"x-presentation": {"baseline_reference": "purchase_order_ref"}}
    )

    purchase_order_ref: str = Field(description=_REFERENCE_DESCRIPTION)
    expected_revision: str
    quantity: DecimalStr
    requested_date: date


class PurchaseOrderView(Record):
    external_ref: str = Field(description=_REFERENCE_DESCRIPTION)
    operation_key: str
    state: str
    purchase_order_ref: str | None = None
    requested_date: date | None = None
    line_count: int | None = None
    product_ref: str = Field(description=_REFERENCE_DESCRIPTION)
    supplier_ref: str = Field(description=_REFERENCE_DESCRIPTION)
    quantity: DecimalStr
    unit: str
    currency: str
    unit_price: DecimalStr
    subtotal: DecimalStr


class PurchaseOrders(Record):
    """Purchase orders read back by host operation key (verification read-back)."""

    orders: tuple[PurchaseOrderView, ...]
