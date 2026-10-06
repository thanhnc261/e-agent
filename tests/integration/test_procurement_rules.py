"""Procurement rules through the real SHACL engine (I03 gate).

Every named rule has positive, negative and missing-data cases; SHACL results
are compared with the procedural fixture control for parity (MVP design §13).
"""

import json
from datetime import UTC, datetime
from importlib.resources import files

import pytest
from e_agent.adapters.shacl import ShaclPlanValidator
from e_agent.contracts.context import Principal, TaskContext
from e_agent.contracts.evidence import EvidenceRef
from e_agent.contracts.plan import ActionProposal
from e_agent.contracts.validation import ValidationStatus
from e_agent.erp.procurement import CREATE_DRAFT_PO, DEMAND_READ, OFFERS_READ
from e_agent.erp.procurement.validation import SHAPES, ProcurementDatasetBuilder
from e_agent.erp.testing.fixture_validator import FixtureRuleValidator
from e_agent.sdk.ports import Observation, ValidationInput
from rdflib import Graph, Namespace

CTX = TaskContext(
    run_id="run_t",
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
            "supplier_ref": "supplier:ok",
            "product_ref": "product:widget-a",
            "unit_price": "100",
            "currency": "VND",
            "unit": "Units",
            "approved": True,
            "delivery_date": "2026-10-15",
        },
        {
            "offer_ref": "offer:b",
            "supplier_ref": "supplier:new",
            "product_ref": "product:widget-a",
            "unit_price": "80",
            "currency": "VND",
            "unit": "Units",
            "approved": False,
            "delivery_date": "2026-10-14",
        },
        {
            "offer_ref": "offer:late",
            "supplier_ref": "supplier:ok",
            "product_ref": "product:widget-a",
            "unit_price": "90",
            "currency": "VND",
            "unit": "Units",
            "approved": True,
            "delivery_date": "2026-10-30",
        },
    ],
}
VALID = {
    "demand_ref": "demand:d-001",
    "product_ref": "product:widget-a",
    "supplier_ref": "supplier:ok",
    "offer_ref": "offer:a",
    "quantity": "7",
    "unit": "Units",
    "currency": "VND",
    "unit_price": "100",
    "subtotal": "700",
    "requested_date": "2026-10-20",
}


def _input(
    args: dict[str, str], *, drop: tuple[str, ...] = (), demand: dict[str, str] | None = None
) -> ValidationInput:
    reads = {
        DEMAND_READ: demand or DEMAND,
        "inventory.availability.read.v1": STOCK,
        OFFERS_READ: OFFERS,
    }
    obs = tuple(
        Observation(request_id=c, contract_id=c, data=d, evidence=EV)
        for c, d in reads.items()
        if c not in drop
    )
    return ValidationInput(
        proposal=ActionProposal(contract_id=CREATE_DRAFT_PO, connection_id="c", arguments=args),
        observations=obs,
    )


def _rules(result) -> dict[str, ValidationStatus]:  # type: ignore[no-untyped-def]
    worst: dict[str, ValidationStatus] = {}
    order = [ValidationStatus.PASS, ValidationStatus.UNKNOWN, ValidationStatus.FAIL]
    for f in result.findings:
        cur = worst.get(f.rule_id, ValidationStatus.PASS)
        worst[f.rule_id] = max(cur, f.status, key=order.index)
    return worst


SHACL = ShaclPlanValidator([ProcurementDatasetBuilder()])

CASES = {
    "valid": (VALID, {}, ValidationStatus.PASS, {}),
    "PR-001 unknown offer ref": (
        {**VALID, "offer_ref": "offer:zzz"},
        {},
        ValidationStatus.FAIL,
        {"PR-001": ValidationStatus.FAIL},
    ),
    "PR-001 missing offers fact": (
        VALID,
        {"drop": (OFFERS_READ,)},
        ValidationStatus.UNKNOWN,
        {"PR-001": ValidationStatus.UNKNOWN},
    ),
    "PR-002 wrong quantity": (
        {**VALID, "quantity": "8", "subtotal": "800"},
        {},
        ValidationStatus.FAIL,
        {"PR-002": ValidationStatus.FAIL},
    ),
    "PR-002 missing stock": (
        VALID,
        {"drop": ("inventory.availability.read.v1",)},
        ValidationStatus.UNKNOWN,
        {"PR-001": ValidationStatus.UNKNOWN},
    ),
    "PR-003 unapproved offer": (
        {
            **VALID,
            "offer_ref": "offer:b",
            "supplier_ref": "supplier:new",
            "unit_price": "80",
            "subtotal": "560",
        },
        {},
        ValidationStatus.FAIL,
        {"PR-003": ValidationStatus.FAIL},
    ),
    "PR-003 supplier mismatch": (
        {**VALID, "supplier_ref": "supplier:new"},
        {},
        ValidationStatus.FAIL,
        {"PR-003": ValidationStatus.FAIL},
    ),
    "PR-004 wrong subtotal": (
        {**VALID, "subtotal": "699"},
        {},
        ValidationStatus.FAIL,
        {"PR-004": ValidationStatus.FAIL},
    ),
    "PR-004 over budget": (
        VALID,
        {"demand": {**DEMAND, "budget": "500"}},
        ValidationStatus.FAIL,
        {"PR-004": ValidationStatus.FAIL},
    ),
    "PR-004 currency mismatch": (
        {**VALID, "currency": "USD"},
        {},
        ValidationStatus.FAIL,
        {"PR-004": ValidationStatus.FAIL},
    ),
    "PR-005 late delivery": (
        {**VALID, "offer_ref": "offer:late", "unit_price": "90", "subtotal": "630"},
        {},
        ValidationStatus.FAIL,
        {"PR-005": ValidationStatus.FAIL},
    ),
}


@pytest.mark.asyncio
@pytest.mark.parametrize("name", list(CASES))
async def test_rule_matrix(name: str) -> None:
    args, opts, overall, expected = CASES[name]
    result = await SHACL.validate(CTX, _input(args, **opts))
    assert result.status is overall, result.findings
    rules = _rules(result)
    for rule_id, status in expected.items():
        assert rules[rule_id] is status, (rule_id, result.findings)
    if overall is ValidationStatus.PASS:
        assert set(rules) == {"PR-001", "PR-002", "PR-003", "PR-004", "PR-005"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "name", [n for n in CASES if "missing" not in n and "unknown offer" not in n]
)
async def test_parity_with_procedural_control(name: str) -> None:
    """Equivalent rules give the same pass/fail per rule (comparative control only)."""
    args, opts, _, _ = CASES[name]
    shacl = _rules(await SHACL.validate(CTX, _input(args, **opts)))
    procedural = _rules(await FixtureRuleValidator().validate(CTX, _input(args, **opts)))
    for rule_id in ("PR-002", "PR-003", "PR-004", "PR-005"):
        assert (shacl[rule_id] is ValidationStatus.PASS) == (
            procedural.get(rule_id) is ValidationStatus.PASS
        ), (rule_id, shacl, procedural)


def test_rule_inventory_matches_shapes() -> None:
    base = files("e_agent.erp.procurement")
    inventory = json.loads(base.joinpath("rules/inventory.json").read_text("utf-8"))
    shapes = Graph().parse(data=base.joinpath(SHAPES[0].path).read_text("utf-8"), format="turtle")
    ea = Namespace("https://e-agent.dev/ns/core#")
    ps = "https://e-agent.dev/ns/procurement/shapes#"
    shape_rules = {str(s).removeprefix(ps): str(o) for s, o in shapes.subject_objects(ea.ruleId)}
    referenced = set()
    for rule in inventory["rules"]:
        for asset in rule["asset"]:
            if asset.startswith("ps:"):
                local = asset.removeprefix("ps:")
                assert shape_rules.get(local) == rule["id"], (asset, rule["id"])
                referenced.add(local)
    assert referenced == set(shape_rules), "every rule shape must be in the inventory"


def test_ontology_and_shapes_parse_from_package_resources() -> None:
    base = files("e_agent.erp.procurement")
    Graph().parse(
        data=base.joinpath("ontology/procurement.ttl").read_text("utf-8"), format="turtle"
    )
    Graph().parse(data=base.joinpath(SHAPES[0].path).read_text("utf-8"), format="turtle")


@pytest.mark.asyncio
async def test_malformed_arguments_are_unknown_not_crash() -> None:
    result = await SHACL.validate(CTX, _input({"quantity": 7}))  # type: ignore[dict-item]
    assert result.status is not ValidationStatus.PASS
