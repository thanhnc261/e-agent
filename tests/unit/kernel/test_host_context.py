"""Host context hints: resolved through connection mappings or dropped (UI §4.7)."""

import pytest
from e_agent.contracts.connection import ConnectionDescriptor, ConnectionOwnership
from e_agent.contracts.context import HostContext, Principal, ResourceHint, TaskContext
from e_agent.kernel.connections import ConnectionCatalog
from pydantic import ValidationError

T = "tenant-a"


def _conn(cid: str, integration: str, **kw: object) -> ConnectionDescriptor:
    return ConnectionDescriptor(
        tenant_id=kw.pop("tenant", T),  # type: ignore[arg-type]
        connection_id=cid,
        version=1,
        integration_id=integration,
        ownership=ConnectionOwnership.TENANT_SHARED,
        **kw,  # type: ignore[arg-type]
    )


def _ctx(scope: set[str]) -> TaskContext:
    p = Principal(principal_id="u1", tenant_id=T, roles=frozenset())
    return TaskContext(run_id="r", tenant_id=T, principal=p, resource_scope=frozenset(scope))


def _hint(system: str, rtype: str = "purchase.order", ext: str = "42") -> ResourceHint:
    return ResourceHint(system_hint=system, resource_type_hint=rtype, external_id_hint=ext)


def test_only_unambiguous_in_scope_hints_resolve() -> None:
    catalog = ConnectionCatalog(
        [
            _conn("erp-1", "erp-x", allowed_resources=frozenset({"purchase.order"})),
            _conn("crm-1", "crm-y"),
            _conn("crm-2", "crm-y"),
            _conn("other", "erp-x", tenant="tenant-b"),
        ]
    )
    resolved, dropped = catalog.resolve_hints(
        _ctx({"erp-1", "crm-1", "crm-2"}),
        [
            _hint("erp-x"),  # resolves to erp-1 (other tenant's connection is invisible)
            _hint("erp-x", rtype="account.move"),  # resource type not allowed
            _hint("crm-y"),  # ambiguous: never choose credentials
            _hint("unknown-system"),
        ],
    )
    assert [(h.connection_id, h.external_id) for h in resolved] == [("erp-1", "42")]
    assert dropped == 3


def test_out_of_scope_connection_never_resolves() -> None:
    catalog = ConnectionCatalog([_conn("erp-1", "erp-x")])
    resolved, dropped = catalog.resolve_hints(_ctx(set()), [_hint("erp-x")])
    assert resolved == () and dropped == 1


@pytest.mark.parametrize(
    "origin",
    ["https://host.example/path?token=secret", "javascript:alert(1)", "https://u:p@host.example"],
)
def test_page_url_must_be_origin_only(origin: str) -> None:
    with pytest.raises(ValidationError):
        HostContext(host_kind="embedded", page_url_origin=origin)
    assert HostContext(
        host_kind="embedded", page_url_origin="https://h.example/"
    ).page_url_origin == ("https://h.example")
