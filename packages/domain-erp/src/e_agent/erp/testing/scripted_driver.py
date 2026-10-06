"""Scripted, deterministic driver (no model). Stands in for the Pydantic AI
driver until I04 so the kernel path can be tested end to end."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

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

from ..inventory import AVAILABILITY_READ
from ..procurement import CREATE_DRAFT_PO, DEMAND_READ, OFFERS_READ
from ..procurement.api import Offer
from ..procurement.normalizer import collect_facts

_READS = {"r-demand": DEMAND_READ, "r-stock": AVAILABILITY_READ, "r-offers": OFFERS_READ}


@dataclass
class ScriptedProcurementDriver:
    connection_id: str
    mode: str = "valid"  # valid | invalid-then-repair | always-invalid
    demand_ref: str = "demand:d-001"
    product_ref: str = "product:widget-a"
    driver_id: str = "scripted-procurement-driver"
    _proposed: dict[str, int] = field(default_factory=dict)

    async def advance(self, ctx: TaskContext, step_input: DriverInput) -> DriverStep:
        if step_input.action_result is not None:
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
        facts = collect_facts(
            (o.contract_id, o.data, o.evidence.evidence_id) for o in step_input.observations
        )
        required = facts.required_quantity
        if facts.demand is None or facts.offers is None or required is None:
            return FinalAnswer(text="Required facts are missing; no action proposed.")
        if required == 0:
            return FinalAnswer(text="No shortage: available stock covers demand. No order needed.")
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
