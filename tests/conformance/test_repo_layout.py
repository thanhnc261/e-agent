"""Repository layout after the Phase 1 move (roadmap Phase 1a, plan Task 1a.2)."""

import importlib
import subprocess
import tomllib
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


def test_no_old_layout_files_remain_tracked() -> None:
    # Ignored caches may survive in older checkouts; only tracked files matter.
    tracked = subprocess.run(
        ["git", "ls-files", "--", "packages", "apps"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert tracked == ""


def test_every_dist_builds_an_existing_src_package() -> None:
    configs = sorted((REPO / "dists").glob("*/pyproject.toml"))
    assert len(configs) == 12
    # The e-agent-erp bundle carries no code: only its dependencies (Task 1d.8).
    bundle = REPO / "dists" / "bundle-erp" / "pyproject.toml"
    assert bundle in configs
    for config in configs:
        build = tomllib.loads(config.read_text(encoding="utf-8"))["tool"]["hatch"]["build"]
        if config == bundle:
            assert "hooks" not in build, config
            assert build["targets"]["wheel"] == {"bypass-selection": True}, config
            continue
        hook = build["hooks"]["custom"]
        assert (config.parent / hook["path"]).is_file(), config
        assert (REPO / "src" / hook["package"]).is_dir(), config


@pytest.mark.parametrize(
    "package",
    ["contracts", "sdk", "kernel", "server"]
    + [f"adapters.{a}" for a in ("pydantic_ai", "postgres", "shacl", "secretstore_local")]
    + [f"plugins.erp.{p}" for p in ("domain", "odoo", "simulator")],
)
def test_development_install_imports_from_src_not_a_copy(package: str) -> None:
    module = importlib.import_module(f"e_agent.{package}")
    assert module.__file__ is not None
    assert Path(module.__file__).resolve().is_relative_to(REPO / "src" / "e_agent")


def test_e_agent_stays_a_namespace_package() -> None:
    assert (REPO / "src" / "e_agent").is_dir()
    assert not (REPO / "src" / "e_agent" / "__init__.py").exists()
    assert not (REPO / "src" / "e_agent" / "adapters" / "__init__.py").exists()


# Old homes of the domain pack and the Odoo adapter before Task 1d.10 (ADR 0026).
OLD_PLUGIN_PATHS = (
    "e_agent.erp",
    "e_agent.adapters.odoo",
    "e_agent/erp",
    "e_agent/adapters/odoo",
    "tests/unit/erp",
    "tests/unit/adapters/odoo",
)
# History, harness records and the mover with its fixtures keep the old paths.
PLUGIN_PATH_EXEMPT = (
    "archive",
    "research",
    "harness/state",
    "docs/handoffs",
    "scripts/repo_move.py",
    "tests/conformance/test_repo_move.py",
    "tests/conformance/test_repo_layout.py",
)
# Dated records keep the paths of their day, as in `repo_move.py check` (DOC_HISTORY).
DATED_DOCS = ("docs/adr/*.md", "docs/plans/*.md", "docs/reviews/*.md", "docs/specs/*.md")


def test_erp_plugins_live_under_plugins_erp() -> None:
    for old in OLD_PLUGIN_PATHS[2:]:
        assert not (REPO / ("src" if old.startswith("e_agent") else "") / old).exists(), old
    plugins = REPO / "src" / "e_agent" / "plugins" / "erp"
    tests = REPO / "tests" / "unit" / "plugins" / "erp"
    for name in ("domain", "odoo", "simulator"):
        assert (plugins / name / "__init__.py").is_file(), name
        assert (plugins / name / "e_agent_plugin.json").is_file(), name
        assert (tests / name).is_dir(), name


def test_no_old_plugin_module_paths_remain() -> None:
    # Code, config and current docs; a word boundary keeps e_agent.erp_x out.
    pattern = "|".join(p.replace(".", "\\.") + "([^A-Za-z0-9_]|$)" for p in OLD_PLUGIN_PATHS)
    exclude = [f":!{p}" for p in PLUGIN_PATH_EXEMPT + DATED_DOCS]
    found = subprocess.run(
        ["git", "grep", "-n", "-E", pattern, "--", ".", *exclude],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert found.returncode in (0, 1), found.stderr
    assert found.stdout == ""
    # Not vacuous: the new module names are in use.
    used = subprocess.run(
        ["git", "grep", "-c", "e_agent.plugins.erp.domain", "--", "src", "tests"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert used.stdout.count("\n") >= 10, used.stdout


def test_plugins_dirs_are_namespace_packages() -> None:
    # An __init__.py here would change the import root and, through the hook, the pins.
    plugins = REPO / "src" / "e_agent" / "plugins"
    for directory in (plugins, plugins / "erp"):
        assert directory.is_dir(), directory
        assert not (directory / "__init__.py").exists(), directory
