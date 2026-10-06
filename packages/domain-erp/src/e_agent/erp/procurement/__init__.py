"""Procurement bounded context."""

DEMAND_READ = "procurement.demand.read.v1"
OFFERS_READ = "procurement.offers.read.v1"
CREATE_DRAFT_PO = "procurement.purchase-order.create-draft.v1"
PURCHASE_ORDER_READ = "procurement.purchase-order.read.v1"
SHORTAGE_ANSWER = "procurement.shortage.answer.v1"
OFFER_RECOMMENDATION = "procurement.offer.recommend.v1"
DRAFT_RFQ_READ = "procurement.draft-rfq.read.v1"
AMEND_DRAFT_RFQ = "procurement.draft-rfq.amend.v1"
# Referenced by contract id only; procurement never imports the inventory module.
INVENTORY_AVAILABILITY_READ = "inventory.availability.read.v1"
