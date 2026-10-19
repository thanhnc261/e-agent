"""Profile.features: typed toggles from the profile only, default off (ADR 0027)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from e_agent.contracts.features import FeatureMode, Features
from e_agent.plugins.erp.simulator import fixture_profile_path
from e_agent.server.bootstrap import build_runtime
from e_agent.server.profile import Profile, load_profile
from pydantic import ValidationError


def _raw() -> dict:  # type: ignore[type-arg]
    return json.loads(fixture_profile_path().read_text("utf-8"))  # type: ignore[no-any-return]


def test_profile_features_default_off(tmp_path: Path) -> None:
    raw = _raw()
    raw.pop("features", None)
    path = tmp_path / "profile.json"
    path.write_text(json.dumps(raw), "utf-8")
    assert load_profile(path).features.execution_ir == "off"
    assert load_profile(path).features == Features()


def test_profile_rejects_unknown_feature() -> None:
    with pytest.raises(ValidationError):
        Profile.model_validate({**_raw(), "features": {"nope": "on"}})


async def test_coordinator_receives_profile_features() -> None:
    profile = load_profile(fixture_profile_path()).model_copy(
        update={"features": Features(execution_ir=FeatureMode.SHADOW)}
    )
    runtime = await build_runtime(profile)
    assert runtime.coordinator._features.execution_ir is FeatureMode.SHADOW


async def test_coordinator_features_default_off() -> None:
    runtime = await build_runtime(load_profile(fixture_profile_path()))
    assert runtime.coordinator._features == Features()
