from datetime import UTC, datetime

import pytest
from e_agent.contracts.step import StepKind, StepRecord, StepStatus, StepUsage
from pydantic import ValidationError

# Target architecture §5.4, in order.
_TARGET_5_4_FIELDS = [
    "schema_version",
    "tenant_id",
    "run_id",
    "step_id",
    "sequence",
    "kind",
    "status",
    "parent_step_id",
    "action_id",
    "input_refs",
    "output_ref",
    "finding_ids",
    "usage",
    "started_at",
    "finished_at",
]


def _step(**overrides: object) -> StepRecord:
    fields: dict[str, object] = {
        "tenant_id": "t1",
        "run_id": "run_1",
        "step_id": "step_1",
        "sequence": 0,
        "kind": StepKind.VALIDATE,
        "status": StepStatus.STARTED,
        "parent_step_id": None,
        "action_id": None,
        "input_refs": (),
        "output_ref": None,
        "finding_ids": (),
        "usage": StepUsage(),
        "started_at": datetime(2026, 10, 18, tzinfo=UTC),
        "finished_at": None,
    }
    fields.update(overrides)
    return StepRecord.model_validate(fields)


def test_step_record_fields_match_target_5_4() -> None:
    assert list(StepRecord.model_fields) == _TARGET_5_4_FIELDS
    step = _step()
    assert step.schema_version == "step.v1"
    assert {k.value for k in StepKind} == {
        "driver_turn",
        "read",
        "validate",
        "approval_wait",
        "dispatch",
        "verify",
        "reconcile",
    }
    assert {s.value for s in StepStatus} == {
        "started",
        "succeeded",
        "failed",
        "blocked",
        "unknown",
        "skipped",
    }
    assert StepUsage().model_dump() == {"model_tokens": 0, "provider_calls": 0, "active_seconds": 0}


def test_step_record_refuses_other_schema_version_and_naive_time() -> None:
    with pytest.raises(ValidationError):
        _step(schema_version="step.v2")
    with pytest.raises(ValidationError, match="timezone-aware"):
        _step(started_at=datetime(2026, 10, 18))


def test_step_record_counts_are_non_negative() -> None:
    with pytest.raises(ValidationError):
        _step(sequence=-1)
    with pytest.raises(ValidationError):
        StepUsage(model_tokens=-1)
    with pytest.raises(ValidationError):
        StepUsage(active_seconds=-0.5)
