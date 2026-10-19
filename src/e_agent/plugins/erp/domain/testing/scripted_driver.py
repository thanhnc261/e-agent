"""Scripted, deterministic driver (no model). Stands in for the Pydantic AI
driver until I04 so the kernel path can be tested end to end.

Given a context pack (``DriverInput.context``, ADR 0032), it reads its facts from the pack's
rendered observations, as a model would: a left-out observation is missing, and a rendering
the facts cannot be read from (masked or cut) counts as missing too."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from e_agent.contracts.common import format_decimal
from e_agent.contracts.context import TaskContext
from e_agent.contracts.plan import ActionProposal
from e_agent.sdk.ports import (
    DriverInput,
    DriverStep,
    FinalAnswer,
    ProposeAction,
    ReadRequest,
    RequestReads,
)
from pydantic import ValidationError

from ..inventory import AVAILABILITY_READ
from ..procurement import (
    CREATE_DRAFT_PO,
    DEMAND_READ,
    OFFER_RECOMMENDATION,
    OFFERS_READ,
    SHORTAGE_ANSWER,
)
from ..procurement.answers import eligible_offers
from ..procurement.api import Offer
from ..procurement.normalizer import collect_facts

_READS = {"r-demand": DEMAND_READ, "r-stock": AVAILABILITY_READ, "r-offers": OFFERS_READ}


@dataclass
class ScriptedProcurementDriver:
    connection_id: str
    mode: str = "valid"  # valid | invalid-then-repair | always-invalid | wrong-answer-then-correct
    task_kind: str = "draft-po"  # draft-po | shortage | recommend
    demand_ref: str = "demand:d-001"
    product_ref: str = "product:widget-a"
    driver_id: str = "scripted-procurement-driver"
    _proposed: dict[str, int] = field(default_factory=dict)

    async def advance(self, ctx: TaskContext, step_input: DriverInput) -> DriverStep:
        if step_input.action_result is not None:
            if self.task_kind != "draft-po" or not step_input.action_result.get("external_refs"):
                return FinalAnswer(text="Answer verified by the host.")
            refs = ", ".join(step_input.action_result.get("external_refs", []))
            return FinalAnswer(text=f"Created and verified draft purchase order {refs}.")
        if not step_input.observations:
            return RequestReads(
                reads=tuple(
                    ReadRequest(
                        request_id=rid,
                        contract_id=cid,
                        connection_id=self.connection_id,
                        arguments={"product_ref": self.product_ref, "demand_ref": self.demand_ref},
                    )
                    for rid, cid in _READS.items()
                )
            )
        try:
            facts = collect_facts(_observed(step_input))
            required = facts.required_quantity
        except (ValidationError, KeyError, ArithmeticError):
            if step_input.context is None:
                raise
            # a rendering the facts cannot be read from (masked or cut) is a missing fact
            return FinalAnswer(text="Required facts are missing; no action proposed.")
        if facts.demand is None or facts.offers is None or required is None:
            return FinalAnswer(text="Required facts are missing; no action proposed.")
        if self.task_kind != "draft-po":
            return self._answer(ctx, facts, required, bool(step_input.findings))
        if required == 0:
            return self._answer(ctx, facts, required, bool(step_input.findings))
        attempt = self._proposed.get(ctx.run_id, 0)
        self._proposed[ctx.run_id] = attempt + 1
        bad_first = self.mode == "always-invalid" or (
            self.mode == "invalid-then-repair" and attempt == 0
        )
        offers = sorted(facts.offers.offers, key=lambda o: Decimal(o.unit_price))
        offer: Offer = (
            next(o for o in offers if not o.approved)
            if bad_first
            else next(o for o in offers if o.approved)
        )
        subtotal = format_decimal(required * Decimal(offer.unit_price))
        return ProposeAction(
            proposal=ActionProposal(
                contract_id=CREATE_DRAFT_PO,
                connection_id=self.connection_id,
                arguments={
                    "demand_ref": facts.demand.demand_ref,
                    "product_ref": facts.demand.product_ref,
                    "supplier_ref": offer.supplier_ref,
                    "offer_ref": offer.offer_ref,
                    "quantity": format_decimal(required),
                    "unit": offer.unit,
                    "currency": offer.currency,
                    "unit_price": offer.unit_price,
                    "subtotal": subtotal,
                    "requested_date": facts.demand.requested_date.isoformat(),
                },
                expected_effects=("one draft purchase order",),
            )
        )

    def _answer(self, ctx: TaskContext, facts: Any, required: Decimal, retry: bool) -> DriverStep:
        wrong = self.mode == "wrong-answer-then-correct" and not retry
        demand = facts.demand
        if self.task_kind == "shortage" or (self.task_kind == "draft-po" and required == 0):
            stock = facts.available if facts.available is not None else Decimal(0)
            return ProposeAction(
                proposal=ActionProposal(
                    contract_id=SHORTAGE_ANSWER,
                    connection_id=self.connection_id,
                    arguments={
                        "demand_ref": demand.demand_ref,
                        "product_ref": demand.product_ref,
                        "demand_quantity": demand.quantity,
                        "available": format_decimal(stock),
                        "inbound": format_decimal(facts.inbound or Decimal(0)),
                        "shortage": format_decimal(required + (1 if wrong else 0)),
                    },
                )
            )
        eligible = eligible_offers(demand, facts.offers, required) if required > 0 else []
        pick = facts.offers.offers[-1] if wrong else (eligible[0] if eligible else None)
        return ProposeAction(
            proposal=ActionProposal(
                contract_id=OFFER_RECOMMENDATION,
                connection_id=self.connection_id,
                arguments={
                    "demand_ref": demand.demand_ref,
                    "product_ref": demand.product_ref,
                    "offer_ref": pick.offer_ref if pick else None,
                    "supplier_ref": pick.supplier_ref if pick else None,
                    "unit_price": pick.unit_price if pick else None,
                    "explanation": "cheapest approved offer within date and budget",
                },
            )
        )


def _observed(step_input: DriverInput) -> Iterable[tuple[str, Mapping[str, Any], str]]:
    """(contract id, data, evidence id) of what the driver may see: the pack's renderings
    when there is a pack, without the observations it left out; else the observations."""
    if step_input.context is None:
        return [(o.contract_id, o.data, o.evidence.evidence_id) for o in step_input.observations]
    contracts = {o.evidence.evidence_id: o.contract_id for o in step_input.observations}
    return [
        (contracts[r.evidence.evidence_id], r.data, r.evidence.evidence_id)
        for r in step_input.context.observations
        if r.evidence.evidence_id in contracts and not (r.truncated and set(r.data) == {"omitted"})
    ]
