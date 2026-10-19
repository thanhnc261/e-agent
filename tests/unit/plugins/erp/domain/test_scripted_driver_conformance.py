"""The scripted drivers' driver-conformance fixes (Task 3f.1).

They read only tools in ``DriverInput.allowed_capabilities`` when it is set, a shortage needs
no offers, and the repair of ``invalid-then-repair`` is the turn that carries findings, so a
fresh instance (the kernel's resume of a driver without ``snapshot``) returns what the
original would. ``tests/conformance/test_driver_conformance.py`` runs the shared cases.
"""

from __future__ import annotations

from e_agent.contracts.validation import Finding, ValidationStatus
from e_agent.plugins.erp.domain.inventory import AVAILABILITY_READ
from e_agent.plugins.erp.domain.procurement import CREATE_DRAFT_PO, DEMAND_READ, SHORTAGE_ANSWER
from e_agent.plugins.erp.domain.sales import PRICING_READ
from e_agent.plugins.erp.domain.testing.scripted_driver import (
    OUTSIDE_TOOL_SET,
    ScriptedProcurementDriver,
)
from e_agent.plugins.erp.domain.testing.scripted_tasks import ScriptedErpDriver
from e_agent.sdk.ports import DriverInput, FinalAnswer, ProposeAction, RequestReads

from .test_scripted_driver_context import OBSERVATIONS, _ctx

TASK = "Calculate the shortage of product:widget-a for demand:d-001."
NO_OFFERS = (DEMAND_READ, AVAILABILITY_READ, SHORTAGE_ANSWER)
FINDING = Finding(
    rule_id="PR-003",
    rule_version="1",
    status=ValidationStatus.FAIL,
    message="the offer's supplier is not approved",
)


async def test_reads_stay_in_the_tool_set_and_the_shortage_needs_no_offers() -> None:
    driver = ScriptedProcurementDriver(connection_id="conn", task_kind="shortage")
    reads = await driver.advance(_ctx(), DriverInput(task=TASK, allowed_capabilities=NO_OFFERS))
    assert isinstance(reads, RequestReads)
    assert [r.contract_id for r in reads.reads] == [DEMAND_READ, AVAILABILITY_READ]
    observed = tuple(o for o in OBSERVATIONS if o.contract_id in NO_OFFERS)
    step = await driver.advance(
        _ctx(), DriverInput(task=TASK, observations=observed, allowed_capabilities=NO_OFFERS)
    )
    assert isinstance(step, ProposeAction) and step.proposal.contract_id == SHORTAGE_ANSWER
    assert step.proposal.arguments["shortage"] == "7"

    every = await driver.advance(_ctx(), DriverInput(task=TASK))  # None: every tool, as today
    assert isinstance(every, RequestReads) and len(every.reads) == 3
    none = await driver.advance(_ctx(), DriverInput(task=TASK, allowed_capabilities=()))
    assert none == FinalAnswer(text=OUTSIDE_TOOL_SET)


async def test_erp_kinds_read_only_in_the_tool_set() -> None:
    driver = ScriptedErpDriver(connection_id="conn", task_kind="quotation")
    narrowed = await driver.advance(_ctx(), DriverInput(task="t", allowed_capabilities=()))
    assert narrowed == FinalAnswer(text=OUTSIDE_TOOL_SET)  # never an empty read request
    every = await driver.advance(_ctx(), DriverInput(task="t"))
    assert isinstance(every, RequestReads)
    assert [r.contract_id for r in every.reads] == [PRICING_READ]


async def test_a_fresh_driver_repairs_on_the_findings_turn() -> None:
    first = ScriptedProcurementDriver(connection_id="conn", mode="invalid-then-repair")
    bad = await first.advance(_ctx(), DriverInput(task="t", observations=OBSERVATIONS))
    assert isinstance(bad, ProposeAction) and bad.proposal.contract_id == CREATE_DRAFT_PO
    assert bad.proposal.arguments["offer_ref"] == "offer:b"
    repair = DriverInput(task="t", observations=OBSERVATIONS, findings=(FINDING,))
    resumed = ScriptedProcurementDriver(connection_id="conn", mode="invalid-then-repair")
    for driver in (first, resumed):
        good = await driver.advance(_ctx(), repair)
        assert isinstance(good, ProposeAction)
        assert good.proposal.arguments["offer_ref"] == "offer:a"
