"""Runs and run states (MVP design §7)."""

from __future__ import annotations

from enum import StrEnum
from typing import Self

from pydantic import model_validator

from .common import Record, UtcDatetime


class RunState(StrEnum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    WAITING_INPUT = "WAITING_INPUT"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    VERIFYING = "VERIFYING"
    NEEDS_RECONCILIATION = "NEEDS_RECONCILIATION"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ReasonCode(StrEnum):
    """Typed cause of a run state change (ADR 0018). The human `reason` text stays."""

    ANSWERED = "answered"
    VERIFIED = "verified"
    VERIFICATION_PENDING = "verification_pending"
    VERIFICATION_FAILED = "verification_failed"
    VALIDATION_FAILED = "validation_failed"
    POLICY_DENIED = "policy_denied"
    STALE = "stale"
    SURFACE_CHANGED = "surface_changed"
    APPROVAL_REJECTED = "approval_rejected"
    APPROVAL_EXPIRED = "approval_expired"
    OPERATION_RESERVED = "operation_reserved"
    CONNECTION_BUSY = "connection_busy"
    EFFECT_UNKNOWN = "effect_unknown"
    PROVIDER_ERROR = "provider_error"
    BUDGET_EXHAUSTED = "budget_exhausted"
    INTERRUPTED = "interrupted"
    CANCELLED = "cancelled"
    ACCEPTANCE_UNMET = "acceptance_unmet"
    """The run ended without meeting its task definition's acceptance spec (ADR 0028)."""
    # Fallback codes (ADR 0025, ADR 0027): carried only by `feature.fallback` and, for an
    # unresolved task, by `ir.shadow_failed`. They never end a run.
    IR_TASK_UNRESOLVED = "ir_task_unresolved"
    IR_COMPILE_FAILED = "ir_compile_failed"
    IR_VALIDATION_FAILED = "ir_validation_failed"


TERMINAL_RUN_STATES = frozenset({RunState.SUCCEEDED, RunState.FAILED, RunState.CANCELLED})

# Allowed run transitions (ADR 0018). Self-transitions carry a new reason or repair;
# terminal states are final. Every pair was observed in the kernel, server and conformance
# suites or is tied to a coordinator call site or crash-recovery rule (MVP design §9) named in
# its comment. Two pairs are marked "defensive": no current call site reaches them, and they
# are kept for the recovery rule that marks an effect UNKNOWN regardless of run state. Other
# pairs no code path reaches are deliberately absent.
ALLOWED_RUN_TRANSITIONS: dict[RunState, frozenset[RunState]] = {
    RunState.CREATED: frozenset(
        {
            RunState.RUNNING,
            RunState.FAILED,  # recovery: driver turn lost before the run left CREATED
            RunState.CANCELLED,  # cancel() of an admitted run that has not started
        }
    ),
    RunState.RUNNING: frozenset(
        {
            RunState.WAITING_INPUT,
            RunState.WAITING_APPROVAL,  # approval checkpoint
            # defensive: no current call site; kept for the recovery rule that marks an effect
            # UNKNOWN regardless of run state
            RunState.NEEDS_RECONCILIATION,
            RunState.SUCCEEDED,  # verified structured answer
            RunState.FAILED,
            RunState.CANCELLED,
        }
    ),
    RunState.WAITING_INPUT: frozenset(
        {
            RunState.RUNNING,  # accept_input
            # recovery: _recover_run VERIFICATION_FAILED rule does not exclude waiting states
            # (an answer failed verification with repairs left, then the driver asked a question)
            RunState.FAILED,
            RunState.CANCELLED,
        }
    ),
    RunState.WAITING_APPROVAL: frozenset(
        {
            RunState.RUNNING,  # stale digest -> repair re-enters the driver loop
            RunState.VERIFYING,  # dispatched and committed
            RunState.NEEDS_RECONCILIATION,  # receipt UNKNOWN
            RunState.SUCCEEDED,  # recovery: COMMITTED receipt re-verified before VERIFYING was set
            RunState.FAILED,
            RunState.CANCELLED,
        }
    ),
    RunState.VERIFYING: frozenset(
        {
            RunState.VERIFYING,  # verifier missing / unavailable / inconclusive, re-checked later
            RunState.SUCCEEDED,
            RunState.FAILED,
            # defensive: no current call site; kept for the recovery rule that marks an effect
            # UNKNOWN regardless of run state
            RunState.NEEDS_RECONCILIATION,
            RunState.CANCELLED,  # cancel() while verifying with no unresolved dispatch
        }
    ),
    RunState.NEEDS_RECONCILIATION: frozenset(
        {
            RunState.NEEDS_RECONCILIATION,  # cancel() or recovery re-asserts the unknown outcome
            RunState.VERIFYING,  # reconcile() found a COMMITTED receipt
            RunState.SUCCEEDED,  # recovery: COMMITTED/VERIFIED action finished before VERIFYING
            RunState.FAILED,  # reconcile() found a FAILED receipt; recovery of failed verification
        }
    ),
    RunState.SUCCEEDED: frozenset(),
    RunState.FAILED: frozenset(),
    RunState.CANCELLED: frozenset(),
}


class RunRecord(Record):
    run_id: str
    tenant_id: str
    requester_id: str
    task: str
    state: RunState
    revision: int
    logical_operation_id: str
    created_at: UtcDatetime
    reason: str | None = None
    reason_code: ReasonCode | None = None
    task_id: str | None = None
    """The task definition the run resolved (ADR 0028, C11); null for free-text runs."""
    task_version: str | None = None

    @model_validator(mode="after")
    def _check_task_link(self) -> Self:
        if (self.task_id is None) != (self.task_version is None):
            raise ValueError("task_id and task_version are set together or not at all")
        return self
