"""NON-AUTHORITATIVE fixture rule checker for the walking skeleton (I02).

It evaluates the inventory rules PR-001..PR-005 procedurally so the kernel's
validation path can be exercised before the SHACL adapter exists. It is wired
only in ``environment=fixture`` profiles and is replaced by the SHACL engine in
I03; it must never be enabled for live runs (ADR 0009, AGENTS.md).
"""

from __future__ import annotations

from decimal import Decimal

from e_agent.contracts.common import format_decimal
from e_agent.contracts.context import TaskContext
from e_agent.contracts.validation import Finding, ValidationResult, ValidationStatus
from e_agent.sdk.ports import ValidationInput
from pydantic import ValidationError

from ..procurement import CREATE_DRAFT_PO
from ..procurement.api import DraftPurchaseOrder
from ..procurement.normalizer import collect_facts

BUNDLE_VERSION = "procurement-rules@0.1.0+fixture"


def _f(
    rule: str, status: ValidationStatus, msg: str, exp: str | None = None, obs: str | None = None
) -> Finding:
    return Finding(
        rule_id=rule, rule_version="1", status=status, message=msg, expected=exp, observed=obs
    )


class FixtureRuleValidator:
    validator_id = "fixture-procedural-rules"

    def supports(self, contract_id: str) -> bool:
        return contract_id == CREATE_DRAFT_PO

    async def validate(self, ctx: TaskContext, item: ValidationInput) -> ValidationResult:
        findings: list[Finding] = []
        P, F, U = ValidationStatus.PASS, ValidationStatus.FAIL, ValidationStatus.UNKNOWN
        try:
            po = DraftPurchaseOrder.model_validate(item.proposal.arguments)
        except ValidationError:
            findings.append(_f("PR-001", F, "proposal arguments do not match the contract"))
            return self._result(findings)
        facts = collect_facts(
            (o.contract_id, o.data, o.evidence.evidence_id) for o in item.observations
        )
        if facts.demand is None or facts.offers is None or facts.required_quantity is None:
            findings.append(_f("PR-001", U, "required facts are missing"))
            return self._result(findings)
        offer = next((o for o in facts.offers.offers if o.offer_ref == po.offer_ref), None)
        resolved = (
            offer is not None
            and po.product_ref == facts.demand.product_ref
            and po.demand_ref == facts.demand.demand_ref
        )
        findings.append(_f("PR-001", P if resolved else F, "references resolve in scope"))
        required = facts.required_quantity_str
        findings.append(
            _f(
                "PR-002",
                P if Decimal(po.quantity) == facts.required_quantity else F,
                "quantity equals shortage",
                required,
                po.quantity,
            )
        )
        if offer is None:
            findings.append(_f("PR-003", F, "offer not found"))
            return self._result(findings)
        ok3 = offer.approved and offer.supplier_ref == po.supplier_ref
        findings.append(
            _f(
                "PR-003",
                P if ok3 else F,
                "offer approved and matches supplier",
                "approved",
                "approved" if offer.approved else "unapproved",
            )
        )
        subtotal = Decimal(po.quantity) * Decimal(offer.unit_price)
        ok4 = (
            Decimal(po.quantity) > 0
            and po.unit == facts.demand.unit == offer.unit
            and po.currency == facts.demand.currency == offer.currency
            and Decimal(po.unit_price) == Decimal(offer.unit_price)
            and Decimal(po.subtotal) == subtotal
            and subtotal <= Decimal(facts.demand.budget)
        )
        findings.append(
            _f(
                "PR-004",
                P if ok4 else F,
                "quantity/unit/currency/subtotal/budget",
                f"<= {facts.demand.budget}",
                format_decimal(subtotal),
            )
        )
        ok5 = offer.delivery_date <= facts.demand.requested_date
        findings.append(
            _f(
                "PR-005",
                P if ok5 else F,
                "delivery meets requested date",
                facts.demand.requested_date.isoformat(),
                offer.delivery_date.isoformat(),
            )
        )
        return self._result(findings)

    def _result(self, findings: list[Finding]) -> ValidationResult:
        statuses = {f.status for f in findings}
        status = (
            ValidationStatus.FAIL
            if ValidationStatus.FAIL in statuses
            else ValidationStatus.UNKNOWN
            if ValidationStatus.UNKNOWN in statuses
            else ValidationStatus.PASS
        )
        return ValidationResult(
            status=status,
            findings=tuple(findings),
            rule_bundle_version=BUNDLE_VERSION,
            validator_id=self.validator_id,
        )
