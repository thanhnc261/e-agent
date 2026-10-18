"""Plugin factory. Contributes capability definitions, verifiers, task definitions
(with the presets projected from them) and the scripted driver.

Validation engines and provider executors are adapters, not part of this pack.
"""

from __future__ import annotations

import json
from importlib.resources import files

from e_agent.contracts.task import TaskDefinition
from e_agent.sdk import MANIFEST_FILENAME
from e_agent.sdk.manifest import PluginManifest
from e_agent.sdk.ports import (
    AgentDriver,
    DriverFactory,
    DriverRequest,
    PluginContribution,
    PluginServices,
    TaskPreset,
)

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
    OpenDemandsQuery,
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
    "procurement.OpenDemandsQuery.v1": OpenDemandsQuery.model_json_schema(),
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
    "Procurement: if the user names no demand reference, list open demands first "
    "and copy the exact demand_ref and product_ref from that result. "
    "Then read the demand, current stock and supplier offers. "
    "The quantity to order is demand minus available minus inbound stock (never negative). "
    "Copy complete resource references from read results, including their prefixes. "
    "For a request to create an order, use the purchase order proposal tool after reading. "
    "If nothing is needed, report the zero shortage with the shortage answer tool. "
    "Otherwise propose one draft "
    "purchase order from an approved offer that delivers by the requested date and stays "
    "within budget; subtotal = quantity x unit price. Write all quantities and amounts as "
    "decimal strings. A host rule engine validates every proposal; if it is blocked, read "
    "the findings and propose a corrected order. If no offer is eligible, use the "
    "offer recommendation tool with null offer and supplier and unit price, then explain why. "
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
    "are read-only questions: never propose any change. Use the late-orders answer tool "
    "for late orders and the overdue-invoices answer tool for overdue invoices, so the "
    "host independently verifies the structured result before your final explanation."
)

# One ref table for every preset, in the order overrides are applied, so an
# override that equals another ref's default chains the same way for every kind.
TASK_REFS = {
    "rfq_ref": "rfq:po-100",
    "customer_ref": "customer:acme",
    "product_ref": "product:widget-a",
    "contact_ref": "contact:jane",
    "team_ref": "team:direct",
    "owner_ref": "user:alice",
    "other_owner_ref": "user:carol",
    "source_ref": "source:website",
    "as_of": "2026-10-06",
    "demand_ref": "demand:d-001",
}
ASSISTANT_TASK = "assistant"
"""The general read-only definition for open questions (ADR 0028). It has no preset:
the scripted driver has no assistant scenario."""


def load_manifest() -> PluginManifest:
    text = files(__package__).joinpath(MANIFEST_FILENAME).read_text("utf-8")
    return PluginManifest.model_validate(json.loads(text))


def load_task_definitions(manifest: PluginManifest | None = None) -> tuple[TaskDefinition, ...]:
    """The task definitions the manifest declares, read from ``tasks/<task_id>.json``."""
    declared = (manifest or load_manifest()).provides_task_definitions
    root = files(__package__).joinpath("tasks")
    return tuple(
        TaskDefinition.model_validate(
            json.loads(root.joinpath(f"{task.task_id}.json").read_text("utf-8"))
        )
        for task in declared
    )


TASK_DEFINITIONS = load_task_definitions()
# One catalogue (Task 2c.2): each preset is its definition's kind, prompt and title (D8).
TASK_PRESETS = tuple(
    TaskPreset(
        kind=definition.task_id,
        prompt=definition.goal_template,
        default_refs=TASK_REFS,
        help=definition.title,
    )
    for definition in TASK_DEFINITIONS
    if definition.task_id != ASSISTANT_TASK
)


def scripted_driver(request: DriverRequest) -> AgentDriver:
    """The deterministic driver for fixture runs and live smoke tests (no model)."""
    # Imported here: the scripted driver reads the presets above, and a profile with
    # a model driver never imports it.
    from .testing.scripted_tasks import ScriptedErpDriver

    return ScriptedErpDriver(
        connection_id=request.connection_id,
        mode=request.mode,
        task_kind=request.task_kind,
        refs=request.refs,
    )


DRIVER_FACTORIES: dict[str, DriverFactory] = {"scripted": scripted_driver}


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
        task_presets=TASK_PRESETS,
        task_definitions=load_task_definitions(manifest),
        driver_factories=dict(DRIVER_FACTORIES),
    )
