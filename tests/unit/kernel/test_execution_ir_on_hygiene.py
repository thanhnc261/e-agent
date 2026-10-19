"""Hygiene parked from Tasks 2c.6 and 2c.7 under `features.execution_ir: on` (Task 2c.8a).

- Every stage of a linked action writes its step rows (target §6.4.5, §6.4.7): the
  dispatch-time revalidation of a first step (passing, stale or past its deadline), an
  approval wait ended by a cancel, a reservation that recovery blocks, and a verify with no
  registered verifier. A finished run leaves no row open.
- Budgets come from the context admitted with the run and are never merged again from the
  definition snapshot, whose ``model_fields_set`` does not survive the JSON round trip
  (2c.6 review R-1).
- No driver turn can follow a verified write, so the plan write budget cannot be exercised
  end to end; it stays pinned at the plan checks (2c.7 review R2-3).

Both stores run through `run_store` (ENG-STORE-1); no plugin is imported.
"""

import ast
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from e_agent.contracts.action import ActionState
from e_agent.contracts.approval import ApprovalDecision
from e_agent.contracts.context import Budgets
from e_agent.contracts.events import RunEventType
from e_agent.contracts.features import FeatureMode, Features
from e_agent.contracts.run import TERMINAL_RUN_STATES, ReasonCode, RunState
from e_agent.contracts.step import StepKind, StepRecord, StepStatus
from e_agent.kernel import coordinator as coordinator_module
from e_agent.kernel.coordinator import RunCoordinator
from e_agent.kernel.policy import DefaultPolicy
from e_agent.sdk.ports import AskClarification, DriverInput, ProposePlan

from .conftest import (
    NOTE_INPUT,
    NOTES_TASK,
    PLAN_BUDGETS,
    TENANT,
    Kernel,
    NotesDriver,
    NotesPlanDriver,
    two_step_plan,
)

MakeKernel = Callable[..., Kernel]
ON = Features(execution_ir=FeatureMode.ON)
V, AW, D, VF = StepKind.VALIDATE, StepKind.APPROVAL_WAIT, StepKind.DISPATCH, StepKind.VERIFY
S, OK, BLOCKED, FAILED, UNKNOWN = (
    StepStatus.STARTED,
    StepStatus.SUCCEEDED,
    StepStatus.BLOCKED,
    StepStatus.FAILED,
    StepStatus.UNKNOWN,
)
PROPOSED = [(V, S), (V, OK), (AW, S)]
"""The rows of a validated proposal waiting for its approval."""
APPROVED = [*PROPOSED, (AW, OK)]


class Crash(BaseException):
    """Simulates the process dying (not an Exception, so nothing catches it)."""


async def _start(k: Kernel) -> Any:
    return await k.coordinator.start_run(
        k.requester, "write standup note", k.scope, task_kind=NOTES_TASK.task_id
    )


async def _decide(coordinator: RunCoordinator, k: Kernel, run_id: str) -> Any:
    pres = await coordinator.pending_approval(TENANT, run_id)
    return await coordinator.decide(
        actor=k.approver,
        run_id=run_id,
        action_id=pres.action_id,
        action_digest=pres.digest,
        expected_run_revision=pres.run_revision,
        decision=ApprovalDecision.APPROVED,
    )


async def _rows(k: Kernel, run_id: str) -> dict[str, list[tuple[StepKind, StepStatus]]]:
    """Each action's step rows, in sequence order."""
    rows: dict[str, list[tuple[StepKind, StepStatus]]] = {}
    for step in await k.store.list_steps(TENANT, run_id):
        rows.setdefault(str(step.action_id), []).append((step.kind, step.status))
    return rows


def _open(steps: list[StepRecord]) -> set[str]:
    """The step ids whose latest row is still STARTED."""
    last: dict[str, StepStatus] = {}
    for step in steps:
        last[step.step_id] = step.status
    return {step_id for step_id, status in last.items() if status is StepStatus.STARTED}


async def _proposed(k: Kernel, run_id: str) -> list[str]:
    """The run's actions in proposal order."""
    events = await k.store.list_events(TENANT, run_id)
    return [str(e.action_id) for e in events if e.type is RunEventType.PROPOSAL_CREATED]


async def _passing(k: Kernel) -> tuple[Any, list[tuple[StepKind, StepStatus]]]:
    run = await _decide(k.coordinator, k, (await _start(k)).run_id)
    assert (run.state, run.reason_code) == (RunState.SUCCEEDED, ReasonCode.VERIFIED)
    return run, [*APPROVED, (V, S), (V, OK), (D, S), (D, OK), (VF, S), (VF, OK)]


async def _stale(k: Kernel) -> tuple[Any, list[tuple[StepKind, StepStatus]]]:
    run = await _start(k)
    k.backend.revision += 1  # a material fact changes while the approval waits
    run = await _decide(k.coordinator, k, run.run_id)
    assert run.state is RunState.WAITING_APPROVAL and k.backend.create_calls == 0
    run = await _decide(k.coordinator, k, run.run_id)  # the repaired proposal
    assert (run.state, run.reason_code) == (RunState.SUCCEEDED, ReasonCode.VERIFIED)
    return run, [*APPROVED, (V, S), (V, BLOCKED)]


async def _deadline(k: Kernel) -> tuple[Any, list[tuple[StepKind, StepStatus]]]:
    async def past_deadline(*_args: Any) -> str | None:
        raise TimeoutError

    run = await _start(k)
    k.coordinator._staleness = past_deadline  # type: ignore[method-assign]
    run = await _decide(k.coordinator, k, run.run_id)
    assert (run.state, run.reason_code) == (RunState.FAILED, ReasonCode.BUDGET_EXHAUSTED)
    return run, [*APPROVED, (V, S), (V, FAILED)]


async def _cancelled(k: Kernel) -> tuple[Any, list[tuple[StepKind, StepStatus]]]:
    run = await k.coordinator.cancel(k.requester, (await _start(k)).run_id)
    assert (run.state, run.reason_code) == (RunState.CANCELLED, ReasonCode.CANCELLED)
    return run, [*PROPOSED, (AW, BLOCKED)]


async def _reserved_then_crash(k: Kernel) -> tuple[Any, list[tuple[StepKind, StepStatus]]]:
    run = await _start(k)
    original = k.store.put_action

    async def die_on_dispatching(action: Any, expected: Any, events: Any) -> Any:
        if action.state is ActionState.DISPATCHING:
            raise Crash
        return await original(action, expected, events)

    k.store.put_action = die_on_dispatching
    with pytest.raises(Crash):
        await _decide(k.coordinator, k, run.run_id)
    k.store.put_action = original
    (run,) = await _restart(k).recover()
    assert (run.state, run.reason_code) == (RunState.FAILED, ReasonCode.INTERRUPTED)
    assert k.backend.create_calls == 0
    return run, [*APPROVED, (V, S), (V, OK), (D, S), (D, BLOCKED)]


async def _no_verifier(k: Kernel) -> tuple[Any, list[tuple[StepKind, StepStatus]]]:
    run = await _start(k)
    k.coordinator._registry.verifier_for = lambda _contract_id: None  # type: ignore[method-assign]
    run = await _decide(k.coordinator, k, run.run_id)
    assert (run.state, run.reason_code) == (RunState.VERIFYING, ReasonCode.VERIFICATION_PENDING)
    return run, [*APPROVED, (V, S), (V, OK), (D, S), (D, OK), (VF, S), (VF, UNKNOWN)]


def _restart(k: Kernel) -> RunCoordinator:
    """A new process: same durable store and registry, fresh coordinator and driver."""
    return RunCoordinator(
        store=k.store,
        registry=k.coordinator._registry,
        connections=k.connections,
        policy=DefaultPolicy(),
        driver=NotesDriver(texts=[]),
        clock=k.clock,
        features=k.coordinator._features,
    )


async def _worker_lost(*_args: Any, **_kw: Any) -> Any:
    raise RuntimeError("worker lost")


async def _step_two_interrupted(k: Kernel) -> tuple[Any, list[tuple[StepKind, StepStatus]]]:
    """The process dies after step 2's action is stored, before it reserves; recovery
    ends the plan INTERRUPTED and step 2's open validate row ends with it (2c.8a R-2)."""
    run = await _start(k)
    original = k.store.put_action

    async def die_at_step_two(action: Any, expected: Any, events: Any) -> Any:
        stored = await original(action, expected, events)
        if action.step_index == 1:
            raise Crash  # stored PROPOSED with its validate row open, then the process dies
        return stored

    k.store.put_action = die_at_step_two
    with pytest.raises(Crash):
        await _decide(k.coordinator, k, run.run_id)
    k.store.put_action = original
    (run,) = await _restart(k).recover()
    assert (run.state, run.reason_code) == (RunState.FAILED, ReasonCode.INTERRUPTED)
    assert run.reason == "interrupted before plan step 2 reserved"
    assert k.backend.create_calls == 1
    return run, [(V, S), (V, FAILED)]


async def _resume_failed(k: Kernel) -> tuple[Any, list[tuple[StepKind, StepStatus]]]:
    """The resume claim stores step 2's action and then fails before it reserves; the
    worker's crash rules, with resume disabled, end the plan INTERRUPTED (2c.8a R-2)."""
    run = await _start(k)
    k.coordinator._after_step_verified = _worker_lost  # type: ignore[method-assign]
    with pytest.raises(RuntimeError):
        await _decide(k.coordinator, k, run.run_id)
    coordinator = _restart(k)
    (queued,) = await coordinator.recover()
    assert queued.state is RunState.VERIFYING
    claim = await k.store.claim_work("worker-test")
    assert claim is not None and claim.kind == "resume"
    coordinator._dispatch = _worker_lost  # type: ignore[method-assign]
    with pytest.raises(RuntimeError):
        async with k.store.work_scope(claim):
            await coordinator.resume_plan(TENANT, run.run_id)
    del coordinator._dispatch
    async with k.store.work_scope(claim):  # the worker's `_mark_failed`
        run = await coordinator.recover_run(TENANT, run.run_id, resume=False)
        await k.store.finish_work(claim)
    assert (run.state, run.reason_code) == (RunState.FAILED, ReasonCode.INTERRUPTED)
    assert run.reason == "plan resume failed before step 2 reserved"
    assert k.backend.create_calls == 1
    return run, [(V, S), (V, FAILED)]


SCENARIOS = {
    "revalidation passes": _passing,
    "revalidation stale": _stale,
    "revalidation past its deadline": _deadline,
    "approval wait cancelled": _cancelled,
    "reservation blocked by recovery": _reserved_then_crash,
    "verifier missing": _no_verifier,
}
PLAN_SCENARIOS = {
    "plan step interrupted before it reserved": _step_two_interrupted,
    "plan resume failed before the step reserved": _resume_failed,
}
"""Two-step plans, whose subject is step 2's action; `off` cannot run a plan at all."""


@pytest.mark.parametrize("scenario", [*SCENARIOS, *PLAN_SCENARIOS])
async def test_every_stage_writes_a_step_row(make_kernel: MakeKernel, scenario: str) -> None:
    """The subject action's rows end with the stage named by the scenario, and a finished
    run leaves no step row open (2c.6 parked items, 2c.8a review R-2). The subject is the
    first action, or a plan's step 2."""
    if scenario in PLAN_SCENARIOS:
        k = make_kernel(
            features=ON,
            budgets=PLAN_BUDGETS,
            driver=NotesPlanDriver(),
            input_schemas={"c": NOTE_INPUT, "p": NOTE_INPUT},
        )
        run, expected = await PLAN_SCENARIOS[scenario](k)
        subject = (await _proposed(k, run.run_id))[1]
    else:
        k = make_kernel(["first", "second"], features=ON)
        run, expected = await SCENARIOS[scenario](k)
        subject = (await _proposed(k, run.run_id))[0]
    rows = await _rows(k, run.run_id)
    assert rows[subject] == expected
    steps = await k.store.list_steps(TENANT, run.run_id)
    assert [s.sequence for s in steps] == list(range(len(steps)))
    if run.state in TERMINAL_RUN_STATES:
        assert _open(steps) == set()
    print(f"{scenario}: {len(steps)} step rows")


async def test_off_writes_no_step_rows_on_any_stage(make_kernel: MakeKernel) -> None:
    """ENG-TOGGLE-1: the same stages in `off` write no step row."""
    count = 0
    for scenario in SCENARIOS.values():
        k = make_kernel(["first", "second"])
        run, _ = await scenario(k)
        assert await k.store.list_steps(TENANT, run.run_id) == []
        count += 1
        truncate = getattr(k.store, "truncate_for_tests", None)
        if truncate is not None:
            await truncate()
    assert count == len(SCENARIOS)


# -- budgets (2c.6 review R-1) ------------------------------------------------------------
def _asking(advance: Any) -> Any:
    asked: set[str] = set()

    async def wrapped(ctx: Any, step_input: DriverInput) -> Any:
        if ctx.run_id not in asked:
            asked.add(ctx.run_id)
            return AskClarification(question="which note?")
        return await advance(ctx, step_input)

    return wrapped


async def test_budgets_never_merged_from_the_snapshot(make_kernel: MakeKernel) -> None:
    """The definition narrows one field; a resumed run keeps the admitted budgets. Merging
    the reloaded snapshot instead would widen every other field back to its default, since
    after the JSON round trip every budget field reads as set."""
    profile = Budgets(max_driver_turns=9, max_read_calls=7, max_validation_repairs=1)
    task = NOTES_TASK.model_copy(update={"budgets": Budgets(max_driver_turns=5)})
    admitted = profile.model_copy(update={"max_driver_turns": 5})
    k = make_kernel(features=ON, budgets=profile, task=task)
    k.driver.advance = _asking(k.driver.advance)
    run = await _start(k)
    assert run.state is RunState.WAITING_INPUT
    k.coordinator.release_continuation(run.run_id)
    run = await k.coordinator.resume_input(k.requester, run.run_id, "standup", run.revision)
    cont = await k.coordinator._load_cont(TENANT, run.run_id)
    assert cont.ctx.budgets == admitted
    assert cont.task is not None and cont.task.budgets is not None
    assert cont.task.budgets.model_fields_set == set(Budgets.model_fields)  # the hazard
    assert cont.task.budgets.max_read_calls != profile.max_read_calls


def test_budgets_are_merged_only_at_admission() -> None:
    """`merged_budgets` has one call site, `_prepare_run`, over the registry's definition
    (`_run_task`), never over a continuation's snapshot."""
    kernel = Path(coordinator_module.__file__).resolve().parent
    calls: list[tuple[str, str]] = []
    for module in sorted(kernel.glob("*.py")):
        tree = ast.parse(module.read_text())
        for func in ast.walk(tree):
            if not isinstance(func, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            for node in ast.walk(func):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "merged_budgets"
                ):
                    calls.append((module.name, func.name))
    assert calls == [("coordinator.py", "_prepare_run")]
    source = ast.unparse(
        next(
            f
            for f in ast.walk(ast.parse(Path(coordinator_module.__file__).read_text()))
            if isinstance(f, ast.FunctionDef) and f.name == "_prepare_run"
        )
    )
    assert "self._run_task(run)" in source and "cont.task" not in source


# -- the plan write budget end to end (2c.7 review R2-3) ----------------------------------
async def test_no_driver_turn_follows_a_verified_write(make_kernel: MakeKernel) -> None:
    """Why the plan write budget is pinned at `_plan_findings` and not end to end: the one
    driver turn after a verified write is the acknowledgement in `_finish_verified`, which
    keeps only a FinalAnswer. A plan proposed there never reaches the plan checks, so no run
    can propose a plan after an earlier write counted. When a driver turn may follow a
    verified write, this test fails and the end-to-end budget test is owed."""
    k = make_kernel(features=ON, budgets=Budgets(max_admitted_writes=2))
    advance = k.driver.advance
    checked: list[int] = []
    plan_findings = k.coordinator._plan_findings

    def counting(*args: Any) -> Any:
        checked.append(1)
        return plan_findings(*args)

    async def plans_after_the_write(ctx: Any, step_input: DriverInput) -> Any:
        if step_input.action_result is not None:
            return ProposePlan(plan=two_step_plan())
        return await advance(ctx, step_input)

    k.coordinator._plan_findings = counting  # type: ignore[method-assign]
    k.driver.advance = plans_after_the_write
    run = await _decide(k.coordinator, k, (await _start(k)).run_id)
    assert (run.state, run.reason_code) == (RunState.SUCCEEDED, ReasonCode.VERIFIED)
    assert checked == [] and k.backend.create_calls == 1
    assert [a.state for a in await k.store.list_actions(TENANT, run.run_id)] == [
        ActionState.VERIFIED
    ]
    events = await k.store.list_events(TENANT, run.run_id)
    assert len([e for e in events if e.type is RunEventType.IR_PLAN_COMPILED]) == 1
    (final,) = [e for e in events if e.type is RunEventType.MESSAGE_FINAL]
    assert final.payload["text"] == "The approved action was independently verified."
