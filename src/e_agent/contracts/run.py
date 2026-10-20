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
    PLAN_LINEAGE_REJECTED = "plan_lineage_rejected"
    """A plan step's lineage placeholder had no value of its declared type in the earlier
    step's verified read-back, so the plan stopped before that step reserved (ADR 0025)."""
    # Fallback codes (ADR 0025, ADR 0027): carried only by `feature.fallback` and, for an
    # unresolved task, by `ir.shadow_failed`. They never end a run.
    IR_TASK_UNRESOLVED = "ir_task_unresolved"
    IR_COMPILE_FAILED = "ir_compile_failed"
    IR_VALIDATION_FAILED = "ir_validation_failed"
    # Phase 3 (ADR 0032 §11). Fallback codes, carried only by `feature.fallback`: they never
    # end a run (ADR 0027).
    CONTEXT_ASSEMBLY_FAILED = "context_assembly_failed"
    REPEAT_CHECK_FAILED = "repeat_check_failed"
    GROUNDING_CHECK_FAILED = "grounding_check_failed"
    # Phase 4 (ADR 0023 §11). Fallback code, carried only by `feature.fallback`: building a
    # run's carried conversation context failed at admission. It never ends a run.
    CONVERSATION_CONTEXT_FAILED = "conversation_context_failed"
    # Phase 3 terminal codes: each ends a run through an existing pair of the table, or is
    # carried by `context.failed` for a skipped acknowledgement turn (ADR 0032 §10, §11).
    CONTEXT_UNAVAILABLE = "context_unavailable"
    REPEAT_UNAVAILABLE = "repeat_unavailable"
    GROUNDING_UNAVAILABLE = "grounding_unavailable"
    DRIVER_STATE_MISMATCH = "driver_state_mismatch"
    """The driver snapshot's rendering marker disagrees with the run's pinned modes."""
    ROUTE_BOUNDARY_UNMET = "route_boundary_unmet"
    """The model route is not ``local`` and has no ``data_processing`` declaration, and the
    run is not pinned ``context_assembler: on``, so no model call is made (T23)."""
    # Phase 3 success code (ADR 0033 §3, Task 3e.2): it ends a run SUCCEEDED.
    GROUNDED = "grounded"
    """A ``grounded.answer.v1`` run: every citation resolved against this run's evidence (ADR
    0033 §3). Never ``verified``, which needs a typed verifier's fresh read-back (PR-19)."""


TERMINAL_RUN_STATES = frozenset({RunState.SUCCEEDED, RunState.FAILED, RunState.CANCELLED})

# Allowed run transitions (ADR 0018). Self-transitions carry a new reason or repair;
# terminal states are final. Every pair was observed in the kernel, server and conformance
# suites or is tied to a coordinator call site or crash-recovery rule (MVP design §9) named in
# its comment. One pair is marked "defensive": no current call site reaches it, and it is
# kept for the recovery rule that marks an effect UNKNOWN regardless of run state. Other
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
            # plan (ADR 0025): a later plan step's receipt is UNKNOWN; the remaining steps wait
            RunState.NEEDS_RECONCILIATION,
            RunState.SUCCEEDED,  # verified structured answer
            RunState.FAILED,
            RunState.CANCELLED,
            RunState.VERIFYING,  # plan only (ADR 0025): a later plan step committed
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
            RunState.RUNNING,  # plan only (ADR 0025): a step verified and steps remain
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


PLAN_STEP_RUN_TRANSITIONS = frozenset(
    {(RunState.VERIFYING, RunState.RUNNING), (RunState.RUNNING, RunState.VERIFYING)}
)
"""The two pairs ADR 0025 adds to the table. They are legal only between the steps of a
multi-step plan: the kernel refuses them for any other run (`kernel/transitions.py`)."""


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
