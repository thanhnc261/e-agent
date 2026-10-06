"""Plugin factory. Contributes capability definitions and the outcome verifier.

Validation engines and provider executors are adapters, not part of this pack.
"""

from __future__ import annotations

import json
from importlib.resources import files

from e_agent.sdk import MANIFEST_FILENAME
from e_agent.sdk.manifest import PluginManifest
from e_agent.sdk.ports import PluginContribution, PluginServices

from .crm.api import ContactQuery, CreateLead, LeadQuery, TeamsQuery
from .crm.lead import LeadDatasetBuilder, LeadVerifier
from .inventory.api import AvailabilityQuery
from .procurement.amend import AmendDatasetBuilder, AmendDraftRfqVerifier
from .procurement.answers import OfferRecommendationVerifier, ShortageAnswerVerifier
from .procurement.api import (
    AmendDraftRfq,
    DemandQuery,
    DraftPurchaseOrder,
    DraftRfqQuery,
    OfferQuery,
    OfferRecommendation,
    PurchaseOrderQuery,
    ShortageAnswer,
)
from .procurement.validation import ProcurementDatasetBuilder
from .procurement.verifier import DraftPurchaseOrderVerifier
from .receivables.api import OpenInvoicesQuery, OverdueInvoicesAnswer
from .receivables.overdue import OverdueInvoicesVerifier
from .sales.api import (
    DraftQuotation,
    LateOrdersAnswer,
    OpenOrdersQuery,
    PricingQuery,
    QuotationQuery,
)
from .sales.late_orders import LateOrdersVerifier
from .sales.quotation import DraftQuotationVerifier, QuotationDatasetBuilder

INPUT_SCHEMAS = {
    "inventory.AvailabilityQuery.v1": AvailabilityQuery.model_json_schema(),
    "procurement.DemandQuery.v1": DemandQuery.model_json_schema(),
    "procurement.OfferQuery.v1": OfferQuery.model_json_schema(),
    "procurement.DraftPurchaseOrder.v1": DraftPurchaseOrder.model_json_schema(),
    "procurement.PurchaseOrderQuery.v1": PurchaseOrderQuery.model_json_schema(),
    "procurement.ShortageAnswer.v1": ShortageAnswer.model_json_schema(),
    "procurement.OfferRecommendation.v1": OfferRecommendation.model_json_schema(),
    "procurement.DraftRfqQuery.v1": DraftRfqQuery.model_json_schema(),
    "procurement.AmendDraftRfq.v1": AmendDraftRfq.model_json_schema(),
    "sales.PricingQuery.v1": PricingQuery.model_json_schema(),
    "sales.DraftQuotation.v1": DraftQuotation.model_json_schema(),
    "sales.QuotationQuery.v1": QuotationQuery.model_json_schema(),
    "sales.OpenOrdersQuery.v1": OpenOrdersQuery.model_json_schema(),
    "sales.LateOrdersAnswer.v1": LateOrdersAnswer.model_json_schema(),
    "crm.ContactQuery.v1": ContactQuery.model_json_schema(),
    "crm.TeamsQuery.v1": TeamsQuery.model_json_schema(),
    "crm.CreateLead.v1": CreateLead.model_json_schema(),
    "crm.LeadQuery.v1": LeadQuery.model_json_schema(),
    "receivables.OpenInvoicesQuery.v1": OpenInvoicesQuery.model_json_schema(),
    "receivables.OverdueInvoicesAnswer.v1": OverdueInvoicesAnswer.model_json_schema(),
}

GUIDANCE = (
    "Procurement: read the demand, current stock and supplier offers first. "
    "The quantity to order is demand minus available minus inbound stock (never negative). "
    "If nothing is needed, say so and do not propose an order. Otherwise propose one draft "
    "purchase order from an approved offer that delivers by the requested date and stays "
    "within budget; subtotal = quantity x unit price. Write all quantities and amounts as "
    "decimal strings. A host rule engine validates every proposal; if it is blocked, read "
    "the findings and propose a corrected order or explain why none is possible. "
    "When asked only about availability or shortage, report it with the shortage answer "
    "tool; when asked which offer to use, report it with the offer recommendation tool "
    "(offer_ref null if no offer is eligible). Answers are verified by the host.\n"
    "Draft RFQ changes: read the RFQ first and send the revision you read; only quantity "
    "and requested date can change, and only while it is a draft.\n"
    "Quotations: read pricing for the customer and product; quote the list price in the "
    "listed unit and currency; subtotal = quantity x unit price. Never confirm or send.\n"
    "Leads: read the contact and the sales teams; the owner must be a member of the team; "
    "use a listed source or none.\n"
    "Late orders and overdue invoices: always state the as-of date you used, read with "
    "it, and report exactly the matching references (and totals per currency). These "
    "are read-only questions: never propose any change."
)


def load_manifest() -> PluginManifest:
    text = files(__package__).joinpath(MANIFEST_FILENAME).read_text("utf-8")
    return PluginManifest.model_validate(json.loads(text))


def create_plugin(services: PluginServices) -> PluginContribution:
    manifest = load_manifest()
    return PluginContribution(
        capabilities=manifest.provides_capabilities,
        verifiers=(
            DraftPurchaseOrderVerifier(),
            ShortageAnswerVerifier(),
            OfferRecommendationVerifier(),
            AmendDraftRfqVerifier(),
            DraftQuotationVerifier(),
            LateOrdersVerifier(),
            LeadVerifier(),
            OverdueInvoicesVerifier(),
        ),
        dataset_builders=(
            ProcurementDatasetBuilder(),
            AmendDatasetBuilder(),
            QuotationDatasetBuilder(),
            LeadDatasetBuilder(),
        ),
        input_schemas=INPUT_SCHEMAS,
        agent_guidance=GUIDANCE,
    )
