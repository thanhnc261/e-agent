"""Committed profiles must carry budgets a real model can finish a run within, and keep new
features off until the owner turns them on (ADR 0027)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from e_agent.contracts.features import FeatureMode
from e_agent.plugins.erp.simulator import fixture_profile_path
from e_agent.server.api import create_app
from e_agent.server.bootstrap import build_runtime
from e_agent.server.profile import load_profile
from fastapi.testclient import TestClient

PROFILES = Path(__file__).resolve().parents[3] / "profiles"
COMMITTED = (PROFILES / "dev-ollama.json", PROFILES / "live.example.json", fixture_profile_path())


@pytest.mark.parametrize("name", ["dev-ollama.json", "live.example.json"])
def test_real_model_profiles_raise_the_default_budgets(name: str) -> None:
    budgets = load_profile(PROFILES / name).budgets
    assert budgets.max_model_tokens == 200000
    assert budgets.max_validation_repairs == 4


ALL_OFF = {
    "execution_ir": "off",
    "context_assembler": "off",
    "kernel_repeat": "off",
    "grounded_answers": "off",
}


def test_committed_profiles_keep_phase3_toggles_off() -> None:
    """Every committed profile names all four toggles, each ``off`` (ADR 0027, ADR 0032)."""
    checked = 0
    for path in COMMITTED:
        assert json.loads(Path(path).read_text("utf-8"))["features"] == ALL_OFF, path
        features = load_profile(path).features
        assert all(getattr(features, name) is FeatureMode.OFF for name in ALL_OFF), path
        checked += 1
    assert checked == 3, f"checked {checked} committed profiles"


def test_readiness_reports_four_toggles() -> None:
    with TestClient(create_app(lambda: build_runtime(load_profile(fixture_profile_path())))) as c:
        features = c.get("/health/ready").json()["features"]
    assert features == ALL_OFF
    print(f"readiness toggles: {len(features)}")
    assert len(features) == 4
