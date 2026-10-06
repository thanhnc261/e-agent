"""Builds the backend-neutral validation dataset for draft purchase orders.

Statements use the procurement vocabulary only; no RDF library objects. The
SHACL assets referenced here are the authoritative rule implementation
(ADR 0009). Missing facts are stated explicitly (po:missingFact), never defaulted.
"""

from __future__ import annotations

from urllib.parse import quote

from e_agent.contracts.context import TaskContext
from e_agent.sdk.ports import ValidationInput
from e_agent.sdk.validation import ResourceRef, Statement, Term, ValidationDataset
from pydantic import ValidationError

from . import CREATE_DRAFT_PO
from .api import DraftPurchaseOrder
from .normalizer import collect_facts

PO = "https://e-agent.dev/ns/procurement#"
RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
RULE_BUNDLE_VERSION = "procurement-rules@0.1.0"
SHACL_RULES = ("PR-001", "PR-002", "PR-003", "PR-004", "PR-005")
SHAPES = (ResourceRef(package="e_agent.erp.procurement", path="shapes/procurement-shapes.ttl"),)
PROPOSAL = "urn:e-agent:proposal"


def ref_iri(kind: str, ref: str) -> str:
    return f"urn:e-agent:{kind}:{quote(ref, safe='')}"


class ProcurementDatasetBuilder:
    builder_id = "procurement-dataset"

    def supports(self, contract_id: str) -> bool:
        return contract_id == CREATE_DRAFT_PO

    def build(self, ctx: TaskContext, item: ValidationInput) -> ValidationDataset:
        st: list[Statement] = []

        def add(s: str, p: str, o: Term) -> None:
            st.append(Statement(subject=s, predicate=p, object=o))

        try:
            po = DraftPurchaseOrder.model_validate(item.proposal.arguments)
        except ValidationError:
            return self._incomplete(["well-formed proposal arguments"])

        facts = collect_facts(
            (o.contract_id, o.data, o.evidence.evidence_id) for o in item.observations
        )
        missing = [
            name
            for name, value in (
                ("demand", facts.demand),
                ("offers", facts.offers),
                ("stock for shortage", facts.required_quantity),
            )
            if value is None
        ]
        if missing:
            return self._incomplete(missing)
        if facts.demand is None or facts.offers is None:  # narrowed by `missing` above
            return self._incomplete(["demand or offers"])

        add(PROPOSAL, RDF_TYPE, Term.iri(PO + "DraftPurchaseOrderProposal"))
        add(PROPOSAL, PO + "quantity", Term.lit(po.quantity, "decimal"))
        add(
            PROPOSAL, PO + "requiredQuantity", Term.lit(str(facts.required_quantity_str), "decimal")
        )
        add(PROPOSAL, PO + "unit", Term.lit(po.unit))
        add(PROPOSAL, PO + "currency", Term.lit(po.currency))
        add(PROPOSAL, PO + "unitPrice", Term.lit(po.unit_price, "decimal"))
        add(PROPOSAL, PO + "subtotal", Term.lit(po.subtotal, "decimal"))
        add(PROPOSAL, PO + "product", Term.iri(ref_iri("product", po.product_ref)))
        add(PROPOSAL, PO + "supplier", Term.iri(ref_iri("supplier", po.supplier_ref)))

        demand = facts.demand
        if demand.demand_ref == po.demand_ref:
            d = ref_iri("demand", demand.demand_ref)
            add(PROPOSAL, PO + "demand", Term.iri(d))
            add(d, RDF_TYPE, Term.iri(PO + "Demand"))
            add(d, PO + "product", Term.iri(ref_iri("product", demand.product_ref)))
            add(d, PO + "unit", Term.lit(demand.unit))
            add(d, PO + "currency", Term.lit(demand.currency))
            add(d, PO + "budget", Term.lit(demand.budget, "decimal"))
            add(d, PO + "requestedDate", Term.lit(demand.requested_date.isoformat(), "date"))

        offer = next((o for o in facts.offers.offers if o.offer_ref == po.offer_ref), None)
        if offer is not None:
            o_iri = ref_iri("offer", offer.offer_ref)
            add(PROPOSAL, PO + "offer", Term.iri(o_iri))
            add(o_iri, RDF_TYPE, Term.iri(PO + "Offer"))
            add(o_iri, PO + "product", Term.iri(ref_iri("product", offer.product_ref)))
            add(o_iri, PO + "supplier", Term.iri(ref_iri("supplier", offer.supplier_ref)))
            add(o_iri, PO + "approved", Term.lit("true" if offer.approved else "false", "boolean"))
            add(o_iri, PO + "unit", Term.lit(offer.unit))
            add(o_iri, PO + "currency", Term.lit(offer.currency))
            add(o_iri, PO + "unitPrice", Term.lit(offer.unit_price, "decimal"))
            add(o_iri, PO + "deliveryDate", Term.lit(offer.delivery_date.isoformat(), "date"))
        return self._dataset(st)

    def _incomplete(self, missing: list[str]) -> ValidationDataset:
        """Only the missing-fact rule is evaluated; nothing is defaulted."""
        st = [
            Statement(
                subject=PROPOSAL, predicate=RDF_TYPE, object=Term.iri(PO + "IncompleteProposal")
            )
        ]
        st += [
            Statement(subject=PROPOSAL, predicate=PO + "missingFact", object=Term.lit(m))
            for m in missing
        ]
        return self._dataset(st, complete=False)

    @staticmethod
    def _dataset(statements: list[Statement], *, complete: bool = True) -> ValidationDataset:
        return ValidationDataset(
            complete=complete,
            contract_id=CREATE_DRAFT_PO,
            statements=tuple(statements),
            shapes=SHAPES,
            rule_bundle_version=RULE_BUNDLE_VERSION,
            expected_rules=SHACL_RULES,
        )
