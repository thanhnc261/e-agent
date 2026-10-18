"""Action ledger records and the action state machine (MVP design §7)."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Self

from pydantic import Field, model_validator

from .common import Record
from .evidence import ApprovedFact


class ActionState(StrEnum):
    PROPOSED = "PROPOSED"
    VALIDATED = "VALIDATED"
    BLOCKED = "BLOCKED"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    APPROVED = "APPROVED"
    RESERVED = "RESERVED"
    DISPATCHING = "DISPATCHING"
    COMMITTED = "COMMITTED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"
    VERIFIED = "VERIFIED"
    VERIFICATION_FAILED = "VERIFICATION_FAILED"


ALLOWED_ACTION_TRANSITIONS: dict[ActionState, frozenset[ActionState]] = {
    ActionState.PROPOSED: frozenset({ActionState.VALIDATED, ActionState.BLOCKED}),
    ActionState.VALIDATED: frozenset(
        {
            ActionState.AWAITING_APPROVAL,
            ActionState.RESERVED,
            # structured answers only (EffectKind.ANSWER): verified without dispatch
            ActionState.VERIFIED,
            ActionState.VERIFICATION_FAILED,
        }
    ),
    ActionState.AWAITING_APPROVAL: frozenset({ActionState.APPROVED, ActionState.BLOCKED}),
    ActionState.APPROVED: frozenset({ActionState.RESERVED, ActionState.BLOCKED}),
    ActionState.RESERVED: frozenset({ActionState.DISPATCHING, ActionState.BLOCKED}),
    ActionState.DISPATCHING: frozenset(
        {ActionState.COMMITTED, ActionState.FAILED, ActionState.UNKNOWN}
    ),
    ActionState.UNKNOWN: frozenset({ActionState.COMMITTED, ActionState.FAILED}),
    ActionState.COMMITTED: frozenset({ActionState.VERIFIED, ActionState.VERIFICATION_FAILED}),
    ActionState.BLOCKED: frozenset(),
    ActionState.FAILED: frozenset(),
    ActionState.VERIFIED: frozenset(),
    ActionState.VERIFICATION_FAILED: frozenset(),
}


class ActionRecord(Record):
    action_id: str
    tenant_id: str
    run_id: str
    logical_operation_id: str
    contract_id: str
    binding_id: str
    connection_id: str
    connection_version: int
    credential_subject: str
    credential_version: str = "none"
    approved_facts: tuple[ApprovedFact, ...] = ()
    arguments: dict[str, Any]
    digest: str
    state: ActionState
    revision: int
    supersedes_action_id: str | None = None
    plan_id: str | None = None
    """The action plan this action's plan step belongs to (target §6.4); null before Phase 2."""
    step_index: int | None = Field(default=None, ge=0)
    """The plan step's position in its plan; set together with ``plan_id``."""

    @model_validator(mode="after")
    def _check_plan_link(self) -> Self:
        if (self.plan_id is None) != (self.step_index is None):
            raise ValueError("plan_id and step_index are set together or not at all")
        return self
