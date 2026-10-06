"""Independent outcome verifier for draft purchase orders (MVP design §8 step 10).

It reads the provider state back through the host's scoped reader and compares
it with the approved arguments. It cannot write, approve or access the ledger.
"""

from __future__ import annotations

from decimal import Decimal

from e_agent.contracts.action import ActionRecord
from e_agent.contracts.common import utc_now
from e_agent.contracts.context import TaskContext
from e_agent.contracts.outcome import OutcomeCheck, OutcomeReport, OutcomeStatus
from e_agent.contracts.receipt import ExecutionReceipt
from e_agent.sdk.ports import ScopedReader

from . import CREATE_DRAFT_PO, PURCHASE_ORDER_READ
from .api import DraftPurchaseOrder, PurchaseOrderView


class DraftPurchaseOrderVerifier:
    verifier_id = "procurement.draft-po-verifier"
    version = "1"

    def supports(self, contract_id: str) -> bool:
        return contract_id == CREATE_DRAFT_PO

    async def verify(
        self,
        ctx: TaskContext,
        action: ActionRecord,
        receipt: ExecutionReceipt | None,
        reader: ScopedReader,
    ) -> OutcomeReport:
        if receipt is None:
            raise ValueError("draft purchase orders are verified against a receipt")
        expected = DraftPurchaseOrder.model_validate(action.arguments)
        obs = await reader.read(PURCHASE_ORDER_READ, {"operation_key": action.logical_operation_id})
        orders = [PurchaseOrderView.model_validate(o) for o in obs.data.get("orders", [])]
        checks = [
            OutcomeCheck(
                name="exactly_one_order",
                passed=len(orders) == 1,
                expected="1",
                observed=str(len(orders)),
            )
        ]
        if len(orders) == 1:
            po = orders[0]
            pairs = {
                "state_is_draft": ("draft", po.state),
                "product": (expected.product_ref, po.product_ref),
                "supplier": (expected.supplier_ref, po.supplier_ref),
                "unit": (expected.unit, po.unit),
                "currency": (expected.currency, po.currency),
                "external_ref_matches_receipt": (",".join(receipt.external_refs), po.external_ref),
            }
            for name, (want, got) in pairs.items():
                checks.append(
                    OutcomeCheck(name=name, passed=want == got, expected=want, observed=got)
                )
            for name, want_s, got_s in (
                ("quantity", expected.quantity, po.quantity),
                ("unit_price", expected.unit_price, po.unit_price),
                ("subtotal", expected.subtotal, po.subtotal),
            ):
                checks.append(
                    OutcomeCheck(
                        name=name,
                        passed=Decimal(want_s) == Decimal(got_s),
                        expected=want_s,
                        observed=got_s,
                    )
                )
        status = OutcomeStatus.VERIFIED if all(c.passed for c in checks) else OutcomeStatus.FAILED
        return OutcomeReport(
            run_id=ctx.run_id,
            action_id=action.action_id,
            status=status,
            checks=tuple(checks),
            verifier_id=self.verifier_id,
            verifier_version=self.version,
            observed_refs=(obs.evidence.evidence_id,),
            reported_at=utc_now(),
        )
