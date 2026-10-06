"""Metadata-only discovery: plugins are found without importing their code."""

import json
import sys
from pathlib import Path

import pytest
from e_agent.sdk.discovery import DiscoveryError, discover
from e_agent.sdk.manifest import PluginManifest

MANIFEST = {
    "plugin_id": "notes-fixture",
    "version": "0.3.0",
    "sdk_api": ">=1.0,<2.0",
    "factory": "notes_fixture.plugin:create_plugin",
    "kind": "domain",
}


def make_dist(root: Path, manifest: dict[str, object] | None = MANIFEST) -> Path:
    """Write a minimal installed distribution whose package records an import marker."""
    pkg = root / "notes_fixture"
    pkg.mkdir(parents=True)
    marker = root / "IMPORTED"
    (pkg / "__init__.py").write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('imported')\n"
    )
    (pkg / "plugin.py").write_text("def create_plugin(services):\n    raise AssertionError\n")
    files = ["notes_fixture/__init__.py", "notes_fixture/plugin.py"]
    if manifest is not None:
        (pkg / "e_agent_plugin.json").write_text(json.dumps(manifest))
        files.append("notes_fixture/e_agent_plugin.json")
    info = root / "notes_fixture-0.3.0.dist-info"
    info.mkdir()
    (info / "METADATA").write_text("Metadata-Version: 2.1\nName: notes-fixture\nVersion: 0.3.0\n")
    (info / "entry_points.txt").write_text(
        "[e_agent.plugins.v1]\nnotes = notes_fixture.plugin:create_plugin\n"
    )
    (info / "RECORD").write_text("\n".join(f"{f},," for f in files) + "\n")
    return marker


def test_discovery_reads_manifest_without_importing(tmp_path: Path) -> None:
    marker = make_dist(tmp_path)
    found = discover([str(tmp_path)])
    assert [p.manifest.plugin_id for p in found] == ["notes-fixture"]
    assert found[0].entry_point_value == "notes_fixture.plugin:create_plugin"
    assert not marker.exists(), "discovery must not import plugin code"
    assert "notes_fixture" not in sys.modules


def test_missing_manifest_is_rejected(tmp_path: Path) -> None:
    make_dist(tmp_path, manifest=None)
    with pytest.raises(DiscoveryError):
        discover([str(tmp_path)])


def test_manifest_validation() -> None:
    m = PluginManifest.model_validate(MANIFEST)
    assert m.supports_sdk("1.0")
    assert not m.supports_sdk("2.0")
    with pytest.raises(ValueError, match="sdk_api"):
        PluginManifest.model_validate({**MANIFEST, "sdk_api": "1.x"})
    with pytest.raises(ValueError, match="factory"):
        PluginManifest.model_validate({**MANIFEST, "factory": "no_colon"})
