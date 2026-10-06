"""Composition root: discover/admit plugins, wire kernel services (MVP design §6)."""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from e_agent.adapters.postgres import PostgresRunStore, apply_migrations
from e_agent.adapters.pydantic_ai import PydanticAiDriver, ToolSpec, ollama_model
from e_agent.adapters.shacl import ShaclPlanValidator
from e_agent.contracts.context import Principal
from e_agent.erp.testing.fake_erp import BINDINGS as FIXTURE_BINDINGS
from e_agent.erp.testing.fake_erp import PLUGIN_ID as FIXTURE_PLUGIN_ID
from e_agent.erp.testing.fake_erp import FakeErp
from e_agent.erp.testing.scenarios import SCENARIOS
from e_agent.erp.testing.scripted_driver import ScriptedProcurementDriver
from e_agent.kernel.connections import ConnectionCatalog
from e_agent.kernel.coordinator import RunCoordinator
from e_agent.kernel.errors import ErrorCode, KernelError
from e_agent.kernel.memory_store import InMemoryRunStore
from e_agent.kernel.policy import DefaultPolicy
from e_agent.kernel.registry import EnabledPlugin, PluginRegistry
from e_agent.sdk.discovery import discover
from e_agent.sdk.ports import AgentDriver, PluginContribution

from .profile import Profile


@dataclass
class Runtime:
    profile: Profile
    coordinator: RunCoordinator
    store: Any
    registry: PluginRegistry
    operator: Principal
    scope: frozenset[str]
    fake_erp: FakeErp | None


async def open_store(profile: Profile) -> Any:
    if profile.store.kind == "memory":
        return InMemoryRunStore()
    dsn = os.environ.get(profile.store.dsn_env)
    if not dsn:
        raise KernelError(ErrorCode.STARTUP_REJECTED, f"{profile.store.dsn_env} is not set")
    await apply_migrations(dsn)
    return await PostgresRunStore.open(dsn)


def tool_specs(registry: PluginRegistry, profile: Profile) -> list[ToolSpec]:
    """Expose agent-visible capabilities that have exactly one binding in scope."""
    specs: list[ToolSpec] = []
    for cap in sorted(registry.capabilities.values(), key=lambda c: c.contract_id):
        if not cap.agent_visible:
            continue
        connections = sorted(
            {b.connection_id for b in registry.bindings if b.contract_id == cap.contract_id}
        )
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


async def build_runtime(
    profile: Profile,
    *,
    scenario: str | None = None,
    driver_mode: str | None = None,
    lose_response_after_commit: bool = False,
    plugin_paths: Iterable[str] | None = None,
    driver_factory: Callable[[PluginRegistry], AgentDriver] | None = None,
) -> Runtime:
    registry = PluginRegistry(profile.bindings)
    enabled = {
        pid: EnabledPlugin(cfg.version, cfg.manifest_sha256, dict(cfg.settings))
        for pid, cfg in profile.enabled_plugins.items()
    }
    registry.admit(discover(plugin_paths), enabled)

    if profile.environment != "fixture" or profile.fixture is None:
        # Live drivers/adapters arrive with I04 (Pydantic AI) and I06 (Odoo).
        raise KernelError(ErrorCode.STARTUP_REJECTED, "only fixture profiles are supported yet")

    scenario_name = scenario or profile.fixture.scenario
    if scenario_name not in SCENARIOS:
        raise KernelError(ErrorCode.INVALID_REQUEST, f"unknown scenario {scenario_name!r}")
    connection_id = profile.connections[0].connection_id
    fake_erp = FakeErp(
        SCENARIOS[scenario_name], lose_response_after_commit=lose_response_after_commit
    )
    scripted = ScriptedProcurementDriver(
        connection_id=connection_id, mode=driver_mode or profile.fixture.driver_mode
    )
    # Fixture components are registered in-process and only in fixture profiles.
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
        driver = scripted
    # The composition root chooses the validation engine; domains supply datasets.
    registry.validators.append(ShaclPlanValidator(registry.dataset_builders))
    store = await open_store(profile)
    coordinator = RunCoordinator(
        store=store,
        registry=registry,
        connections=ConnectionCatalog(profile.connections),
        policy=DefaultPolicy(),
        driver=driver,
        budgets=profile.budgets,
    )
    operator = Principal(
        principal_id=profile.operator.principal_id,
        tenant_id=profile.tenant_id,
        roles=profile.operator.roles,
        display_name=profile.operator.display_name,
    )
    scope = frozenset(c.connection_id for c in profile.connections)
    return Runtime(profile, coordinator, store, registry, operator, scope, fake_erp)
