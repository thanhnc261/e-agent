"""The progress ledger projection (ADR 0031 §1, Task 3c.1).

The runs are recorded fixture runs of the notes domain, driven through the kernel; the
``run_store`` fixture runs them on both stores.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from e_agent.contracts.approval import ApprovalDecision
from e_agent.contracts.events import RunEvent, RunEventType
from e_agent.contracts.features import FeatureMode, Features
from e_agent.contracts.plan import ActionProposal
from e_agent.contracts.progress import (
    ProgressLedger,
    StageKind,
    StageSource,
    StageStatus,
    TaskRefState,
)
from e_agent.contracts.run import RunState
from e_agent.contracts.step import StepKind, StepRecord, StepStatus, StepUsage
from e_agent.kernel.progress import project_progress
from e_agent.sdk.ports import (
    DriverInput,
    FinalAnswer,
    ProposeAction,
    ReadRequest,
    RequestReads,
)

from .conftest import (
    CONN,
    NOTE_INPUT,
    NOTES_TASK,
    PLAN_BUDGETS,
    READ,
    SUMMARY,
    TENANT,
    Kernel,
    NotesPlanDriver,
)
from .test_unusable_connection import AnsweringDriver

MakeKernel = Callable[..., Kernel]
SENTINEL = "SENTINEL-model-text-must-not-leak"
AT = datetime(2026, 10, 19, 9, 0, tzinfo=UTC)


async def _ledger(k: Kernel, run_id: str) -> ProgressLedger:
    events = await k.store.list_events(TENANT, run_id)
    steps = await k.store.list_steps(TENANT, run_id)
    return project_progress(events, steps)


async def _approve(k: Kernel, run_id: str) -> Any:
    pres = await k.coordinator.pending_approval(TENANT, run_id)
    return await k.coordinator.decide(
        actor=k.approver,
        run_id=run_id,
        action_id=pres.action_id,
        action_digest=pres.digest,
        expected_run_revision=pres.run_revision,
        decision=ApprovalDecision.APPROVED,
    )


def _kinds(stages: Any) -> list[tuple[StageKind, StageStatus]]:
    return [(s.kind, s.status) for s in stages]


@dataclass
class ReplyingDriver:
    """Reads once, then answers in plain text, which the kernel repairs (KERNEL-VERIFICATION)."""

    driver_id: str = "replying-driver"
    seen: list[DriverInput] = field(default_factory=list)

    async def advance(self, ctx: Any, step_input: DriverInput) -> Any:
        self.seen.append(step_input)
        if not step_input.observations:
            request = ReadRequest(
                request_id="r1", contract_id=READ.contract_id, connection_id=CONN, arguments={}
            )
            return RequestReads(reads=(request,))
        return FinalAnswer(text=SENTINEL)


async def test_progress_of_a_verified_answer_run(make_kernel: MakeKernel) -> None:
    k = make_kernel(driver=AnsweringDriver(answer_on=CONN), with_answer=True)
    run = await k.coordinator.start_run(k.requester, "count the notes", k.scope)
    assert run.state is RunState.SUCCEEDED
    ledger = await _ledger(k, run.run_id)

    assert ledger.run_id == run.run_id
    assert ledger.goal == "count the notes"
    # off: no definition is linked and the events do not say so: unknown, not "none"
    assert (ledger.task_ref, ledger.task_ref_state) == (None, TaskRefState.UNKNOWN)
    events = await k.store.list_events(TENANT, run.run_id)
    recorded = [e for e in events if e.type is RunEventType.READ_RECORDED]
    assert [(f.evidence_id, f.contract_id, f.revision) for f in ledger.facts] == [
        (e.payload["evidence_id"], READ.contract_id, e.payload["revision"]) for e in recorded
    ]
    assert ledger.pending == ()
    kinds = _kinds(ledger.done)
    assert kinds[0] == (StageKind.READ, StageStatus.SUCCEEDED)
    assert (StageKind.PROPOSE, StageStatus.SUCCEEDED) in kinds
    assert kinds[-1] == (StageKind.VERIFY, StageStatus.SUCCEEDED)
    assert all(s.source is StageSource.EVENT for s in ledger.done)  # off writes no steps
    assert ledger.open_findings == ()
    assert ledger.repair_turns == ()
    used = ledger.budgets_used
    assert (used.failed_validations, used.admitted_writes) == (0, 0)
    assert used.reads_recorded >= 1
    assert (used.driver_turns, used.model_tokens) == ("unknown", "unknown")


async def test_progress_of_a_blocked_then_repaired_run(make_kernel: MakeKernel) -> None:
    k = make_kernel(texts=["", "standup notes"])
    run = await k.coordinator.start_run(k.requester, "write standup note", k.scope)
    assert run.state is RunState.WAITING_APPROVAL
    ledger = await _ledger(k, run.run_id)

    # the blocked proposal is superseded by the repaired one, whose validation passed
    assert ledger.open_findings == ()
    assert ledger.budgets_used.failed_validations == 1
    validations = [s.status for s in ledger.done if s.kind is StageKind.VALIDATE]
    assert validations == [StageStatus.BLOCKED, StageStatus.SUCCEEDED]
    assert _kinds(ledger.pending) == [(StageKind.APPROVAL_WAIT, StageStatus.WAITING)]
    assert ledger.pending[0].action_id is not None

    run = await _approve(k, run.run_id)
    assert run.state is RunState.SUCCEEDED
    done = await _ledger(k, run.run_id)
    assert done.pending == ()
    assert (StageKind.APPROVAL_WAIT, StageStatus.SUCCEEDED) in _kinds(done.done)
    assert (StageKind.DISPATCH, StageStatus.SUCCEEDED) in _kinds(done.done)
    assert _kinds(done.done)[-1] == (StageKind.VERIFY, StageStatus.SUCCEEDED)
    assert done.budgets_used.admitted_writes == 1


async def test_progress_keeps_the_findings_of_a_blocked_proposal_open(
    make_kernel: MakeKernel,
) -> None:
    k = make_kernel(texts=[""], budgets=None)
    run = await k.coordinator.start_run(k.requester, "write standup note", k.scope)
    # budgets allow two repairs: the driver proposes "" once, then "" again (texts exhausted)
    ledger = await _ledger(k, run.run_id)
    assert run.state is RunState.FAILED
    assert [f.rule_id for f in ledger.open_findings] == ["NOTE-001"]
    assert ledger.open_findings[0].status == "FAIL"
    assert ledger.open_findings[0].message == "text must be non-empty"
    # every non-PASS validation counts, including the one that ended the run
    assert ledger.budgets_used.failed_validations == 3


async def test_progress_of_a_two_step_plan(make_kernel: MakeKernel) -> None:
    k = make_kernel(
        features=Features(execution_ir=FeatureMode.ON),
        budgets=PLAN_BUDGETS,
        driver=NotesPlanDriver(),
        input_schemas={"c": NOTE_INPUT, "p": NOTE_INPUT},
    )
    run = await k.coordinator.start_run(
        k.requester, "write standup note", k.scope, task_kind=NOTES_TASK.task_id
    )
    assert run.state is RunState.WAITING_APPROVAL
    waiting = await _ledger(k, run.run_id)
    assert (waiting.task_ref, waiting.task_ref_state) == (
        f"{NOTES_TASK.task_id}@{NOTES_TASK.version}",
        TaskRefState.KNOWN,
    )
    assert [(s.kind, s.status) for s in waiting.pending] == [
        (StageKind.APPROVAL_WAIT, StageStatus.STARTED)
    ]
    assert waiting.pending[0].source is StageSource.STEP

    run = await _approve(k, run.run_id)
    assert run.state is RunState.SUCCEEDED
    ledger = await _ledger(k, run.run_id)
    assert ledger.pending == ()
    steps = await k.store.list_steps(TENANT, run.run_id)
    step_stages = [s for s in ledger.done if s.source is StageSource.STEP]
    # one stage per step id (the latest row of each), not one per appended row
    assert len(step_stages) == len({s.step_id for s in steps})
    assert [s.kind for s in step_stages].count(StageKind.VERIFY) == 2
    assert [s.kind for s in step_stages].count(StageKind.DISPATCH) == 2
    assert all(s.status is StageStatus.SUCCEEDED for s in step_stages)
    assert ledger.budgets_used.admitted_writes == 2
    assert len(ledger.facts) >= 3  # the driver's read, and a read-back per verified step


async def test_progress_shows_plain_text_repair_turns(make_kernel: MakeKernel) -> None:
    k = make_kernel(driver=ReplyingDriver())
    run = await k.coordinator.start_run(k.requester, "answer me", k.scope)
    assert run.state is RunState.FAILED
    events = await k.store.list_events(TENANT, run.run_id)
    expected = [
        e.event_id
        for e in events
        if e.type is RunEventType.VALIDATION_COMPLETED
        and any(f["rule_id"] == "KERNEL-VERIFICATION" for f in e.payload["findings"])
    ]
    assert len(expected) == 2  # max_validation_repairs
    ledger = await _ledger(k, run.run_id)
    assert list(ledger.repair_turns) == expected
    assert ledger.budgets_used.failed_validations == 2
    assert [f.rule_id for f in ledger.open_findings] == ["KERNEL-VERIFICATION"]


async def test_progress_is_pure(make_kernel: MakeKernel) -> None:
    k = make_kernel(texts=["", "standup notes"])
    run = await k.coordinator.start_run(k.requester, "write standup note", k.scope)
    events = await k.store.list_events(TENANT, run.run_id)
    steps = await k.store.list_steps(TENANT, run.run_id)
    before_run = await k.store.get_run(TENANT, run.run_id)
    events_copy, steps_copy = list(events), list(steps)

    first = project_progress(events, steps)
    second = project_progress(events, steps)

    assert first == second
    assert first == project_progress(tuple(reversed(events)), steps)  # order is by sequence
    assert events == events_copy and steps == steps_copy
    assert await k.store.list_events(TENANT, run.run_id) == events_copy  # no store write
    assert await k.store.get_run(TENANT, run.run_id) == before_run


async def test_progress_holds_no_model_text(make_kernel: MakeKernel) -> None:
    k = make_kernel(driver=ReplyingDriver())
    run = await k.coordinator.start_run(k.requester, "answer me", k.scope)
    events = await k.store.list_events(TENANT, run.run_id)
    assert not any(e.type is RunEventType.MESSAGE_FINAL for e in events)  # repaired, not final
    ledger = await _ledger(k, run.run_id)
    assert SENTINEL not in ledger.model_dump_json()

    # the ledger also leaves out the text of a message.final and an input.requested question
    texty = [
        _event(1, RunEventType.RUN_CREATED, {"task": "t", "driver": "d"}),
        _event(2, RunEventType.INPUT_REQUESTED, {"question": SENTINEL, "kind": "reply"}),
        _event(3, RunEventType.MESSAGE_FINAL, {"text": SENTINEL}),
    ]
    projected = project_progress(texty, [])
    assert SENTINEL not in projected.model_dump_json()
    assert _kinds(projected.pending) == [(StageKind.INPUT, StageStatus.WAITING)]


# -- facts the events do not record are unknown, never guessed (PR-24) ------------------------
def _event(
    sequence: int,
    type_: RunEventType,
    payload: dict[str, Any] | None = None,
    action_id: str | None = None,
) -> RunEvent:
    return RunEvent(
        event_id=f"ev{sequence}",
        tenant_id=TENANT,
        run_id="run_x",
        sequence=sequence,
        type=type_,
        occurred_at=AT,
        action_id=action_id,
        payload=payload or {},
    )


def _step(
    sequence: int,
    kind: StepKind,
    status: StepStatus,
    step_id: str,
    usage: StepUsage | None = None,
) -> StepRecord:
    return StepRecord(
        tenant_id=TENANT,
        run_id="run_x",
        step_id=step_id,
        sequence=sequence,
        kind=kind,
        status=status,
        usage=usage or StepUsage(),
        started_at=AT,
    )


def test_an_empty_run_is_all_unknown() -> None:
    ledger = project_progress([], [])
    assert ledger.run_id is None and ledger.goal is None
    assert ledger.task_ref_state is TaskRefState.UNKNOWN
    assert (ledger.facts, ledger.done, ledger.pending) == ((), (), ())
    assert ledger.budgets_used.driver_turns == "unknown"
    assert ledger.budgets_used.model_tokens == "unknown"


def test_run_created_keys_decide_the_task_ref() -> None:
    none = project_progress(
        [_event(1, RunEventType.RUN_CREATED, {"task": "t", "task_id": None, "task_version": None})],
        [],
    )
    assert (none.task_ref, none.task_ref_state) == (None, TaskRefState.NONE)
    known = project_progress(
        [_event(1, RunEventType.RUN_CREATED, {"task": "t", "task_id": "a", "task_version": "2"})],
        [],
    )
    assert (known.task_ref, known.task_ref_state) == ("a@2", TaskRefState.KNOWN)


def test_driver_turn_steps_give_turns_and_tokens() -> None:
    steps = [
        _step(0, StepKind.DRIVER_TURN, StepStatus.STARTED, "d1"),
        _step(1, StepKind.DRIVER_TURN, StepStatus.SUCCEEDED, "d1", StepUsage(model_tokens=10)),
        _step(2, StepKind.DRIVER_TURN, StepStatus.SUCCEEDED, "d2", StepUsage(model_tokens=5)),
    ]
    used = project_progress([], steps).budgets_used
    assert (used.driver_turns, used.model_tokens) == (2, 15)


def test_an_unfinished_step_is_pending_and_a_finished_one_done() -> None:
    steps = [
        _step(0, StepKind.VALIDATE, StepStatus.STARTED, "s1"),
        _step(1, StepKind.VALIDATE, StepStatus.SUCCEEDED, "s1"),
        _step(2, StepKind.APPROVAL_WAIT, StepStatus.STARTED, "s2"),
    ]
    ledger = project_progress([], steps)
    assert _kinds(ledger.done) == [(StageKind.VALIDATE, StageStatus.SUCCEEDED)]
    assert _kinds(ledger.pending) == [(StageKind.APPROVAL_WAIT, StageStatus.STARTED)]


def test_an_unknown_receipt_waits_for_reconciliation() -> None:
    events = [
        _event(1, RunEventType.ACTION_RESERVED, action_id="a1"),
        _event(2, RunEventType.ACTION_DISPATCHING, action_id="a1"),
        _event(3, RunEventType.ACTION_UNKNOWN, action_id="a1"),
        _event(
            4,
            RunEventType.RUN_STATE_CHANGED,
            {"from": "RUNNING", "to": "NEEDS_RECONCILIATION", "reason": None},
        ),
    ]
    ledger = project_progress(events, [])
    assert (StageKind.DISPATCH, StageStatus.UNKNOWN) in _kinds(ledger.pending)
    assert (StageKind.RECONCILE, StageStatus.WAITING) in _kinds(ledger.pending)
    done = project_progress(
        [*events, _event(5, RunEventType.RECONCILIATION_COMPLETED, {"found": "COMMITTED"}, "a1")],
        [],
    )
    assert (StageKind.RECONCILE, StageStatus.SUCCEEDED) in _kinds(done.done)
    assert (StageKind.RECONCILE, StageStatus.WAITING) not in _kinds(done.pending)


@dataclass
class WrongAnswerDriver:
    """Reads, then proposes a notes answer whose count the verifier will refuse."""

    driver_id: str = "wrong-answer-driver"

    async def advance(self, ctx: Any, step_input: DriverInput) -> Any:
        if step_input.action_result is not None:
            return FinalAnswer(text="done")
        if not step_input.observations:
            request = ReadRequest(
                request_id="r1", contract_id=READ.contract_id, connection_id=CONN, arguments={}
            )
            return RequestReads(reads=(request,))
        return ProposeAction(
            proposal=ActionProposal(
                contract_id=SUMMARY.contract_id,
                connection_id=CONN,
                arguments={"count": "999"},
            )
        )


async def test_failed_answer_verification_is_not_counted_as_a_failed_validation(
    make_kernel: MakeKernel,
) -> None:
    k = make_kernel(driver=WrongAnswerDriver(), with_answer=True)
    run = await k.coordinator.start_run(k.requester, "count the notes", k.scope)
    events = await k.store.list_events(TENANT, run.run_id)
    written = sum(
        1
        for e in events
        if e.type is RunEventType.VALIDATION_COMPLETED and e.payload.get("status") != "PASS"
    )
    ledger = await _ledger(k, run.run_id)
    assert ledger.budgets_used.failed_validations == written
    assert not hasattr(ledger.budgets_used, "repairs")
    assert ledger.repair_turns == ()


def test_stale_validation_then_budget_exhausted_counts_one() -> None:
    events = [
        _event(1, RunEventType.VALIDATION_COMPLETED, {"status": "STALE", "findings": []}),
        _event(2, RunEventType.BUDGET_EXHAUSTED, {"budget": "active seconds"}),
        _event(3, RunEventType.RUN_STATE_CHANGED, {"from": "RUNNING", "to": "FAILED"}),
    ]
    assert project_progress(events, []).budgets_used.failed_validations == 1


def test_an_unknown_reconciliation_stays_pending() -> None:
    events = [
        _event(
            1,
            RunEventType.RUN_STATE_CHANGED,
            {"from": "RUNNING", "to": "NEEDS_RECONCILIATION", "reason": None},
        ),
        _event(2, RunEventType.RECONCILIATION_COMPLETED, {"found": "UNKNOWN"}, "a1"),
    ]
    ledger = project_progress(events, [])
    assert _kinds(ledger.pending) == [(StageKind.RECONCILE, StageStatus.WAITING)]
    assert ledger.done == ()
