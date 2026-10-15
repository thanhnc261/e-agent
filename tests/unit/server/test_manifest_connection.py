"""Auth placement and the live sandbox probe come from adapter manifests (R-1, ADR 0026).

The server keeps no table keyed by provider id: a second provider is wired by its
manifest alone, an unknown placement is refused at admission, and a live provider
whose manifest declares no sandbox probe makes startup refuse.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from e_agent.contracts.context import TaskContext
from e_agent.kernel.connections import ConnectionCatalog
from e_agent.kernel.credentials import CredentialService
from e_agent.kernel.errors import ErrorCode, KernelError
from e_agent.kernel.registry import EnabledPlugin, PluginRegistry
from e_agent.sdk.auth import Secret
from e_agent.sdk.connection import ConnectionSpec
from e_agent.sdk.discovery import DiscoveredPlugin, artifact_digest, discover
from e_agent.sdk.manifest import PluginManifest
from e_agent.sdk.ports import PluginContribution
from e_agent.server import bootstrap
from e_agent.server.profile import Profile

ARTIFACT = "pkg/e_agent_plugin.json"
PREVIOUS_ODOO_PLACEMENT = {"method": "api_key", "header": "Authorization", "prefix": "bearer "}
KEY = "k-CANARY-1d2"
ODOO_SETTINGS = {
    "base_url": "http://localhost:8069",
    "database": "odoo19_learning",
    "namespace": "e-agent-test",
    "expected_sandbox_marker": "odoo19-learning",
    "expected_company_id": "1",
    "expected_bridge_version": "19.0.0.4.0",
}
ODOO_INFO = {
    "sandbox_marker": "odoo19-learning",
    "database": "odoo19_learning",
    "company_id": "1",
    "bridge_version": "19.0.0.4.0",
    "server_version": "19.0-20251001",
}


def _api_key_section(header: str = "X-Api-Key", prefix: str = "", **extra: Any) -> dict[str, Any]:
    return {
        "auth_methods": [
            {
                "id": "key",
                "type": "api_key",
                "levels": ["tenant"],
                "api_key": {"placement": "header", "header": header, "prefix": prefix},
                "input_schema": {"type": "object"},
            }
        ],
        **extra,
    }


def _odoo_section() -> dict[str, object]:
    odoo = next(p for p in discover() if p.manifest.plugin_id == "odoo19")
    return odoo.manifest.connection


class Secrets:
    async def get(self, ref: str, expected_version: str | None = None) -> Secret:
        return Secret(KEY)

    async def put(self, ref: str, value: Secret) -> None: ...

    async def delete(self, ref: str) -> None: ...


class ProbeExecutor:
    """Stands in for a provider executor; ``sandbox_info`` is the manifest's probe."""

    def __init__(self, credentials: Any, info: dict[str, Any] | None) -> None:
        self.credentials = credentials
        self.info = info
        self.probed: list[str] = []

    def supports(self, binding: Any) -> bool:
        return False

    async def sandbox_info(self, ctx: TaskContext, connection_id: str) -> dict[str, Any]:
        self.probed.append(connection_id)
        assert self.info is not None
        return self.info


@pytest.fixture
def loaded(monkeypatch: pytest.MonkeyPatch) -> dict[str, ProbeExecutor]:
    """Replace plugin import with an in-test factory; records which plugins were loaded."""
    executors: dict[str, ProbeExecutor] = {}

    def load(plugin: DiscoveredPlugin, config: EnabledPlugin, creds: Any = None) -> Any:
        info = config.settings.get("_probe_info")
        executor = ProbeExecutor(creds, info if isinstance(info, dict) else None)
        executors[plugin.manifest.plugin_id] = executor
        return PluginContribution(executors=(executor,))

    monkeypatch.setattr(PluginRegistry, "_load", staticmethod(load))
    return executors


def _plugin(pid: str, connection: dict[str, object], artifact: Path) -> DiscoveredPlugin:
    factory = f"absent_{pid.replace('-', '_')}.plugin:create_plugin"
    manifest = PluginManifest(
        plugin_id=pid,
        version="0.1.0",
        sdk_api=">=1.0,<2.0",
        factory=factory,
        kind="provider",
        connection=connection,
    )
    return DiscoveredPlugin(
        entry_point_name=pid,
        entry_point_value=factory,
        distribution=pid,
        distribution_version="0.1.0",
        manifest=manifest,
        manifest_text=manifest.model_dump_json(),
        artifact_files=((ARTIFACT, artifact),),
    )


def _profile(
    environment: str,
    plugins: dict[str, dict[str, Any]],
    artifact: Path,
) -> Profile:
    digest = artifact_digest(((ARTIFACT, artifact),))
    return Profile.model_validate(
        {
            "profile_version": "1",
            "environment": environment,
            "tenant_id": "t",
            "operator": {"principal_id": "op", "roles": ["requester", "approver"]},
            "enabled_plugins": {
                pid: {"version": "0.1.0", "artifact_sha256": digest, "settings": settings}
                for pid, settings in plugins.items()
            },
            "connections": [
                {
                    "tenant_id": "t",
                    "connection_id": f"conn-{pid}",
                    "version": 1,
                    "integration_id": pid,
                    "ownership": "tenant_shared",
                    "secret_ref": f"secretref:local/{pid}",
                }
                for pid in plugins
            ],
            "bindings": {},
        }
    )


@pytest.fixture
def artifact(tmp_path: Path) -> Path:
    path = tmp_path / "e_agent_plugin.json"
    path.write_text("{}")
    return path


def _admit(
    profile: Profile, discovered: list[DiscoveredPlugin]
) -> tuple[PluginRegistry, CredentialService]:
    return bootstrap.admit_plugins(
        profile, ConnectionCatalog(profile.connections), discovered, Secrets()
    )


async def _header(
    profile: Profile, executors: dict[str, ProbeExecutor], pid: str
) -> dict[str, str]:
    ctx = TaskContext(
        run_id="r",
        tenant_id="t",
        principal=bootstrap._operator(profile),
        resource_scope=frozenset({f"conn-{pid}"}),
    )
    auth = await executors[pid].credentials.context_for(ctx, f"conn-{pid}")
    headers: dict[str, str] = {}
    auth.apply(headers)
    return headers


async def _sandbox(profile: Profile, registry: PluginRegistry) -> dict[str, Any]:
    scope = frozenset(c.connection_id for c in profile.connections)
    return await bootstrap._check_sandbox(profile, registry, bootstrap._operator(profile), scope)


def test_constants_keyed_by_provider_are_gone() -> None:
    source = Path(bootstrap.__file__).read_text("utf-8")
    assert "AUTH_PLACEMENT" not in source
    assert "LIVE_PROVIDERS_WITH_SANDBOX" not in source


async def test_odoo_auth_placement_from_manifest_equals_previous(
    loaded: dict[str, ProbeExecutor], artifact: Path
) -> None:
    spec = ConnectionSpec.from_manifest(_odoo_section())
    assert spec is not None
    assert spec.placement() == PREVIOUS_ODOO_PLACEMENT
    assert spec.test_connection == "sandbox_info"

    profile = _profile("fixture", {"odoo19": ODOO_SETTINGS}, artifact)
    registry, _ = _admit(profile, [_plugin("odoo19", _odoo_section(), artifact)])
    assert registry.auth_placements["odoo19"] == PREVIOUS_ODOO_PLACEMENT
    assert await _header(profile, loaded, "odoo19") == {"Authorization": f"bearer {KEY}"}


@pytest.mark.parametrize(
    "section",
    [
        {"auth_methods": [{"id": "k", "type": "api_key"}]},
        {
            "auth_methods": [
                {"id": "k", "type": "api_key", "api_key": {"placement": "query", "header": "k"}}
            ]
        },
        {
            "auth_methods": [
                {
                    "id": "k",
                    "type": "api_key",
                    "api_key": {"placement": "header", "header": "X-Api-Key"},
                }
            ]
        },
        {"auth_methods": [{"id": "k", "type": "oauth2"}]},
        {"auth_methods": _api_key_section()["auth_methods"] * 2},
        _api_key_section(cookie="session"),
        _api_key_section(test_connection="_private"),
    ],
    ids=[
        "api-key-without-placement",
        "query-placement",
        "missing-prefix",
        "unknown-type",
        "two-methods",
        "unknown-key",
        "private-probe",
    ],
)
def test_unknown_auth_placement_refused(
    loaded: dict[str, ProbeExecutor], artifact: Path, section: dict[str, object]
) -> None:
    profile = _profile("fixture", {"acme-crm": {}}, artifact)
    with pytest.raises(KernelError) as exc:
        _admit(profile, [_plugin("acme-crm", section, artifact)])
    assert exc.value.code is ErrorCode.STARTUP_REJECTED
    assert "acme-crm" in str(exc.value)
    assert loaded == {}, "the plugin must be refused before its code is loaded"


def test_manifest_without_connection_section_is_valid(
    loaded: dict[str, ProbeExecutor], artifact: Path
) -> None:
    assert ConnectionSpec.from_manifest({}) is None
    profile = _profile("fixture", {"notes": {}}, artifact)
    registry, _ = _admit(profile, [_plugin("notes", {}, artifact)])
    assert registry.report.admitted == ["notes"]
    assert "notes" not in registry.auth_placements


async def test_second_provider_wired_without_server_edit(
    loaded: dict[str, ProbeExecutor], artifact: Path
) -> None:
    profile = _profile("fixture", {"odoo19": ODOO_SETTINGS, "acme-crm": {}}, artifact)
    _admit(
        profile,
        [
            _plugin("odoo19", _odoo_section(), artifact),
            _plugin("acme-crm", _api_key_section(header="X-Api-Key", prefix=""), artifact),
        ],
    )
    assert await _header(profile, loaded, "acme-crm") == {"X-Api-Key": KEY}
    assert await _header(profile, loaded, "odoo19") == {"Authorization": f"bearer {KEY}"}


async def test_live_provider_without_sandbox_probe_refuses_startup(
    loaded: dict[str, ProbeExecutor], artifact: Path
) -> None:
    # Every sandbox setting is present and the executor could answer, so the only
    # reason to refuse is that the manifest declares no probe.
    settings = ODOO_SETTINGS | {"_probe_info": ODOO_INFO}
    profile = _profile("live", {"acme-crm": settings}, artifact)
    registry, _ = _admit(profile, [_plugin("acme-crm", _api_key_section(), artifact)])
    with pytest.raises(KernelError) as exc:
        await _sandbox(profile, registry)
    assert exc.value.code is ErrorCode.STARTUP_REJECTED
    assert "acme-crm" in str(exc.value)
    assert loaded["acme-crm"].probed == []


async def test_live_odoo_sandbox_check_unchanged(
    loaded: dict[str, ProbeExecutor], artifact: Path
) -> None:
    profile = _profile("live", {"odoo19": ODOO_SETTINGS | {"_probe_info": ODOO_INFO}}, artifact)
    registry, _ = _admit(profile, [_plugin("odoo19", _odoo_section(), artifact)])
    assert await _sandbox(profile, registry) == {"conn-odoo19": ODOO_INFO}
    assert loaded["odoo19"].probed == ["conn-odoo19"]


@pytest.mark.parametrize(
    ("settings", "info", "message"),
    [
        ({}, {"sandbox_marker": "other"}, "sandbox marker mismatch"),
        ({}, {"database": "prod"}, "sandbox marker mismatch"),
        ({}, {"company_id": "2"}, "sandbox marker mismatch"),
        ({}, {"bridge_version": "19.0.0.3.0"}, "sandbox marker mismatch"),
        ({}, {"server_version": "18.0"}, "sandbox marker mismatch"),
        ({"expected_sandbox_marker": ""}, {}, "sandbox check not configured"),
        ({"expected_bridge_version": None}, {}, "sandbox marker mismatch"),
    ],
    ids=[
        "marker",
        "database",
        "company",
        "bridge",
        "server-version",
        "no-marker",
        "no-bridge-setting",
    ],
)
async def test_live_odoo_sandbox_mismatch_refuses(
    loaded: dict[str, ProbeExecutor],
    artifact: Path,
    settings: dict[str, Any],
    info: dict[str, Any],
    message: str,
) -> None:
    probe = ODOO_SETTINGS | settings | {"_probe_info": ODOO_INFO | info}
    profile = _profile("live", {"odoo19": probe}, artifact)
    registry, _ = _admit(profile, [_plugin("odoo19", _odoo_section(), artifact)])
    with pytest.raises(KernelError) as exc:
        await _sandbox(profile, registry)
    assert exc.value.code is ErrorCode.STARTUP_REJECTED
    assert message in str(exc.value)


async def test_two_live_providers_each_probe_their_own_executor(
    loaded: dict[str, ProbeExecutor], artifact: Path
) -> None:
    other_info = ODOO_INFO | {"sandbox_marker": "acme-sandbox"}
    profile = _profile(
        "live",
        {
            "odoo19": ODOO_SETTINGS | {"_probe_info": ODOO_INFO},
            "acme-erp": ODOO_SETTINGS
            | {"expected_sandbox_marker": "acme-sandbox", "_probe_info": other_info},
        },
        artifact,
    )
    registry, _ = _admit(
        profile,
        [
            _plugin("odoo19", _odoo_section(), artifact),
            _plugin("acme-erp", _api_key_section(test_connection="sandbox_info"), artifact),
        ],
    )
    found = await _sandbox(profile, registry)
    assert found == {"conn-odoo19": ODOO_INFO, "conn-acme-erp": other_info}
    assert loaded["odoo19"].probed == ["conn-odoo19"]
    assert loaded["acme-erp"].probed == ["conn-acme-erp"]
