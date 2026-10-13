"""Repository layout after the Phase 1 move (roadmap Phase 1a, plan Task 1a.2)."""

import tomllib
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.xfail(
    (REPO / "packages").exists(),
    reason="the layout move runs in Task 1a.3",
    strict=True,
)


def test_no_old_layout_directories_remain() -> None:
    assert not (REPO / "packages").exists()
    assert not (REPO / "apps").exists()


def test_every_dist_force_include_source_exists() -> None:
    configs = sorted((REPO / "dists").glob("*/pyproject.toml"))
    assert len(configs) == 10
    for config in configs:
        wheel = tomllib.loads(config.read_text(encoding="utf-8"))["tool"]["hatch"]["build"][
            "targets"
        ]["wheel"]
        assert wheel["force-include"], config
        for source in wheel["force-include"]:
            assert (config.parent / source).resolve().is_dir(), f"{config}: {source}"


def test_e_agent_stays_a_namespace_package() -> None:
    assert (REPO / "src" / "e_agent").is_dir()
    assert not (REPO / "src" / "e_agent" / "__init__.py").exists()
    assert not (REPO / "src" / "e_agent" / "adapters" / "__init__.py").exists()
