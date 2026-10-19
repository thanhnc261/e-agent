"""Step-record builders (ADR 0025, target §5.4, §6.4.7).

A step record is an append-only state row: a stage starts with a ``STARTED`` row and ends
with a second row of the same ``step_id`` and a higher ``sequence``. The builders are pure:
the caller supplies the time, the step id and the run's next sequence, and puts the rows
into the `EventBatch` of the write that records the stage (`sdk/store.py`).
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from e_agent.contracts.evidence import EvidenceRef
from e_agent.contracts.step import StepKind, StepRecord, StepStatus, StepUsage


def start_step(
    *,
    tenant_id: str,
    run_id: str,
    step_id: str,
    sequence: int,
    kind: StepKind,
    now: datetime,
    action_id: str | None = None,
    parent_step_id: str | None = None,
    input_refs: Iterable[EvidenceRef] = (),
) -> StepRecord:
    """The ``STARTED`` row of one kernel stage or driver turn."""
    return StepRecord(
        tenant_id=tenant_id,
        run_id=run_id,
        step_id=step_id,
        sequence=sequence,
        kind=kind,
        status=StepStatus.STARTED,
        parent_step_id=parent_step_id,
        action_id=action_id,
        input_refs=tuple(input_refs),
        started_at=now,
    )


def finish_step(
    started: StepRecord,
    *,
    sequence: int,
    status: StepStatus,
    now: datetime,
    action_id: str | None = None,
    output_ref: EvidenceRef | None = None,
    finding_ids: Iterable[str] = (),
    usage: StepUsage | None = None,
) -> StepRecord:
    """The terminal row that ends ``started``: same step, higher sequence, a finish time.

    ``action_id`` may name the action the stage created when the start row had none; it may
    not replace a different one."""
    if started.status is not StepStatus.STARTED:
        raise ValueError(f"step {started.step_id!r} is {started.status}, not started")
    if status is StepStatus.STARTED:
        raise ValueError("a finishing row needs a terminal status")
    if sequence <= started.sequence:
        raise ValueError(
            f"sequence {sequence} must be greater than the start row's {started.sequence}"
        )
    if now.tzinfo is None:
        raise ValueError("a step's finish time must be timezone-aware")
    if now < started.started_at:
        raise ValueError("a step cannot finish before it started")
    if action_id is not None and started.action_id not in (None, action_id):
        raise ValueError(f"step {started.step_id!r} belongs to action {started.action_id!r}")
    # Built, not `model_copy`-ed, so the new row's fields are validated (e.g. a UTC time).
    return StepRecord(
        tenant_id=started.tenant_id,
        run_id=started.run_id,
        step_id=started.step_id,
        sequence=sequence,
        kind=started.kind,
        status=status,
        parent_step_id=started.parent_step_id,
        action_id=action_id or started.action_id,
        input_refs=started.input_refs,
        output_ref=output_ref,
        finding_ids=tuple(finding_ids),
        usage=usage or started.usage,
        started_at=started.started_at,
        finished_at=now,
    )
