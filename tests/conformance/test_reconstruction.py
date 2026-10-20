"""Run reconstruction from ``run_events`` equals the stored rows (U3, ADR 0031 §2, Task 3c.2).

Every scenario is a recorded fixture run of the notes domain, driven through the kernel on
the ``run_store`` fixture's store: in-memory by default, PostgreSQL with
``E_AGENT_TEST_STORE=postgres``. The run's events alone are reconstructed and compared with
the run, action, approval and receipt rows the store holds; ``revision`` and the data of
approved facts are outside reconstruction (ADR 0031 §2). Events with the ADR 0031 §3 keys
removed reconstruct as ``partial`` or ``unknown``, never as a guessed value (PR-24).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pytest
from e_agent.contracts.action import ActionRecord, ActionState
from e_agent.contracts.approval import ApprovalDecision, ApprovalRecord
from e_agent.contracts.common import Record
from e_agent.contracts.events import RunEvent, RunEventType
from e_agent.contracts.features import FeatureMode, Features
from e_agent.contracts.receipt import ExecutionReceipt
from e_agent.contracts.run import ReasonCode, RunRecord, RunState
from e_agent.kernel.errors import KernelError
from e_agent.kernel.reconstruct import (
    ACTION_STATE_KEY,
    APPROVAL_KEYS,
    BLOCKED_KEY,
    BY_DESIGN_PARTIAL,
    INPUT_STATE_KEYS,
    PLAN_LINK_KEYS,
    PROPOSAL_KEYS,
    RUN_CREATED_KEYS,
    FieldState,
    Rebuilt,
    Reconstructed,
    reconstruct,
    without_reconstruction_keys,
)
from e_agent.sdk.ports import AskClarification, DriverInput, DriverStep

from tests.unit.kernel import conftest as notes
from tests.unit.kernel.conftest import (
    CONN,
    NOTE_INPUT,
    NOTES_TASK,
    PLAN_BUDGETS,
    TENANT,
    Kernel,
    NotesDriver,
    NotesPlanDriver,
)
from tests.unit.kernel.test_progress import WrongAnswerDriver
from tests.unit.kernel.test_unusable_connection import AnsweringDriver

run_store = notes.run_store  # the kernel suite's fixtures: both stores (ENG-STORE-1)
make_kernel = notes.make_kernel

MakeKernel = Callable[..., Kernel]
ON = Features(execution_ir=FeatureMode.ON)
OUTSIDE = frozenset({"revision"})
"""Row fields outside reconstruction (ADR 0031 §2)."""


class Crash(BaseException):
    """A process dying mid-call (as in the kernel's recovery tests)."""


async def _approve(
    k: Kernel, run_id: str, decision: ApprovalDecision = ApprovalDecision.APPROVED
) -> RunRecord:
    pres = await k.coordinator.pending_approval(TENANT, run_id)
    return await k.coordinator.decide(
        actor=k.approver,
        run_id=run_id,
        action_id=pres.action_id,
        action_digest=pres.digest,
        expected_run_revision=pres.run_revision,
        decision=decision,
    )


async def _start(k: Kernel, **kw: Any) -> RunRecord:
    return await k.coordinator.start_run(k.requester, "write standup note", k.scope, **kw)


@dataclass
class ClarifyingDriver:
    """Asks one question, then writes a note as `NotesDriver` does."""

    inner: NotesDriver
    driver_id: str = "notes-clarifying-driver"
    asked: bool = False

    async def advance(self, ctx: Any, step_input: DriverInput) -> DriverStep:
        if not self.asked:
            self.asked = True
            return AskClarification(question="which note?")
        return await self.inner.advance(ctx, step_input)


# -- the scenarios: each returns its run's final row ------------------------------------------
async def single_write(mk: MakeKernel) -> RunRecord:
    k = mk()
    return await _approve(k, (await _start(k)).run_id)


async def blocked_and_repaired(mk: MakeKernel) -> RunRecord:
    k = mk(["", "standup notes"])
    return await _approve(k, (await _start(k)).run_id)


async def reconciliation(mk: MakeKernel) -> RunRecord:
    k = mk()
    k.backend.fail_mode = "timeout"
    run = await _approve(k, (await _start(k)).run_id)
    assert run.state is RunState.NEEDS_RECONCILIATION
    return await k.coordinator.reconcile(k.approver, run.run_id)


async def two_step_plan(mk: MakeKernel) -> RunRecord:
    k = mk(
        features=ON,
        budgets=PLAN_BUDGETS,
        driver=NotesPlanDriver(),
        input_schemas={"c": NOTE_INPUT, "p": NOTE_INPUT},
    )
    return await _approve(k, (await _start(k, task_kind=NOTES_TASK.task_id)).run_id)


async def one_step_plan(mk: MakeKernel) -> RunRecord:
    """``on`` links the action to its 1-step plan after ``proposal.created``."""
    k = mk(features=ON)
    return await _approve(k, (await _start(k, task_kind=NOTES_TASK.task_id)).run_id)


async def answer(mk: MakeKernel) -> RunRecord:
    k = mk(driver=AnsweringDriver(answer_on=CONN), with_answer=True)
    return await k.coordinator.start_run(k.requester, "count the notes", k.scope)


async def failed_answer(mk: MakeKernel) -> RunRecord:
    k = mk(driver=WrongAnswerDriver(), with_answer=True)
    return await k.coordinator.start_run(k.requester, "count the notes", k.scope)


async def rejected(mk: MakeKernel) -> RunRecord:
    k = mk()
    return await _approve(k, (await _start(k)).run_id, ApprovalDecision.REJECTED)


async def expired(mk: MakeKernel) -> RunRecord:
    k = mk()
    run = await _start(k)
    k.clock.advance(minutes=16)
    with pytest.raises(KernelError):
        await _approve(k, run.run_id)
    return await k.store.get_run(TENANT, run.run_id)


async def input_answered(mk: MakeKernel) -> RunRecord:
    k = mk(driver=ClarifyingDriver(NotesDriver(texts=["standup notes"])))
    run = await _start(k)
    assert run.state is RunState.WAITING_INPUT
    run = await k.coordinator.resume_input(k.requester, run.run_id, "the standup", run.revision)
    return await _approve(k, run.run_id)


async def cancelled(mk: MakeKernel) -> RunRecord:
    """Event-less BLOCKED write (`kernel/recovery.py`, cancel)."""
    k = mk()
    return await k.coordinator.cancel(k.requester, (await _start(k)).run_id)


async def revalidation_deadline(mk: MakeKernel) -> RunRecord:
    """Event-less BLOCKED write of a first step (`kernel/dispatch.py`, through `_exhausted`)."""
    k = mk()

    async def past_deadline(*_args: Any) -> str | None:
        raise TimeoutError

    run = await _start(k)
    k.coordinator._staleness = past_deadline  # type: ignore[method-assign]
    return await _approve(k, run.run_id)


async def interrupted_before_dispatch(mk: MakeKernel) -> RunRecord:
    """Event-less BLOCKED write of startup recovery (`kernel/recovery.py`)."""
    k = mk()
    run = await _start(k)
    original = k.store.put_action

    async def die_on_dispatching(action: ActionRecord, expected: Any, events: Any) -> Any:
        if action.state is ActionState.DISPATCHING:
            raise Crash
        return await original(action, expected, events)

    k.store.put_action = die_on_dispatching
    try:
        with pytest.raises(Crash):
            await _approve(k, run.run_id)
    finally:
        k.store.put_action = original
    k.coordinator.release_continuation(run.run_id)
    return await k.coordinator.recover_run(TENANT, run.run_id)


async def connection_busy(mk: MakeKernel) -> RunRecord:
    """Event-less BLOCKED write of a refused reservation (`kernel/dispatch.py`). Last: it
    leaves another run's action UNKNOWN on the connection, which the test writes itself."""
    k = mk(["first note", "second note"])
    first = await _start(k)
    pres = await k.coordinator.pending_approval(TENANT, first.run_id)
    stuck = await k.store.get_action(TENANT, pres.action_id)
    await k.store.put_action(
        stuck.model_copy(update={"state": ActionState.UNKNOWN, "revision": stuck.revision + 1}),
        stuck.revision,
        [],
    )
    second = await k.coordinator.start_run(k.requester, "write another note", k.scope)
    return await _approve(k, second.run_id)


Scenario = Callable[[MakeKernel], Awaitable[RunRecord]]
SCENARIOS: dict[str, tuple[Scenario, tuple[RunState, ReasonCode | None]]] = {
    "single write": (single_write, (RunState.SUCCEEDED, ReasonCode.VERIFIED)),
    "blocked and repaired": (blocked_and_repaired, (RunState.SUCCEEDED, ReasonCode.VERIFIED)),
    "reconciliation": (reconciliation, (RunState.SUCCEEDED, ReasonCode.VERIFIED)),
    "two-step plan": (two_step_plan, (RunState.SUCCEEDED, ReasonCode.VERIFIED)),
    "one-step plan": (one_step_plan, (RunState.SUCCEEDED, ReasonCode.VERIFIED)),
    "answer": (answer, (RunState.SUCCEEDED, ReasonCode.ANSWERED)),
    "failed answer": (failed_answer, (RunState.FAILED, ReasonCode.VERIFICATION_FAILED)),
    "rejected": (rejected, (RunState.FAILED, ReasonCode.APPROVAL_REJECTED)),
    "expired": (expired, (RunState.FAILED, ReasonCode.APPROVAL_EXPIRED)),
    "input answered": (input_answered, (RunState.SUCCEEDED, ReasonCode.VERIFIED)),
    "cancelled": (cancelled, (RunState.CANCELLED, ReasonCode.CANCELLED)),
    "revalidation deadline": (
        revalidation_deadline,
        (RunState.FAILED, ReasonCode.BUDGET_EXHAUSTED),
    ),
    "interrupted before dispatch": (
        interrupted_before_dispatch,
        (RunState.FAILED, ReasonCode.INTERRUPTED),
    ),
    "connection busy": (connection_busy, (RunState.FAILED, ReasonCode.CONNECTION_BUSY)),
}
EVENT_LESS_BLOCKS = frozenset(
    {"cancelled", "revalidation deadline", "interrupted before dispatch", "connection busy"}
)
"""The scenarios that reach the four event-less BLOCKED writes (ADR 0031 §3)."""


@dataclass
class Rows:
    run: RunRecord
    actions: dict[str, ActionRecord]
    approvals: list[ApprovalRecord]
    receipts: list[ExecutionReceipt]
    events: list[RunEvent]


async def _rows(store: Any, run: RunRecord) -> Rows:
    actions = {a.action_id: a for a in await store.list_actions(TENANT, run.run_id)}
    approvals = [p for a in actions for p in await store.list_approvals(TENANT, a)]
    receipts = [r for a in actions for r in await store.list_receipts(TENANT, a)]
    events = await store.list_events(TENANT, run.run_id)
    return Rows(await store.get_run(TENANT, run.run_id), actions, approvals, receipts, events)


async def _played(mk: MakeKernel, store: Any) -> list[tuple[str, Rows]]:
    played = []
    for name, (scenario, expected) in SCENARIOS.items():
        run = await scenario(mk)
        assert (run.state, run.reason_code) == expected, name
        played.append((name, await _rows(store, run)))
    return played


def _compare(name: str, rebuilt: Rebuilt, row: Record) -> None:
    """Every field of ``row`` but those outside reconstruction is known and equal; the
    approved facts are their evidence ids, ``partial`` by design."""
    fields = set(type(row).model_fields) - OUTSIDE
    assert set(rebuilt.fields) == fields, name
    for field in sorted(fields):
        slot, value = rebuilt.fields[field], getattr(row, field)
        if field in BY_DESIGN_PARTIAL:
            assert slot.state is FieldState.PARTIAL, (name, field)
            assert slot.value == tuple(f.evidence.evidence_id for f in value), (name, field)
        else:
            assert (slot.state, slot.value) == (FieldState.KNOWN, value), (name, field)


def _by(records: tuple[Rebuilt, ...], key: str) -> dict[Any, list[Rebuilt]]:
    grouped: dict[Any, list[Rebuilt]] = {}
    for record in records:
        grouped.setdefault(record.fields[key].value, []).append(record)
    return grouped


def _assert_equal(name: str, got: Reconstructed, rows: Rows) -> None:
    _compare(f"{name}: run", got.run, rows.run)
    rebuilt = {a.fields["action_id"].value: a for a in got.actions}
    assert set(rebuilt) == set(rows.actions), name
    for action_id, action in rows.actions.items():
        _compare(f"{name}: action {action.state}", rebuilt[action_id], action)
    approvals = _by(got.approvals, "action_id")
    for action_id in rows.actions:
        stored = [p for p in rows.approvals if p.action_id == action_id]
        assert len(approvals.get(action_id, [])) == len(stored), name
        for rebuilt_one, row in zip(approvals.get(action_id, []), stored, strict=True):
            _compare(f"{name}: approval", rebuilt_one, row)
    receipts = _by(got.receipts, "action_id")
    for action_id in rows.actions:
        stored_receipts = [r for r in rows.receipts if r.action_id == action_id]
        assert len(receipts.get(action_id, [])) == len(stored_receipts), name
        for rebuilt_one, receipt in zip(receipts.get(action_id, []), stored_receipts, strict=True):
            _compare(f"{name}: receipt", rebuilt_one, receipt)
    assert got.state is FieldState.KNOWN, name


def _writer_keys(name: str, events: list[RunEvent]) -> bool:
    """The writers add exactly the §3 keys, where §3 puts them; True when the run recorded
    ``blocked_action_ids``."""
    blocked = False
    for e in events:
        keys = set(e.payload)
        match e.type:
            case RunEventType.RUN_CREATED:
                assert set(RUN_CREATED_KEYS) <= keys, name
            case RunEventType.RUN_STATE_CHANGED:
                assert set(INPUT_STATE_KEYS) <= keys, name
                if BLOCKED_KEY in keys:
                    assert e.payload[BLOCKED_KEY], name  # never an empty list
                    blocked = True
            case RunEventType.PROPOSAL_CREATED:
                assert set(PROPOSAL_KEYS) <= keys, name
            case RunEventType.VALIDATION_COMPLETED | RunEventType.OUTCOME_REPORTED:
                assert (ACTION_STATE_KEY in keys) == (e.action_id is not None), (name, e.type)
            case RunEventType.APPROVAL_REQUESTED:
                assert set(PLAN_LINK_KEYS) <= keys, name
            case RunEventType.APPROVAL_DECIDED:
                recorded = e.payload["decision"] in {"approved", "rejected"}
                assert (set(APPROVAL_KEYS) <= keys) == recorded, name
                assert recorded or not keys & set(APPROVAL_KEYS), name
    return blocked


async def test_reconstruction_equals_stored_rows(
    make_kernel: MakeKernel,
    run_store: Any,
) -> None:
    played = await _played(make_kernel, run_store)
    blocked = set()
    for name, rows in played:
        _assert_equal(name, reconstruct(rows.events), rows)
        if _writer_keys(name, rows.events):
            blocked.add(name)
    assert blocked == EVENT_LESS_BLOCKS
    print(f"reconstruction: {len(played)} scenarios equal their stored rows")
    assert len(played) > 0


# -- events written before the keys ----------------------------------------------------------
def _phase2(event: RunEvent) -> RunEvent:
    """``event`` as written before Task 3c.2: the §3 keys removed. ``accept_input``'s state
    change had ``state`` only; every other state change already had ``from`` and ``to``."""
    payload = without_reconstruction_keys(event.type, event.payload)
    return event.model_copy(update={"payload": payload})


DEPENDENT = {
    "run": frozenset(RUN_CREATED_KEYS),
    "action": frozenset(
        {"binding_id", "connection_id", "connection_version", "credential_subject"}
        | {"credential_version", "plan_id", "step_index", "approved_facts"}
    ),
    "approval": frozenset(APPROVAL_KEYS),
}
"""Fields only the §3 keys record; ``digest`` and ``logical_operation_id`` are also recorded
by ``approval.requested`` and ``action.reserved``, so an approved action keeps them."""


def _never_guessed(name: str, got: Rebuilt, row: Record | None, dependent: frozenset[str]) -> int:
    """A known field equals the row; a field only the keys record is not known."""
    for field, slot in got.fields.items():
        if field in dependent:
            assert slot.state is not FieldState.KNOWN, (name, field)
        if slot.state is FieldState.KNOWN and row is not None:
            assert slot.value == getattr(row, field), (name, field)
        if slot.state is FieldState.UNKNOWN:
            assert slot.value is None, (name, field)
    return len(got.fields)


async def test_pre_key_events_reconstruct_as_partial(
    make_kernel: MakeKernel,
    run_store: Any,
) -> None:
    checked = 0
    for name, rows in await _played(make_kernel, run_store):
        got = reconstruct([_phase2(e) for e in rows.events])
        assert got.state is FieldState.PARTIAL, name
        assert got.run.state is FieldState.PARTIAL, name
        checked += _never_guessed(name, got.run, rows.run, DEPENDENT["run"])
        for action in got.actions:
            row = rows.actions[action.fields["action_id"].value]
            checked += _never_guessed(name, action, row, DEPENDENT["action"])
            state = action.fields["state"]
            if state.state is not FieldState.KNOWN:  # what the events show, never a guess
                assert state.state is FieldState.UNKNOWN or state.value in set(ActionState)
        for approval in got.approvals:
            checked += _never_guessed(name, approval, None, DEPENDENT["approval"])
    print(f"pre-key reconstruction: {checked} fields checked")
    assert checked > 0


AT = datetime(2026, 10, 19, 9, 0, tzinfo=UTC)


def _event(seq: int, type_: RunEventType, payload: dict[str, Any], action_id: str | None = None):
    return RunEvent(
        event_id=f"ev{seq}",
        tenant_id=TENANT,
        run_id="run_x",
        sequence=seq,
        type=type_,
        occurred_at=AT,
        action_id=action_id,
        payload=payload,
    )


PHASE2_PROPOSAL = {"contract_id": "c", "arguments": {"text": "t"}, "supersedes": None}


def test_phase2_shapes_give_unknown_not_guessed_values() -> None:
    """``accept_input``'s ``{state}`` leaves the reason unknown; a ``validation.completed``
    or ``outcome.reported`` without ``action_state`` leaves the action state unknown; an
    approval-wait state of a run without the keys is partial."""
    created = _event(1, RunEventType.RUN_CREATED, {"task": "t", "driver": "d"})
    got = reconstruct([created, _event(2, RunEventType.RUN_STATE_CHANGED, {"state": "RUNNING"})])
    assert got.run.fields["state"].value == RunState.RUNNING
    assert got.run.fields["reason"].state is FieldState.UNKNOWN
    assert got.run.fields["requester_id"].state is FieldState.UNKNOWN
    assert got.state is FieldState.PARTIAL

    proposed = _event(2, RunEventType.PROPOSAL_CREATED, PHASE2_PROPOSAL, "a1")
    validated = _event(3, RunEventType.VALIDATION_COMPLETED, {"status": "FAIL"}, "a1")
    (action,) = reconstruct([created, proposed, validated]).actions
    assert action.fields["state"].state is FieldState.UNKNOWN
    waiting = _event(3, RunEventType.APPROVAL_REQUESTED, {"digest": "d", "expires_at": "x"}, "a1")
    (action,) = reconstruct([created, proposed, waiting]).actions
    assert (action.fields["state"].state, action.fields["state"].value) == (
        FieldState.PARTIAL,
        ActionState.AWAITING_APPROVAL,
    )
    assert action.fields["digest"].value == "d"  # recorded by approval.requested
    outcome = _event(4, RunEventType.OUTCOME_REPORTED, {"status": "VERIFIED"}, "a1")
    (action,) = reconstruct([created, proposed, outcome]).actions
    assert action.fields["state"].state is FieldState.UNKNOWN


def test_action_state_null_keeps_the_state() -> None:
    """A ``validation.completed`` or ``outcome.reported`` whose write left the action
    unchanged keeps the earlier state; ``blocked_action_ids`` moves it to BLOCKED."""
    keys = dict.fromkeys(RUN_CREATED_KEYS, "x") | {"task": "t", "created_at": AT.isoformat()}
    created = _event(1, RunEventType.RUN_CREATED, keys | {"task_id": None, "task_version": None})
    proposed = _event(2, RunEventType.PROPOSAL_CREATED, PHASE2_PROPOSAL, "a1")
    validated = _event(
        3,
        RunEventType.VALIDATION_COMPLETED,
        {"status": "PASS", ACTION_STATE_KEY: "VALIDATED"},
        "a1",
    )
    refused = _event(
        4, RunEventType.VALIDATION_COMPLETED, {"status": "STALE", ACTION_STATE_KEY: None}, "a1"
    )
    (action,) = reconstruct([created, proposed, validated, refused]).actions
    assert action.fields["state"].value == ActionState.VALIDATED
    assert action.fields["state"].state is FieldState.KNOWN
    failed = _event(
        5,
        RunEventType.RUN_STATE_CHANGED,
        {
            "from": "RUNNING",
            "to": "FAILED",
            "reason": "r",
            "reason_code": None,
            BLOCKED_KEY: ["a1"],
        },
    )
    got = reconstruct([created, proposed, validated, failed])
    assert got.actions[0].fields["state"].value == ActionState.BLOCKED
    assert got.run.fields["state"].value == RunState.FAILED


def test_an_answer_without_its_outcome_is_partial() -> None:
    """Its ``PROPOSED -> VALIDATED`` write has no event (ADR 0031 §2)."""
    proposed = _event(1, RunEventType.PROPOSAL_CREATED, PHASE2_PROPOSAL | {"kind": "answer"}, "a1")
    (action,) = reconstruct([proposed]).actions
    assert action.fields["state"].state is FieldState.PARTIAL


def test_the_driver_is_read_from_run_created() -> None:
    """``driver`` is not a run row field: it sits beside the run and is unknown when
    ``run.created`` does not record it (review C3-26, PR-24)."""
    created = _event(1, RunEventType.RUN_CREATED, {"task": "t", "driver": "d"})
    got = reconstruct([created])
    assert (got.driver.state, got.driver.value) == (FieldState.KNOWN, "d")
    assert "driver" not in got.run.fields
    bare = reconstruct([_event(1, RunEventType.RUN_CREATED, {"task": "t"})])
    assert bare.driver.state is FieldState.UNKNOWN and bare.driver.value is None
    assert reconstruct([]).driver.state is FieldState.UNKNOWN


def test_an_empty_log_is_unknown() -> None:
    got = reconstruct([])
    assert got.state is FieldState.UNKNOWN
    assert (got.actions, got.approvals, got.receipts) == ((), (), ())
    assert all(s.state is FieldState.UNKNOWN for s in got.run.fields.values())


def test_reconstruction_is_pure() -> None:
    created = _event(1, RunEventType.RUN_CREATED, {"task": "t", "driver": "d"})
    events = [created, _event(2, RunEventType.PROPOSAL_CREATED, PHASE2_PROPOSAL, "a1")]
    copies = [e.model_copy(deep=True) for e in events]
    assert reconstruct(events) == reconstruct(list(reversed(events)))  # read by sequence
    assert events == copies
