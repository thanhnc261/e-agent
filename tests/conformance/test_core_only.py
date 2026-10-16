"""The core-only install gate's helpers (roadmap Phase 1d, Task 1d.8, decision D3).

``scripts/check_core_only.py`` builds wheels and starts a server, so it runs as
its own gate set (``core``). These tests check its helpers and the test pack it
builds without building any wheel.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
from e_agent.sdk import ENTRY_POINT_GROUP, MANIFEST_FILENAME
from e_agent.sdk.manifest import PluginManifest
from e_agent.server.profile import Profile

REPO = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "check_core_only", REPO / "scripts" / "check_core_only.py"
)
assert _spec is not None and _spec.loader is not None
core = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(core)


def test_script_constants_match_the_sdk() -> None:
    assert core.ENTRY_POINT_GROUP == ENTRY_POINT_GROUP
    assert core.MANIFEST_FILENAME == MANIFEST_FILENAME


def test_core_list_is_every_distribution_minus_erp() -> None:
    derived = core.core_distributions()
    print(f"classified {len(derived)} core and {len(core.ERP_DISTRIBUTIONS)} ERP distributions")
    assert derived, "no core distributions found"
    assert sorted(core.CORE_DISTRIBUTIONS) == derived


def test_core_list_fails_on_an_unclassified_or_missing_distribution(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="no distributions"):
        core.core_distributions(tmp_path)
    for name in sorted(core.ERP_DISTRIBUTIONS):
        (tmp_path / name).mkdir()
        (tmp_path / name / "pyproject.toml").write_text(f'[project]\nname = "{name}"\n')
    assert core.core_distributions(tmp_path) == []
    (tmp_path / "x").mkdir()
    (tmp_path / "x" / "pyproject.toml").write_text('[project]\nname = "e-agent-new"\n')
    assert core.core_distributions(tmp_path) == ["e-agent-new"]
    (tmp_path / "e-agent-erp" / "pyproject.toml").unlink()
    with pytest.raises(ValueError, match="e-agent-erp"):
        core.core_distributions(tmp_path)


def test_no_core_distribution_depends_on_erp() -> None:
    projects = core.dist_projects()
    checked = 0
    problems = []
    for name in core.CORE_DISTRIBUTIONS:
        requires = core.requirement_names(projects[name])
        checked += len(requires)
        problems += [f"{name} -> {r}" for r in requires if r in core.ERP_DISTRIBUTIONS]
    print(f"checked {checked} requirements of {len(core.CORE_DISTRIBUTIONS)} core distributions")
    assert checked > 0
    assert problems == []


def test_requirement_names_read_optional_extras() -> None:
    project = {
        "dependencies": ["e-agent-plugin-sdk[http]>=0.1,<0.2"],
        "optional-dependencies": {"erp": ["E_Agent_Domain_ERP>=0.1"]},
    }
    assert core.requirement_names(project) == ["e-agent-domain-erp", "e-agent-plugin-sdk"]


def test_pack_project_entry_point_and_manifest_agree(tmp_path: Path) -> None:
    project_dir = core.write_pack_project(tmp_path)
    project = tomllib.loads((project_dir / "pyproject.toml").read_text("utf-8"))["project"]
    [(_, value)] = project["entry-points"][ENTRY_POINT_GROUP].items()
    manifest_path = project_dir / core.PACK_PACKAGE / MANIFEST_FILENAME
    manifest = PluginManifest.model_validate(json.loads(manifest_path.read_text("utf-8")))
    assert value == manifest.factory
    assert manifest.version == project["version"] == core.PACK_VERSION
    assert manifest.plugin_id == core.PACK_PLUGIN_ID
    assert project["name"] == core.PACK_DISTRIBUTION
    module, attr = manifest.factory.split(":")
    assert (project_dir / Path(*module.split("."))).with_suffix(".py").is_file()
    assert attr == "create_plugin"


def test_pack_imports_only_contracts_and_sdk() -> None:
    imports = [
        line.split()[1]
        for line in core.PACK_MODULE_SOURCE.splitlines()
        if line.startswith(("from ", "import ")) and "__future__" not in line
    ]
    assert imports
    assert all(m.startswith(("e_agent.contracts", "e_agent.sdk", "dataclasses")) for m in imports)


def test_profile_validates_and_names_the_pack_preset() -> None:
    profile = Profile.model_validate(core.core_profile())
    assert profile.driver.task_kind == core.PRESET_KIND
    assert profile.driver.kind == core.DRIVER_KIND
    assert list(profile.enabled_plugins) == [core.PACK_PLUGIN_ID]
    assert profile.tenant_id == core.TENANT
    [conn] = profile.connections
    assert (conn.connection_id, conn.integration_id) == (core.CONNECTION, core.INTEGRATION)
    bindings = [b["binding_id"] for b in core.pack_manifest()["provides_bindings"]]
    assert sorted(profile.bindings) == sorted(bindings)
    assert profile.store.kind == "memory"


_COMPOSE = """
import asyncio, json, sys
sys.path.insert(0, sys.argv[1])
from e_agent.server.bootstrap import build_runtime
from e_agent.server.profile import Profile

async def main():
    profile = Profile.model_validate(json.loads(sys.argv[2]))
    rt = await build_runtime(profile, plugin_paths=[sys.argv[1]])
    print(json.dumps({
        "admitted": rt.registry.report.admitted,
        "presets": sorted(rt.registry.task_presets),
        "driver": rt.versions.get("driver"),
        "modules": sorted(sys.modules),
    }))

asyncio.run(main())
"""


def _install_pack(root: Path) -> None:
    """The pack as an installed distribution, from the files the script writes."""
    for relative, text in core.pack_package_files().items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, "utf-8")
    project = tomllib.loads(core.pack_pyproject())["project"]
    info = root / f"{core.PACK_PACKAGE}-{project['version']}.dist-info"
    info.mkdir()
    (info / "METADATA").write_text(
        f"Metadata-Version: 2.1\nName: {project['name']}\nVersion: {project['version']}\n"
    )
    entry_points = "".join(
        f"{name} = {value}\n" for name, value in project["entry-points"][ENTRY_POINT_GROUP].items()
    )
    (info / "entry_points.txt").write_text(f"[{ENTRY_POINT_GROUP}]\n{entry_points}")
    (info / "RECORD").write_text("".join(f"{p},,\n" for p in core.pack_package_files()))


def test_pack_composes_through_bootstrap(tmp_path: Path) -> None:
    _install_pack(tmp_path)
    out = subprocess.run(
        [sys.executable, "-c", _COMPOSE, str(tmp_path), json.dumps(core.core_profile())],
        capture_output=True,
        text=True,
        check=True,
        cwd=REPO,
    ).stdout
    result = json.loads(out)
    assert result["admitted"] == [core.PACK_PLUGIN_ID]
    assert result["presets"] == [core.PRESET_KIND]
    assert result["driver"] == "core-notes-driver"
    assert f"{core.PACK_PACKAGE}.plugin" in result["modules"]
    assert [m for m in result["modules"] if m.startswith(core.ERP_MODULES)] == []


def test_forbidden_check_flags_each_erp_distribution() -> None:
    clean = ["e-agent-server", "fastapi"]
    assert core.forbidden_installed(clean) == []
    for name in sorted(core.ERP_DISTRIBUTIONS):
        # Installed names come in any case and with underscores.
        assert core.forbidden_installed([*clean, name.replace("-", "_").upper()]) == [name]
    assert core.forbidden_installed([*clean, *core.ERP_DISTRIBUTIONS]) == sorted(
        core.ERP_DISTRIBUTIONS
    )
    with pytest.raises(ValueError, match="no installed distributions"):
        core.forbidden_installed([])


def test_wait_ready_fails_at_once_when_the_server_exits(tmp_path: Path) -> None:
    log = tmp_path / "server.log"
    with log.open("wb") as out:
        proc = subprocess.Popen(
            [sys.executable, "-c", "print('boom'); raise SystemExit(3)"],
            stdout=out,
            stderr=subprocess.STDOUT,
        )
        proc.wait()
    url = f"http://127.0.0.1:{core.free_port()}/health/ready"
    with pytest.raises(RuntimeError, match=r"(?s)exited with 3.*boom"):
        core.wait_ready(proc, url, log, timeout=5)


def test_locked_constraints_are_exact_third_party_pins() -> None:
    text = "# header\n\nanyio==4.15.1\ncffi==2.1.1 ; platform_python_implementation != 'PyPy'\n"
    assert core.locked_constraints(text) == ["anyio", "cffi"]
    for bad in (
        "e-agent-kernel==0.1.0",
        "E_Agent_Server==0.1.0",
        "core-test-pack==0.1.0",
        "-e ./dists/kernel",
        "pkg @ file:///x/pkg.whl",
        "fastapi>=0.142",
    ):
        with pytest.raises(ValueError, match="constraint"):
            core.locked_constraints(f"anyio==4.15.1\n{bad}\n")
    with pytest.raises(ValueError, match="no locked third-party constraints"):
        core.locked_constraints("# only a comment\n\n")


def test_uv_export_gives_the_locked_third_party_pins() -> None:
    out = subprocess.run(
        [
            "uv",
            "export",
            "--frozen",
            "--no-hashes",
            "--no-header",
            "--no-annotate",
            "--no-emit-workspace",
            "--all-groups",
        ],
        capture_output=True,
        text=True,
        check=True,
        cwd=REPO,
    ).stdout
    pins = core.locked_constraints(out)
    lock = tomllib.loads((REPO / "uv.lock").read_text("utf-8"))
    registry = {p["name"] for p in lock["package"] if "registry" in p.get("source", {})}
    print(f"{len(pins)} constraints, {len(registry)} registry packages in uv.lock")
    assert set(pins) == registry
