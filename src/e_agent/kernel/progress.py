"""The progress ledger projection (ADR 0031 §1, Task 3c.1).

``project_progress(events, steps)`` is a pure function over a run's recorded events and step
records. It reads nothing else, writes nothing, calls no model and holds no model text (PR-28).
A fact the events do not record is reported as unknown, never guessed (PR-24).

Stage sources: a step record gives the stage when one exists for the same kind and action (the
latest row of each step id wins); the events give the stage otherwise.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import datetime
from typing import Any

from e_agent.contracts.events import RunEvent, RunEventType
from e_agent.contracts.progress import (
    UNKNOWN,
    BudgetsUsed,
    FactRef,
    OpenFinding,
    ProgressLedger,
    RuleRef,
    Stage,
    StageKind,
    StageSource,
    StageStatus,
    TaskRefState,
)
from e_agent.contracts.step import StepKind, StepRecord, StepStatus

REPAIR_RULE_ID = "KERNEL-VERIFICATION"
"""The rule id of the plain-text repair finding (`kernel/run_loop.py`)."""

_PENDING = frozenset({StageStatus.STARTED, StageStatus.WAITING})
_PENDING_WHEN_UNKNOWN = frozenset({StageKind.DISPATCH, StageKind.RECONCILE})
_STEP_STATUS = {
    StepStatus.STARTED: StageStatus.STARTED,
    StepStatus.SUCCEEDED: StageStatus.SUCCEEDED,
    StepStatus.FAILED: StageStatus.FAILED,
    StepStatus.BLOCKED: StageStatus.BLOCKED,
    StepStatus.UNKNOWN: StageStatus.UNKNOWN,
    StepStatus.SKIPPED: StageStatus.SKIPPED,
}
_VALIDATION_STATUS = {
    "PASS": StageStatus.SUCCEEDED,
    "FAIL": StageStatus.BLOCKED,
    "ERROR": StageStatus.FAILED,
    "UNKNOWN": StageStatus.UNKNOWN,
}
_RECEIPT_STATUS = {
    "COMMITTED": StageStatus.SUCCEEDED,
    "FAILED": StageStatus.FAILED,
    "UNKNOWN": StageStatus.UNKNOWN,
}
_OUTCOME_STATUS = {
    "VERIFIED": StageStatus.SUCCEEDED,
    "FAILED": StageStatus.FAILED,
    "UNKNOWN": StageStatus.UNKNOWN,
}
_UNRESOLVED = frozenset({"not_found", "UNKNOWN"})


def project_progress(events: Iterable[RunEvent], steps: Iterable[StepRecord]) -> ProgressLedger:
    """The run's progress ledger. Order of the arguments does not matter: events are read in
    sequence order and steps in step-sequence order."""
    ordered = sorted(events, key=lambda e: e.sequence)
    latest = _latest_steps(steps)
    task_ref, task_state = _task_ref(ordered)
    created = next((e for e in ordered if e.type is RunEventType.RUN_CREATED), None)
    goal = created.payload.get("task") if created is not None else None
    stages = _stages(ordered, latest)
    findings, rules, repair_turns = _findings(ordered)
    return ProgressLedger(
        run_id=ordered[0].run_id if ordered else (latest[0][1].run_id if latest else None),
        goal=goal if isinstance(goal, str) else None,
        task_ref=task_ref,
        task_ref_state=task_state,
        facts=_facts(ordered),
        done=tuple(s for _, s in stages if not _is_pending(s)),
        pending=tuple(s for _, s in stages if _is_pending(s)),
        open_findings=findings,
        rules_evaluated=rules,
        repair_turns=repair_turns,
        budgets_used=_budgets(ordered, [row for _, row in latest]),
    )


def _is_pending(stage: Stage) -> bool:
    if stage.status in _PENDING:
        return True
    return stage.status is StageStatus.UNKNOWN and stage.kind in _PENDING_WHEN_UNKNOWN


# -- goal and task definition ----------------------------------------------------------------
def _task_ref(events: Sequence[RunEvent]) -> tuple[str | None, TaskRefState]:
    for event in events:
        if event.type is RunEventType.RUN_CREATED:
            payload = event.payload
            if "task_id" in payload:  # the ADR 0031 §3 keys: null says "no definition"
                if payload["task_id"] is None:
                    return None, TaskRefState.NONE
                return f"{payload['task_id']}@{payload.get('task_version')}", TaskRefState.KNOWN
        elif event.type is RunEventType.IR_PLAN_COMPILED:
            task_id = event.payload.get("task_id")
            if task_id is not None:
                return f"{task_id}@{event.payload.get('task_version')}", TaskRefState.KNOWN
    return None, TaskRefState.UNKNOWN


# -- facts -----------------------------------------------------------------------------------
def _facts(events: Sequence[RunEvent]) -> tuple[FactRef, ...]:
    return tuple(
        FactRef(
            evidence_id=str(e.payload["evidence_id"]),
            contract_id=_text(e.payload.get("contract_id")),
            revision=_text(e.payload.get("revision")),
        )
        for e in events
        if e.type is RunEventType.READ_RECORDED and e.payload.get("evidence_id") is not None
    )


def _text(value: Any) -> str | None:
    return None if value is None else str(value)


# -- findings and repairs --------------------------------------------------------------------
def _findings(
    events: Sequence[RunEvent],
) -> tuple[tuple[OpenFinding, ...], tuple[RuleRef, ...], tuple[str, ...]]:
    """Open findings are those of the latest validation that no later proposal superseded.
    The evaluated rules come from every validation of the run: one per rule id and version,
    in first-seen order, with the latest status seen (``PASS`` included)."""
    latest: RunEvent | None = None
    repairs: list[str] = []
    statuses: dict[tuple[str, str], str] = {}  # insertion order is first-seen order
    for event in events:
        if event.type is RunEventType.PROPOSAL_CREATED:
            latest = None
        elif event.type is RunEventType.VALIDATION_COMPLETED:
            latest = event
            for f in _finding_dicts(event):
                statuses[(str(f.get("rule_id")), str(f.get("rule_version")))] = str(f.get("status"))
            if any(f.get("rule_id") == REPAIR_RULE_ID for f in _finding_dicts(event)):
                repairs.append(event.event_id)
    rules = tuple(
        RuleRef(rule_id=rule_id, rule_version=version, status=status)
        for (rule_id, version), status in statuses.items()
    )
    if latest is None:
        return (), rules, tuple(repairs)
    open_findings = tuple(
        OpenFinding(
            rule_id=str(f.get("rule_id")),
            rule_version=str(f.get("rule_version")),
            status=str(f.get("status")),
            message=str(f.get("message")),
        )
        for f in _finding_dicts(latest)
        if f.get("status") != "PASS"
    )
    return open_findings, rules, tuple(repairs)


def _finding_dicts(event: RunEvent) -> list[dict[str, Any]]:
    raw = event.payload.get("findings")
    return [f for f in raw if isinstance(f, dict)] if isinstance(raw, list) else []


# -- budgets ---------------------------------------------------------------------------------
def _budgets(events: Sequence[RunEvent], rows: Sequence[StepRecord]) -> BudgetsUsed:
    turns = [r for r in rows if r.kind is StepKind.DRIVER_TURN]
    return BudgetsUsed(
        reads_recorded=sum(1 for e in events if e.type is RunEventType.READ_RECORDED),
        failed_validations=_failed_validations(events),
        admitted_writes=sum(1 for e in events if e.type is RunEventType.ACTION_RESERVED),
        driver_turns=len(turns) if turns else UNKNOWN,
        model_tokens=sum(r.usage.model_tokens for r in turns) if turns else UNKNOWN,
    )


def _failed_validations(events: Sequence[RunEvent]) -> int:
    """``validation.completed`` events whose status is present and not ``PASS``."""
    return sum(
        1
        for e in events
        if e.type is RunEventType.VALIDATION_COMPLETED
        and e.payload.get("status") not in (None, "PASS")
    )


# -- stages ----------------------------------------------------------------------------------
_Keyed = tuple[tuple[datetime, int, int], Stage]


def _latest_steps(steps: Iterable[StepRecord]) -> list[tuple[datetime, StepRecord]]:
    """The latest row of each step id, with the time the step first started."""
    first: dict[str, StepRecord] = {}
    last: dict[str, StepRecord] = {}
    for row in sorted(steps, key=lambda r: r.sequence):
        first.setdefault(row.step_id, row)
        last[row.step_id] = row
    return [(first[sid].started_at, row) for sid, row in last.items()]


_STEP_KIND = {
    StepKind.READ: StageKind.READ,
    StepKind.VALIDATE: StageKind.VALIDATE,
    StepKind.APPROVAL_WAIT: StageKind.APPROVAL_WAIT,
    StepKind.DISPATCH: StageKind.DISPATCH,
    StepKind.VERIFY: StageKind.VERIFY,
    StepKind.RECONCILE: StageKind.RECONCILE,
    StepKind.DRIVER_TURN: StageKind.DRIVER_TURN,
}


def _stages(
    events: Sequence[RunEvent], latest: Sequence[tuple[datetime, StepRecord]]
) -> list[_Keyed]:
    covered = {(_STEP_KIND[row.kind], row.action_id) for _, row in latest}
    covers_reads = any(kind is StageKind.READ for kind, _ in covered)
    merged: list[_Keyed] = []
    for started, row in latest:
        stage = Stage(
            kind=_STEP_KIND[row.kind],
            status=_STEP_STATUS[row.status],
            source=StageSource.STEP,
            action_id=row.action_id,
            step_id=row.step_id,
        )
        merged.append(((started, 1, row.sequence), stage))
    for event, stage in _event_stages(events):
        if stage.kind is StageKind.READ:
            if covers_reads:
                continue
        elif (stage.kind, stage.action_id) in covered:
            continue
        merged.append(((event.occurred_at, 0, event.sequence), stage))
    merged.sort(key=lambda item: item[0])
    return merged


def _event_stages(events: Sequence[RunEvent]) -> list[tuple[RunEvent, Stage]]:
    """Stages the events show, in event order. Some update an earlier stage in place (an
    approval wait that was decided, a dispatch that got its receipt)."""
    out: list[tuple[RunEvent, Stage]] = []
    open_slot: dict[tuple[StageKind, str | None], int] = {}

    def add(event: RunEvent, kind: StageKind, status: StageStatus, *, slot: bool = False) -> None:
        stage = Stage(
            kind=kind,
            status=status,
            source=StageSource.EVENT,
            action_id=event.action_id,
            event_id=event.event_id,
        )
        key = (kind, event.action_id)
        if slot and key in open_slot:
            out[open_slot[key]] = (out[open_slot[key]][0], stage)
            return
        if slot:
            open_slot[key] = len(out)
        out.append((event, stage))

    for event in events:
        payload = event.payload
        match event.type:
            case RunEventType.READ_RECORDED:
                add(event, StageKind.READ, StageStatus.SUCCEEDED)
            case RunEventType.READ_REJECTED:
                add(event, StageKind.READ, StageStatus.FAILED)
            case RunEventType.PROPOSAL_CREATED:
                add(event, StageKind.PROPOSE, StageStatus.SUCCEEDED)
            case RunEventType.VALIDATION_COMPLETED:
                status = _VALIDATION_STATUS.get(str(payload.get("status")), StageStatus.UNKNOWN)
                add(event, StageKind.VALIDATE, status)
            case RunEventType.APPROVAL_REQUESTED:
                add(event, StageKind.APPROVAL_WAIT, StageStatus.WAITING, slot=True)
            case RunEventType.APPROVAL_DECIDED:
                approved = payload.get("decision") == "approved"
                add(
                    event,
                    StageKind.APPROVAL_WAIT,
                    StageStatus.SUCCEEDED if approved else StageStatus.BLOCKED,
                    slot=True,
                )
            case RunEventType.ACTION_RESERVED | RunEventType.ACTION_DISPATCHING:
                add(event, StageKind.DISPATCH, StageStatus.STARTED, slot=True)
            case RunEventType.ACTION_RECEIPT_RECORDED:
                status = _RECEIPT_STATUS.get(str(payload.get("status")), StageStatus.UNKNOWN)
                add(event, StageKind.DISPATCH, status, slot=True)
            case RunEventType.ACTION_UNKNOWN:
                add(event, StageKind.DISPATCH, StageStatus.UNKNOWN, slot=True)
            case RunEventType.RUN_STATE_CHANGED if payload.get("to") == "NEEDS_RECONCILIATION":
                if (StageKind.RECONCILE, None) not in open_slot:
                    add(event, StageKind.RECONCILE, StageStatus.WAITING, slot=True)
            case RunEventType.RECONCILIATION_COMPLETED:
                found = payload.get("found")
                waiting = open_slot.pop((StageKind.RECONCILE, None), None)
                if waiting is not None:
                    out.pop(waiting)  # the generic wait is replaced by this action's stage
                    open_slot = {k: (i - 1 if i > waiting else i) for k, i in open_slot.items()}
                done = found is not None and found not in _UNRESOLVED
                add(
                    event,
                    StageKind.RECONCILE,
                    StageStatus.SUCCEEDED if done else StageStatus.WAITING,
                    slot=True,
                )
            case RunEventType.OUTCOME_REPORTED:
                status = _OUTCOME_STATUS.get(str(payload.get("status")), StageStatus.UNKNOWN)
                add(event, StageKind.VERIFY, status)
            case RunEventType.INPUT_REQUESTED:
                add(event, StageKind.INPUT, StageStatus.WAITING, slot=True)
            case RunEventType.INPUT_RECEIVED:
                add(event, StageKind.INPUT, StageStatus.SUCCEEDED, slot=True)
            case _:
                pass
    return out
