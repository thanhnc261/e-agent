"""A binding routes only to its own provider's connections (phase review 1d R-1).

The live sandbox guard probes the providers that profile connections name. A
binding mapped to a connection of another integration, or a connection naming no
enabled plugin, would let a provider without a sandbox probe serve a live profile;
admission refuses both, and the guard also treats every provider that owns a
routable binding as live.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from e_agent.kernel.connections import ConnectionCatalog
from e_agent.kernel.errors import ErrorCode, KernelError
from e_agent.kernel.registry import EnabledPlugin, PluginRegistry
from e_agent.plugins.erp.simulator import fixture_profile_path
from e_agent.sdk.discovery import artifact_digest, discover
from e_agent.server import bootstrap
from e_agent.server.profile import Profile, load_profile

REPO = Path(__file__).resolve().parents[3]
LIVE_EXAMPLE = REPO / "profiles" / "live.example.json"
SIMULATOR = "fixture-erp"
DEMAND = f"{SIMULATOR}.procurement.demand"


def _pinned(data: dict[str, Any]) -> dict[str, Any]:
    """Pin the installed artifacts, as the owner pins a live profile."""
    found = {p.manifest.plugin_id: p for p in discover()}
    for pid, cfg in data["enabled_plugins"].items():
        cfg["artifact_sha256"] = artifact_digest(found[pid].artifact_files)
    return data


def _connection(tenant_id: str, connection_id: str, integration_id: str) -> dict[str, Any]:
    return {
        "tenant_id": tenant_id,
        "connection_id": connection_id,
        "version": 1,
        "integration_id": integration_id,
        "ownership": "tenant_shared",
        "secret_ref": f"secretref:local/{integration_id}",
    }


def _live_with_simulator(
    connections: list[tuple[str, str]], bindings: dict[str, list[str]], *, odoo: bool
) -> Profile:
    """A live profile that also enables the simulator, which has no sandbox probe."""
    data = load_profile(LIVE_EXAMPLE).model_dump(mode="json")
    fixture = load_profile(fixture_profile_path()).model_dump(mode="json")
    if not odoo:
        del data["enabled_plugins"]["odoo19"]
    data["enabled_plugins"][SIMULATOR] = fixture["enabled_plugins"][SIMULATOR]
    data["connections"] = [_connection(data["tenant_id"], c, i) for c, i in connections]
    data["bindings"] = bindings
    return Profile.model_validate(_pinned(data))


def _admit(profile: Profile) -> PluginRegistry:
    registry, _ = bootstrap.admit_plugins(
        profile, ConnectionCatalog(profile.connections), discover(), None
    )
    return registry


def _refused(profile: Profile) -> str:
    with pytest.raises(KernelError) as exc:
        _admit(profile)
    assert exc.value.code is ErrorCode.STARTUP_REJECTED
    return exc.value.safe_message


def test_binding_on_a_connection_of_an_unconfigured_integration_refused() -> None:
    # The phase review's reproduction: the guard skipped the simulator because the
    # connection names an integration that no enabled plugin is.
    profile = _live_with_simulator([("conn-x", "unconfigured")], {DEMAND: ["conn-x"]}, odoo=False)
    message = _refused(profile)
    assert "conn-x" in message
    assert "unconfigured" in message


def test_binding_on_another_providers_connection_refused() -> None:
    profile = _live_with_simulator([("conn-odoo", "odoo19")], {DEMAND: ["conn-odoo"]}, odoo=True)
    message = _refused(profile)
    assert DEMAND in message
    assert "conn-odoo" in message


def test_connection_naming_no_enabled_plugin_refused() -> None:
    data = _pinned(load_profile(LIVE_EXAMPLE).model_dump(mode="json"))
    data["connections"].append(_connection(data["tenant_id"], "conn-x", "unconfigured"))
    message = _refused(Profile.model_validate(data))
    assert "conn-x" in message
    assert "unconfigured" in message


@pytest.mark.parametrize("path", [LIVE_EXAMPLE, fixture_profile_path()], ids=["live", "fixture"])
def test_shipped_profiles_still_admit(path: Path) -> None:
    profile = Profile.model_validate(_pinned(load_profile(path).model_dump(mode="json")))
    registry = _admit(profile)
    owners = {c.connection_id: c.integration_id for c in profile.connections}
    assert registry.bindings
    assert all(owners[b.connection_id] == b.plugin_id for b in registry.bindings)


async def test_sandbox_guard_probes_every_provider_with_a_routable_binding() -> None:
    # Defence in depth: a registry admitted without the ownership check still makes
    # the guard refuse a live profile whose bindings reach a provider with no probe.
    profile = _live_with_simulator([("conn-x", "unconfigured")], {DEMAND: ["conn-x"]}, odoo=False)
    registry = PluginRegistry(profile.bindings)
    enabled = {
        pid: EnabledPlugin(cfg.version, settings=cfg.settings, artifact_sha256=cfg.artifact_sha256)
        for pid, cfg in profile.enabled_plugins.items()
    }
    registry.admit(discover(), enabled, credentials_for=lambda pid: object())
    assert [b.plugin_id for b in registry.bindings] == [SIMULATOR]
    operator = bootstrap._operator(profile)
    with pytest.raises(KernelError) as exc:
        await bootstrap._check_sandbox(profile, registry, operator, frozenset({"conn-x"}))
    assert exc.value.code is ErrorCode.STARTUP_REJECTED
    assert f"{SIMULATOR}: live provider declares no sandbox probe" in exc.value.safe_message


def test_live_profile_refuses_a_defaulted_write_binding() -> None:
    # ADR 0029 through bootstrap: admission sees the profile's environment, so the
    # simulator's write binding, which keeps the default idempotency, is refused live.
    po_create = f"{SIMULATOR}.procurement.po-create"
    profile = _live_with_simulator([("conn-sim", SIMULATOR)], {po_create: ["conn-sim"]}, odoo=False)
    message = _refused(profile)
    assert po_create in message
    assert "idempotency" in message
