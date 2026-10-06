"""Credential resolution is scoped, fails closed and never leaks secret material."""

import pytest
from e_agent.contracts.connection import ConnectionDescriptor, ConnectionOwnership
from e_agent.contracts.context import Principal, TaskContext
from e_agent.kernel.connections import ConnectionCatalog
from e_agent.kernel.credentials import CredentialService
from e_agent.sdk.auth import AuthRequired, ScopeMissing, Secret

pytestmark = pytest.mark.asyncio
CANARY = "api-key-CANARY-5521"


class Store:
    async def get(self, ref: str) -> Secret:
        assert ref == "secretref:local/odoo"
        return Secret(CANARY)

    async def put(self, ref: str, value: Secret) -> None: ...

    async def delete(self, ref: str) -> None: ...


def _ctx(
    principal: str = "alice", scope: frozenset[str] = frozenset({"odoo", "other"})
) -> TaskContext:
    return TaskContext(
        run_id="r",
        tenant_id="t",
        principal=Principal(principal_id=principal, tenant_id="t", roles=frozenset({"requester"})),
        resource_scope=scope,
    )


def _service() -> CredentialService:
    conns = [
        ConnectionDescriptor(
            tenant_id="t",
            connection_id="odoo",
            version=3,
            integration_id="odoo19",
            ownership=ConnectionOwnership.TENANT_SHARED,
            provider_subject="svc",
            secret_ref="secretref:local/odoo",
        ),
        ConnectionDescriptor(
            tenant_id="t",
            connection_id="other",
            version=1,
            integration_id="crm-x",
            ownership=ConnectionOwnership.TENANT_SHARED,
        ),
    ]
    return CredentialService(
        ConnectionCatalog(conns), Store(), {"odoo19": {"method": "api_key", "prefix": "bearer "}}
    )


async def test_context_applies_header_and_redacts() -> None:
    auth = await _service().scoped("odoo19").context_for(_ctx(), "odoo")
    headers: dict[str, str] = {}
    auth.apply(headers)
    assert headers["Authorization"] == f"bearer {CANARY}"
    assert CANARY not in repr(auth)
    assert auth.connection_version == 3


async def test_adapter_cannot_use_another_integrations_connection() -> None:
    with pytest.raises(AuthRequired):
        await _service().scoped("odoo19").context_for(_ctx(), "other")


async def test_out_of_scope_connection_rejected_before_secret_access() -> None:
    from e_agent.kernel.errors import KernelError

    with pytest.raises(KernelError):
        await _service().scoped("odoo19").context_for(_ctx(scope=frozenset()), "odoo")


async def test_missing_secret_is_auth_required() -> None:
    with pytest.raises(AuthRequired):
        await _service().scoped("crm-x").context_for(_ctx(), "other")


async def test_scope_check() -> None:
    auth = await _service().scoped("odoo19").context_for(_ctx(), "odoo")
    with pytest.raises(ScopeMissing):
        auth.require_scopes(frozenset({"purchase.write"}))
