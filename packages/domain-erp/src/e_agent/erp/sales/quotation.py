"""ERP-05: create one draft customer quotation (no confirmation, email or delivery)."""

from __future__ import annotations

from e_agent.contracts.action import ActionRecord
from e_agent.contracts.context import TaskContext
from e_agent.contracts.outcome import OutcomeReport
from e_agent.contracts.receipt import ExecutionReceipt
from e_agent.sdk.ports import ScopedReader, ValidationInput
from e_agent.sdk.validation import ResourceRef, Term, ValidationDataset
from pydantic import ValidationError

from ..common import PROPOSAL, DatasetWriter, check, num_check, ref_iri, report
from . import CREATE_DRAFT_QUOTATION, PRICING_READ, QUOTATION_READ
from .api import DraftQuotation, Pricing, QuotationView

SO = "https://e-agent.dev/ns/sales#"
QUOTATION_RULES = ("SQ-001", "SQ-002", "SQ-003", "SQ-004")
QUOTATION_SHAPES = ResourceRef(package="e_agent.erp.sales", path="shapes/quotation-shapes.ttl")
QUOTATION_BUNDLE = "sales-quotation-rules@0.1.0"


class QuotationDatasetBuilder:
    builder_id = "sales-quotation-dataset"

    def supports(self, contract_id: str) -> bool:
        return contract_id == CREATE_DRAFT_QUOTATION

    def build(self, ctx: TaskContext, item: ValidationInput) -> ValidationDataset:
        w = DatasetWriter(
            SO, CREATE_DRAFT_QUOTATION, QUOTATION_SHAPES, QUOTATION_BUNDLE, QUOTATION_RULES
        )
        try:
            q = DraftQuotation.model_validate(item.proposal.arguments)
        except ValidationError:
            return w.incomplete(["well-formed quotation arguments"])
        pricing = next(
            (
                p
                for p in (
                    Pricing.model_validate(o.data)
                    for o in item.observations
                    if o.contract_id == PRICING_READ and o.data
                )
                if p.customer_ref == q.customer_ref and p.product_ref == q.product_ref
            ),
            None,
        )
        if pricing is None:
            return w.incomplete(["customer and product pricing"])
        w.typed(PROPOSAL, "QuotationProposal")
        w.add(PROPOSAL, "quantity", Term.lit(q.quantity, "decimal"))
        w.add(PROPOSAL, "unit", Term.lit(q.unit))
        w.add(PROPOSAL, "currency", Term.lit(q.currency))
        w.add(PROPOSAL, "unitPrice", Term.lit(q.unit_price, "decimal"))
        w.add(PROPOSAL, "subtotal", Term.lit(q.subtotal, "decimal"))
        p = ref_iri("pricing", f"{pricing.customer_ref}|{pricing.product_ref}")
        w.add(PROPOSAL, "pricing", Term.iri(p))
        w.add(
            p, "customerActive", Term.lit("true" if pricing.customer_active else "false", "boolean")
        )
        w.add(
            p,
            "productSaleable",
            Term.lit("true" if pricing.product_saleable else "false", "boolean"),
        )
        w.add(p, "unit", Term.lit(pricing.unit))
        w.add(p, "currency", Term.lit(pricing.currency))
        w.add(p, "unitPrice", Term.lit(pricing.list_price, "decimal"))
        return w.dataset()


class DraftQuotationVerifier:
    verifier_id = "sales.draft-quotation-verifier"

    def supports(self, contract_id: str) -> bool:
        return contract_id == CREATE_DRAFT_QUOTATION

    async def verify(
        self,
        ctx: TaskContext,
        action: ActionRecord,
        receipt: ExecutionReceipt | None,
        reader: ScopedReader,
    ) -> OutcomeReport:
        if receipt is None:
            raise ValueError("quotations are verified against a receipt")
        want = DraftQuotation.model_validate(action.arguments)
        obs = await reader.read(QUOTATION_READ, {"operation_key": action.logical_operation_id})
        quotes = [QuotationView.model_validate(o) for o in obs.data.get("quotations", [])]
        checks = [check("exactly_one_quotation", 1, len(quotes))]
        if len(quotes) == 1:
            got = quotes[0]
            checks += [
                check("state_is_draft", "draft", got.state),
                check("not_sent", False, got.sent),
                check(
                    "external_ref_matches_receipt",
                    ",".join(receipt.external_refs),
                    got.external_ref,
                ),
                check("customer", want.customer_ref, got.customer_ref),
                check("product", want.product_ref, got.product_ref),
                check("unit", want.unit, got.unit),
                check("currency", want.currency, got.currency),
                num_check("quantity", want.quantity, got.quantity),
                num_check("unit_price", want.unit_price, got.unit_price),
                num_check("subtotal", want.subtotal, got.subtotal),
            ]
        return report(ctx, action, self.verifier_id, checks, [obs.evidence.evidence_id])
