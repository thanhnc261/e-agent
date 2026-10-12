"""Member-readable discovery read models (ADR 0017).

Two projections assembled from metadata the host has already admitted: the
connections a requester may actually use, and the task templates they may
actually start. Both reuse the execution authority that already exists —
``ConnectionCatalog.usable`` — so a read model can never widen access.

Nothing here performs a provider call. Observed health is therefore always
unknown, and a connection outside the requester's tenant, scope or ownership is
simply absent: the response never explains what was withheld.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from e_agent.contracts.capability import EffectKind
from e_agent.contracts.common import utc_now
from e_agent.contracts.context import TaskContext

from .connections import ConnectionCatalog
from .errors import ErrorCode, KernelError
from .registry import PluginRegistry

SCHEMA_VERSION = "1"

Availability = Literal["available", "unavailable"]
UnavailableReason = Literal[
    "no_usable_connection",
    "ambiguous_binding",
    "no_executor",
    "no_verifier",
]


@dataclass(frozen=True)
class MemberConnection:
    """One connection, described with member-safe fields only."""

    connection_id: str
    integration_id: str
    ownership: str
    #: The identity whose credential executes, when the connection publishes one.
    acting_identity: str | None
    allowed_resources: tuple[str, ...]
    #: Capability contracts bound through this connection and admitted at startup.
    capabilities: tuple[str, ...]
    #: Recorded configuration state. Not a health check and not a permission.
    configuration_status: str
    #: Always "unknown": rendering never probes a provider (ADR 0017).
    observed_health: Literal["unknown"]
    revision: int


@dataclass(frozen=True)
class TaskTemplate:
    """One admitted task type a requester can ask for."""

    template_id: str
    title: str
    description: str
    #: How a requester supplies input today. Free text is the only supported intent.
    input_intent: Literal["free_text"]
    availability: Availability
    unavailable_reason: UnavailableReason | None
    required_capabilities: tuple[str, ...]
    #: Admitted contracts only; never a binding or a connection the client may choose.
    bounded_context: str


@dataclass(frozen=True)
class DiscoveryProjection:
    schema_version: str
    observed_at: str
    connections: tuple[MemberConnection, ...]
    templates: tuple[TaskTemplate, ...]


def _usable_connection_ids(catalog: ConnectionCatalog, ctx: TaskContext) -> list[str]:
    usable = []
    for conn in catalog.for_tenant(ctx.tenant_id):
        try:
            catalog.usable(ctx, conn.connection_id)
        except KernelError:
            continue  # Absent, out of scope, inactive or someone else's delegation.
        usable.append(conn.connection_id)
    return sorted(usable)


def member_connections(
    catalog: ConnectionCatalog, registry: PluginRegistry, ctx: TaskContext
) -> tuple[MemberConnection, ...]:
    bound: dict[str, set[str]] = {}
    for binding in registry.bindings:
        if binding.contract_id in registry.capabilities:
            bound.setdefault(binding.connection_id, set()).add(binding.contract_id)
    projected = []
    for connection_id in _usable_connection_ids(catalog, ctx):
        conn = catalog.usable(ctx, connection_id)
        projected.append(
            MemberConnection(
                connection_id=conn.connection_id,
                integration_id=conn.integration_id,
                ownership=str(conn.ownership),
                acting_identity=conn.provider_subject,
                allowed_resources=tuple(sorted(conn.allowed_resources)),
                capabilities=tuple(sorted(bound.get(conn.connection_id, set()))),
                configuration_status=str(conn.status),
                observed_health="unknown",
                revision=conn.version,
            )
        )
    return tuple(projected)


def _title(contract_id: str) -> str:
    """A neutral label from the contract id; no provider or marketing name."""
    _, _, rest = contract_id.partition(".")
    parts = rest.rsplit(".v", 1)[0].split(".")
    label = " · ".join(part.replace("-", " ") for part in parts)
    return label[:1].upper() + label[1:]


def _availability(
    registry: PluginRegistry, usable: set[str], contract_id: str, effect: EffectKind
) -> UnavailableReason | None:
    """Why this task type cannot be started, or ``None`` when it can.

    Availability is decided with the host's own resolution rules rather than a
    cheaper approximation of them, so the catalog cannot promise something the
    coordinator would refuse. Nothing here relaxes those rules: the checks call
    the registry and report its refusal, they never resolve an ambiguity.
    """
    if effect is EffectKind.ANSWER:
        # An answer has no provider binding of its own: it is produced and then
        # recomputed through the run's read connection, so the workspace must have
        # exactly one usable read connection, as the agent tool surface requires.
        reachable = sorted({b.connection_id for b in registry.bindings} & usable)
        if not reachable:
            return "no_usable_connection"
        if len(reachable) > 1:
            return "ambiguous_binding"
        try:
            # An answer without an independent verifier fails at execution
            # (DEPENDENCY_UNAVAILABLE), so it is not offered as available.
            if registry.verifier_for(contract_id) is None:
                return "no_verifier"
        except KernelError:
            return "ambiguous_binding"  # More than one verifier claims the contract.
        return None

    reachable = sorted(
        {b.connection_id for b in registry.bindings if b.contract_id == contract_id} & usable
    )
    if not reachable:
        return "no_usable_connection"
    if len(reachable) > 1:
        # The host never picks between connections, and neither may a client.
        return "ambiguous_binding"
    try:
        # Duplicate bindings for the same contract and connection are a conflict the
        # registry refuses; counting distinct connections would hide exactly that.
        binding = registry.resolve(contract_id, reachable[0])
    except KernelError as exc:
        return "no_usable_connection" if exc.code is ErrorCode.FORBIDDEN else "ambiguous_binding"
    try:
        registry.executor_for(binding)
    except KernelError:
        return "no_executor"
    return None


def task_catalog(
    catalog: ConnectionCatalog, registry: PluginRegistry, ctx: TaskContext
) -> tuple[TaskTemplate, ...]:
    """Admitted, requester-visible task types with their actual availability.

    A template is assistance for task entry. The server still resolves the binding
    and the connection and authorizes the action again at execution, so nothing
    here lets a client or a model choose a credential.
    """
    usable = set(_usable_connection_ids(catalog, ctx))
    templates = []
    for contract_id, capability in sorted(registry.capabilities.items()):
        if not capability.agent_visible or capability.effect is EffectKind.READ:
            continue  # Host reads are not task types a requester starts.
        reason = _availability(registry, usable, contract_id, capability.effect)
        templates.append(
            TaskTemplate(
                template_id=contract_id,
                title=_title(contract_id),
                description=capability.description,
                input_intent="free_text",
                availability="available" if reason is None else "unavailable",
                unavailable_reason=reason,
                required_capabilities=(contract_id,),
                bounded_context=capability.bounded_context,
            )
        )
    return tuple(templates)


def project(
    catalog: ConnectionCatalog, registry: PluginRegistry, ctx: TaskContext
) -> DiscoveryProjection:
    return DiscoveryProjection(
        schema_version=SCHEMA_VERSION,
        observed_at=utc_now().isoformat(),
        connections=member_connections(catalog, registry, ctx),
        templates=task_catalog(catalog, registry, ctx),
    )
