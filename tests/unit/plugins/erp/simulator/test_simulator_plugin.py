"""The ERP simulator is the discovered provider plugin ``fixture-erp`` (R-2 part 2, ADR 0026).

A fixture profile enables it the way a live profile enables ``odoo19``; a profile
that does not enable it never imports it.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from e_agent.erp.procurement import CREATE_DRAFT_PO, DEMAND_READ
from e_agent.kernel.connections import ConnectionCatalog
from e_agent.kernel.errors import ErrorCode, KernelError
from e_agent.kernel.registry import EnabledPlugin, PluginRegistry
from e_agent.plugins.erp.simulator import fixture_profile_path
from e_agent.plugins.erp.simulator.fake_erp import BINDINGS, PLUGIN_ID, FakeErp
from e_agent.plugins.erp.simulator.scenarios import SCENARIOS
from e_agent.sdk.discovery import discover
from e_agent.sdk.ports import PluginContribution
from e_agent.server.bootstrap import admit_plugins, build_runtime
from e_agent.server.cli import main
from e_agent.server.profile import Profile, load_profile

REPO = Path(__file__).resolve().parents[5]
SIMULATOR = "e_agent.plugins.erp.simulator"

FIXTURE = ("--profile", str(fixture_profile_path()))


def _demo(capsys: pytest.CaptureFixture[str], *args: str) -> dict[str, Any]:
    assert main([*FIXTURE, "demo", "--json", *args]) == 0
    return json.loads(capsys.readouterr().out)  # type: ignore[no-any-return]


async def test_fixture_profile_composes_through_discovery() -> None:
    [plugin] = [p for p in discover() if p.manifest.plugin_id == PLUGIN_ID]
    assert plugin.distribution == "e-agent-adapter-erp-simulator"
    assert plugin.manifest.kind == "provider"
    assert [(t.binding_id, t.contract_id) for t in plugin.manifest.provides_bindings] == [
        (t.binding_id, t.contract_id) for t in BINDINGS
    ]

    rt = await build_runtime(load_profile(fixture_profile_path()))
    assert PLUGIN_ID in rt.registry.report.admitted
    [executor] = rt.registry.plugin_executors[PLUGIN_ID]
    assert isinstance(executor, FakeErp)
    assert executor.scenario is SCENARIOS["valid"]
    assert {b.binding_id for b in rt.registry.bindings} == {t.binding_id for t in BINDINGS}
    assert rt.diagnostics() == {PLUGIN_ID: {"create_calls": 0}}

    # The same scenarios as before the move, each selectable through the setting.
    assert sorted(SCENARIOS) == [
        "over-budget",
        "rfq-confirmed",
        "unsaleable-product",
        "valid",
        "zero-shortage",
    ]
    for name, scenario in SCENARIOS.items():
        rt = await build_runtime(
            load_profile(fixture_profile_path()), plugin_settings={PLUGIN_ID: {"scenario": name}}
        )
        assert rt.registry.plugin_executors[PLUGIN_ID][0].scenario is scenario  # type: ignore[attr-defined]


def test_fixture_profile_create_calls_unchanged(capsys: pytest.CaptureFixture[str]) -> None:
    # The same create-call count: one draft per approved valid request, none when blocked.
    assert _demo(capsys, "--approve")["provider_diagnostics"] == {PLUGIN_ID: {"create_calls": 1}}
    blocked = _demo(capsys, "--scenario", "over-budget", "--approve")
    assert blocked["provider_diagnostics"] == {PLUGIN_ID: {"create_calls": 0}}


_ADMIT_AND_LIST_MODULES = """
import json, sys
import e_agent.server.api, e_agent.server.bootstrap, e_agent.server.cli
from e_agent.kernel.connections import ConnectionCatalog
from e_agent.sdk.discovery import artifact_digest, discover
from e_agent.server.bootstrap import admit_plugins
from e_agent.server.profile import Profile, load_profile

found = {p.manifest.plugin_id: p for p in discover()}
data = load_profile(sys.argv[1]).model_dump(mode="json")
if data["environment"] == "live":
    # Pin the installed artifacts, as the owner pins the real live profile.
    for pid, cfg in data["enabled_plugins"].items():
        cfg["artifact_sha256"] = artifact_digest(found[pid].artifact_files)
profile = Profile.model_validate(data)
registry, _ = admit_plugins(profile, ConnectionCatalog(profile.connections), found.values(), None)
print(json.dumps({"admitted": registry.report.admitted, "modules": sorted(sys.modules)}))
"""


def _admit_in_subprocess(profile_path: Path) -> dict[str, Any]:
    out = subprocess.run(
        [sys.executable, "-c", _ADMIT_AND_LIST_MODULES, str(profile_path)],
        capture_output=True,
        text=True,
        check=True,
        cwd=REPO,
    ).stdout
    return json.loads(out)  # type: ignore[no-any-return]


def test_live_profile_never_imports_simulator() -> None:
    live = _admit_in_subprocess(REPO / "profiles" / "live.example.json")
    assert live["admitted"] == ["domain-erp", "odoo19"]
    assert [m for m in live["modules"] if m.startswith(SIMULATOR)] == []
    assert [m for m in live["modules"] if m.endswith(("fake_erp", "scenarios"))] == []
    # The check is not vacuous: the fixture profile imports the simulator.
    fixture = _admit_in_subprocess(fixture_profile_path())
    assert PLUGIN_ID in fixture["admitted"]
    assert f"{SIMULATOR}.fake_erp" in fixture["modules"]


_ODOO_SETTINGS = {
    "base_url": "http://localhost:8069",
    "database": "sandbox",
    "namespace": "e-agent-test",
    "expected_sandbox_marker": "odoo19-learning",
    "expected_company_id": "1",
    "expected_bridge_version": "19.0.0.4.0",
}


def _registry(binding_connections: dict[str, list[str]], *providers: str) -> PluginRegistry:
    """Admit the domain pack and the named providers from the installed plugins."""
    settings: dict[str, dict[str, Any]] = {"odoo19": _ODOO_SETTINGS, PLUGIN_ID: {}}
    registry = PluginRegistry(binding_connections)
    enabled = {
        pid: EnabledPlugin("0.1.0", settings=settings.get(pid, {}), allow_unverified_fixture=True)
        for pid in ("domain-erp", *providers)
    }
    # Stub credentials: the Odoo factory needs a resolver, and nothing is called here.
    registry.admit(discover(), enabled, credentials_for=lambda pid: object())
    return registry


def _odoo(binding: str) -> str:
    return binding.replace(f"{PLUGIN_ID}.", "odoo19.", 1)


def test_two_erp_providers_routing() -> None:
    # Both installed, one enabled: it composes, and the other is never imported.
    for provider, other in ((PLUGIN_ID, "odoo19"), ("odoo19", PLUGIN_ID)):
        name = (lambda b: b) if provider == PLUGIN_ID else _odoo
        registry = _registry({name(t.binding_id): ["conn-a"] for t in BINDINGS}, provider)
        assert other in registry.report.skipped
        binding = registry.resolve(DEMAND_READ, "conn-a")
        assert binding.plugin_id == provider
        assert registry.executor_for(binding) is registry.plugin_executors[provider][0]

    # Both enabled, each with its own connection: each binding resolves to its own executor.
    own = {t.binding_id: ["conn-sim"] for t in BINDINGS} | {
        _odoo(t.binding_id): ["conn-odoo"] for t in BINDINGS
    }
    registry = _registry(own, PLUGIN_ID, "odoo19")
    assert registry.report.admitted == ["domain-erp", PLUGIN_ID, "odoo19"]
    for connection, provider in (("conn-sim", PLUGIN_ID), ("conn-odoo", "odoo19")):
        for contract in (DEMAND_READ, CREATE_DRAFT_PO):
            binding = registry.resolve(contract, connection)
            assert binding.plugin_id == provider
            assert registry.executor_for(binding) is registry.plugin_executors[provider][0]

    # Two bindings of one contract on the same connection: refused, never chosen.
    shared = {t.binding_id: ["conn-a"] for t in BINDINGS} | {
        _odoo(t.binding_id): ["conn-a"] for t in BINDINGS
    }
    registry = _registry(shared, PLUGIN_ID, "odoo19")
    with pytest.raises(KernelError) as exc:
        registry.resolve(DEMAND_READ, "conn-a")
    assert exc.value.code is ErrorCode.CONFLICT

    # A duplicate binding id: refused at startup.
    with pytest.raises(KernelError) as exc:
        registry.register(
            plugin_id="other-provider",
            plugin_version="0.1.0",
            declared_capabilities=(),
            binding_templates=BINDINGS[:1],
            contribution=PluginContribution(),
        )
    assert exc.value.code is ErrorCode.STARTUP_REJECTED
    assert "duplicate binding id" in exc.value.safe_message


SYNTHETIC = "REVIEW_SYNTHETIC_PRIVATE_VALUE"


@pytest.mark.parametrize(
    ("settings", "named"),
    [
        ({"scenario": "no-such-scenario"}, "'scenario'"),
        ({"scenario": 3}, "'scenario'"),
        ({"scenario": {"api_key": SYNTHETIC}}, "'scenario'"),
        ({"lose_response_after_commit": SYNTHETIC}, "'lose_response_after_commit'"),
        ({"scenrio": "valid"}, "'scenrio'"),
        ({f"key {SYNTHETIC}": "valid"}, "<unnamed setting>"),
    ],
)
async def test_unknown_scenario_refused(settings: dict[str, Any], named: str) -> None:
    with pytest.raises(KernelError) as exc:
        await build_runtime(
            load_profile(fixture_profile_path()), plugin_settings={PLUGIN_ID: settings}
        )
    assert exc.value.code is ErrorCode.STARTUP_REJECTED
    message = exc.value.safe_message
    assert PLUGIN_ID in message and named in message
    # A setting's value never reaches the operator's message (R-1 of the 1d.5 review).
    assert SYNTHETIC not in message and "no-such-scenario" not in message


async def test_settings_for_a_plugin_not_enabled_refused() -> None:
    with pytest.raises(KernelError) as exc:
        await build_runtime(
            load_profile(fixture_profile_path()), plugin_settings={"odoo19": {"scenario": "valid"}}
        )
    assert exc.value.code is ErrorCode.STARTUP_REJECTED


def test_live_profile_settings_are_not_overridden() -> None:
    profile = load_profile(REPO / "profiles" / "live.example.json")
    with pytest.raises(KernelError) as exc:
        admit_plugins(
            profile,
            ConnectionCatalog(profile.connections),
            discover(),
            None,
            {"odoo19": {"base_url": "http://elsewhere"}},
        )
    assert exc.value.code is ErrorCode.STARTUP_REJECTED
    assert "fixture profiles only" in exc.value.safe_message


def _fixture_profile(scenario: str | None, settings: dict[str, Any] | None) -> Profile:
    data = load_profile(fixture_profile_path()).model_dump(mode="json")
    data["fixture"]["scenario"] = scenario
    if settings is None:
        del data["enabled_plugins"][PLUGIN_ID]
    else:
        data["enabled_plugins"][PLUGIN_ID]["settings"] = settings
    return Profile.model_validate(data)


async def test_fixture_scenario_equal_to_the_plugin_setting_is_one_setting() -> None:
    profile = _fixture_profile("over-budget", {"scenario": "over-budget"})
    rt = await build_runtime(profile)
    assert rt.registry.plugin_executors[PLUGIN_ID][0].scenario is SCENARIOS["over-budget"]  # type: ignore[attr-defined]


async def test_fixture_scenario_differing_from_the_plugin_setting_refused() -> None:
    with pytest.raises(KernelError) as exc:
        await build_runtime(_fixture_profile("over-budget", {"scenario": "valid"}))
    assert exc.value.code is ErrorCode.STARTUP_REJECTED
    assert "fixture.scenario" in exc.value.safe_message
    assert f"enabled_plugins.{PLUGIN_ID}.settings.scenario" in exc.value.safe_message


@pytest.mark.parametrize("settings", [{}, None], ids=["no-setting", "pre-1d.5-profile"])
async def test_fixture_scenario_no_plugin_takes_refused(settings: dict[str, Any] | None) -> None:
    # A profile written before 1d.5 (no fixture-erp entry) still loads; it cannot run,
    # because ADR 0026 has fixture profiles enable the simulator, and startup says why.
    profile = _fixture_profile("over-budget", settings)
    with pytest.raises(KernelError) as exc:
        await build_runtime(profile)
    assert exc.value.code is ErrorCode.STARTUP_REJECTED
    assert "no enabled plugin takes the setting 'scenario' (from fixture.scenario)" in (
        exc.value.safe_message
    )


def test_cli_scenario_needs_a_plugin_taking_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main([*FIXTURE, "demo", "--json", "--scenario", "no-such-scenario"]) == 2
    err = capsys.readouterr().err
    assert "invalid setting 'scenario'" in err and "no-such-scenario" not in err
    # A profile whose plugins take no scenario setting refuses --scenario.
    data = load_profile(fixture_profile_path()).model_dump(mode="json")
    data["enabled_plugins"][PLUGIN_ID]["settings"] = {}
    profile = tmp_path / "profile.json"
    profile.write_text(json.dumps(data), encoding="utf-8")
    assert main(["--profile", str(profile), "demo", "--json", "--scenario", "valid"]) == 2
    assert "scenario" in capsys.readouterr().err
