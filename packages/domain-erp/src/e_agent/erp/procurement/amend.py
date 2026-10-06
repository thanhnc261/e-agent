"""ERP-04: amend quantity or requested date on a draft RFQ.

Validation (AM-001..AM-004) runs on the RFQ the agent read; the provider
enforces the same draft-only and revision preconditions atomically, and the
verifier reads the RFQ back by operation key.
"""

from __future__ import annotations

from decimal import Decimal

from e_agent.contracts.action import ActionRecord
from e_agent.contracts.context import TaskContext
from e_agent.contracts.outcome import OutcomeReport
from e_agent.contracts.receipt import ExecutionReceipt
from e_agent.sdk.ports import ScopedReader, ValidationInput
from e_agent.sdk.validation import ResourceRef, Term, ValidationDataset
from pydantic import ValidationError

from ..common import PROPOSAL, DatasetWriter, check, num_check, ref_iri, report
from . import AMEND_DRAFT_RFQ, DRAFT_RFQ_READ, PURCHASE_ORDER_READ
from .api import AmendDraftRfq, DraftRfq, PurchaseOrderView

PO = "https://e-agent.dev/ns/procurement#"
AMEND_RULES = ("AM-001", "AM-002", "AM-003", "AM-004")
AMEND_SHAPES = ResourceRef(package="e_agent.erp.procurement", path="shapes/amend-shapes.ttl")
AMEND_BUNDLE = "procurement-amend-rules@0.1.0"


class AmendDatasetBuilder:
    builder_id = "procurement-amend-dataset"

    def supports(self, contract_id: str) -> bool:
        return contract_id == AMEND_DRAFT_RFQ

    def build(self, ctx: TaskContext, item: ValidationInput) -> ValidationDataset:
        w = DatasetWriter(PO, AMEND_DRAFT_RFQ, AMEND_SHAPES, AMEND_BUNDLE, AMEND_RULES)
        try:
            amend = AmendDraftRfq.model_validate(item.proposal.arguments)
        except ValidationError:
            return w.incomplete(["well-formed amendment arguments"])
        observed = [
            DraftRfq.model_validate(o.data)
            for o in item.observations
            if o.contract_id == DRAFT_RFQ_READ and o.data
        ]
        target = next(
            (r for r in observed if r.purchase_order_ref == amend.purchase_order_ref), None
        )
        if target is None:
            return w.incomplete(["the RFQ being amended"])
        w.typed(PROPOSAL, "RfqAmendmentProposal")
        w.add(PROPOSAL, "quantity", Term.lit(amend.quantity, "decimal"))
        w.add(PROPOSAL, "requestedDate", Term.lit(amend.requested_date.isoformat(), "date"))
        w.add(PROPOSAL, "expectedRevision", Term.lit(amend.expected_revision))
        t = ref_iri("rfq", target.purchase_order_ref)
        w.add(PROPOSAL, "target", Term.iri(t))
        w.add(t, "state", Term.lit(target.state))
        w.add(t, "revision", Term.lit(target.revision))
        w.add(t, "quantity", Term.lit(target.quantity, "decimal"))
        w.add(t, "requestedDate", Term.lit(target.requested_date.isoformat(), "date"))
        return w.dataset()


class AmendDraftRfqVerifier:
    verifier_id = "procurement.amend-rfq-verifier"
    version = "1"

    def supports(self, contract_id: str) -> bool:
        return contract_id == AMEND_DRAFT_RFQ

    async def verify(
        self,
        ctx: TaskContext,
        action: ActionRecord,
        receipt: ExecutionReceipt | None,
        reader: ScopedReader,
    ) -> OutcomeReport:
        if receipt is None:
            raise ValueError("amendments are verified against a receipt")
        want = AmendDraftRfq.model_validate(action.arguments)
        obs = await reader.read(PURCHASE_ORDER_READ, {"operation_key": action.logical_operation_id})
        orders = [PurchaseOrderView.model_validate(o) for o in obs.data.get("orders", [])]
        checks = [check("exactly_one_order", 1, len(orders))]
        if len(orders) == 1:
            po = orders[0]
            checks += [
                check("same_rfq", want.purchase_order_ref, po.purchase_order_ref),
                check("still_draft", "draft", po.state),
                check(
                    "external_ref_matches_receipt", ",".join(receipt.external_refs), po.external_ref
                ),
                num_check("quantity", want.quantity, po.quantity),
                check("requested_date", want.requested_date, po.requested_date),
                num_check(
                    "subtotal_consistent",
                    Decimal(po.quantity) * Decimal(po.unit_price),
                    po.subtotal,
                ),
            ]
        return report(ctx, action, self.verifier_id, checks, [obs.evidence.evidence_id])
