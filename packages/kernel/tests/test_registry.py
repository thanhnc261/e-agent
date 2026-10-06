"""Registry admission and binding resolution (MVP design §6, §13)."""

import json
from pathlib import Path

import pytest
from e_agent.contracts.capability import CapabilityDescriptor, EffectKind
from e_agent.kernel.errors import ErrorCode, KernelError
from e_agent.kernel.registry import EnabledPlugin, PluginRegistry
from e_agent.sdk.discovery import discover
from e_agent.sdk.manifest import BindingTemplate
from e_agent.sdk.ports import PluginContribution

from .conftest import BINDINGS, CREATE, READ


def _registry(**connections: tuple[str, ...]) -> PluginRegistry:
    reg = PluginRegistry(connections or {"notes-mem.read": ("c1",)})
    reg.register(
        plugin_id="notes-fixture",
        plugin_version="1",
        declared_capabilities=(READ, CREATE),
        binding_templates=BINDINGS,
        contribution=PluginContribution(capabilities=(READ, CREATE)),
    )
    return reg


def test_conflicting_capability_definitions_rejected() -> None:
    reg = _registry()
    other = CapabilityDescriptor(
        contract_id=READ.contract_id,
        effect=EffectKind.WRITE,
        input_schema_id="x",
        output_schema_id="y",
    )
    with pytest.raises(KernelError) as err:
        reg.register(
            plugin_id="other",
            plugin_version="1",
            declared_capabilities=(other,),
            binding_templates=(),
            contribution=PluginContribution(capabilities=(other,)),
        )
    assert err.value.code is ErrorCode.STARTUP_REJECTED


def test_duplicate_binding_id_rejected() -> None:
    reg = _registry()
    with pytest.raises(KernelError):
        reg.register(
            plugin_id="other",
            plugin_version="1",
            declared_capabilities=(),
            binding_templates=(
                BindingTemplate(binding_id="notes-mem.read", contract_id=READ.contract_id),
            ),
            contribution=PluginContribution(),
        )


def test_contribution_must_match_manifest() -> None:
    reg = PluginRegistry({})
    with pytest.raises(KernelError):
        reg.register(
            plugin_id="p",
            plugin_version="1",
            declared_capabilities=(READ,),
            binding_templates=(),
            contribution=PluginContribution(capabilities=()),
        )


def test_two_connections_resolve_and_ambiguity_is_refused() -> None:
    reg = _registry(**{"notes-mem.read": ("c1", "c2")})
    assert reg.resolve(READ.contract_id, "c1").connection_id == "c1"
    assert reg.resolve(READ.contract_id, "c2").connection_id == "c2"
    with pytest.raises(KernelError) as err:
        reg.resolve(READ.contract_id, "c3")
    assert err.value.code is ErrorCode.FORBIDDEN
    reg2 = PluginRegistry({"notes-mem.read": ("c1",), "other-impl.read": ("c1",)})
    reg2.register(
        plugin_id="a",
        plugin_version="1",
        declared_capabilities=(READ, CREATE),
        binding_templates=BINDINGS,
        contribution=PluginContribution(capabilities=(READ, CREATE)),
    )
    reg2.register(
        plugin_id="b",
        plugin_version="1",
        declared_capabilities=(),
        binding_templates=(
            BindingTemplate(binding_id="other-impl.read", contract_id=READ.contract_id),
        ),
        contribution=PluginContribution(),
    )
    with pytest.raises(KernelError) as amb:
        reg2.resolve(READ.contract_id, "c1")
    assert amb.value.code is ErrorCode.CONFLICT


# --- admission through discovery (no import for disabled plugins) ----------------


def _install(root: Path, version: str = "0.3.0", sdk_api: str = ">=1.0,<2.0") -> Path:
    pkg = root / "notes_fixture"
    pkg.mkdir(parents=True)
    marker = root / "IMPORTED"
    (pkg / "__init__.py").write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('imported')\n"
    )
    (pkg / "plugin.py").write_text(
        "from e_agent.sdk.ports import PluginContribution\n"
        "def create_plugin(services):\n    return PluginContribution()\n"
    )
    manifest = {
        "plugin_id": "notes-fixture",
        "version": version,
        "sdk_api": sdk_api,
        "factory": "notes_fixture.plugin:create_plugin",
        "kind": "domain",
    }
    (pkg / "e_agent_plugin.json").write_text(json.dumps(manifest))
    info = root / f"notes_fixture-{version}.dist-info"
    info.mkdir()
    (info / "METADATA").write_text(
        f"Metadata-Version: 2.1\nName: notes-fixture\nVersion: {version}\n"
    )
    (info / "entry_points.txt").write_text(
        "[e_agent.plugins.v1]\nnotes = notes_fixture.plugin:create_plugin\n"
    )
    (info / "RECORD").write_text(
        "notes_fixture/__init__.py,,\nnotes_fixture/plugin.py,,\n"
        "notes_fixture/e_agent_plugin.json,,\n"
    )
    return marker


def test_disabled_plugin_is_never_imported(tmp_path: Path) -> None:
    marker = _install(tmp_path)
    reg = PluginRegistry({})
    report = reg.admit(discover([str(tmp_path)]), enabled={})
    assert report.skipped == ["notes-fixture"]
    assert not marker.exists()


def test_enabled_but_missing_plugin_fails_startup(tmp_path: Path) -> None:
    with pytest.raises(KernelError):
        PluginRegistry({}).admit(discover([str(tmp_path)]), {"ghost": EnabledPlugin("1.0")})


def test_version_mismatch_rejected_before_import(tmp_path: Path) -> None:
    marker = _install(tmp_path)
    with pytest.raises(KernelError):
        PluginRegistry({}).admit(
            discover([str(tmp_path)]), {"notes-fixture": EnabledPlugin("9.9.9")}
        )
    assert not marker.exists()


def test_incompatible_sdk_rejected_before_import(tmp_path: Path) -> None:
    marker = _install(tmp_path, sdk_api=">=2.0,<3.0")
    with pytest.raises(KernelError):
        PluginRegistry({}).admit(
            discover([str(tmp_path)]), {"notes-fixture": EnabledPlugin("0.3.0")}
        )
    assert not marker.exists()


def test_manifest_digest_must_match_inventory(tmp_path: Path) -> None:
    marker = _install(tmp_path)
    with pytest.raises(KernelError):
        PluginRegistry({}).admit(
            discover([str(tmp_path)]),
            {"notes-fixture": EnabledPlugin("0.3.0", manifest_sha256="0" * 64)},
        )
    assert not marker.exists()
