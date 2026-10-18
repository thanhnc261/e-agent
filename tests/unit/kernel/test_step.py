"""Step-record builders (ADR 0025, target §5.4, §6.4.7): append-only state rows."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from e_agent.contracts.evidence import EvidenceRef
from e_agent.contracts.step import StepKind, StepRecord, StepStatus, StepUsage
from e_agent.kernel.step import finish_step, start_step

AT = datetime(2026, 10, 18, 9, 0, tzinfo=UTC)
LATER = AT + timedelta(seconds=3)


def _ref() -> EvidenceRef:
    return EvidenceRef(
        evidence_id="ev1",
        tenant_id="t1",
        source="notes",
        locator="note/1",
        revision="r1",
        observed_at=AT,
        scope="tenant:t1",
    )


def _started(**overrides: object) -> StepRecord:
    fields: dict[str, object] = {
        "tenant_id": "t1",
        "run_id": "run_1",
        "step_id": "stp_validate",
        "sequence": 4,
        "kind": StepKind.VALIDATE,
        "now": AT,
    }
    return start_step(**{**fields, **overrides})  # type: ignore[arg-type]


def test_start_step_builds_a_started_row() -> None:
    step = _started(action_id="act_1", parent_step_id="stp_prev", input_refs=(_ref(),))
    assert step == StepRecord(
        tenant_id="t1",
        run_id="run_1",
        step_id="stp_validate",
        sequence=4,
        kind=StepKind.VALIDATE,
        status=StepStatus.STARTED,
        parent_step_id="stp_prev",
        action_id="act_1",
        input_refs=(_ref(),),
        started_at=AT,
    )
    assert step.finished_at is None


def test_finish_step_appends_a_row_with_the_same_step_id() -> None:
    started = _started(action_id="act_1", input_refs=(_ref(),))
    usage = StepUsage(provider_calls=1, active_seconds=3)
    done = finish_step(
        started,
        sequence=5,
        status=StepStatus.SUCCEEDED,
        now=LATER,
        output_ref=_ref(),
        finding_ids=("f1",),
        usage=usage,
    )
    assert (done.step_id, done.kind, done.run_id, done.tenant_id) == (
        "stp_validate",
        StepKind.VALIDATE,
        "run_1",
        "t1",
    )
    assert done.sequence == 5
    assert done.status is StepStatus.SUCCEEDED
    assert (done.started_at, done.finished_at) == (AT, LATER)
    assert done.action_id == "act_1"
    assert done.input_refs == (_ref(),)
    assert (done.output_ref, done.finding_ids, done.usage) == (_ref(), ("f1",), usage)
    assert started.status is StepStatus.STARTED  # the earlier row is unchanged


def test_finish_step_may_set_the_action_found_during_the_stage() -> None:
    done = finish_step(_started(), sequence=5, status=StepStatus.BLOCKED, now=LATER, action_id="a")
    assert done.action_id == "a"


@pytest.mark.parametrize("sequence", [3, 4])
def test_finish_step_needs_a_higher_sequence(sequence: int) -> None:
    with pytest.raises(ValueError, match="sequence"):
        finish_step(_started(), sequence=sequence, status=StepStatus.FAILED, now=LATER)


def test_finish_step_refuses_started_status_and_a_finished_row() -> None:
    with pytest.raises(ValueError, match="terminal"):
        finish_step(_started(), sequence=5, status=StepStatus.STARTED, now=LATER)
    done = finish_step(_started(), sequence=5, status=StepStatus.FAILED, now=LATER)
    with pytest.raises(ValueError, match="started"):
        finish_step(done, sequence=6, status=StepStatus.SUCCEEDED, now=LATER)


def test_finish_step_refuses_time_before_start() -> None:
    with pytest.raises(ValueError, match="before"):
        finish_step(_started(), sequence=5, status=StepStatus.FAILED, now=AT - timedelta(seconds=1))


def test_finish_step_refuses_another_action() -> None:
    with pytest.raises(ValueError, match="action"):
        finish_step(
            _started(action_id="act_1"),
            sequence=5,
            status=StepStatus.FAILED,
            now=LATER,
            action_id="act_2",
        )


def test_finish_step_refuses_a_naive_time() -> None:
    with pytest.raises(ValueError, match="timezone"):
        finish_step(
            _started(), sequence=5, status=StepStatus.FAILED, now=datetime(2026, 10, 18, 10)
        )
