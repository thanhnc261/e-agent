"""Scripted, deterministic driver (no model). Stands in for the Pydantic AI
driver until I04 so the kernel path can be tested end to end.

Given a context pack (``DriverInput.context``, ADR 0032), it reads its facts from the pack's
rendered observations, as a model would: a left-out observation is missing, and a rendering
the facts cannot be read from (masked or cut) counts as missing too.

Grounding (ADR 0033 §5): when the kernel offers it (``DriverInput.grounding`` is not ``off``),
an answer cites the read values it was computed from, by evidence id and RFC 6901 pointer,
and a draft PO carries a rationale naming the reads and the procedural rules. With ``off``
the proposals are today's.

Driver conformance (Task 3f.1): it reads only tools in ``DriverInput.allowed_capabilities``
when the kernel sets it, and it keeps no state between turns: the repair of
``invalid-then-repair`` is the turn that carries findings, so a fresh instance (the kernel's
resume of a driver without ``snapshot``) returns what the original would."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from e_agent.contracts.common import format_decimal
from e_agent.contracts.context import TaskContext
from e_agent.contracts.grounding import Citation, ProposalRationale
from e_agent.contracts.plan import ActionProposal
from e_agent.sdk.ports import (
    DriverInput,
    DriverStep,
    FinalAnswer,
    GroundingOffer,
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
from .fixture_validator import RULE_INVENTORY

_READS = {"r-demand": DEMAND_READ, "r-stock": AVAILABILITY_READ, "r-offers": OFFERS_READ}
OUTSIDE_TOOL_SET = "The reads this task needs are outside the run's tool set; nothing proposed."


@dataclass
class ScriptedProcurementDriver:
    connection_id: str
    mode: str = "valid"  # valid | invalid-then-repair | always-invalid | wrong-answer-then-correct
    task_kind: str = "draft-po"  # draft-po | shortage | recommend
    demand_ref: str = "demand:d-001"
    product_ref: str = "product:widget-a"
    driver_id: str = "scripted-procurement-driver"

    async def advance(self, ctx: TaskContext, step_input: DriverInput) -> DriverStep:
        if step_input.action_result is not None:
            if self.task_kind != "draft-po" or not step_input.action_result.get("external_refs"):
                return FinalAnswer(text="Answer verified by the host.")
            refs = ", ".join(step_input.action_result.get("external_refs", []))
            return FinalAnswer(text=f"Created and verified draft purchase order {refs}.")
        if not step_input.observations:
            allowed = step_input.allowed_capabilities  # the run's tool set; None: every tool
            reads = tuple(
                ReadRequest(
                    request_id=rid,
                    contract_id=cid,
                    connection_id=self.connection_id,
                    arguments={"product_ref": self.product_ref, "demand_ref": self.demand_ref},
                )
                for rid, cid in _READS.items()
                if allowed is None or cid in allowed
            )
            if not reads:  # never an empty read request
                return FinalAnswer(text=OUTSIDE_TOOL_SET)
            return RequestReads(reads=reads)
        observed = list(_observed(step_input))
        grounded = step_input.grounding is not GroundingOffer.OFF
        try:
            facts = collect_facts(observed)
            required = facts.required_quantity
        except (ValidationError, KeyError, ArithmeticError):
            if step_input.context is None:
                raise
            # a rendering the facts cannot be read from (masked or cut) is a missing fact
            return FinalAnswer(text="Required facts are missing; no action proposed.")
        # the shortage needs no offers; a proposal that names one does
        needs_offers = self.task_kind == "recommend" or (
            self.task_kind == "draft-po" and required != 0
        )
        if facts.demand is None or required is None or (needs_offers and facts.offers is None):
            return FinalAnswer(text="Required facts are missing; no action proposed.")
        cites = _Cites(observed) if grounded else None
        if self.task_kind != "draft-po":
            return self._answer(ctx, facts, required, bool(step_input.findings), cites)
        if required == 0:
            return self._answer(ctx, facts, required, bool(step_input.findings), cites)
        assert facts.offers is not None
        # the repair is the turn that carries findings, so a fresh driver resumes alike
        bad_first = self.mode == "always-invalid" or (
            self.mode == "invalid-then-repair" and not step_input.findings
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
                rationale=None if cites is None else cites.rationale(offer.offer_ref),
            )
        )

    def _answer(
        self, ctx: TaskContext, facts: Any, required: Decimal, retry: bool, cites: _Cites | None
    ) -> DriverStep:
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
                    citations=()
                    if cites is None
                    else cites.of(
                        (DEMAND_READ, "/quantity"),
                        (AVAILABILITY_READ, "/available"),
                        (AVAILABILITY_READ, "/inbound"),
                    ),
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
                citations=() if cites is None else cites.offer(pick.offer_ref if pick else None),
            )
        )


class _Cites:
    """Citations and the rationale of the reads the driver saw, under the pointers it read
    them at: a value the rendering left out is not cited."""

    def __init__(self, observed: Iterable[tuple[str, Mapping[str, Any], str]]) -> None:
        self._reads = {contract: (data, evidence) for contract, data, evidence in observed}

    def of(self, *refs: tuple[str, str]) -> tuple[Citation, ...]:
        cited = []
        for contract, pointer in refs:
            data, evidence = self._reads.get(contract, ({}, ""))
            value = _at(data, pointer)
            if evidence and value is not _MISSING:
                cited.append(Citation(evidence_id=evidence, pointer=pointer, value=value))
        return tuple(cited)

    def offer(self, offer_ref: str | None) -> tuple[Citation, ...]:
        """The demand quantity, and the recommended offer's price when there is one."""
        refs = [(DEMAND_READ, "/quantity")]
        offers = self._reads.get(OFFERS_READ, ({}, ""))[0].get("offers")
        for index, offer in enumerate(offers if isinstance(offers, list) else []):
            if isinstance(offer, Mapping) and offer.get("offer_ref") == offer_ref:
                refs.append((OFFERS_READ, f"/offers/{index}/unit_price"))
        return self.of(*refs)

    def rationale(self, offer_ref: str) -> ProposalRationale:
        return ProposalRationale(
            goal_ref="run",
            cited_evidence=tuple(evidence for _, evidence in self._reads.values()),
            rules_considered=tuple(sorted(RULE_INVENTORY)),
            summary=f"Draft PO for the demand's shortage from offer {offer_ref}.",
        )


_MISSING = object()


def _at(data: Any, pointer: str) -> Any:
    """The value at a ``/key`` or ``/key/index/key`` pointer, or `_MISSING`."""
    for part in pointer.split("/")[1:]:
        if isinstance(data, Mapping) and part in data:
            data = data[part]
        elif isinstance(data, list) and part.isdigit() and int(part) < len(data):
            data = data[int(part)]
        else:
            return _MISSING
    return data


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
