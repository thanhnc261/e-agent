"""Feature toggles are typed records, default off (ADR 0027)."""

from __future__ import annotations

import pytest
from e_agent.contracts.features import FeatureMode, Features
from pydantic import ValidationError


def test_feature_mode_values() -> None:
    assert [m.value for m in FeatureMode] == ["off", "shadow", "on"]


def test_features_default_all_off() -> None:
    features = Features()
    assert features.execution_ir is FeatureMode.OFF
    assert all(v is FeatureMode.OFF for v in features.model_dump().values())


def test_features_reject_unknown_name_and_mode() -> None:
    with pytest.raises(ValidationError):
        Features.model_validate({"nope": "on"})
    with pytest.raises(ValidationError):
        Features.model_validate({"execution_ir": "enabled"})


def test_features_parse_modes() -> None:
    assert Features.model_validate({"execution_ir": "shadow"}).execution_ir is FeatureMode.SHADOW
