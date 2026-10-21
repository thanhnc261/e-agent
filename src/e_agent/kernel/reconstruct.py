"""Run reconstruction from ``run_events`` (ADR 0031 §2 and §3, Task 3c.2, fitness row U3).

``reconstruct(events)`` is a pure function over one run's recorded events. It rebuilds the
run, its actions, its approvals and its receipts, and reads nothing else. Each field is a
`Slot`:

- ``known``: the value the row holds, recorded in an event;
- ``partial``: what the events show, which is less than the row or may be behind it (the
  evidence ids of approved facts; the state of an action that an event-less write may have
  moved);
- ``unknown``: the events do not record it, and the slot holds no value.

Nothing is guessed (PR-24). Outside reconstruction (§2): ``revision`` on runs and actions (a
compare-and-swap token), the data of approved facts (observation values never enter an event,
PR-26), and outcomes, steps and plans, which have their own rows.

The module also holds the payload keys of §3 and the helpers the event writers build them
with, so the writers and this reader share one list.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from enum import StrEnum
from functools import cache
from types import MappingProxyType
from typing import Annotated, Any

from e_agent.contracts.action import ActionRecord, ActionState
from e_agent.contracts.approval import ApprovalRecord
from e_agent.contracts.common import Record
from e_agent.contracts.events import RunEvent, RunEventType
from e_agent.contracts.receipt import ExecutionReceipt
from e_agent.contracts.run import RunRecord, RunState
from pydantic import Field, TypeAdapter, ValidationError

# -- the payload keys of ADR 0031 §3 ---------------------------------------------------------
RUN_CREATED_KEYS = ("requester_id", "logical_operation_id", "created_at", "task_id", "task_version")
INPUT_STATE_KEYS = ("from", "to", "reason", "reason_code")
"""Added to ``accept_input``'s ``run.state_changed``, which keeps its ``state`` key."""
BLOCKED_KEY = "blocked_action_ids"
"""On the ``run.state_changed`` that follows an event-less ``BLOCKED`` write, only there."""
PROPOSAL_KEYS = (
    "binding_id",
    "connection_id",
    "connection_version",
    "credential_subject",
    "credential_version",
    "digest",
    "logical_operation_id",
    "plan_id",
    "step_index",
    "evidence_ids",
)
ACTION_STATE_KEY = "action_state"
"""On ``validation.completed`` and ``outcome.reported`` written with an action id: the state
the write left the action in, or null when it left the action unchanged."""
PLAN_LINK_KEYS = ("plan_id", "step_index")
APPROVAL_KEYS = ("approval_id", "policy_version", "issued_at", "expires_at")
"""On ``approval.decided`` for ``approved`` and ``rejected``, the decisions with a record."""

ADDED_KEYS: Mapping[RunEventType, frozenset[str]] = MappingProxyType(
    {
        RunEventType.RUN_CREATED: frozenset(RUN_CREATED_KEYS),
        RunEventType.RUN_STATE_CHANGED: frozenset((*INPUT_STATE_KEYS, BLOCKED_KEY)),
        RunEventType.PROPOSAL_CREATED: frozenset(PROPOSAL_KEYS),
        RunEventType.VALIDATION_COMPLETED: frozenset({ACTION_STATE_KEY}),
        RunEventType.APPROVAL_REQUESTED: frozenset(PLAN_LINK_KEYS),
        RunEventType.APPROVAL_DECIDED: frozenset(APPROVAL_KEYS),
        RunEventType.OUTCOME_REPORTED: frozenset({ACTION_STATE_KEY}),
    }
)
"""Every key ADR 0031 §3 adds, by event type. No other key is added to any event."""


def run_created_keys(run: RunRecord) -> dict[str, Any]:
    """The ``run.created`` keys of ``run``, timestamps as the record serialises them."""
    wire = run.model_dump(mode="json")
    keys = {key: wire[key] for key in RUN_CREATED_KEYS}
    if run.conversation_id is not None:  # only when set, so the `off` goldens do not move
        keys["conversation_id"] = run.conversation_id
    return keys


def proposal_keys(action: ActionRecord) -> dict[str, Any]:
    """The ``proposal.created`` keys of ``action``: ids, versions and its digest, and the
    evidence ids of its approved facts, never their data (PR-26)."""
    keys = {key: getattr(action, key) for key in PROPOSAL_KEYS if key != "evidence_ids"}
    return {**keys, "evidence_ids": [f.evidence.evidence_id for f in action.approved_facts]}


def approval_keys(record: ApprovalRecord) -> dict[str, Any]:
    wire = record.model_dump(mode="json")
    return {key: wire[key] for key in APPROVAL_KEYS}


def without_reconstruction_keys(
    event_type: RunEventType | str, payload: Mapping[str, Any]
) -> dict[str, Any]:
    """``payload`` without the keys §3 added to its event type: the payload as written before
    Task 3c.2, for a reader that parses it as a record (an ``outcome.reported`` report). An
    ``accept_input`` state change (it keeps ``state``) drops ``from``, ``to``, ``reason`` and
    ``reason_code``; every other state change had those before and drops only
    ``blocked_action_ids``."""
    kind = RunEventType(event_type)
    if kind is RunEventType.RUN_STATE_CHANGED:
        added = set(INPUT_STATE_KEYS) if "state" in payload else {BLOCKED_KEY}
    else:
        added = set(ADDED_KEYS.get(kind, ()))
    return {key: value for key, value in payload.items() if key not in added}


# -- the reconstruction ----------------------------------------------------------------------
class FieldState(StrEnum):
    KNOWN = "known"
    PARTIAL = "partial"
    UNKNOWN = "unknown"


class Slot(Record):
    """One reconstructed field; ``value`` is None when ``state`` is ``unknown``."""

    state: FieldState
    value: Any = None


UNKNOWN_SLOT = Slot(state=FieldState.UNKNOWN)
BY_DESIGN_PARTIAL = frozenset({"approved_facts"})
"""Fields that are ``partial`` even when every key is recorded: the events hold the approved
facts' evidence ids, never their data (§2)."""


class Rebuilt(Record):
    """One reconstructed row, its fields by the row's field names."""

    fields: dict[str, Slot]

    @property
    def state(self) -> FieldState:
        """``known`` when every field is (a by-design ``partial`` field counts as known),
        ``unknown`` when none is, ``partial`` otherwise."""
        states = [
            FieldState.KNOWN
            if name in BY_DESIGN_PARTIAL and slot.state is FieldState.PARTIAL
            else slot.state
            for name, slot in self.fields.items()
        ]
        if all(s is FieldState.KNOWN for s in states):
            return FieldState.KNOWN
        if all(s is FieldState.UNKNOWN for s in states):
            return FieldState.UNKNOWN
        return FieldState.PARTIAL

    def known(self) -> dict[str, Any]:
        return {n: s.value for n, s in self.fields.items() if s.state is FieldState.KNOWN}


class Reconstructed(Record):
    run: Rebuilt
    actions: tuple[Rebuilt, ...]
    """In the order of their ``proposal.created``."""
    approvals: tuple[Rebuilt, ...]
    receipts: tuple[Rebuilt, ...]
    driver: Slot = UNKNOWN_SLOT
    """The driver id ``run.created`` records (``driver``); ``unknown`` when it records none.
    It is not a run row field (``RunRecord`` has no driver), so it is outside ``run`` and
    outside ``state``."""
    rationales: dict[str, dict[str, Any]] = Field(default_factory=dict)
    """The at-rest rationale (ADR 0033 §4) each ``proposal.created`` holds, by action id:
    its ``rationale`` and ``step_rationales`` keys as recorded (no schema version keys them,
    so the Task 3.R1 digest keys pass through): ids, codes and digests only, never text.
    Not an action row field (``ActionRecord`` has none), so it is outside ``state``; a
    proposal without one is absent."""

    @property
    def state(self) -> FieldState:
        """``known`` only when every row is: a run whose events predate the §3 keys, or that
        has an answer whose state the events cannot tell, is ``partial`` (D7)."""
        if self.run.state is FieldState.UNKNOWN:
            return FieldState.UNKNOWN
        rows = (self.run, *self.actions, *self.approvals, *self.receipts)
        known = all(row.state is FieldState.KNOWN for row in rows)
        return FieldState.KNOWN if known else FieldState.PARTIAL


_BLOCKABLE = frozenset(
    {
        ActionState.PROPOSED,
        ActionState.AWAITING_APPROVAL,
        ActionState.APPROVED,
        ActionState.RESERVED,
    }
)
"""States an event-less ``BLOCKED`` write leaves (§3): in a run without the keys, such a
state is only what the events show, so it is ``partial``."""
_DECIDED = {"approved": ActionState.APPROVED}
_DECIDED_BLOCKED = frozenset({"rejected", "expired", "surface_changed"})
_RECORDED = frozenset({"approved", "rejected"})
_STATE_OF_TYPE = {
    RunEventType.APPROVAL_REQUESTED: ActionState.AWAITING_APPROVAL,
    RunEventType.ACTION_RESERVED: ActionState.RESERVED,
    RunEventType.ACTION_DISPATCHING: ActionState.DISPATCHING,
    RunEventType.ACTION_UNKNOWN: ActionState.UNKNOWN,
}
_RECEIPT_FIELDS = tuple(ExecutionReceipt.model_fields)


@cache
def _adapter(model: type[Record], name: str) -> TypeAdapter[Any]:
    info = model.model_fields[name]
    annotation: Any = info.annotation
    if info.metadata:
        annotation = Annotated[(annotation, *info.metadata)]
    return TypeAdapter(annotation)


def _known(model: type[Record], name: str, raw: Any) -> Slot:
    """``raw`` as the row's field type; a value the type refuses is ``unknown``."""
    try:
        return Slot(state=FieldState.KNOWN, value=_adapter(model, name).validate_python(raw))
    except ValidationError:
        return UNKNOWN_SLOT


def _keyed(model: type[Record], name: str, payload: Mapping[str, Any], key: str = "") -> Slot:
    key = key or name
    return _known(model, name, payload[key]) if key in payload else UNKNOWN_SLOT


def reconstruct(events: Iterable[RunEvent]) -> Reconstructed:
    """The run's rows rebuilt from its events, read in sequence order."""
    ordered = sorted(events, key=lambda e: e.sequence)
    created = next((e for e in ordered if e.type is RunEventType.RUN_CREATED), None)
    keyed = created is not None and set(RUN_CREATED_KEYS) <= created.payload.keys()
    run = _run(ordered, created)
    actions: dict[str, dict[str, Slot]] = {}
    answers: set[str] = set()
    rationales: dict[str, dict[str, Any]] = {}
    approvals: list[Rebuilt] = []
    receipts: list[Rebuilt] = []
    for event in ordered:
        if event.type is RunEventType.PROPOSAL_CREATED and event.action_id is not None:
            actions[event.action_id] = _proposed(event)
            if stored := _rationale(event):
                rationales[event.action_id] = stored
            if event.payload.get("kind") == "answer":
                answers.add(event.action_id)
            continue
        if event.type is RunEventType.RUN_STATE_CHANGED:
            for action_id in event.payload.get(BLOCKED_KEY) or ():
                if action_id in actions:
                    actions[action_id]["state"] = _known(ActionRecord, "state", "BLOCKED")
            continue
        if event.type in {RunEventType.ACTION_RECEIPT_RECORDED, RunEventType.ACTION_UNKNOWN}:
            receipts.append(_receipt(event.payload))
        if (
            event.type is RunEventType.APPROVAL_DECIDED
            and event.payload.get("decision") in _RECORDED
        ):
            approvals.append(_approval(event))
        fields = actions.get(event.action_id or "")
        if fields is not None:
            _apply(fields, event)
            if event.type is RunEventType.OUTCOME_REPORTED:
                answers.discard(event.action_id or "")
    rebuilt = []
    for action_id, fields in actions.items():
        state = fields["state"]
        undecided = action_id in answers  # PROPOSED or VALIDATED: that write has no event
        if state.state is FieldState.KNOWN and (
            undecided or (not keyed and state.value in _BLOCKABLE)
        ):
            fields["state"] = Slot(state=FieldState.PARTIAL, value=state.value)
        rebuilt.append(Rebuilt(fields=fields))
    return Reconstructed(
        run=run,
        actions=tuple(rebuilt),
        approvals=tuple(approvals),
        receipts=tuple(receipts),
        driver=_driver(created),
        rationales=rationales,
    )


def _driver(created: RunEvent | None) -> Slot:
    driver = created.payload.get("driver") if created is not None else None
    return Slot(state=FieldState.KNOWN, value=driver) if isinstance(driver, str) else UNKNOWN_SLOT


def _run(events: list[RunEvent], created: RunEvent | None) -> Rebuilt:
    first = events[0] if events else None
    payload = created.payload if created is not None else {}
    fields = {
        "run_id": _known(RunRecord, "run_id", first.run_id) if first else UNKNOWN_SLOT,
        "tenant_id": _known(RunRecord, "tenant_id", first.tenant_id) if first else UNKNOWN_SLOT,
        "task": _keyed(RunRecord, "task", payload),
        **{key: _keyed(RunRecord, key, payload) for key in RUN_CREATED_KEYS},
    }
    if created is not None:  # written only when set (`run_created_keys`): absent means none
        fields["conversation_id"] = _known(
            RunRecord, "conversation_id", payload.get("conversation_id")
        )
    else:
        fields["conversation_id"] = UNKNOWN_SLOT
    # Created CREATED with no reason (`_prepare_run`); every state change carries the new one.
    state = reason = code = UNKNOWN_SLOT
    if created is not None:
        state = _known(RunRecord, "state", RunState.CREATED)
        reason = code = _known(RunRecord, "reason", None)
    for event in events:
        if event.type is not RunEventType.RUN_STATE_CHANGED:
            continue
        changed = event.payload
        if "to" in changed:
            state = _keyed(RunRecord, "state", changed, "to")
            reason = _keyed(RunRecord, "reason", changed)
            code = _keyed(RunRecord, "reason_code", changed)
        else:  # `accept_input` before the keys: {state} only, its reason not recorded
            state = _keyed(RunRecord, "state", changed)
            reason = code = UNKNOWN_SLOT
    fields.update(state=state, reason=reason, reason_code=code)
    return Rebuilt(fields=fields)


RATIONALE_KEYS = ("rationale", "step_rationales")
"""The ``proposal.created`` keys of the at-rest rationale (ADR 0033 §4, Task 3e.3)."""


def _rationale(event: RunEvent) -> dict[str, Any]:
    """The at-rest rationale keys of a ``proposal.created``, as recorded."""
    return {key: event.payload[key] for key in RATIONALE_KEYS if key in event.payload}


def _proposed(event: RunEvent) -> dict[str, Slot]:
    payload = event.payload
    ids = payload.get("evidence_ids")
    return {
        "action_id": _known(ActionRecord, "action_id", event.action_id),
        "tenant_id": _known(ActionRecord, "tenant_id", event.tenant_id),
        "run_id": _known(ActionRecord, "run_id", event.run_id),
        "contract_id": _keyed(ActionRecord, "contract_id", payload),
        "arguments": _keyed(ActionRecord, "arguments", payload),
        "supersedes_action_id": _keyed(ActionRecord, "supersedes_action_id", payload, "supersedes"),
        **{
            key: _keyed(ActionRecord, key, payload)
            for key in PROPOSAL_KEYS
            if key != "evidence_ids"
        },
        "approved_facts": UNKNOWN_SLOT
        if not isinstance(ids, list)
        else Slot(state=FieldState.PARTIAL, value=tuple(str(i) for i in ids)),
        "state": _known(ActionRecord, "state", ActionState.PROPOSED),
    }


def _apply(fields: dict[str, Slot], event: RunEvent) -> None:
    """The state after ``event`` (the §2 table), and the facts later events also record."""
    payload, kind = event.payload, event.type
    unknown_digest = fields["digest"].state is FieldState.UNKNOWN
    if kind in {RunEventType.APPROVAL_REQUESTED, RunEventType.APPROVAL_DECIDED} and unknown_digest:
        fields["digest"] = _keyed(ActionRecord, "digest", payload)  # the approved digest
    if kind is RunEventType.ACTION_RESERVED and fields["logical_operation_id"].state is (
        FieldState.UNKNOWN
    ):
        fields["logical_operation_id"] = _keyed(ActionRecord, "logical_operation_id", payload)
    if kind is RunEventType.APPROVAL_REQUESTED and set(PLAN_LINK_KEYS) <= payload.keys():
        for key in PLAN_LINK_KEYS:  # the link the stored action has (`on` links it late)
            fields[key] = _keyed(ActionRecord, key, payload)
    if kind in _STATE_OF_TYPE:
        fields["state"] = _known(ActionRecord, "state", _STATE_OF_TYPE[kind])
    elif kind in {RunEventType.VALIDATION_COMPLETED, RunEventType.OUTCOME_REPORTED}:
        if ACTION_STATE_KEY not in payload:  # before the keys: the write may or may not move it
            fields["state"] = UNKNOWN_SLOT
        elif payload[ACTION_STATE_KEY] is not None:
            fields["state"] = _known(ActionRecord, "state", payload[ACTION_STATE_KEY])
    elif kind is RunEventType.APPROVAL_DECIDED:
        decision = payload.get("decision")
        target = "BLOCKED" if decision in _DECIDED_BLOCKED else _DECIDED.get(str(decision))
        fields["state"] = UNKNOWN_SLOT if target is None else _known(ActionRecord, "state", target)
    elif kind is RunEventType.ACTION_RECEIPT_RECORDED:
        status = payload.get("status")
        target = status if status in {"COMMITTED", "FAILED"} else None
        fields["state"] = UNKNOWN_SLOT if target is None else _known(ActionRecord, "state", target)


def _approval(event: RunEvent) -> Rebuilt:
    payload = event.payload
    return Rebuilt(
        fields={
            "approval_id": _keyed(ApprovalRecord, "approval_id", payload),
            "tenant_id": _known(ApprovalRecord, "tenant_id", event.tenant_id),
            "run_id": _known(ApprovalRecord, "run_id", event.run_id),
            "action_id": _known(ApprovalRecord, "action_id", event.action_id),
            "action_digest": _keyed(ApprovalRecord, "action_digest", payload, "digest"),
            "actor_id": _keyed(ApprovalRecord, "actor_id", payload),
            "decision": _keyed(ApprovalRecord, "decision", payload),
            **{key: _keyed(ApprovalRecord, key, payload) for key in APPROVAL_KEYS[1:]},
        }
    )


def _receipt(payload: Mapping[str, Any]) -> Rebuilt:
    """Receipts are recorded whole (``receipt.model_dump``, `kernel/dispatch.py`)."""
    return Rebuilt(
        fields={name: _keyed(ExecutionReceipt, name, payload) for name in _RECEIPT_FIELDS}
    )
