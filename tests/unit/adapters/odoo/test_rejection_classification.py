"""A 4xx the client cannot classify stays ambiguous at the executor (review 1d.7b R-3).

An unreadable rejection may be an identity rejection (``E_AGENT_CONFLICT``,
``E_AGENT_DUPLICATE_IN_FLIGHT``) that needs reconciliation, so it must never become
``KnownNoEffectError``.
"""

from types import SimpleNamespace

import httpx
import pytest
from e_agent.adapters.odoo.client import OdooJson2Client
from e_agent.adapters.odoo.executor import OdooExecutor
from e_agent.contracts.action import ActionRecord, ActionState
from e_agent.contracts.connection import ConnectionOwnership
from e_agent.contracts.context import Principal, TaskContext
from e_agent.erp.procurement import CREATE_DRAFT_PO
from e_agent.sdk.auth import AuthContext, Secret
from e_agent.sdk.errors import KnownNoEffectError

AUTH = AuthContext(
    connection_id="connection",
    connection_version=1,
    ownership=ConnectionOwnership.TENANT_SHARED,
    provider_subject="synthetic-user",
    method="api_key",
    _secret=Secret("synthetic-credential-canary"),
)
CTX = TaskContext(
    run_id="run",
    tenant_id="tenant",
    principal=Principal(principal_id="actor", tenant_id="tenant", roles=frozenset()),
    resource_scope=frozenset({"connection"}),
)
ACTION = ActionRecord(
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


class Credentials:
    async def context_for(self, ctx, connection_id):
        return AUTH


async def _execute(response: httpx.Response) -> None:
    client = OdooJson2Client(
        "http://127.0.0.1:8069", "synthetic", transport=httpx.MockTransport(lambda r: response)
    )
    executor = OdooExecutor(client, Credentials(), "owned-test")
    await executor.execute(CTX, SimpleNamespace(connection_id="connection"), ACTION, 1)


@pytest.mark.parametrize(
    "body",
    [["E_AGENT_CONFLICT: identity already reserved"], {"name": ["E_AGENT_CONFLICT"]}],
    ids=["list-body", "list-name"],
)
async def test_unclassifiable_rejection_is_not_known_no_effect(body: object) -> None:
    with pytest.raises(Exception) as error:  # noqa: PT011 - any ambiguous outcome
        await _execute(httpx.Response(409, json=body))
    assert not isinstance(error.value, KnownNoEffectError)


@pytest.mark.parametrize(
    ("response", "code"),
    [
        (httpx.Response(409, json={"message": "E_AGENT_STALE: facts changed"}), "E_AGENT_STALE"),
        (httpx.Response(400, content=b"not json"), "REJECTED"),
        (httpx.Response(403, json={"name": "odoo.exceptions.AccessError"}), "REJECTED"),
    ],
    ids=["allowed-code", "not-json", "unknown-name"],
)
async def test_classified_rejection_is_known_no_effect(response: httpx.Response, code: str) -> None:
    with pytest.raises(KnownNoEffectError) as error:
        await _execute(response)
    assert error.value.code == code
