"""Composition root: discover/admit plugins, wire kernel services (MVP design §6)."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

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
from e_agent.sdk.ports import PluginContribution

from .profile import Profile


@dataclass
class Runtime:
    profile: Profile
    coordinator: RunCoordinator
    store: InMemoryRunStore
    registry: PluginRegistry
    operator: Principal
    scope: frozenset[str]
    fake_erp: FakeErp | None


def build_runtime(
    profile: Profile,
    *,
    scenario: str | None = None,
    driver_mode: str | None = None,
    lose_response_after_commit: bool = False,
    plugin_paths: Iterable[str] | None = None,
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
    driver = ScriptedProcurementDriver(
        connection_id=connection_id, mode=driver_mode or profile.fixture.driver_mode
    )
    # Fixture components are registered in-process and only in fixture profiles.
    registry.register(
        plugin_id=FIXTURE_PLUGIN_ID,
        plugin_version="0.1.0+fixture",
        declared_capabilities=(),
        binding_templates=FIXTURE_BINDINGS,
        contribution=PluginContribution(executors=(fake_erp,), drivers=(driver,)),
    )
    # The composition root chooses the validation engine; domains supply datasets.
    registry.validators.append(ShaclPlanValidator(registry.dataset_builders))
    store = InMemoryRunStore()
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
