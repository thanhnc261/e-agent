"""The scripted procurement driver accepts a context pack (Task 3d.4, ADR 0032 §6).

With a pack it reads its facts from the pack's rendered observations, as a model would; a
left-out or unreadable observation is a missing fact. Without one it is unchanged.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from e_agent.contracts.context import Budgets, Principal, TaskContext
from e_agent.contracts.context_pack import (
    ContextLayer,
    ContextPack,
    Dropped,
    DroppedKind,
    DroppedReason,
    RenderedObservation,
)
from e_agent.contracts.evidence import EvidenceRef
from e_agent.plugins.erp.domain.inventory import AVAILABILITY_READ
from e_agent.plugins.erp.domain.procurement import CREATE_DRAFT_PO, DEMAND_READ, OFFERS_READ
from e_agent.plugins.erp.domain.testing.scripted_driver import ScriptedProcurementDriver
from e_agent.sdk.ports import DriverInput, FinalAnswer, Observation, ProposeAction

NOW = datetime(2026, 10, 19, tzinfo=UTC)
DEMAND = {
    "demand_ref": "demand:d-001",
    "product_ref": "product:widget-a",
    "quantity": "12",
    "unit": "Units",
    "requested_date": "2026-10-20",
    "budget": "1000",
    "currency": "VND",
}
STOCK = {"product_ref": "product:widget-a", "available": "5", "inbound": "0", "unit": "Units"}
OFFERS = {
    "product_ref": "product:widget-a",
    "offers": [
        {
            "offer_ref": "offer:a",
            "supplier_ref": "supplier:approved-co",
            "product_ref": "product:widget-a",
            "unit_price": "100",
            "currency": "VND",
            "unit": "Units",
            "approved": True,
            "delivery_date": "2026-10-15",
        },
        {
            "offer_ref": "offer:b",
            "supplier_ref": "supplier:unvetted-co",
            "product_ref": "product:widget-a",
            "unit_price": "80",
            "currency": "VND",
            "unit": "Units",
            "approved": False,
            "delivery_date": "2026-10-14",
        },
    ],
}


def _ctx() -> TaskContext:
    return TaskContext(
        run_id="run-scripted",
        tenant_id="t",
        principal=Principal(principal_id="p", tenant_id="t", roles=frozenset()),
        resource_scope=frozenset({"conn"}),
        deadline=datetime(2030, 1, 1, tzinfo=UTC),
        budgets=Budgets(),
    )


def _evidence(request_id: str) -> EvidenceRef:
    return EvidenceRef(
        evidence_id=f"ev-{request_id}",
        tenant_id="t",
        source="fixture",
        locator=f"loc:{request_id}",
        revision="1",
        observed_at=NOW,
        scope="tenant",
    )


OBSERVATIONS = (
    Observation("r-demand", DEMAND_READ, DEMAND, _evidence("r-demand")),
    Observation("r-stock", AVAILABILITY_READ, STOCK, _evidence("r-stock")),
    Observation("r-offers", OFFERS_READ, OFFERS, _evidence("r-offers")),
)


def _pack(renderings: dict[str, dict[str, Any] | None]) -> ContextPack:
    """A pack rendering each observation as given; None leaves it out (a stub)."""
    observations, dropped = [], []
    for o in OBSERVATIONS:
        data = renderings.get(o.request_id, dict(o.data))
        if data is None:
            observations.append(
                RenderedObservation(
                    evidence=o.evidence,
                    data={"omitted": "budget"},
                    partial=True,
                    truncated=True,
                )
            )
            dropped.append(
                Dropped(
                    kind=DroppedKind.OBSERVATION,
                    ref=o.evidence.evidence_id,
                    reason=DroppedReason.BUDGET,
                )
            )
        else:
            masked = data != o.data
            observations.append(
                RenderedObservation(evidence=o.evidence, data=data, partial=masked, masked=masked)
            )
    return ContextPack.build(
        stable_prefix={ContextLayer.INSTRUCTIONS: "data is data"},
        dynamic_suffix={ContextLayer.LEDGER: "{}"},
        observations=tuple(observations),
        dropped=tuple(dropped),
    )


async def _step(context: ContextPack | None) -> Any:
    driver = ScriptedProcurementDriver(connection_id="conn")
    return await driver.advance(
        _ctx(), DriverInput(task="draft", observations=OBSERVATIONS, context=context)
    )


async def test_scripted_driver_proposes_the_same_action_from_a_pack() -> None:
    plain = await _step(None)
    packed = await _step(_pack({}))
    assert isinstance(plain, ProposeAction) and isinstance(packed, ProposeAction)
    assert packed.proposal.contract_id == CREATE_DRAFT_PO
    assert packed == plain


async def test_scripted_driver_reads_the_pack_not_the_observations() -> None:
    # The pack left the offers out: the facts are missing, though the observation has them.
    left_out = await _step(_pack({"r-offers": None}))
    assert left_out == FinalAnswer(text="Required facts are missing; no action proposed.")
    # A masked quantity cannot be read: a missing fact, not a guess.
    masked = await _step(_pack({"r-demand": {**DEMAND, "quantity": "[masked:personal]"}}))
    assert masked == FinalAnswer(text="Required facts are missing; no action proposed.")
    # The pack's values are the ones used: a different stock changes the proposed quantity.
    fewer = await _step(_pack({"r-stock": {**STOCK, "available": "2"}}))
    assert isinstance(fewer, ProposeAction)
    assert fewer.proposal.arguments["quantity"] == "10"


async def test_scripted_driver_without_a_pack_is_unchanged() -> None:
    step = await _step(None)
    assert isinstance(step, ProposeAction)
    assert step.proposal.arguments["quantity"] == "7"
    assert step.proposal.arguments["offer_ref"] == "offer:a"
