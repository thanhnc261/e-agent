"""The adapter preserves host targeting and logical-operation uncertainty."""

import json
from types import SimpleNamespace

import httpx
import pytest
from e_agent.adapters.odoo.client import OdooJson2Client, OdooRejected
from e_agent.adapters.odoo.executor import OdooExecutor
from e_agent.contracts.action import ActionRecord, ActionState
from e_agent.contracts.connection import ConnectionOwnership
from e_agent.contracts.context import Principal, TaskContext
from e_agent.erp.procurement import CREATE_DRAFT_PO, OPEN_DEMANDS_READ
from e_agent.sdk.auth import AuthContext, Secret
from e_agent.sdk.errors import KnownNoEffectError
from e_agent.sdk.ports import ReadRequest

AUTH = AuthContext(
    connection_id="connection",
    connection_version=1,
    ownership=ConnectionOwnership.TENANT_SHARED,
    provider_subject="synthetic-user",
    method="api_key",
    _secret=Secret("synthetic-credential-canary"),
    _placement={"header": "Authorization", "prefix": "bearer "},
)
TARGET = {
    "database": "synthetic",
    "company_id": "7",
    "sandbox_marker": "owned",
    "bridge_version": "19.0.0.4.0",
}


async def test_transport_injects_exact_host_target_and_disallows_override():
    seen = []

    def response(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"ok": True})

    client = OdooJson2Client(
        "http://127.0.0.1:8069", "synthetic", transport=httpx.MockTransport(response), target=TARGET
    )
    await client.call(AUTH, "e_agent.bridge", "create_draft_purchase_order", payload={})
    assert seen == [{"payload": {}, "context": {"e_agent_target": TARGET}}]
    with pytest.raises(ValueError, match="override the host target"):
        await client.call(AUTH, "e_agent.bridge", "anything", context={})
    assert len(seen) == 1


async def test_provider_rejection_does_not_export_raw_body_or_credentials():
    client = OdooJson2Client(
        "http://127.0.0.1:8069",
        "synthetic",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                400,
                json={
                    "message": "synthetic-credential-canary",
                    "name": "synthetic-credential-canary",
                },
            )
        ),
    )
    with pytest.raises(OdooRejected) as error:
        await client.call(AUTH, "e_agent.bridge", "anything")
    assert error.value.code == "REJECTED"
    assert "canary" not in error.value.safe_message


@pytest.mark.parametrize("code", ["E_AGENT_DUPLICATE_IN_FLIGHT", "E_AGENT_CONFLICT"])
async def test_identity_rejection_requires_reconciliation_instead_of_no_effect(code):
    client = OdooJson2Client(
        "http://127.0.0.1:8069",
        "synthetic",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                400, json={"message": code + ": identity already reserved"}
            )
        ),
        target=TARGET,
    )

    class Credentials:
        async def context_for(self, ctx, connection_id):
            return AUTH

    executor = OdooExecutor(client, Credentials(), "owned-test")
    ctx = TaskContext(
        run_id="run",
        tenant_id="tenant",
        principal=Principal(principal_id="actor", tenant_id="tenant", roles=frozenset()),
        resource_scope=frozenset({"connection"}),
    )
    action = ActionRecord(
        action_id="action",
        tenant_id="tenant",
        run_id="run",
        logical_operation_id="operation",
        contract_id=CREATE_DRAFT_PO,
        binding_id="binding",
        connection_id="connection",
        connection_version=1,
        credential_subject="synthetic-user",
        arguments={
            "demand_ref": "demand:d",
            "product_ref": "product:p",
            "supplier_ref": "supplier:s",
            "offer_ref": "offer:o",
            "quantity": "1",
            "unit": "unit",
            "currency": "USD",
            "unit_price": "10",
            "subtotal": "10",
            "requested_date": "2026-10-07",
        },
        digest="digest",
        state=ActionState.DISPATCHING,
        revision=1,
    )
    with pytest.raises(RuntimeError) as error:
        await executor.execute(ctx, SimpleNamespace(connection_id="connection"), action, 1)
    assert not isinstance(error.value, KnownNoEffectError)


async def test_revoked_credentials_are_known_no_effect_before_http():
    from e_agent.sdk.auth import CredentialRevoked

    calls = []

    class Credentials:
        async def context_for(self, ctx, connection_id):
            raise CredentialRevoked("revoked")

    client = OdooJson2Client(
        "http://127.0.0.1:8069",
        "synthetic",
        transport=httpx.MockTransport(
            lambda request: calls.append(request) or httpx.Response(200, json={})
        ),
    )
    executor = OdooExecutor(client, Credentials(), "owned-test")
    with pytest.raises(KnownNoEffectError):
        await executor._call(SimpleNamespace(), "connection", "create_draft_purchase_order")
    assert calls == []


@pytest.mark.parametrize(
    ("command", "digest", "committed"),
    [
        ("create_lead", "digest", True),
        ("create_draft_purchase_order", "digest", False),
        ("create_lead", "different", False),
        (None, "digest", False),
    ],
)
async def test_reconciliation_requires_matching_command_and_digest(command, digest, committed):
    from e_agent.erp.crm import CREATE_LEAD

    class Credentials:
        async def context_for(self, ctx, connection_id):
            return AUTH

    raw = {
        "found": True,
        "command": command,
        "payload_digest": digest,
        "leads": [{"external_ref": "crm.lead:synthetic"}],
    }
    client = OdooJson2Client(
        "http://127.0.0.1:8069",
        "synthetic",
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=raw)),
    )
    executor = OdooExecutor(client, Credentials(), "owned-test")
    action = SimpleNamespace(
        contract_id=CREATE_LEAD,
        digest="digest",
        logical_operation_id="operation",
        action_id="action",
        arguments={
            "contact_ref": "contact:1",
            "name": "Synthetic",
            "team_ref": "team:1",
            "owner_ref": "owner:1",
            "source_ref": "source:1",
            "expected_revenue": "0",
        },
    )
    receipt = await executor.reconcile(
        SimpleNamespace(), SimpleNamespace(connection_id="connection"), action
    )
    assert (receipt is not None) is committed


async def test_open_demands_read_copies_refs_exactly_and_passes_the_namespace():
    seen = []

    def response(request):
        seen.append((request.url.path, json.loads(request.content)))
        return httpx.Response(
            200,
            json={
                "demands": [
                    {
                        "demand_ref": "odoo/e_agent.demand/1",
                        "product_ref": "odoo/product.product/201",
                        "product_name": "Widget A",
                        "quantity": 12.0,
                        "unit": "Units",
                        "requested_date": "2026-10-20",
                        "secret_note": "x",
                    }
                ],
                "complete": True,
            },
        )

    client = OdooJson2Client(
        "http://127.0.0.1:8069", "synthetic", transport=httpx.MockTransport(response), target=TARGET
    )

    class Credentials:
        async def context_for(self, ctx, connection_id):
            return AUTH

    executor = OdooExecutor(client, Credentials(), "owned-test")
    ctx = TaskContext(
        run_id="run",
        tenant_id="tenant",
        principal=Principal(principal_id="actor", tenant_id="tenant", roles=frozenset()),
        resource_scope=frozenset({"connection"}),
    )
    obs = await executor.read(
        ctx,
        SimpleNamespace(connection_id="connection"),  # type: ignore[arg-type]
        ReadRequest("r", OPEN_DEMANDS_READ, "connection", {}),
    )
    [row] = obs.data["demands"]
    assert set(row) == {
        "demand_ref",
        "product_ref",
        "product_name",
        "quantity",
        "unit",
        "requested_date",
    }
    assert row["quantity"] == "12"
    assert row["demand_ref"] == "odoo/e_agent.demand/1"
    assert row["product_ref"] == "odoo/product.product/201"
    assert obs.data["complete"] is True
    assert seen[0][0].endswith("/e_agent.bridge/read_open_demands")
    assert seen[0][1]["namespace"] == "owned-test"
