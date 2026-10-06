"""Procurement domain: normalizer, verifier, rule inventory, fixture ERP semantics."""

import json
from datetime import UTC, datetime
from importlib.resources import files

import pytest
from e_agent.contracts.action import ActionRecord, ActionState
from e_agent.contracts.context import Principal, TaskContext
from e_agent.contracts.outcome import OutcomeStatus
from e_agent.contracts.receipt import ExecutionReceipt, ReceiptStatus
from e_agent.erp.plugin import create_plugin, load_manifest
from e_agent.erp.procurement import CREATE_DRAFT_PO, DEMAND_READ, OFFERS_READ
from e_agent.erp.procurement.normalizer import collect_facts
from e_agent.erp.procurement.verifier import DraftPurchaseOrderVerifier
from e_agent.erp.testing.fake_erp import FakeErp
from e_agent.erp.testing.scenarios import SCENARIOS
from e_agent.sdk.errors import KnownNoEffectError
from e_agent.sdk.ports import PluginServices

CTX = TaskContext(
    run_id="run_1",
    tenant_id="t",
    principal=Principal(principal_id="p", tenant_id="t", roles=frozenset()),
    resource_scope=frozenset({"c"}),
)
ARGS = {
    "demand_ref": "demand:d-001",
    "product_ref": "product:widget-a",
    "supplier_ref": "supplier:approved-co",
    "offer_ref": "offer:a",
    "quantity": "7",
    "unit": "Units",
    "currency": "VND",
    "unit_price": "100",
    "subtotal": "700",
    "requested_date": "2026-10-20",
}


def _action(args: dict[str, str] = ARGS, digest: str = "d1", op: str = "op_1") -> ActionRecord:
    return ActionRecord(
        action_id="act_1",
        tenant_id="t",
        run_id="run_1",
        logical_operation_id=op,
        contract_id=CREATE_DRAFT_PO,
        binding_id="b",
        connection_id="c",
        connection_version=1,
        credential_subject="c@1/s",
        arguments=args,
        digest=digest,
        state=ActionState.DISPATCHING,
        revision=5,
    )


def test_shortage_is_derived_and_missing_facts_stay_unknown() -> None:
    facts = collect_facts(
        [
            (
                DEMAND_READ,
                {
                    "demand_ref": "d",
                    "product_ref": "p",
                    "quantity": "12",
                    "unit": "Units",
                    "requested_date": "2026-10-20",
                    "budget": "1000",
                    "currency": "VND",
                },
                "e1",
            ),
            ("inventory.availability.read.v1", {"available": "5", "inbound": "2"}, "e2"),
        ]
    )
    assert facts.required_quantity_str == "5"
    assert facts.offers is None
    assert collect_facts([]).required_quantity is None


def test_shortage_never_negative() -> None:
    facts = collect_facts(
        [
            (
                DEMAND_READ,
                {
                    "demand_ref": "d",
                    "product_ref": "p",
                    "quantity": "3",
                    "unit": "Units",
                    "requested_date": "2026-10-20",
                    "budget": "1",
                    "currency": "VND",
                },
                "e1",
            ),
            ("inventory.availability.read.v1", {"available": "10", "inbound": "0"}, "e2"),
        ]
    )
    assert facts.required_quantity_str == "0"


def test_manifest_is_packaged_and_matches_contribution() -> None:
    manifest = load_manifest()
    contribution = create_plugin(PluginServices(settings={}))
    assert set(contribution.capabilities) == set(manifest.provides_capabilities)
    contexts = {c.bounded_context for c in manifest.provides_capabilities}
    assert contexts == {"procurement", "inventory"}


def test_rule_inventory_lists_every_rule_with_an_engine() -> None:
    raw = files("e_agent.erp").joinpath("procurement/rules/inventory.json").read_text("utf-8")
    rules = json.loads(raw)["rules"]
    assert [r["id"] for r in rules] == [f"PR-00{i}" for i in range(1, 7)]
    allowed = {"shacl-core", "shacl-sparql", "normalizer-derived", "policy", "verifier"}
    for rule in rules:
        assert rule["engine"] and set(rule["engine"]) <= allowed


class _Reader:
    def __init__(self, erp: FakeErp) -> None:
        self.erp = erp

    async def read(self, contract_id, arguments):  # type: ignore[no-untyped-def]
        from e_agent.sdk.ports import ReadRequest

        return await self.erp.read(CTX, None, ReadRequest("v", contract_id, "c", arguments))  # type: ignore[arg-type]


def _receipt(refs: tuple[str, ...]) -> ExecutionReceipt:
    now = datetime(2026, 10, 6, tzinfo=UTC)
    return ExecutionReceipt(
        action_id="act_1",
        attempt=1,
        status=ReceiptStatus.COMMITTED,
        external_refs=refs,
        started_at=now,
        finished_at=now,
    )


@pytest.mark.asyncio
async def test_verifier_passes_matching_draft_and_fails_tampered_one() -> None:
    erp = FakeErp(SCENARIOS["valid"])
    receipt = await erp.execute(CTX, None, _action(), 1)  # type: ignore[arg-type]
    verifier = DraftPurchaseOrderVerifier()
    ok = await verifier.verify(CTX, _action(), receipt, _Reader(erp))
    assert ok.status is OutcomeStatus.VERIFIED
    erp.orders["op_1"].state = "purchase"  # someone confirmed it
    bad = await verifier.verify(CTX, _action(), receipt, _Reader(erp))
    assert bad.status is OutcomeStatus.FAILED
    assert not next(c for c in bad.checks if c.name == "state_is_draft").passed


@pytest.mark.asyncio
async def test_verifier_fails_when_no_order_exists() -> None:
    erp = FakeErp(SCENARIOS["valid"])
    report = await DraftPurchaseOrderVerifier().verify(
        CTX, _action(), _receipt(("PO/X",)), _Reader(erp)
    )
    assert report.status is OutcomeStatus.FAILED


@pytest.mark.asyncio
async def test_operation_key_is_idempotent_and_conflicts_on_new_payload() -> None:
    erp = FakeErp(SCENARIOS["valid"])
    first = await erp.execute(CTX, None, _action(), 1)  # type: ignore[arg-type]
    again = await erp.execute(CTX, None, _action(), 2)  # type: ignore[arg-type]
    assert first.external_refs == again.external_refs and len(erp.orders) == 1
    with pytest.raises(KnownNoEffectError):
        await erp.execute(CTX, None, _action(digest="d2"), 3)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_offers_read_reports_approval_status() -> None:
    from e_agent.sdk.ports import ReadRequest

    erp = FakeErp(SCENARIOS["valid"])
    obs = await erp.read(CTX, None, ReadRequest("r", OFFERS_READ, "c", {}))  # type: ignore[arg-type]
    assert {o["offer_ref"]: o["approved"] for o in obs.data["offers"]} == {
        "offer:a": True,
        "offer:b": False,
    }
    assert obs.evidence.environment == "fixture"
