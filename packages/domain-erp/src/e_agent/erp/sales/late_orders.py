"""ERP-06: late sales orders as of an explicit date, verified by recomputation."""

from __future__ import annotations

from e_agent.contracts.action import ActionRecord
from e_agent.contracts.context import TaskContext
from e_agent.contracts.outcome import OutcomeReport
from e_agent.contracts.receipt import ExecutionReceipt
from e_agent.sdk.ports import ScopedReader

from ..common import check, report
from . import LATE_ORDERS_ANSWER, OPEN_ORDERS_READ
from .api import LateOrdersAnswer, OpenOrders

LATE_RULE_VERSION = "so-late-v1"  # late = promised_date < as_of and not fully delivered


def late_orders(orders: OpenOrders) -> list[str]:
    return sorted(
        o.order_ref
        for o in orders.orders
        if o.promised_date < orders.as_of and o.delivery_status != "delivered"
    )


class LateOrdersVerifier:
    verifier_id = "sales.late-orders-verifier"

    def supports(self, contract_id: str) -> bool:
        return contract_id == LATE_ORDERS_ANSWER

    async def verify(
        self,
        ctx: TaskContext,
        action: ActionRecord,
        receipt: ExecutionReceipt | None,
        reader: ScopedReader,
    ) -> OutcomeReport:
        answer = LateOrdersAnswer.model_validate(action.arguments)
        obs = await reader.read(OPEN_ORDERS_READ, {"as_of": answer.as_of.isoformat()})
        expected = late_orders(OpenOrders.model_validate(obs.data))
        checks = [
            check("as_of_matches_read", answer.as_of.isoformat(), str(obs.data.get("as_of"))),
            check("late_orders", expected, sorted(answer.late_order_refs)),
            check("no_duplicates", len(set(answer.late_order_refs)), len(answer.late_order_refs)),
        ]
        return report(
            ctx, action, self.verifier_id, checks, [obs.evidence.evidence_id], LATE_RULE_VERSION
        )
