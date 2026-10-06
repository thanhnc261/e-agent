"""Live Odoo 19 integration (I06/I07). Runs only when a sandbox Odoo is configured:

    E_AGENT_TEST_ODOO_URL, E_AGENT_TEST_ODOO_DB,
    E_AGENT_TEST_ODOO_KEY (integration user), E_AGENT_TEST_ODOO_ADMIN_KEY (seed/reset)

The target database must carry the e_agent.sandbox_marker system parameter.
"""

import asyncio
import json
import os
import uuid
from pathlib import Path
from typing import Any

import httpx
import pytest
from e_agent.adapters.odoo.client import OdooJson2Client, OdooRejected
from e_agent.adapters.secretstore_local import LocalSecretStore, generate_key
from e_agent.contracts.approval import ApprovalDecision
from e_agent.contracts.connection import ConnectionOwnership
from e_agent.contracts.run import RunState
from e_agent.kernel.errors import KernelError
from e_agent.sdk.auth import AuthContext, Secret
from e_agent.server.bootstrap import build_runtime
from e_agent.server.profile import Profile

URL = os.environ.get("E_AGENT_TEST_ODOO_URL")
DB = os.environ.get("E_AGENT_TEST_ODOO_DB", "")
KEY = os.environ.get("E_AGENT_TEST_ODOO_KEY", "")
ADMIN_KEY = os.environ.get("E_AGENT_TEST_ODOO_ADMIN_KEY", "")
MARKER = os.environ.get("E_AGENT_TEST_ODOO_MARKER", "e-agent-ci-sandbox")
pytestmark = [pytest.mark.asyncio, pytest.mark.skipif(not URL, reason="no sandbox Odoo")]


def _auth(key: str) -> AuthContext:
    return AuthContext(
        connection_id="c",
        connection_version=1,
        ownership=ConnectionOwnership.TENANT_SHARED,
        provider_subject="t",
        method="api_key",
        _secret=Secret(key),
        _placement={"header": "Authorization", "prefix": "bearer "},
    )


async def _bridge(method: str, key: str = KEY, **kw: Any) -> Any:
    return await OdooJson2Client(str(URL), DB).call(_auth(key), "e_agent.bridge", method, **kw)


@pytest.fixture
async def seeded() -> Any:
    namespace = f"e-agent-test-{uuid.uuid4().hex[:8]}"
    refs = await _bridge("sandbox_seed", ADMIN_KEY, namespace=namespace)
    yield namespace, refs
    await _bridge("sandbox_reset", ADMIN_KEY, namespace=namespace)


def _payload(refs: dict[str, str], offers: dict[str, Any], qty: str = "7") -> dict[str, Any]:
    offer = next(o for o in offers["offers"] if o["approved"])
    return {
        "product_ref": refs["product_ref"],
        "supplier_ref": offer["supplier_ref"],
        "offer_ref": offer["offer_ref"],
        "quantity": qty,
        "unit_price": "100",
        "requested_date": "2030-01-01",
    }


async def test_bridge_is_idempotent_and_detects_payload_conflicts(seeded: Any) -> None:
    namespace, refs = seeded
    offers = await _bridge("read_offers", product_ref=refs["product_ref"])
    payload = _payload(refs, offers)
    first = await _bridge(
        "create_draft_purchase_order",
        namespace=namespace,
        operation_key="op-1",
        payload_digest="d1",
        payload=payload,
    )
    again = await _bridge(
        "create_draft_purchase_order",
        namespace=namespace,
        operation_key="op-1",
        payload_digest="d1",
        payload=payload,
    )
    assert first["status"] == "created" and again["status"] == "existing"
    assert first["orders"][0]["external_ref"] == again["orders"][0]["external_ref"]
    assert first["orders"][0]["state"] == "draft"
    with pytest.raises(OdooRejected) as err:
        await _bridge(
            "create_draft_purchase_order",
            namespace=namespace,
            operation_key="op-1",
            payload_digest="d2",
            payload={**payload, "quantity": "8"},
        )
    assert err.value.code == "E_AGENT_CONFLICT"


async def test_concurrent_duplicates_create_exactly_one_order(seeded: Any) -> None:
    namespace, refs = seeded
    offers = await _bridge("read_offers", product_ref=refs["product_ref"])
    payload = _payload(refs, offers)

    async def attempt() -> str:
        try:
            r = await _bridge(
                "create_draft_purchase_order",
                namespace=namespace,
                operation_key="op-race",
                payload_digest="d",
                payload=payload,
            )
            return str(r["status"])
        except OdooRejected as exc:
            return exc.code

    outcomes = await asyncio.gather(*(attempt() for _ in range(6)))
    assert outcomes.count("created") == 1, outcomes
    read = await _bridge("read_operation", namespace=namespace, operation_key="op-race")
    assert len(read["orders"]) == 1


async def test_integration_user_cannot_run_sandbox_tools() -> None:
    with pytest.raises(OdooRejected):
        await _bridge("sandbox_seed", KEY, namespace="nope")


def _profile(namespace: str, refs: dict[str, str], marker: str = MARKER) -> Profile:
    contracts = {
        "inventory.availability": "inventory",
        "procurement.demand": "demand",
        "procurement.offers": "offers",
        "procurement.po-create": "c",
        "procurement.po-read": "r",
    }
    return Profile.model_validate(
        {
            "profile_version": "1",
            "environment": "live",
            "tenant_id": "tenant-live",
            "operator": {"principal_id": "op", "roles": ["requester", "approver"]},
            "enabled_plugins": {
                "domain-erp": {"version": "0.1.0"},
                "odoo19": {
                    "version": "0.1.0",
                    "settings": {
                        "base_url": URL,
                        "database": DB,
                        "namespace": namespace,
                        "expected_sandbox_marker": marker,
                    },
                },
            },
            "connections": [
                {
                    "tenant_id": "tenant-live",
                    "connection_id": "conn-odoo",
                    "version": 1,
                    "integration_id": "odoo19",
                    "ownership": "tenant_shared",
                    "provider_subject": "e-agent-integration",
                    "secret_ref": "secretref:local/odoo-integration",
                }
            ],
            "bindings": {f"odoo19.{k}": ["conn-odoo"] for k in contracts},
            "driver": {
                "kind": "scripted",
                "demand_ref": refs["demand_ref"],
                "product_ref": refs["product_ref"],
            },
        }
    )


@pytest.fixture
async def secrets(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    kek = generate_key()
    monkeypatch.setenv("E_AGENT_SECRET_KEY", kek)
    monkeypatch.setenv("E_AGENT_SECRETS_PATH", str(tmp_path / "secrets.json"))
    await LocalSecretStore(tmp_path / "secrets.json", kek).put(
        "secretref:local/odoo-integration", Secret(KEY)
    )


async def _approve(rt: Any, run: Any) -> Any:
    pres = await rt.coordinator.pending_approval(rt.operator.tenant_id, run.run_id)
    return await rt.coordinator.decide(
        actor=rt.operator,
        run_id=run.run_id,
        action_id=pres.action_id,
        action_digest=pres.digest,
        expected_run_revision=pres.run_revision,
        decision=ApprovalDecision.APPROVED,
    )


async def test_live_procurement_run_creates_one_verified_draft(seeded: Any, secrets: None) -> None:
    namespace, refs = seeded
    rt = await build_runtime(_profile(namespace, refs))
    assert rt.sandbox["conn-odoo"]["sandbox_marker"] == MARKER
    run = await rt.coordinator.start_run(rt.operator, "restock", rt.scope)
    assert run.state is RunState.WAITING_APPROVAL, run.reason
    pres = await rt.coordinator.pending_approval(rt.operator.tenant_id, run.run_id)
    assert pres.canonical_proposal["arguments"]["quantity"] == "7"
    assert pres.credential_subject == "conn-odoo@1/e-agent-integration"
    run = await _approve(rt, run)
    assert run.state is RunState.SUCCEEDED, run.reason
    [action] = await rt.store.list_actions(rt.operator.tenant_id, run.run_id)
    read = await _bridge(
        "read_operation", namespace=namespace, operation_key=action.logical_operation_id
    )
    assert len(read["orders"]) == 1 and read["orders"][0]["state"] == "draft"
    events = await rt.store.list_events(rt.operator.tenant_id, run.run_id)
    outcome = next(e for e in events if e.type == "outcome.reported")
    assert outcome.payload["status"] == "VERIFIED"
    assert all(e.payload.get("environment") != "fixture" for e in events)
    assert KEY not in json.dumps([e.model_dump(mode="json") for e in events])


async def test_live_invalid_proposal_is_blocked_then_repaired(seeded: Any, secrets: None) -> None:
    namespace, refs = seeded
    profile = _profile(namespace, refs)
    rt = await build_runtime(profile, driver_mode="invalid-then-repair")
    run = await rt.coordinator.start_run(rt.operator, "restock", rt.scope)
    events = await rt.store.list_events(rt.operator.tenant_id, run.run_id)
    statuses = [e.payload["status"] for e in events if e.type == "validation.completed"]
    assert statuses == ["FAIL", "PASS"]


async def test_lost_response_reconciles_without_a_second_order(
    seeded: Any, secrets: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    namespace, refs = seeded
    rt = await build_runtime(_profile(namespace, refs))
    run = await rt.coordinator.start_run(rt.operator, "restock", rt.scope)
    real_post = httpx.AsyncClient.post
    dropped = {"n": 0}

    async def drop_after_commit(self: httpx.AsyncClient, url: str, **kw: Any) -> httpx.Response:
        resp = await real_post(self, url, **kw)
        if url.endswith("/create_draft_purchase_order") and dropped["n"] == 0:
            dropped["n"] += 1
            raise httpx.ReadTimeout("response lost after commit")
        return resp

    monkeypatch.setattr(httpx.AsyncClient, "post", drop_after_commit)
    run = await _approve(rt, run)
    assert run.state is RunState.NEEDS_RECONCILIATION
    run = await rt.coordinator.reconcile(rt.operator, run.run_id)
    assert run.state is RunState.SUCCEEDED
    [action] = await rt.store.list_actions(rt.operator.tenant_id, run.run_id)
    read = await _bridge(
        "read_operation", namespace=namespace, operation_key=action.logical_operation_id
    )
    assert len(read["orders"]) == 1


async def test_wrong_sandbox_marker_refuses_to_start(seeded: Any, secrets: None) -> None:
    namespace, refs = seeded
    with pytest.raises(KernelError):
        await build_runtime(_profile(namespace, refs, marker="production"))


@pytest.mark.parametrize("task", ["shortage", "recommend"])
async def test_live_answers_are_verified_against_odoo(
    seeded: Any, secrets: None, task: str
) -> None:
    namespace, refs = seeded
    rt = await build_runtime(_profile(namespace, refs), task_kind=task)
    run = await rt.coordinator.start_run(rt.operator, task, rt.scope)
    assert run.state is RunState.SUCCEEDED, run.reason
    events = await rt.store.list_events(rt.operator.tenant_id, run.run_id)
    outcome = next(e for e in events if e.type == "outcome.reported")
    assert outcome.payload["status"] == "VERIFIED"
    if task == "shortage":
        proposal = next(e for e in events if e.type == "proposal.created")
        assert proposal.payload["arguments"]["shortage"] == "7"
