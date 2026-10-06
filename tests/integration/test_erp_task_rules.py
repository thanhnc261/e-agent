"""ERP-04/05/07 rules through the real SHACL engine: each rule has a passing,
a failing and a missing-facts case (I10/I11 gate)."""

from datetime import UTC, datetime
from typing import Any

import pytest
from e_agent.adapters.shacl import ShaclPlanValidator
from e_agent.contracts.context import Principal, TaskContext
from e_agent.contracts.evidence import EvidenceRef
from e_agent.contracts.plan import ActionProposal
from e_agent.contracts.validation import ValidationStatus
from e_agent.erp.crm import CONTACT_READ, CREATE_LEAD, TEAMS_READ
from e_agent.erp.crm.lead import LeadDatasetBuilder
from e_agent.erp.procurement import AMEND_DRAFT_RFQ, DRAFT_RFQ_READ
from e_agent.erp.procurement.amend import AmendDatasetBuilder
from e_agent.erp.sales import CREATE_DRAFT_QUOTATION, PRICING_READ
from e_agent.erp.sales.quotation import QuotationDatasetBuilder
from e_agent.sdk.ports import Observation, ValidationInput

pytestmark = pytest.mark.asyncio
CTX = TaskContext(
    run_id="r",
    tenant_id="t",
    principal=Principal(principal_id="p", tenant_id="t", roles=frozenset()),
    resource_scope=frozenset({"c"}),
)
EV = EvidenceRef(
    evidence_id="ev",
    tenant_id="t",
    source="fixture",
    locator="x",
    revision="1",
    observed_at=datetime(2026, 10, 6, tzinfo=UTC),
    scope="t",
)
ENGINE = ShaclPlanValidator(
    (AmendDatasetBuilder(), QuotationDatasetBuilder(), LeadDatasetBuilder())
)

RFQ = {
    "purchase_order_ref": "rfq:1",
    "external_ref": "P1",
    "state": "draft",
    "revision": "rev-1",
    "supplier_ref": "s",
    "product_ref": "p",
    "quantity": "10",
    "unit": "Units",
    "unit_price": "100",
    "currency": "VND",
    "requested_date": "2026-10-20",
}
AMEND = {
    "purchase_order_ref": "rfq:1",
    "expected_revision": "rev-1",
    "quantity": "15",
    "requested_date": "2026-10-20",
}
PRICING = {
    "customer_ref": "cu",
    "customer_name": "Cu",
    "customer_active": True,
    "product_ref": "p",
    "product_saleable": True,
    "list_price": "150",
    "currency": "VND",
    "unit": "Units",
}
QUOTE = {
    "customer_ref": "cu",
    "product_ref": "p",
    "quantity": "3",
    "unit": "Units",
    "unit_price": "150",
    "currency": "VND",
    "subtotal": "450",
}
CONTACT = {"contact_ref": "ct", "name": "Jane", "active": True}
TEAMS = {
    "teams": [{"team_ref": "tm", "name": "Direct", "member_refs": ["u1", "u2"]}],
    "sources": [{"source_ref": "web", "name": "Website"}],
}
LEAD = {
    "name": "Big deal",
    "contact_ref": "ct",
    "team_ref": "tm",
    "owner_ref": "u1",
    "source_ref": "web",
    "expected_revenue": "100",
}


async def _validate(
    contract: str, args: dict[str, Any], reads: dict[str, dict[str, Any]]
) -> dict[str, ValidationStatus]:
    obs = tuple(
        Observation(request_id=c, contract_id=c, data=d, evidence=EV) for c, d in reads.items()
    )
    result = await ENGINE.validate(
        CTX,
        ValidationInput(
            proposal=ActionProposal(contract_id=contract, connection_id="c", arguments=args),
            observations=obs,
        ),
    )
    worst: dict[str, ValidationStatus] = {}
    rank = [ValidationStatus.PASS, ValidationStatus.UNKNOWN, ValidationStatus.FAIL]
    for f in result.findings:
        if rank.index(f.status) >= rank.index(worst.get(f.rule_id, ValidationStatus.PASS)):
            worst[f.rule_id] = f.status
    return worst


P, F, U = ValidationStatus.PASS, ValidationStatus.FAIL, ValidationStatus.UNKNOWN


async def test_amendment_rules() -> None:
    reads = {DRAFT_RFQ_READ: RFQ}
    assert await _validate(AMEND_DRAFT_RFQ, AMEND, reads) == dict.fromkeys(
        ("AM-001", "AM-002", "AM-003", "AM-004"), P
    )
    assert (
        await _validate(AMEND_DRAFT_RFQ, AMEND, {DRAFT_RFQ_READ: {**RFQ, "state": "purchase"}})
    )["AM-001"] is F
    assert (await _validate(AMEND_DRAFT_RFQ, {**AMEND, "expected_revision": "rev-0"}, reads))[
        "AM-002"
    ] is F
    assert (await _validate(AMEND_DRAFT_RFQ, {**AMEND, "quantity": "0"}, reads))["AM-003"] is F
    assert (await _validate(AMEND_DRAFT_RFQ, {**AMEND, "quantity": "10"}, reads))["AM-004"] is F
    assert (
        await _validate(
            AMEND_DRAFT_RFQ, {**AMEND, "quantity": "10", "requested_date": "2026-10-25"}, reads
        )
    )["AM-004"] is P
    missing = await _validate(AMEND_DRAFT_RFQ, AMEND, {})
    assert missing["AM-001"] is U and set(missing.values()) == {U}
    other = await _validate(AMEND_DRAFT_RFQ, {**AMEND, "purchase_order_ref": "rfq:2"}, reads)
    assert set(other.values()) == {U}  # an unread RFQ is never assumed


async def test_quotation_rules() -> None:
    reads = {PRICING_READ: PRICING}
    assert set((await _validate(CREATE_DRAFT_QUOTATION, QUOTE, reads)).values()) == {P}
    archived = {PRICING_READ: {**PRICING, "customer_active": False}}
    assert (await _validate(CREATE_DRAFT_QUOTATION, QUOTE, archived))["SQ-002"] is F
    unsaleable = {PRICING_READ: {**PRICING, "product_saleable": False}}
    assert (await _validate(CREATE_DRAFT_QUOTATION, QUOTE, unsaleable))["SQ-002"] is F
    discounted = {**QUOTE, "unit_price": "140", "subtotal": "420"}
    assert (await _validate(CREATE_DRAFT_QUOTATION, discounted, reads))["SQ-003"] is F
    assert (await _validate(CREATE_DRAFT_QUOTATION, {**QUOTE, "currency": "USD"}, reads))[
        "SQ-003"
    ] is F
    assert (await _validate(CREATE_DRAFT_QUOTATION, {**QUOTE, "subtotal": "451"}, reads))[
        "SQ-004"
    ] is F
    assert (
        await _validate(CREATE_DRAFT_QUOTATION, {**QUOTE, "quantity": "0", "subtotal": "0"}, reads)
    )["SQ-004"] is F
    assert set((await _validate(CREATE_DRAFT_QUOTATION, QUOTE, {})).values()) == {U}


async def test_lead_rules() -> None:
    reads = {CONTACT_READ: CONTACT, TEAMS_READ: TEAMS}
    assert set((await _validate(CREATE_LEAD, LEAD, reads)).values()) == {P}
    assert (
        await _validate(CREATE_LEAD, LEAD, {**reads, CONTACT_READ: {**CONTACT, "active": False}})
    )["CL-001"] is F
    assert (await _validate(CREATE_LEAD, {**LEAD, "owner_ref": "u9"}, reads))["CL-002"] is F
    assert (await _validate(CREATE_LEAD, {**LEAD, "team_ref": "nope"}, reads))["CL-002"] is F
    assert (await _validate(CREATE_LEAD, {**LEAD, "source_ref": "tv"}, reads))["CL-003"] is F
    assert (await _validate(CREATE_LEAD, {**LEAD, "source_ref": None}, reads))["CL-003"] is P
    assert (await _validate(CREATE_LEAD, {**LEAD, "expected_revenue": "-1"}, reads))["CL-004"] is F
    assert set((await _validate(CREATE_LEAD, LEAD, {TEAMS_READ: TEAMS})).values()) == {U}
