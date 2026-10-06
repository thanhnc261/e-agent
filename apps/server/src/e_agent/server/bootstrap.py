"""Composition root: discover/admit plugins, wire kernel services (MVP design §6).

The only place that chooses concrete implementations. Fixture components are
wired only in ``environment=fixture`` profiles; live profiles must pass the
sandbox-marker check before any run starts.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

from e_agent.adapters.postgres import PostgresRunStore, apply_migrations, database_name
from e_agent.adapters.pydantic_ai import PydanticAiDriver, ToolSpec, ollama_model
from e_agent.adapters.secretstore_local import LocalSecretStore
from e_agent.adapters.shacl import ShaclPlanValidator
from e_agent.contracts.capability import EffectKind
from e_agent.contracts.context import Principal, TaskContext
from e_agent.erp.testing.fake_erp import BINDINGS as FIXTURE_BINDINGS
from e_agent.erp.testing.fake_erp import PLUGIN_ID as FIXTURE_PLUGIN_ID
from e_agent.erp.testing.fake_erp import FakeErp
from e_agent.erp.testing.scenarios import SCENARIOS
from e_agent.erp.testing.scripted_tasks import ScriptedErpDriver
from e_agent.kernel.connections import ConnectionCatalog
from e_agent.kernel.coordinator import RunCoordinator
from e_agent.kernel.credentials import CredentialService
from e_agent.kernel.errors import ErrorCode, KernelError
from e_agent.kernel.memory_store import InMemoryRunStore
from e_agent.kernel.policy import DefaultPolicy
from e_agent.kernel.registry import EnabledPlugin, PluginRegistry
from e_agent.sdk.discovery import discover
from e_agent.sdk.ports import AgentDriver, PluginContribution

from .profile import Profile

AUTH_PLACEMENT = {"odoo19": {"method": "api_key", "header": "Authorization", "prefix": "bearer "}}
LIVE_PROVIDERS_WITH_SANDBOX = {"odoo19"}


@dataclass
class Runtime:
    profile: Profile
    coordinator: RunCoordinator
    store: Any
    registry: PluginRegistry
    operator: Principal
    scope: frozenset[str]
    fake_erp: FakeErp | None
    sandbox: dict[str, Any] = field(default_factory=dict)
    versions: dict[str, Any] = field(default_factory=dict)


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
        "profile_environment": profile.environment,
    }


async def open_store(profile: Profile) -> Any:
    if profile.store.kind == "memory":
        return InMemoryRunStore()
    dsn = os.environ.get(profile.store.dsn_env)
    if not dsn:
        raise KernelError(ErrorCode.STARTUP_REJECTED, f"{profile.store.dsn_env} is not set")
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


def build_driver(profile: Profile, registry: PluginRegistry) -> AgentDriver:
    cfg = profile.driver
    if cfg.provider != "ollama" or not cfg.model:
        raise KernelError(ErrorCode.STARTUP_REJECTED, "pydantic-ai driver needs an ollama model")
    base_url = os.environ.get(cfg.base_url_env, "http://localhost:11434/v1")
    settings: dict[str, object] = {}
    if cfg.temperature is not None:
        settings["temperature"] = float(cfg.temperature)
    return PydanticAiDriver(
        ollama_model(cfg.model, base_url),
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


async def build_runtime(
    profile: Profile,
    *,
    scenario: str | None = None,
    driver_mode: str | None = None,
    lose_response_after_commit: bool = False,
    plugin_paths: Iterable[str] | None = None,
    driver_factory: Callable[[PluginRegistry], AgentDriver] | None = None,
    task_kind: str | None = None,
) -> Runtime:
    catalog = ConnectionCatalog(profile.connections)
    credentials = CredentialService(catalog, _secret_store(profile), AUTH_PLACEMENT)
    registry = PluginRegistry(profile.bindings)
    enabled = {
        pid: EnabledPlugin(cfg.version, cfg.manifest_sha256, dict(cfg.settings))
        for pid, cfg in profile.enabled_plugins.items()
    }
    registry.admit(discover(plugin_paths), enabled, credentials_for=credentials.scoped)
    # The composition root chooses the validation engine; domains supply datasets.
    registry.validators.append(ShaclPlanValidator(registry.dataset_builders))
    operator = _operator(profile)
    scope = frozenset(c.connection_id for c in profile.connections)
    connection_id = profile.connections[0].connection_id

    fake_erp: FakeErp | None = None
    if profile.environment == "fixture":
        if profile.fixture is None:
            raise KernelError(ErrorCode.STARTUP_REJECTED, "fixture profile lacks fixture config")
        scenario_name = scenario or profile.fixture.scenario
        if scenario_name not in SCENARIOS:
            raise KernelError(ErrorCode.INVALID_REQUEST, f"unknown scenario {scenario_name!r}")
        fake_erp = FakeErp(
            SCENARIOS[scenario_name], lose_response_after_commit=lose_response_after_commit
        )
        registry.register(
            plugin_id=FIXTURE_PLUGIN_ID,
            plugin_version="0.1.0+fixture",
            declared_capabilities=(),
            binding_templates=FIXTURE_BINDINGS,
            contribution=PluginContribution(executors=(fake_erp,)),
        )

    driver: AgentDriver
    if driver_factory is not None:
        driver = driver_factory(registry)
    elif profile.driver.kind == "pydantic-ai":
        driver = build_driver(profile, registry)
    else:
        mode = driver_mode or (profile.fixture.driver_mode if profile.fixture else "valid")
        driver = ScriptedErpDriver(
            connection_id=connection_id,
            mode=mode,
            task_kind=task_kind or profile.driver.task_kind,
            demand_ref=profile.driver.demand_ref or "demand:d-001",
            product_ref=profile.driver.product_ref or "product:widget-a",
            refs=profile.driver.refs,
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
        budgets=profile.budgets,
    )
    return Runtime(
        profile,
        coordinator,
        store,
        registry,
        operator,
        scope,
        fake_erp,
        sandbox,
        runtime_versions(profile, registry, driver),
    )


async def _check_sandbox(
    profile: Profile, registry: PluginRegistry, operator: Principal, scope: frozenset[str]
) -> dict[str, Any]:
    """Refuse to start unless every live provider reports the expected sandbox marker."""
    found: dict[str, Any] = {}
    ctx = TaskContext(
        run_id="startup-check",
        tenant_id=profile.tenant_id,
        principal=operator,
        resource_scope=scope,
    )
    probes = [e for e in registry.executors if hasattr(e, "sandbox_info")]
    for pid, cfg in profile.enabled_plugins.items():
        if pid not in LIVE_PROVIDERS_WITH_SANDBOX:
            continue
        expected = cfg.settings.get("expected_sandbox_marker")
        if not expected or len(probes) != 1:
            raise KernelError(ErrorCode.STARTUP_REJECTED, f"{pid}: sandbox check not configured")
        for conn in profile.connections:
            if conn.integration_id != pid:
                continue
            info = await probes[0].sandbox_info(ctx, conn.connection_id)
            if info.get("sandbox_marker") != expected:
                raise KernelError(
                    ErrorCode.STARTUP_REJECTED,
                    f"{conn.connection_id}: sandbox marker mismatch; refusing to start",
                )
            found[conn.connection_id] = info
    return found
