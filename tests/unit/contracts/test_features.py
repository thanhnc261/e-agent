"""Feature toggles are typed records, default off (ADR 0027)."""

from __future__ import annotations

import pytest
from e_agent.contracts.features import FeatureMode, Features, RunModes
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


PHASE3_TOGGLES = ("context_assembler", "kernel_repeat", "grounded_answers")


def test_phase3_toggles_default_off() -> None:
    """The three Phase 3 toggles exist, default off, and parse like every toggle (ADR 0032)."""
    features = Features()
    assert list(Features.model_fields) == ["execution_ir", *PHASE3_TOGGLES, "conversations"]
    for name in PHASE3_TOGGLES:
        assert getattr(features, name) is FeatureMode.OFF, name
        assert getattr(Features.model_validate({name: "on"}), name) is FeatureMode.ON, name
        with pytest.raises(ValidationError):
            Features.model_validate({name: "enabled"})
    print(f"phase 3 toggles: {len(PHASE3_TOGGLES)}")
    assert len(PHASE3_TOGGLES) == 3


def test_run_modes_pin_exactly_the_runtime_toggles() -> None:
    """``execution_ir`` is not pinned (ADR 0032 §8); an absent pin means every mode is off.
    ``conversations`` is pinned with the Phase 3 modes (ADR 0023 §9)."""
    assert list(RunModes.model_fields) == [*PHASE3_TOGGLES, "conversations"]
    assert RunModes().all_off
    on = Features(context_assembler=FeatureMode.ON, execution_ir=FeatureMode.ON)
    assert RunModes.from_features(on) == RunModes(context_assembler=FeatureMode.ON)
    assert not RunModes.from_features(on).all_off
    assert RunModes.from_features(Features(execution_ir=FeatureMode.ON)).all_off
    with pytest.raises(ValidationError):
        RunModes.model_validate({"execution_ir": "on"})


def test_conversations_default_off() -> None:
    """``features.conversations`` exists, defaults to ``off``, parses like every toggle and is
    pinned per run; ``conversations`` alone makes a pin that is not all off (ADR 0023 §9)."""
    assert Features().conversations is FeatureMode.OFF
    assert RunModes().conversations is FeatureMode.OFF
    for mode in FeatureMode:
        assert Features.model_validate({"conversations": mode.value}).conversations is mode
    with pytest.raises(ValidationError):
        Features.model_validate({"conversations": "enabled"})
    shadow = RunModes.from_features(Features(conversations=FeatureMode.SHADOW))
    assert shadow == RunModes(conversations=FeatureMode.SHADOW)
    assert not shadow.all_off
    assert RunModes.from_features(Features()).all_off
