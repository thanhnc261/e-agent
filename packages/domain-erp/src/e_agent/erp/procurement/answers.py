"""Independent verifiers for structured procurement answers (ERP-01, ERP-02).

They never trust the model's numbers or the run's earlier observations: each
recomputes the expected answer from fresh reads through the host's scoped reader.
"""

from __future__ import annotations

from decimal import Decimal

from e_agent.contracts.action import ActionRecord
from e_agent.contracts.common import format_decimal, utc_now
from e_agent.contracts.context import TaskContext
from e_agent.contracts.outcome import OutcomeCheck, OutcomeReport, OutcomeStatus
from e_agent.contracts.receipt import ExecutionReceipt
from e_agent.sdk.ports import ScopedReader

from . import (
    DEMAND_READ,
    INVENTORY_AVAILABILITY_READ,
    OFFER_RECOMMENDATION,
    OFFERS_READ,
    SHORTAGE_ANSWER,
)
from .api import Demand, Offer, OfferRecommendation, Offers, ShortageAnswer


def _report(
    ctx: TaskContext,
    action: ActionRecord,
    verifier_id: str,
    checks: list[OutcomeCheck],
    refs: list[str],
) -> OutcomeReport:
    status = (
        OutcomeStatus.VERIFIED
        if checks and all(c.passed for c in checks)
        else (OutcomeStatus.FAILED)
    )
    return OutcomeReport(
        run_id=ctx.run_id,
        action_id=action.action_id,
        status=status,
        checks=tuple(checks),
        verifier_id=verifier_id,
        verifier_version="1",
        observed_refs=tuple(refs),
        reported_at=utc_now(),
    )


def _num_check(name: str, expected: Decimal, observed: str | None) -> OutcomeCheck:
    ok = observed is not None and Decimal(observed) == expected
    return OutcomeCheck(
        name=name, passed=ok, expected=format_decimal(expected), observed=str(observed)
    )


async def _facts(
    reader: ScopedReader, demand_ref: str, product_ref: str
) -> tuple[Demand, Decimal, Decimal, list[str]]:
    d_obs = await reader.read(DEMAND_READ, {"demand_ref": demand_ref})
    s_obs = await reader.read(INVENTORY_AVAILABILITY_READ, {"product_ref": product_ref})
    demand = Demand.model_validate(d_obs.data)
    return (
        demand,
        Decimal(str(s_obs.data["available"])),
        Decimal(str(s_obs.data["inbound"])),
        [d_obs.evidence.evidence_id, s_obs.evidence.evidence_id],
    )


class ShortageAnswerVerifier:
    verifier_id = "procurement.shortage-answer-verifier"

    def supports(self, contract_id: str) -> bool:
        return contract_id == SHORTAGE_ANSWER

    async def verify(
        self,
        ctx: TaskContext,
        action: ActionRecord,
        receipt: ExecutionReceipt | None,
        reader: ScopedReader,
    ) -> OutcomeReport:
        answer = ShortageAnswer.model_validate(action.arguments)
        demand, available, inbound, refs = await _facts(
            reader, answer.demand_ref, answer.product_ref
        )
        shortage = max(Decimal(demand.quantity) - available - inbound, Decimal(0))
        checks = [
            OutcomeCheck(
                name="product_matches_demand",
                passed=demand.product_ref == answer.product_ref,
                expected=demand.product_ref,
                observed=answer.product_ref,
            ),
            _num_check("demand_quantity", Decimal(demand.quantity), answer.demand_quantity),
            _num_check("available", available, answer.available),
            _num_check("inbound", inbound, answer.inbound),
            _num_check("shortage", shortage, answer.shortage),
        ]
        return _report(ctx, action, self.verifier_id, checks, refs)


def eligible_offers(demand: Demand, offers: Offers, shortage: Decimal) -> list[Offer]:
    """Offers that satisfy PR-003..PR-005 for the derived shortage (cheapest first)."""
    ok = [
        o
        for o in offers.offers
        if o.approved
        and o.delivery_date <= demand.requested_date
        and o.currency == demand.currency
        and o.unit == demand.unit
        and shortage * Decimal(o.unit_price) <= Decimal(demand.budget)
    ]
    return sorted(ok, key=lambda o: (Decimal(o.unit_price), o.delivery_date, o.offer_ref))


class OfferRecommendationVerifier:
    verifier_id = "procurement.offer-recommendation-verifier"

    def supports(self, contract_id: str) -> bool:
        return contract_id == OFFER_RECOMMENDATION

    async def verify(
        self,
        ctx: TaskContext,
        action: ActionRecord,
        receipt: ExecutionReceipt | None,
        reader: ScopedReader,
    ) -> OutcomeReport:
        answer = OfferRecommendation.model_validate(action.arguments)
        demand, available, inbound, refs = await _facts(
            reader, answer.demand_ref, answer.product_ref
        )
        o_obs = await reader.read(OFFERS_READ, {"product_ref": answer.product_ref})
        offers = Offers.model_validate(o_obs.data)
        shortage = max(Decimal(demand.quantity) - available - inbound, Decimal(0))
        eligible = eligible_offers(demand, offers, shortage) if shortage > 0 else []
        best = eligible[0] if eligible else None
        checks = [
            OutcomeCheck(
                name="recommended_offer",
                passed=answer.offer_ref == (best.offer_ref if best else None),
                expected=str(best.offer_ref if best else None),
                observed=str(answer.offer_ref),
            )
        ]
        if best is not None and answer.offer_ref == best.offer_ref:
            checks.append(
                OutcomeCheck(
                    name="supplier",
                    passed=answer.supplier_ref == best.supplier_ref,
                    expected=best.supplier_ref,
                    observed=str(answer.supplier_ref),
                )
            )
            checks.append(_num_check("unit_price", Decimal(best.unit_price), answer.unit_price))
        return _report(ctx, action, self.verifier_id, checks, [*refs, o_obs.evidence.evidence_id])
