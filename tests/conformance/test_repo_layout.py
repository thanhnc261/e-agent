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
    assert len(configs) == 10
    for config in configs:
        build = tomllib.loads(config.read_text(encoding="utf-8"))["tool"]["hatch"]["build"]
        hook = build["hooks"]["custom"]
        assert (config.parent / hook["path"]).is_file(), config
        assert (REPO / "src" / hook["package"]).is_dir(), config


@pytest.mark.parametrize(
    "package",
    ["contracts", "sdk", "kernel", "erp", "server"]
    + [f"adapters.{a}" for a in ("pydantic_ai", "postgres", "odoo", "shacl", "secretstore_local")],
)
def test_development_install_imports_from_src_not_a_copy(package: str) -> None:
    module = importlib.import_module(f"e_agent.{package}")
    assert module.__file__ is not None
    assert Path(module.__file__).resolve().is_relative_to(REPO / "src" / "e_agent")


def test_e_agent_stays_a_namespace_package() -> None:
    assert (REPO / "src" / "e_agent").is_dir()
    assert not (REPO / "src" / "e_agent" / "__init__.py").exists()
    assert not (REPO / "src" / "e_agent" / "adapters" / "__init__.py").exists()
