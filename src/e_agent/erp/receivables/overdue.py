"""ERP-08: overdue customer invoices, verified by recomputation from a fresh read."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from e_agent.contracts.action import ActionRecord
from e_agent.contracts.common import format_decimal
from e_agent.contracts.context import TaskContext
from e_agent.contracts.outcome import OutcomeReport
from e_agent.contracts.receipt import ExecutionReceipt
from e_agent.sdk.ports import ScopedReader

from ..common import check, report
from . import OPEN_INVOICES_READ, OVERDUE_INVOICES_ANSWER
from .api import CurrencyTotal, OpenInvoices, OverdueInvoicesAnswer

OVERDUE_RULE_VERSION = "ar-overdue-v1"  # overdue = due_date < as_of and residual > 0


def overdue(invoices: OpenInvoices) -> tuple[list[str], list[CurrencyTotal]]:
    refs: list[str] = []
    totals: dict[str, Decimal] = defaultdict(Decimal)
    for inv in invoices.invoices:
        if inv.due_date < invoices.as_of and Decimal(inv.residual) > 0:
            refs.append(inv.invoice_ref)
            totals[inv.currency] += Decimal(inv.residual)
    return sorted(refs), [
        CurrencyTotal(currency=c, total=format_decimal(t)) for c, t in sorted(totals.items())
    ]


class OverdueInvoicesVerifier:
    verifier_id = "receivables.overdue-invoices-verifier"

    def supports(self, contract_id: str) -> bool:
        return contract_id == OVERDUE_INVOICES_ANSWER

    async def verify(
        self,
        ctx: TaskContext,
        action: ActionRecord,
        receipt: ExecutionReceipt | None,
        reader: ScopedReader,
    ) -> OutcomeReport:
        answer = OverdueInvoicesAnswer.model_validate(action.arguments)
        obs = await reader.read(OPEN_INVOICES_READ, {"as_of": answer.as_of.isoformat()})
        refs, totals = overdue(OpenInvoices.model_validate(obs.data))
        given = {t.currency: Decimal(t.total) for t in answer.totals}
        checks = [
            check("as_of_matches_read", answer.as_of.isoformat(), str(obs.data.get("as_of"))),
            check("overdue_invoices", refs, sorted(answer.overdue_invoice_refs)),
            check(
                "totals_per_currency",
                {t.currency: format_decimal(Decimal(t.total)) for t in totals},
                {c: format_decimal(v) for c, v in sorted(given.items())},
            ),
        ]
        return report(
            ctx, action, self.verifier_id, checks, [obs.evidence.evidence_id], OVERDUE_RULE_VERSION
        )
