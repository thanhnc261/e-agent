"""Committed profiles must carry budgets a real model can finish a run within."""

from __future__ import annotations

from pathlib import Path

import pytest
from e_agent.server.profile import load_profile

PROFILES = Path(__file__).resolve().parents[3] / "profiles"


@pytest.mark.parametrize("name", ["dev-ollama.json", "live.example.json"])
def test_real_model_profiles_raise_the_default_budgets(name: str) -> None:
    budgets = load_profile(PROFILES / name).budgets
    assert budgets.max_model_tokens == 200000
    assert budgets.max_validation_repairs == 4
