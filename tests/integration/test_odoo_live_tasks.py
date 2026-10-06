"""Live Odoo 19 checks for ERP-04..08 (I10/I11). Same sandbox requirements as
test_odoo_live.py; every test seeds and resets its own namespace."""

import uuid
from typing import Any

import pytest
from e_agent.adapters.odoo.client import OdooRejected
from e_agent.contracts.run import RunState
from e_agent.server.bootstrap import build_runtime

from .test_odoo_live import ADMIN_KEY, URL, _approve, _bridge, _profile, secrets  # noqa: F401

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(not URL, reason="no sandbox Odoo"),
    pytest.mark.usefixtures("secrets"),
]


@pytest.fixture
async def tasks() -> Any:
    namespace = f"e-agent-tasks-{uuid.uuid4().hex[:8]}"
    refs = await _bridge("sandbox_seed_tasks", ADMIN_KEY, namespace=namespace)
    yield namespace, refs
    await _bridge("sandbox_reset", ADMIN_KEY, namespace=namespace)


async def _run(
    namespace: str, refs: dict[str, Any], task: str, **kw: Any
) -> tuple[Any, Any, list[Any]]:
    rt = await build_runtime(_profile(namespace, refs, task_kind=task), **kw)
    run = await rt.coordinator.start_run(rt.operator, task, rt.scope)
    if run.state is RunState.WAITING_APPROVAL:
        run = await _approve(rt, run)
    events = await rt.store.list_events(rt.operator.tenant_id, run.run_id)
    return rt, run, events


def _outcomes(events: list[Any]) -> list[str]:
    return [e.payload["status"] for e in events if e.type == "outcome.reported"]


def _failed(events: list[Any]) -> list[set[str]]:
    return [
        {f["rule_id"] for f in e.payload.get("findings", []) if f["status"] == "FAIL"}
        for e in events
        if e.type == "validation.completed"
    ]


# -- bridge preconditions (authoritative rejections, nothing written) ----------


async def test_bridge_refuses_stale_or_non_draft_amendments(tasks: Any) -> None:
    namespace, refs = tasks
    rfq = await _bridge("read_draft_rfq", purchase_order_ref=refs["rfq_ref"])
    payload = {
        "purchase_order_ref": refs["rfq_ref"],
        "expected_revision": "old",
        "quantity": "11",
        "requested_date": rfq["requested_date"],
    }
    with pytest.raises(OdooRejected) as err:
        await _bridge(
            "amend_draft_purchase_order",
            namespace=namespace,
            operation_key="a1",
            payload_digest="d",
            payload=payload,
        )
    assert err.value.code == "E_AGENT_STALE"
    confirmed = await _bridge("read_draft_rfq", purchase_order_ref=refs["confirmed_rfq_ref"])
    with pytest.raises(OdooRejected) as err:
        await _bridge(
            "amend_draft_purchase_order",
            namespace=namespace,
            operation_key="a2",
            payload_digest="d",
            payload={
                **payload,
                "purchase_order_ref": refs["confirmed_rfq_ref"],
                "expected_revision": confirmed["revision"],
            },
        )
    assert err.value.code == "E_AGENT_INVALID"
    assert (await _bridge("read_draft_rfq", purchase_order_ref=refs["rfq_ref"]))["quantity"] == 10.0


async def test_bridge_refuses_invalid_quotations_and_leads(tasks: Any) -> None:
    namespace, refs = tasks
    quote = {
        "customer_ref": refs["archived_customer_ref"],
        "product_ref": refs["product_ref"],
        "quantity": "1",
        "unit_price": "150",
    }
    with pytest.raises(OdooRejected):
        await _bridge(
            "create_draft_quotation",
            namespace=namespace,
            operation_key="q1",
            payload_digest="d",
            payload=quote,
        )
    lead = {
        "name": "x lead",
        "contact_ref": refs["contact_ref"],
        "team_ref": refs["team_ref"],
        "owner_ref": refs["other_owner_ref"],
        "source_ref": None,
        "expected_revenue": "1",
    }
    with pytest.raises(OdooRejected):
        await _bridge(
            "create_lead", namespace=namespace, operation_key="l1", payload_digest="d", payload=lead
        )


async def test_repeated_lead_command_never_duplicates(tasks: Any) -> None:
    namespace, refs = tasks
    lead = {
        "name": "Repeat lead",
        "contact_ref": refs["contact_ref"],
        "team_ref": refs["team_ref"],
        "owner_ref": refs["owner_ref"],
        "source_ref": refs["source_ref"],
        "expected_revenue": "10",
    }
    first = await _bridge(
        "create_lead", namespace=namespace, operation_key="l-rep", payload_digest="d", payload=lead
    )
    again = await _bridge(
        "create_lead", namespace=namespace, operation_key="l-rep", payload_digest="d", payload=lead
    )
    assert first["status"] == "created" and again["status"] == "existing"
    assert first["leads"] == again["leads"] and len(again["leads"]) == 1


# -- full runs through kernel, SHACL, approval and independent verification -----


async def test_erp04_amendment_blocked_when_stale_then_repaired_and_verified(tasks: Any) -> None:
    namespace, refs = tasks
    _, run, events = await _run(namespace, refs, "amend-rfq", driver_mode="invalid-then-repair")
    assert _failed(events)[:2] == [{"AM-002"}, set()]
    assert run.state is RunState.SUCCEEDED, run.reason
    assert _outcomes(events) == ["VERIFIED"]
    rfq = await _bridge("read_draft_rfq", purchase_order_ref=refs["rfq_ref"])
    assert rfq["state"] == "draft" and rfq["quantity"] == 15.0


async def test_erp04_confirmed_rfq_is_blocked(tasks: Any) -> None:
    namespace, refs = tasks
    refs = {**refs, "rfq_ref": refs["confirmed_rfq_ref"]}
    _, run, events = await _run(namespace, refs, "amend-rfq")
    assert run.state is RunState.FAILED
    assert "AM-001" in _failed(events)[0]


async def test_erp05_quotation_is_draft_unsent_and_verified(tasks: Any) -> None:
    namespace, refs = tasks
    rt, run, events = await _run(namespace, refs, "quotation", driver_mode="invalid-then-repair")
    assert _failed(events)[0] == {"SQ-003"}
    assert run.state is RunState.SUCCEEDED, run.reason
    [action] = [
        a
        for a in await rt.store.list_actions(rt.operator.tenant_id, run.run_id)
        if a.state.value == "VERIFIED"
    ]
    read = await _bridge(
        "read_operation", namespace=namespace, operation_key=action.logical_operation_id
    )
    [quote] = read["quotations"]
    assert quote["state"] == "draft" and quote["sent"] is False and quote["subtotal"] == 450.0


async def test_erp05_unsaleable_product_is_blocked(tasks: Any) -> None:
    namespace, refs = tasks
    refs = {**refs, "product_ref": refs["unsaleable_product_ref"]}
    _, run, events = await _run(namespace, refs, "quotation")
    assert run.state is RunState.FAILED and "SQ-002" in _failed(events)[0]


async def test_erp06_late_orders_match_odoo(tasks: Any) -> None:
    namespace, refs = tasks
    assert refs["delivered_status"] == "full"
    _, run, events = await _run(
        namespace, refs, "late-orders", driver_mode="wrong-answer-then-correct"
    )
    assert run.state is RunState.SUCCEEDED and _outcomes(events) == ["FAILED", "VERIFIED"]
    late = [e for e in events if e.type == "proposal.created"][-1].payload["arguments"][
        "late_order_refs"
    ]
    assert refs["late_order_ref"] in late
    assert refs["future_order_ref"] not in late and refs["delivered_order_ref"] not in late


async def test_erp07_lead_owner_must_be_team_member_then_verified(tasks: Any) -> None:
    namespace, refs = tasks
    _, run, events = await _run(namespace, refs, "crm-lead", driver_mode="invalid-then-repair")
    assert _failed(events)[0] == {"CL-002"}
    assert run.state is RunState.SUCCEEDED and _outcomes(events) == ["VERIFIED"]


async def test_erp08_overdue_invoices_match_odoo_and_nothing_is_posted(tasks: Any) -> None:
    namespace, refs = tasks
    before = await _bridge("read_open_invoices", as_of=refs["as_of"])
    _, run, events = await _run(
        namespace, refs, "overdue-invoices", driver_mode="wrong-answer-then-correct"
    )
    assert run.state is RunState.SUCCEEDED and _outcomes(events) == ["FAILED", "VERIFIED"]
    answer = [e for e in events if e.type == "proposal.created"][-1].payload["arguments"]
    assert refs["overdue_invoice_ref"] in answer["overdue_invoice_refs"]
    assert refs["not_due_invoice_ref"] not in answer["overdue_invoice_refs"]
    after = await _bridge("read_open_invoices", as_of=refs["as_of"])
    assert before["invoices"] == after["invoices"]  # read-only: no posting, payment or write-off
