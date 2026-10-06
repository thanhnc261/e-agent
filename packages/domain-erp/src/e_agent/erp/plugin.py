"""Plugin factory. Contributes capability definitions and the outcome verifier.

Validation engines and provider executors are adapters, not part of this pack.
"""

from __future__ import annotations

import json
from importlib.resources import files

from e_agent.sdk import MANIFEST_FILENAME
from e_agent.sdk.manifest import PluginManifest
from e_agent.sdk.ports import PluginContribution, PluginServices

from .inventory.api import AvailabilityQuery
from .procurement.api import DemandQuery, DraftPurchaseOrder, OfferQuery, PurchaseOrderQuery
from .procurement.validation import ProcurementDatasetBuilder
from .procurement.verifier import DraftPurchaseOrderVerifier

INPUT_SCHEMAS = {
    "inventory.AvailabilityQuery.v1": AvailabilityQuery.model_json_schema(),
    "procurement.DemandQuery.v1": DemandQuery.model_json_schema(),
    "procurement.OfferQuery.v1": OfferQuery.model_json_schema(),
    "procurement.DraftPurchaseOrder.v1": DraftPurchaseOrder.model_json_schema(),
    "procurement.PurchaseOrderQuery.v1": PurchaseOrderQuery.model_json_schema(),
}

GUIDANCE = (
    "Procurement: read the demand, current stock and supplier offers first. "
    "The quantity to order is demand minus available minus inbound stock (never negative). "
    "If nothing is needed, say so and do not propose an order. Otherwise propose one draft "
    "purchase order from an approved offer that delivers by the requested date and stays "
    "within budget; subtotal = quantity x unit price. Write all quantities and amounts as "
    "decimal strings. A host rule engine validates every proposal; if it is blocked, read "
    "the findings and propose a corrected order or explain why none is possible."
)


def load_manifest() -> PluginManifest:
    text = files(__package__).joinpath(MANIFEST_FILENAME).read_text("utf-8")
    return PluginManifest.model_validate(json.loads(text))


def create_plugin(services: PluginServices) -> PluginContribution:
    manifest = load_manifest()
    return PluginContribution(
        capabilities=manifest.provides_capabilities,
        verifiers=(DraftPurchaseOrderVerifier(),),
        dataset_builders=(ProcurementDatasetBuilder(),),
        input_schemas=INPUT_SCHEMAS,
        agent_guidance=GUIDANCE,
    )
