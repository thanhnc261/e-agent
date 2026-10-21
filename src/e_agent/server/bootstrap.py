"""Composition root: discover/admit plugins, wire kernel services (MVP design §6).

The only place that chooses concrete implementations. Fixture providers are
plugins a fixture profile enables, admitted like any other; live profiles must
pass the sandbox-marker check before any run starts.
"""

from __future__ import annotations

import ipaddress
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

from e_agent.adapters.postgres import PostgresRunStore, apply_migrations, database_name
from e_agent.adapters.pydantic_ai import PydanticAiDriver, ToolSpec, litellm_model, ollama_model
from e_agent.adapters.secretstore_local import LocalSecretStore
from e_agent.adapters.shacl import ShaclPlanValidator
from e_agent.contracts.capability import EffectKind
from e_agent.contracts.context import Principal, TaskContext
from e_agent.contracts.data import BoundaryBasis, DataBoundary, RouteBoundary
from e_agent.contracts.features import FeatureMode
from e_agent.kernel.connections import ConnectionCatalog
from e_agent.kernel.coordinator import RunCoordinator
from e_agent.kernel.credentials import CredentialService
from e_agent.kernel.errors import ErrorCode, KernelError
from e_agent.kernel.memory_conversations import InMemoryConversationStore
from e_agent.kernel.policy import DefaultPolicy
from e_agent.kernel.registry import EnabledPlugin, PluginRegistry
from e_agent.sdk.auth import SecretStore
from e_agent.sdk.discovery import DiscoveredPlugin, discover
from e_agent.sdk.ports import AgentDriver, DriverRequest

from .environment import optional_env, require_env
from .profile import DriverConfig, Profile


@dataclass
class Runtime:
    profile: Profile
    coordinator: RunCoordinator
    store: Any
    registry: PluginRegistry
    operator: Principal
    scope: frozenset[str]
    connections: ConnectionCatalog | None = None
    sandbox: dict[str, Any] = field(default_factory=dict)
    versions: dict[str, Any] = field(default_factory=dict)
    route: RouteBoundary | None = None
    """The model route's data boundary and its basis (ADR 0030)."""

    def route_facts(self) -> dict[str, Any]:
        """The route boundary facts readiness and the evidence bundle both report (ADR 0030)."""
        return route_facts(self.profile, self.route)

    def diagnostics(self) -> dict[str, dict[str, Any]]:
        """The admitted plugins' diagnostics, by plugin id (fixture runs and tests)."""
        return {pid: dict(hook()) for pid, hook in sorted(self.registry.diagnostics.items())}


def route_facts(profile: Profile, route: RouteBoundary | None) -> dict[str, Any]:
    """The route boundary facts as plain values (ADR 0030): what readiness and the evidence
    bundle report, and what the kernel's per-call route check reads (ADR 0032 §9)."""
    return {
        "data_boundary": route.boundary if route else None,
        "data_boundary_basis": route.basis if route else None,
        "data_processing_declared": profile.data_processing is not None,
    }


def runtime_versions(
    profile: Profile, registry: PluginRegistry, driver: AgentDriver
) -> dict[str, Any]:
    """Versions recorded in every evidence bundle (MVP design §11, ADR 0010)."""
    from importlib import metadata

    dists = {}
    for dist in metadata.distributions():
        name = dist.metadata["Name"] or ""
        if name.startswith("e-agent-") or name in {"pydantic-ai-slim", "pyshacl"}:
            dists[name] = dist.version
    return {
        "distributions": dict(sorted(dists.items())),
        "plugins": sorted(registry.report.admitted),
        "driver": getattr(driver, "driver_id", type(driver).__name__),
        "driver_versions": getattr(driver, "versions", {}),
        "model": profile.driver.model if profile.driver.kind == "pydantic-ai" else None,
        "model_provider": profile.driver.provider if profile.driver.kind == "pydantic-ai" else None,
        "profile_environment": profile.environment,
    }


async def open_store(profile: Profile) -> Any:
    if profile.store.kind == "memory":
        if profile.environment == "live":
            raise KernelError(ErrorCode.STARTUP_REJECTED, "live runs require a PostgreSQL ledger")
        return InMemoryConversationStore()  # the run store and the conversation store
    dsn = require_env(profile.store.dsn_env)
    check_ledger_separation(profile, dsn)
    await apply_migrations(dsn)
    return await PostgresRunStore.open(dsn)


def check_ledger_separation(profile: Profile, dsn: str) -> None:
    """Threat model T16: the e-agent ledger never lives in a provider's database."""
    ledger_db = database_name(dsn)
    provider_dbs = {
        str(cfg.settings["database"])
        for cfg in profile.enabled_plugins.values()
        if "database" in cfg.settings
    }
    if ledger_db in provider_dbs:
        raise KernelError(
            ErrorCode.STARTUP_REJECTED,
            "the ledger database must be separate from provider databases",
        )


def tool_specs(registry: PluginRegistry, profile: Profile) -> list[ToolSpec]:
    """Expose agent-visible capabilities that have exactly one binding in scope."""
    specs: list[ToolSpec] = []
    for cap in sorted(registry.capabilities.values(), key=lambda c: c.contract_id):
        if not cap.agent_visible:
            continue
        bound = (
            registry.bindings
            if cap.effect is EffectKind.ANSWER
            else [b for b in registry.bindings if b.contract_id == cap.contract_id]
        )
        # answers have no provider binding: they verify through the run's read connection
        connections = sorted({b.connection_id for b in bound})
        if len(connections) != 1:
            continue  # unbound or ambiguous: never let the model choose credentials
        schema = registry.input_schemas.get(cap.input_schema_id)
        if schema is None:
            raise KernelError(ErrorCode.STARTUP_REJECTED, f"no schema for {cap.input_schema_id}")
        specs.append(
            ToolSpec(
                contract_id=cap.contract_id,
                effect=cap.effect,
                description=cap.description,
                parameters=schema,
                connection_id=connections[0],
            )
        )
    return specs


def check_task_tool_sets(registry: PluginRegistry, profile: Profile) -> None:
    """In ``execution_ir: on`` a run's tool set is its definition's capabilities (ADR 0028,
    D6), so every admitted definition's capability must be one `tool_specs` offers. One it
    leaves out (unbound, or bound on more than one connection) refuses startup with the
    capabilities named, never a silent drop from the run's tool set (2c.2 review R-1, PR-10).
    ``off`` and ``shadow`` narrow nothing and are not checked."""
    if profile.features.execution_ir is not FeatureMode.ON:
        return
    offered = {spec.contract_id for spec in tool_specs(registry, profile)}
    missing = sorted(
        {
            contract_id
            for task in registry.task_definitions.values()
            for contract_id in task.capabilities
            if contract_id not in offered
        }
    )
    if missing:
        raise KernelError(
            ErrorCode.STARTUP_REJECTED,
            "execution_ir: on offers each task definition capability to the driver; "
            f"{', '.join(missing)} cannot be offered (unbound, or bound on more than one "
            "connection)",
        )


MODEL_ENDPOINTS: dict[str, tuple[str, str]] = {
    "ollama": ("E_AGENT_OLLAMA_URL", "http://localhost:11434/v1"),
    "litellm": ("E_AGENT_LITELLM_URL", "http://localhost:4000"),
}
"""Default endpoint variable and URL per model provider (ADR 0021)."""


_LOOPBACK_NETS = (ipaddress.ip_network("127.0.0.0/8"), ipaddress.ip_network("::1/128"))


def _is_loopback_host(base_url: str) -> bool:
    """Literal check, no DNS lookup: ``localhost``, ``127.0.0.0/8`` or ``::1`` (ADR 0030)."""
    try:
        host = urlsplit(base_url).hostname
    except ValueError:
        return False
    if host is None:
        return False
    if host.lower() == "localhost":
        return True
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        return False
    return any(addr in net for net in _LOOPBACK_NETS)


def effective_boundary(
    cfg: DriverConfig, base_url: str | None
) -> tuple[DataBoundary, BoundaryBasis]:
    """The route's data boundary and how it is known (ADR 0030, Phase 3 plan D2).

    The scripted driver makes no model call: ``local``, verified. An ``ollama`` route on a
    literal loopback host is ``local`` and verified, also when the profile declares ``local``.
    Any other declared boundary is ``declared``; an undeclared route is ``hosted:unknown`` by
    default. A LiteLLM route is never verified: its upstream is outside e-agent.
    """
    if cfg.kind != "pydantic-ai":
        return "local", "verified"
    loopback = cfg.provider == "ollama" and base_url is not None and _is_loopback_host(base_url)
    if cfg.data_boundary is None:
        return ("local", "verified") if loopback else ("hosted:unknown", "default")
    if cfg.data_boundary == "local" and loopback:
        return "local", "verified"
    return cfg.data_boundary, "declared"


def route_base_url(cfg: DriverConfig) -> str:
    env_name, default_url = MODEL_ENDPOINTS[cfg.provider]
    return optional_env(cfg.base_url_env or env_name, default_url)


def check_route_boundary(profile: Profile) -> RouteBoundary:
    """Startup rule (ADR 0030): a route that is not ``local`` needs ``data_processing``,
    unless ``features.context_assembler`` is ``on``: every run that profile prepares is
    pinned ``on``, so what it sends the route is the masked pack (ADR 0032 §5, §9; Task
    3d.5). A run pinned otherwise that resumes on the route makes no model call (the per-call
    route check). ``local_only`` refuses a hosted route whatever the toggle says. Messages
    name the setting, never its value.
    """
    cfg = profile.driver
    base_url = route_base_url(cfg) if cfg.kind == "pydantic-ai" else None
    boundary, basis = effective_boundary(cfg, base_url)
    if boundary != "local":
        if profile.local_only:
            raise KernelError(
                ErrorCode.STARTUP_REJECTED,
                "local_only is set but the model route is not local; "
                "use a local route or unset local_only",
            )
        masked = profile.features.context_assembler is FeatureMode.ON
        if profile.data_processing is None and not masked:
            raise KernelError(
                ErrorCode.STARTUP_REJECTED,
                "the model route is not local and the profile has no data_processing "
                "declaration (data_owner, legal_basis, region)",
            )
    return RouteBoundary(boundary=boundary, basis=basis)


def check_conversation_toggle(profile: Profile) -> None:
    """Startup rule (ADR 0023 §9): ``features.conversations`` ``on`` needs
    ``features.context_assembler`` ``on``. Both modes are pinned together, so a run pinned
    ``conversations: on`` is pinned ``context_assembler: on`` and the per-call route check
    (ADR 0032 §9) covers the carried context it sends. ``shadow`` carries nothing to the
    driver and is allowed with any ``context_assembler`` mode. The message names the
    settings, never a value."""
    on, features = FeatureMode.ON, profile.features
    if features.conversations is on and features.context_assembler is not on:
        raise KernelError(
            ErrorCode.STARTUP_REJECTED,
            "features.conversations needs features.context_assembler: carried conversation "
            "context is sent only in the context pack; raise features.context_assembler or "
            "lower features.conversations",
        )


def build_driver(profile: Profile, registry: PluginRegistry) -> AgentDriver:
    cfg = profile.driver
    if not cfg.model:
        raise KernelError(
            ErrorCode.STARTUP_REJECTED, f"pydantic-ai driver needs a {cfg.provider} model"
        )
    base_url = route_base_url(cfg)
    try:
        if cfg.provider == "litellm":
            api_key = None
            if cfg.api_key_env is not None:
                api_key = require_env(cfg.api_key_env, purpose="for the LiteLLM proxy")
            model = litellm_model(cfg.model, base_url, api_key)
        else:
            model = ollama_model(cfg.model, base_url)
    except ValueError as exc:
        raise KernelError(ErrorCode.STARTUP_REJECTED, str(exc)) from exc
    settings: dict[str, object] = {}
    if cfg.temperature is not None:
        settings["temperature"] = float(cfg.temperature)
    return PydanticAiDriver(
        model,
        tool_specs(registry, profile),
        guidance=registry.agent_guidance,
        requests_per_step=cfg.requests_per_step,
        model_settings=settings,
    )


def _secret_store(profile: Profile) -> LocalSecretStore | None:
    if not any(c.secret_ref for c in profile.connections):
        return None
    try:
        return LocalSecretStore.from_environment()
    except ValueError as exc:
        raise KernelError(ErrorCode.STARTUP_REJECTED, str(exc)) from exc


def _operator(profile: Profile) -> Principal:
    return Principal(
        principal_id=profile.operator.principal_id,
        tenant_id=profile.tenant_id,
        roles=profile.operator.roles,
        display_name=profile.operator.display_name,
    )


def admit_plugins(
    profile: Profile,
    catalog: ConnectionCatalog,
    discovered: Iterable[DiscoveredPlugin],
    secrets: SecretStore | None,
    plugin_settings: Mapping[str, Mapping[str, Any]] | None = None,
) -> tuple[PluginRegistry, CredentialService]:
    """Admit the profile's enabled plugins; credentials follow their manifests.

    ``plugin_settings`` overrides settings of enabled plugins, by plugin id, in
    fixture profiles only: a live plugin runs with its profile's settings. The
    plugin's factory checks them.
    """
    overrides = dict(plugin_settings or {})
    if overrides and profile.environment != "fixture":
        raise KernelError(
            ErrorCode.STARTUP_REJECTED, "plugin settings overrides are for fixture profiles only"
        )
    not_enabled = sorted(set(overrides) - set(profile.enabled_plugins))
    if not_enabled:
        raise KernelError(
            ErrorCode.STARTUP_REJECTED, f"settings given for plugins not enabled: {not_enabled}"
        )
    # The profile's environment and budgets drive the ADR 0029 live refusal of defaulted
    # write declarations and the ADR 0028 budget narrowing of task definitions.
    registry = PluginRegistry(
        profile.bindings, environment=profile.environment, budgets=profile.budgets
    )
    credentials = CredentialService(catalog, secrets, registry.auth_placements)
    enabled = {
        pid: EnabledPlugin(
            cfg.version,
            cfg.manifest_sha256,
            {**cfg.settings, **overrides.get(pid, {})},
            artifact_sha256=cfg.artifact_sha256,
            allow_unverified_fixture=profile.environment == "fixture",
        )
        for pid, cfg in profile.enabled_plugins.items()
    }
    registry.admit(discovered, enabled, credentials_for=credentials.scoped)
    _check_connection_owners(profile, registry)
    # Task definitions need the final binding set (ADR 0028).
    registry.admit_task_definitions()
    return registry, credentials


def _check_connection_owners(profile: Profile, registry: PluginRegistry) -> None:
    """In a live profile every connection belongs to an enabled plugin, and a binding
    uses only its own plugin's connections.

    The live sandbox guard probes the providers that connections name, and live
    credentials are looked up by the connection's integration id as a plugin id; a
    binding on another integration's connection would route to a provider the guard
    never probed (phase review 1d R-1). Fixture profiles are never probed, and their
    test packs may name an integration apart from the plugin.
    """
    if profile.environment != "live":
        return
    owners = {conn.connection_id: conn.integration_id for conn in profile.connections}
    for connection_id, integration_id in owners.items():
        if integration_id not in profile.enabled_plugins:
            raise KernelError(
                ErrorCode.STARTUP_REJECTED,
                f"connection {connection_id} names integration {integration_id!r}, "
                "which is not an enabled plugin",
            )
    for binding in registry.bindings:
        owner = owners.get(binding.connection_id)
        if owner != binding.plugin_id:
            raise KernelError(
                ErrorCode.STARTUP_REJECTED,
                f"binding {binding.binding_id} of {binding.plugin_id} is mapped to "
                f"connection {binding.connection_id} of {owner!r}",
            )


def settings_for_takers(
    profile: Profile, wanted: Mapping[str, Any], source: str
) -> dict[str, dict[str, Any]]:
    """Each wanted setting for every enabled plugin whose profile entry names it.

    The plugin checks the value at startup. A setting that no enabled plugin takes
    is refused, never dropped.
    """
    overrides: dict[str, dict[str, Any]] = {}
    for key, value in wanted.items():
        takers = [pid for pid, cfg in profile.enabled_plugins.items() if key in cfg.settings]
        if not takers:
            raise KernelError(
                ErrorCode.STARTUP_REJECTED,
                f"no enabled plugin takes the setting {key!r} (from {source})",
            )
        for pid in takers:
            overrides.setdefault(pid, {})[key] = value
    return overrides


def fixture_scenario_check(profile: Profile) -> None:
    """``fixture.scenario`` from a profile written before ADR 0026 (the 1d.4 rule).

    It must equal the scenario setting of the enabled plugins that take one: equal
    values are one setting, a different value is refused, and so is a scenario no
    enabled plugin takes. Live profiles never used it, as before.
    """
    fixture = profile.fixture
    if profile.environment != "fixture" or fixture is None or fixture.scenario is None:
        return
    for pid in settings_for_takers(profile, {"scenario": fixture.scenario}, "fixture.scenario"):
        if profile.enabled_plugins[pid].settings["scenario"] != fixture.scenario:
            raise KernelError(
                ErrorCode.STARTUP_REJECTED,
                f"fixture.scenario and enabled_plugins.{pid}.settings.scenario differ; "
                "keep only the plugin setting",
            )


def check_live_write_budget(profile: Profile) -> None:
    """A live profile admits at most one write per run (ADR 0025, live guard): no UI can yet
    present and recompute a multi-step plan's digest (Phase 5). A task definition only
    narrows the profile's budgets (ADR 0028, owner decision D7), so no definition in a live
    profile can admit more either."""
    if profile.environment == "live" and profile.budgets.max_admitted_writes > 1:
        raise KernelError(
            ErrorCode.STARTUP_REJECTED,
            "a live profile admits at most one write per run (budgets.max_admitted_writes); "
            "multi-step plans run in fixture profiles only",
        )


async def build_runtime(
    profile: Profile,
    *,
    driver_mode: str | None = None,
    plugin_settings: Mapping[str, Mapping[str, Any]] | None = None,
    plugin_paths: Iterable[str] | None = None,
    driver_factory: Callable[[PluginRegistry], AgentDriver] | None = None,
    task_kind: str | None = None,
) -> Runtime:
    check_live_write_budget(profile)
    fixture_scenario_check(profile)
    route = check_route_boundary(profile)
    check_conversation_toggle(profile)
    catalog = ConnectionCatalog(profile.connections)
    registry, credentials = admit_plugins(
        profile, catalog, discover(plugin_paths), _secret_store(profile), plugin_settings
    )
    # The composition root chooses the validation engine; domains supply datasets.
    registry.validators.append(ShaclPlanValidator(registry.dataset_builders))
    operator = _operator(profile)
    scope = frozenset(c.connection_id for c in profile.connections)
    connection_id = profile.connections[0].connection_id

    check_task_tool_sets(registry, profile)
    task_kind = task_kind or profile.driver.task_kind
    if task_kind not in registry.task_presets:
        known = ", ".join(sorted(registry.task_presets)) or "none"
        raise KernelError(
            ErrorCode.STARTUP_REJECTED,
            f"task kind {task_kind!r} is not a task preset of an admitted plugin "
            f"(admitted: {known})",
        )

    driver: AgentDriver
    if driver_factory is not None:
        driver = driver_factory(registry)
    elif profile.driver.kind == "pydantic-ai":
        driver = build_driver(profile, registry)
    else:
        # Every other kind is contributed by an admitted plugin (ADR 0026).
        factory = registry.driver_factories.get(profile.driver.kind)
        if factory is None:
            raise KernelError(
                ErrorCode.STARTUP_REJECTED,
                f"driver kind {profile.driver.kind!r} is not contributed by an admitted plugin",
            )
        mode = driver_mode or (profile.fixture.driver_mode if profile.fixture else "valid")
        driver = factory(
            DriverRequest(
                connection_id=connection_id,
                mode=mode,
                task_kind=task_kind,
                refs={**registry.task_presets[task_kind].default_refs, **profile.driver.refs},
            )
        )

    sandbox: dict[str, Any] = {}
    if profile.environment == "live":
        sandbox = await _check_sandbox(profile, registry, operator, scope)

    store = await open_store(profile)
    coordinator = RunCoordinator(
        store=store,
        registry=registry,
        connections=catalog,
        policy=DefaultPolicy(),
        driver=driver,
        allow_self_approval=profile.operator.allow_self_approval,
        budgets=profile.budgets,
        credentials=credentials,
        features=profile.features,
        route=route_facts(profile, route),  # the per-call route check (ADR 0032 §9)
    )
    return Runtime(
        profile,
        coordinator,
        store,
        registry,
        operator,
        scope,
        catalog,
        sandbox,
        runtime_versions(profile, registry, driver),
        route,
    )


async def _check_sandbox(
    profile: Profile, registry: PluginRegistry, operator: Principal, scope: frozenset[str]
) -> dict[str, Any]:
    """Refuse to start unless every live provider reports the expected sandbox marker.

    A live provider is an enabled plugin that a profile connection names or an
    admitted binding routes to. Its
    manifest names the probe (``connection.test_connection``); one without a
    probe refuses startup, never skips the check.
    """
    found: dict[str, Any] = {}
    ctx = TaskContext(
        run_id="startup-check",
        tenant_id=profile.tenant_id,
        principal=operator,
        resource_scope=scope,
    )
    # A provider is live when a connection names it or a binding routes to it.
    live = {conn.integration_id for conn in profile.connections}
    live |= {binding.plugin_id for binding in registry.bindings}
    for pid, cfg in profile.enabled_plugins.items():
        if pid not in live:
            continue
        spec = registry.connection_specs.get(pid)
        probe = spec.test_connection if spec is not None else None
        if probe is None:
            raise KernelError(
                ErrorCode.STARTUP_REJECTED, f"{pid}: live provider declares no sandbox probe"
            )
        probes = [
            getattr(e, probe)
            for e in registry.plugin_executors.get(pid, ())
            if callable(getattr(e, probe, None))
        ]
        expected = cfg.settings.get("expected_sandbox_marker")
        if not expected or len(probes) != 1:
            raise KernelError(ErrorCode.STARTUP_REJECTED, f"{pid}: sandbox check not configured")
        for conn in profile.connections:
            if conn.integration_id != pid:
                continue
            info = await probes[0](ctx, conn.connection_id)
            target = {
                "sandbox_marker": expected,
                "database": cfg.settings.get("database"),
                "company_id": str(cfg.settings.get("expected_company_id", "")),
                "bridge_version": cfg.settings.get("expected_bridge_version"),
            }
            if (
                not all(target.values())
                or any(info.get(k) != v for k, v in target.items())
                or not str(info.get("server_version", "")).startswith("19.0")
            ):
                raise KernelError(
                    ErrorCode.STARTUP_REJECTED,
                    f"{conn.connection_id}: sandbox marker mismatch; refusing to start",
                )
            found[conn.connection_id] = info
    return found
