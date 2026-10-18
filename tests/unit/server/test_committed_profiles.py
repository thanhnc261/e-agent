"""Committed profiles must carry budgets a real model can finish a run within, and keep new
features off until the owner turns them on (ADR 0027)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from e_agent.contracts.features import FeatureMode
from e_agent.plugins.erp.simulator import fixture_profile_path
from e_agent.server.profile import load_profile

PROFILES = Path(__file__).resolve().parents[3] / "profiles"
COMMITTED = (PROFILES / "dev-ollama.json", PROFILES / "live.example.json", fixture_profile_path())


@pytest.mark.parametrize("name", ["dev-ollama.json", "live.example.json"])
def test_real_model_profiles_raise_the_default_budgets(name: str) -> None:
    budgets = load_profile(PROFILES / name).budgets
    assert budgets.max_model_tokens == 200000
    assert budgets.max_validation_repairs == 4


def test_committed_profiles_keep_execution_ir_off() -> None:
    checked = 0
    for path in COMMITTED:
        assert json.loads(Path(path).read_text("utf-8"))["features"] == {"execution_ir": "off"}
        assert load_profile(path).features.execution_ir is FeatureMode.OFF, path
        checked += 1
    assert checked == 3, f"checked {checked} committed profiles"
