"""The scripted procurement driver emits citations and a rationale when offered (Task 3e.4).

With ``DriverInput.grounding`` not ``off`` an answer cites the read values it was computed
from and a draft PO carries a rationale naming the reads and the procedural rules; every
citation resolves against the observations it was given. With ``off`` it is today's.
"""

from __future__ import annotations

from typing import Any

import pytest
from e_agent.kernel.grounding import check_citations
from e_agent.plugins.erp.domain.testing.fixture_validator import RULE_INVENTORY
from e_agent.plugins.erp.domain.testing.scripted_driver import ScriptedProcurementDriver
from e_agent.sdk.ports import DriverInput, GroundingOffer, ProposeAction

from .test_scripted_driver_context import OBSERVATIONS, _ctx

EVIDENCE = tuple(o.evidence.evidence_id for o in OBSERVATIONS)


async def _proposal(kind: str, grounding: GroundingOffer) -> Any:
    driver = ScriptedProcurementDriver(connection_id="conn", task_kind=kind)
    step = await driver.advance(
        _ctx(), DriverInput(task=kind, observations=OBSERVATIONS, grounding=grounding)
    )
    assert isinstance(step, ProposeAction)
    return step.proposal


@pytest.mark.parametrize("kind", ["shortage", "recommend", "draft-po"])
async def test_off_proposals_are_todays(kind: str) -> None:
    proposal = await _proposal(kind, GroundingOffer.OFF)
    assert proposal.citations == () and proposal.rationale is None


@pytest.mark.parametrize(
    ("kind", "pointers"),
    [
        ("shortage", ["/quantity", "/available", "/inbound"]),
        ("recommend", ["/quantity", "/offers/0/unit_price"]),
    ],
)
async def test_answers_cite_resolving_values(kind: str, pointers: list[str]) -> None:
    for offer in (GroundingOffer.CITE, GroundingOffer.CITE_AND_ANSWER):
        proposal = await _proposal(kind, offer)
        assert [c.pointer for c in proposal.citations] == pointers
        assert check_citations(OBSERVATIONS, proposal.citations).grounded
        assert "citations" not in proposal.arguments
    print(f"{kind}: {len(pointers)} citations resolve")


async def test_draft_po_carries_a_resolving_rationale() -> None:
    proposal = await _proposal("draft-po", GroundingOffer.CITE)
    rationale = proposal.rationale
    assert rationale is not None and proposal.citations == ()
    assert rationale.goal_ref == "run"
    assert rationale.cited_evidence == EVIDENCE
    assert set(rationale.rules_considered) == set(RULE_INVENTORY)
    assert "rationale" not in proposal.arguments
