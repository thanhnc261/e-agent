"""The progress ledger: a read-only projection of a run's events and steps (ADR 0031 §1).

The ledger is computed on demand, never stored, and holds no model text: no ``message.final``
text, no ``input.requested`` question, no thinking (PR-28). A fact the events do not record is
``None`` or ``unknown``, never a guess (PR-24).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import Field

from .common import Record

UNKNOWN: Literal["unknown"] = "unknown"
"""A budget the events and step records do not show (never zero)."""


class TaskRefState(StrEnum):
    """Whether the run's task definition is known from its events."""

    KNOWN = "known"
    NONE = "none"
    """The run was created without a task definition (``run.created`` says so)."""
    UNKNOWN = "unknown"
    """The events record no task definition and do not say there was none."""


class StageKind(StrEnum):
    READ = "read"
    PROPOSE = "propose"
    VALIDATE = "validate"
    APPROVAL_WAIT = "approval_wait"
    DISPATCH = "dispatch"
    VERIFY = "verify"
    RECONCILE = "reconcile"
    INPUT = "input"
    DRIVER_TURN = "driver_turn"


class StageStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    BLOCKED = "blocked"
    UNKNOWN = "unknown"
    SKIPPED = "skipped"
    STARTED = "started"
    WAITING = "waiting"


class StageSource(StrEnum):
    STEP = "step"
    EVENT = "event"


class Stage(Record):
    """One kernel stage of the run, in the order it began."""

    kind: StageKind
    status: StageStatus
    source: StageSource
    action_id: str | None = None
    step_id: str | None = None
    event_id: str | None = None
    """The event the stage came from, for an event-derived stage."""


class FactRef(Record):
    """One recorded read: ids and a revision, never the observation data."""

    evidence_id: str
    contract_id: str | None
    revision: str | None


class OpenFinding(Record):
    rule_id: str
    rule_version: str
    status: str
    message: str


class RuleRef(Record):
    """One evaluated rule: its id, version and status, never its message or values."""

    rule_id: str
    rule_version: str
    status: str


class BudgetsUsed(Record):
    """What the events and steps show. ``unknown`` means they do not show it, not zero."""

    reads_recorded: int = Field(ge=0)
    """``read.recorded`` events, which include verifier read-backs; the read-call budget
    counts driver reads only, so this is an upper bound of it."""
    failed_validations: int = Field(ge=0)
    """``validation.completed`` events whose status is not ``PASS``, including one that ended
    the run. A failed answer verification writes no such event, so this is not the repair
    budget's counter (that lives only in the continuation)."""
    admitted_writes: int = Field(ge=0)
    """``action.reserved`` events."""
    driver_turns: int | Literal["unknown"]
    model_tokens: int | Literal["unknown"]


class ProgressLedger(Record):
    run_id: str | None
    goal: str | None
    """The run's task text from ``run.created``; None when the events do not hold it."""
    task_ref: str | None
    """``task_id@task_version`` when ``task_ref_state`` is ``known``."""
    task_ref_state: TaskRefState
    facts: tuple[FactRef, ...]
    done: tuple[Stage, ...]
    pending: tuple[Stage, ...]
    open_findings: tuple[OpenFinding, ...]
    rules_evaluated: tuple[RuleRef, ...]
    """Every rule evaluated in this run (across every validation), latest status per rule
    version: one entry per rule id and version, in first-seen order, never a message."""
    repair_turns: tuple[str, ...]
    """Event ids of the plain-text repair turns (``KERNEL-VERIFICATION``), never their text."""
    budgets_used: BudgetsUsed
