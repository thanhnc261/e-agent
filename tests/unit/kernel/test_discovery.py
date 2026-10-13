"""Member discovery read models (ADR 0017): authorization, safety and freshness."""

from __future__ import annotations

import pytest
from e_agent.contracts.capability import CapabilityBinding, CapabilityDescriptor, EffectKind
from e_agent.contracts.connection import (
    ConnectionDescriptor,
    ConnectionOwnership,
    ConnectionStatus,
)
from e_agent.contracts.context import Principal, TaskContext
from e_agent.kernel.connections import ConnectionCatalog
from e_agent.kernel.discovery import member_connections, project, task_catalog
from e_agent.kernel.errors import ErrorCode, KernelError
from e_agent.kernel.registry import PluginRegistry

TENANT = "tenant-a"


def principal(principal_id: str = "user-1", tenant_id: str = TENANT) -> Principal:
    return Principal(principal_id=principal_id, tenant_id=tenant_id, roles=frozenset({"member"}))


def context(scope: set[str], who: Principal | None = None) -> TaskContext:
    who = who or principal()
    return TaskContext(
        run_id="discovery",
        tenant_id=who.tenant_id,
        principal=who,
        resource_scope=frozenset(scope),
    )


def connection(
    connection_id: str,
    *,
    tenant_id: str = TENANT,
    ownership: ConnectionOwnership = ConnectionOwnership.TENANT_SHARED,
    owner: str | None = None,
    status: ConnectionStatus = ConnectionStatus.ACTIVE,
    subject: str | None = "integration-user",
) -> ConnectionDescriptor:
    return ConnectionDescriptor(
        tenant_id=tenant_id,
        connection_id=connection_id,
        version=3,
        integration_id="erp",
        ownership=ownership,
        owner_principal=owner,
        provider_subject=subject,
        secret_ref="secret://never-returned",
        status=status,
    )


class _Executor:
    """Minimal stand-in: the catalog only asks whether exactly one executor claims a binding."""

    def supports(self, binding: CapabilityBinding) -> bool:
        return True


class _Verifier:
    def __init__(self, contract_id: str) -> None:
        self._contract_id = contract_id

    def supports(self, contract_id: str) -> bool:
        return contract_id == self._contract_id


def registry_with(
    *contracts: tuple[str, EffectKind, list[str]], executors: int = 1
) -> PluginRegistry:
    registry = PluginRegistry({})
    for _ in range(executors):
        registry.executors.append(_Executor())  # type: ignore[arg-type]
    for contract_id, effect, connections in contracts:
        registry.capabilities[contract_id] = CapabilityDescriptor(
            contract_id=contract_id,
            effect=effect,
            input_schema_id="in.v1",
            output_schema_id="out.v1",
            description=f"{contract_id} description",
        )
        if effect is EffectKind.ANSWER:
            registry.verifiers.append(_Verifier(contract_id))  # type: ignore[arg-type]
        for connection_id in connections:
            registry.bindings.append(
                CapabilityBinding(
                    binding_id=f"{contract_id}@{connection_id}",
                    contract_id=contract_id,
                    plugin_id="p",
                    plugin_version="1.0.0",
                    connection_id=connection_id,
                )
            )
    return registry


def test_only_connections_this_requester_may_use_are_returned() -> None:
    catalog = ConnectionCatalog(
        [
            connection("conn-shared"),
            connection("conn-out-of-scope"),
            connection("conn-other-tenant", tenant_id="tenant-b"),
            connection("conn-mine", ownership=ConnectionOwnership.USER_DELEGATED, owner="user-1"),
            connection("conn-theirs", ownership=ConnectionOwnership.USER_DELEGATED, owner="user-2"),
            connection("conn-revoked", status=ConnectionStatus.REVOKED),
        ]
    )
    registry = registry_with(("erp.order.create.v1", EffectKind.WRITE, ["conn-shared"]))
    ctx = context({"conn-shared", "conn-mine", "conn-theirs", "conn-revoked"})

    ids = [c.connection_id for c in member_connections(catalog, registry, ctx)]
    assert ids == ["conn-mine", "conn-shared"]


def test_absence_carries_no_explanation_of_what_was_withheld() -> None:
    catalog = ConnectionCatalog([connection("conn-theirs", tenant_id="tenant-b")])
    projected = member_connections(catalog, registry_with(), context({"conn-theirs"}))
    assert projected == ()


def test_projection_never_carries_secret_material_or_health_claims() -> None:
    catalog = ConnectionCatalog([connection("conn-shared")])
    registry = registry_with(("erp.order.create.v1", EffectKind.WRITE, ["conn-shared"]))
    conn = member_connections(catalog, registry, context({"conn-shared"}))[0]
    assert not hasattr(conn, "secret_ref")
    assert conn.observed_health == "unknown"
    assert conn.configuration_status == "active"
    assert conn.acting_identity == "integration-user"
    assert conn.capabilities == ("erp.order.create.v1",)
    assert conn.revision == 3


def test_an_undisclosed_acting_identity_stays_none_instead_of_a_placeholder() -> None:
    catalog = ConnectionCatalog([connection("conn-shared", subject=None)])
    conn = member_connections(catalog, registry_with(), context({"conn-shared"}))[0]
    assert conn.acting_identity is None


@pytest.mark.parametrize(
    ("bound_to", "scope", "availability", "reason"),
    [
        (["conn-shared"], {"conn-shared"}, "available", None),
        (["conn-shared"], set(), "unavailable", "no_usable_connection"),
        (
            ["conn-shared", "conn-two"],
            {"conn-shared", "conn-two"},
            "unavailable",
            "ambiguous_binding",
        ),
        ([], {"conn-shared"}, "unavailable", "no_usable_connection"),
    ],
)
def test_catalog_availability_is_explicit(
    bound_to: list[str], scope: set[str], availability: str, reason: str | None
) -> None:
    catalog = ConnectionCatalog([connection("conn-shared"), connection("conn-two")])
    registry = registry_with(("erp.order.create.v1", EffectKind.WRITE, bound_to))
    template = task_catalog(catalog, registry, context(scope))[0]
    assert template.availability == availability
    assert template.unavailable_reason == reason
    assert template.required_capabilities == ("erp.order.create.v1",)


def test_host_only_and_read_capabilities_are_not_offered_as_task_types() -> None:
    registry = registry_with(
        ("erp.demand.read.v1", EffectKind.READ, ["conn-shared"]),
        ("erp.order.create.v1", EffectKind.WRITE, ["conn-shared"]),
    )
    registry.capabilities["erp.order.verify.v1"] = CapabilityDescriptor(
        contract_id="erp.order.verify.v1",
        effect=EffectKind.WRITE,
        input_schema_id="in.v1",
        output_schema_id="out.v1",
        agent_visible=False,
    )
    catalog = ConnectionCatalog([connection("conn-shared")])
    ids = [t.template_id for t in task_catalog(catalog, registry, context({"conn-shared"}))]
    assert ids == ["erp.order.create.v1"]


def test_projection_is_versioned_and_timestamped() -> None:
    catalog = ConnectionCatalog([connection("conn-shared")])
    projection = project(catalog, registry_with(), context({"conn-shared"}))
    assert projection.schema_version == "1"
    assert projection.observed_at.startswith("20")


def test_duplicate_bindings_on_one_connection_are_ambiguous_not_available() -> None:
    """The defect this guards: two admitted bindings for the same contract and the
    same connection collapse to one connection id, but ``PluginRegistry.resolve``
    refuses exactly that state, so the catalog must not call it available."""
    catalog = ConnectionCatalog([connection("conn-shared")])
    registry = registry_with(("erp.order.create.v1", EffectKind.WRITE, ["conn-shared"]))
    registry.bindings.append(
        CapabilityBinding(
            binding_id="erp.order.create.v1@conn-shared#second",
            contract_id="erp.order.create.v1",
            plugin_id="other-plugin",
            plugin_version="2.0.0",
            connection_id="conn-shared",
        )
    )
    # The host's own rule refuses to choose; the catalog must report the same thing.
    with pytest.raises(KernelError) as refused:
        registry.resolve("erp.order.create.v1", "conn-shared")
    assert refused.value.code is ErrorCode.CONFLICT

    template = task_catalog(catalog, registry, context({"conn-shared"}))[0]
    assert template.availability == "unavailable"
    assert template.unavailable_reason == "ambiguous_binding"


def test_a_contract_without_a_unique_executor_is_not_offered() -> None:
    catalog = ConnectionCatalog([connection("conn-shared")])
    registry = registry_with(
        ("erp.order.create.v1", EffectKind.WRITE, ["conn-shared"]), executors=2
    )
    template = task_catalog(catalog, registry, context({"conn-shared"}))[0]
    assert template.availability == "unavailable"
    assert template.unavailable_reason == "no_executor"


def test_an_answer_needs_one_usable_read_connection_and_a_verifier() -> None:
    registry = registry_with(("erp.shortage.answer.v1", EffectKind.ANSWER, []))
    registry.bindings.append(
        CapabilityBinding(
            binding_id="erp.demand.read.v1@conn-shared",
            contract_id="erp.demand.read.v1",
            plugin_id="p",
            plugin_version="1.0.0",
            connection_id="conn-shared",
        )
    )
    catalog = ConnectionCatalog([connection("conn-shared"), connection("conn-two")])
    assert task_catalog(catalog, registry, context({"conn-shared"}))[0].availability == "available"

    # No usable read connection at all.
    unreachable = task_catalog(catalog, registry, context(set()))[0]
    assert unreachable.unavailable_reason == "no_usable_connection"

    # A second usable read connection is ambiguity, not a free choice.
    registry.bindings.append(
        CapabilityBinding(
            binding_id="erp.demand.read.v1@conn-two",
            contract_id="erp.demand.read.v1",
            plugin_id="p",
            plugin_version="1.0.0",
            connection_id="conn-two",
        )
    )
    ambiguous = task_catalog(catalog, registry, context({"conn-shared", "conn-two"}))[0]
    assert ambiguous.unavailable_reason == "ambiguous_binding"


def test_an_answer_without_a_verifier_is_not_offered() -> None:
    """``_answer`` raises DEPENDENCY_UNAVAILABLE without a verifier, so a usable
    read connection alone is not proof that the answer can be produced."""
    registry = registry_with(("erp.shortage.answer.v1", EffectKind.ANSWER, []))
    registry.verifiers.clear()
    registry.bindings.append(
        CapabilityBinding(
            binding_id="erp.demand.read.v1@conn-shared",
            contract_id="erp.demand.read.v1",
            plugin_id="p",
            plugin_version="1.0.0",
            connection_id="conn-shared",
        )
    )
    catalog = ConnectionCatalog([connection("conn-shared")])
    template = task_catalog(catalog, registry, context({"conn-shared"}))[0]
    assert template.availability == "unavailable"
    assert template.unavailable_reason == "no_verifier"


def test_availability_never_relaxes_the_rule_it_reports() -> None:
    """Whatever the catalog calls available must actually resolve for the host."""
    catalog = ConnectionCatalog([connection("conn-shared"), connection("conn-two")])
    registry = registry_with(("erp.order.create.v1", EffectKind.WRITE, ["conn-shared"]))
    for scope in ({"conn-shared"}, {"conn-shared", "conn-two"}, set()):
        template = task_catalog(catalog, registry, context(scope))[0]
        if template.availability != "available":
            continue
        reachable = [
            c
            for c in scope
            if any(
                b.contract_id == "erp.order.create.v1" and b.connection_id == c
                for b in registry.bindings
            )
        ]
        assert len(reachable) == 1
        binding = registry.resolve("erp.order.create.v1", reachable[0])
        assert registry.executor_for(binding) is not None


def test_catalog_title_is_generic_and_keeps_operation_visible():
    from e_agent.kernel.discovery import _title

    assert _title("workspace.document.create-draft.v1") == "Document · create draft"
    assert _title("service.ticket.close.v2") == "Ticket · close"
