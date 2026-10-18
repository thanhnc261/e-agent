"""`features.execution_ir: shadow` (Task 2c.5, ADR 0027, target §6.4.8, XA-24).

The run acts on today's path. After today's validation passes a write proposal, the kernel
compiles it into a 1-step plan, validates it, computes the plan digest and records
`ir.plan_compiled` (with whether the step digest equals the action digest) and the step
records of the stage it observed. A run that names no task definition, or a compile or
validation error, records `ir.shadow_failed` with a kernel-fixed payload and nothing else.
Shadow adds no driver call, provider read or budget use, and changes nothing the run acts on.
Runs over both stores through the `run_store` fixture (ENG-STORE-1).
"""

import json
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

import pytest
from e_agent.contracts.approval import ApprovalDecision
from e_agent.contracts.events import RunEventType
from e_agent.contracts.features import FeatureMode, Features
from e_agent.contracts.run import ReasonCode, RunState
from e_agent.contracts.step import StepKind, StepRecord, StepStatus
from e_agent.contracts.validation import Finding, ValidationStatus
from e_agent.kernel import continuation as continuation_module
from e_agent.kernel import features as features_module
from e_agent.kernel.approval import compute_digest
from e_agent.kernel.connections import ConnectionCatalog
from e_agent.kernel.coordinator import RunCoordinator
from e_agent.kernel.errors import ErrorCode, KernelError
from e_agent.kernel.features import FALLBACK_MESSAGES, SHADOW_MESSAGES
from e_agent.kernel.memory_store import InMemoryRunStore
from e_agent.kernel.policy import DefaultPolicy
from e_agent.kernel.registry import PluginRegistry

from .conftest import NOTES_TASK, TENANT, Kernel, NotesDriver
from .record_off_baseline import _normalise, deterministic_ids

MakeKernel = Callable[..., Kernel]
OFF = Features()
SHADOW = Features(execution_ir=FeatureMode.SHADOW)
IR_EVENTS = {RunEventType.IR_PLAN_COMPILED, RunEventType.IR_SHADOW_FAILED}
SENTINEL = "SENTINEL-7f3a-exception-text"


async def _start(k: Kernel, *, task_kind: str | None = NOTES_TASK.task_id) -> Any:
    return await k.coordinator.start_run(
        k.requester, "write standup note", k.scope, task_kind=task_kind
    )


async def _types(k: Kernel, run_id: str) -> list[RunEventType]:
    return [e.type for e in await k.store.list_events(TENANT, run_id)]


async def _of(k: Kernel, run_id: str, kind: RunEventType) -> list[Any]:
    return [e for e in await k.store.list_events(TENANT, run_id) if e.type is kind]


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


def _without_ir(types: list[RunEventType]) -> list[RunEventType]:
    return [t for t in types if t not in IR_EVENTS]


async def _reset(store: Any) -> None:
    """Empty the shared test store, so an `off` and a `shadow` run under the same
    deterministic ids do not collide on run, action or operation ids."""
    truncate = getattr(store, "truncate_for_tests", None)
    if truncate is not None:
        await truncate()
    else:
        store.__init__()


# -- success -----------------------------------------------------------------------------
async def test_shadow_records_plan_compiled_with_matching_digest(make_kernel: MakeKernel) -> None:
    k = make_kernel(features=SHADOW)
    run = await _start(k)
    assert run.state is RunState.WAITING_APPROVAL
    pres = await k.coordinator.pending_approval(TENANT, run.run_id)

    (compiled,) = await _of(k, run.run_id, RunEventType.IR_PLAN_COMPILED)
    assert compiled.action_id == pres.action_id
    assert compiled.payload == {
        "plan_id": compiled.payload["plan_id"],
        "plan_digest": pres.digest,
        "step_count": 1,
        "task_id": NOTES_TASK.task_id,
        "task_version": NOTES_TASK.version,
        "digest_matches": True,
    }
    assert not await _of(k, run.run_id, RunEventType.IR_SHADOW_FAILED)
    plan = await k.store.get_plan(TENANT, compiled.payload["plan_id"])
    assert (plan.task_id, plan.task_version) == (NOTES_TASK.task_id, NOTES_TASK.version)
    assert [dict(s.proposal.arguments) for s in plan.steps] == [{"text": "standup notes"}]
    # Shadow records the run's definition; the run record is otherwise today's.
    stored = await k.store.get_run(TENANT, run.run_id)
    assert (stored.task_id, stored.task_version) == (NOTES_TASK.task_id, NOTES_TASK.version)
    types = await _types(k, run.run_id)
    assert (
        types.index(RunEventType.VALIDATION_COMPLETED)
        < types.index(RunEventType.IR_PLAN_COMPILED)
        < types.index(RunEventType.APPROVAL_REQUESTED)
    )


async def test_shadow_writes_step_records(make_kernel: MakeKernel) -> None:
    k = make_kernel(features=SHADOW)
    run = await _start(k)
    pres = await k.coordinator.pending_approval(TENANT, run.run_id)
    (compiled,) = await _of(k, run.run_id, RunEventType.IR_PLAN_COMPILED)
    reads = await _of(k, run.run_id, RunEventType.READ_RECORDED)

    steps = await k.store.list_steps(TENANT, run.run_id)
    assert [(s.sequence, s.kind, s.status) for s in steps] == [
        (0, StepKind.VALIDATE, StepStatus.STARTED),
        (1, StepKind.VALIDATE, StepStatus.SUCCEEDED),
    ]
    assert {s.step_id for s in steps} == {f"{compiled.payload['plan_id']}/step-1/validate"}
    assert all(s.action_id == pres.action_id for s in steps)
    assert [r.evidence_id for r in steps[0].input_refs] == [e.payload["evidence_id"] for e in reads]
    assert steps[1].finished_at is not None


async def test_shadow_step_sequence_follows_the_runs_existing_steps(
    make_kernel: MakeKernel,
) -> None:
    """The shadow rows take the next sequence after any step the run already has; a repaired
    proposal (the first is blocked) is compiled once, when it validates."""
    k = make_kernel(["", "standup notes"], features=SHADOW)
    run_id, _ = await k.coordinator.admit_run(
        k.requester,
        "write standup note",
        k.scope,
        run_id="run-seq",
        idempotency_key="seq",
        request_digest="d",
    )
    run = await k.store.get_run(TENANT, run_id)
    earlier = StepRecord(
        tenant_id=TENANT,
        run_id=run_id,
        step_id="earlier",
        sequence=5,
        kind=StepKind.DRIVER_TURN,
        status=StepStatus.SUCCEEDED,
        started_at=k.clock(),
        finished_at=k.clock(),
    )
    await k.store.update_run(
        run.model_copy(update={"revision": run.revision + 1}), run.revision, [earlier]
    )
    # An admitted (API) run names no definition: give this one the notes task directly.
    run = await k.store.get_run(TENANT, run_id)
    await k.store.update_run(
        run.model_copy(
            update={
                "revision": run.revision + 1,
                "task_id": NOTES_TASK.task_id,
                "task_version": NOTES_TASK.version,
            }
        ),
        run.revision,
        [],
    )
    run = await k.coordinator.start_admitted_run(TENANT, run_id)
    assert run.state is RunState.WAITING_APPROVAL
    assert len(await _of(k, run_id, RunEventType.VALIDATION_COMPLETED)) == 2
    assert len(await _of(k, run_id, RunEventType.IR_PLAN_COMPILED)) == 1
    steps = await k.store.list_steps(TENANT, run_id)
    assert [s.sequence for s in steps] == [5, 6, 7]


# -- failures ----------------------------------------------------------------------------
def _id_free(pres: Any) -> str:
    """The presentation with generated ids normalised and the digest dropped, after checking
    the digest is that of its canonical proposal. The admission event takes an event id, so
    later generated ids (evidence) shift under the deterministic source; the presentation is
    otherwise the same."""
    assert pres.digest == compute_digest(pres.canonical_proposal)
    return _normalise(json.dumps(pres.model_dump(mode="json", exclude={"digest"})), {})


async def _admitted(k: Kernel) -> tuple[Any, Any]:
    """An API-style run: free text through `admit_run`, no task kind (D8)."""
    run_id, _ = await k.coordinator.admit_run(
        k.requester,
        "write standup note",
        k.scope,
        run_id="run-api",
        idempotency_key="api-key",
        request_digest="d",
    )
    return run_id, await k.coordinator.start_admitted_run(TENANT, run_id)


def _assert_unresolved_once(events: list[Any]) -> None:
    """One `ir.shadow_failed` (`IR_TASK_UNRESOLVED`), at creation, and no other IR record."""
    failed = [e for e in events if e.type in IR_EVENTS]
    assert [(e.type, e.payload, e.action_id) for e in failed] == [
        (
            RunEventType.IR_SHADOW_FAILED,
            {
                "reason_code": "ir_task_unresolved",
                "message": FALLBACK_MESSAGES[ReasonCode.IR_TASK_UNRESOLVED],
            },
            None,
        )
    ]
    assert [e.type for e in events[:2]] == [RunEventType.RUN_CREATED, RunEventType.IR_SHADOW_FAILED]
    assert events[0].sequence + 1 == events[1].sequence


async def test_shadow_without_definition_records_shadow_failed(make_kernel: MakeKernel) -> None:
    """An API-style run that reaches approval records `IR_TASK_UNRESOLVED` once, in the
    creating write, and nothing else; its proposal skips the shadow step."""
    seen = {}
    for name, mode in (("off", OFF), ("shadow", SHADOW)):
        k = make_kernel(features=mode)
        with deterministic_ids():
            run_id, run = await _admitted(k)
            presentation = await k.coordinator.pending_approval(TENANT, run_id)
            stored = await k.store.get_run(TENANT, run_id)
            done = await _approve(k, run_id)
        (outcome,) = await _of(k, run_id, RunEventType.OUTCOME_REPORTED)
        seen[name] = {
            "run": run,
            "presentation": presentation,
            "events": await k.store.list_events(TENANT, run_id),
            "steps": await k.store.list_steps(TENANT, run_id),
            "stored": stored,
            "end": (done.state, done.reason_code, done.revision, outcome.payload["status"]),
        }
        await _reset(k.store)
    off, shadow = seen["off"], seen["shadow"]

    _assert_unresolved_once(shadow["events"])
    assert shadow["steps"] == []
    assert (shadow["stored"].task_id, shadow["stored"].task_version) == (None, None)
    # Nothing else differs: the stream without the shadow event, the run and the approval.
    assert _without_ir([e.type for e in shadow["events"]]) == [e.type for e in off["events"]]
    assert shadow["run"] == off["run"]
    assert _id_free(shadow["presentation"]) == _id_free(off["presentation"])
    assert shadow["presentation"].run_revision == off["presentation"].run_revision
    assert shadow["end"] == off["end"]
    assert off["end"][0] is RunState.SUCCEEDED


async def test_shadow_unresolved_blocked_run_records_task_unresolved(
    make_kernel: MakeKernel,
) -> None:
    """An API-style run whose every proposal is blocked still records the unresolved task once."""
    seen = {}
    for name, mode in (("off", OFF), ("shadow", SHADOW)):
        k = make_kernel(["", "", ""], features=mode)
        with deterministic_ids():
            run_id, run = await _admitted(k)
        seen[name] = (run, await k.store.list_events(TENANT, run_id))
        await _reset(k.store)
    (off_run, off_events), (run, events) = seen["off"], seen["shadow"]

    assert run.state is RunState.FAILED and run.reason_code is ReasonCode.VALIDATION_FAILED
    _assert_unresolved_once(events)
    assert run == off_run
    assert _without_ir([e.type for e in events]) == [e.type for e in off_events]


async def test_shadow_with_an_unknown_task_kind_is_unresolved(make_kernel: MakeKernel) -> None:
    """A kind that names no admitted definition leaves the run unlinked (the CLI only passes
    admitted preset kinds, so this is the defensive path)."""
    k = make_kernel(features=SHADOW)
    run = await _start(k, task_kind="no-such-task")
    stored = await k.store.get_run(TENANT, run.run_id)
    assert (stored.task_id, stored.task_version) == (None, None)
    _assert_unresolved_once(await k.store.list_events(TENANT, run.run_id))
    assert await k.store.list_steps(TENANT, run.run_id) == []


async def test_shadow_linked_definition_gone_at_proposal_is_unresolved(
    make_kernel: MakeKernel,
) -> None:
    """A linked run whose definition is no longer admitted when it proposes (a resumed run
    after a redeploy) records `IR_TASK_UNRESOLVED` for that proposal, in the approval write."""
    k = make_kernel(features=SHADOW)
    advance = k.driver.advance

    async def drop_definition(ctx: Any, step_input: Any) -> Any:
        if step_input.observations:
            k.coordinator._registry.task_definitions.pop(NOTES_TASK.task_id, None)
        return await advance(ctx, step_input)

    k.driver.advance = drop_definition  # type: ignore[method-assign]
    run = await _start(k)
    pres = await k.coordinator.pending_approval(TENANT, run.run_id)
    (failed,) = [e for e in await k.store.list_events(TENANT, run.run_id) if e.type in IR_EVENTS]
    assert failed.type is RunEventType.IR_SHADOW_FAILED
    assert failed.payload["reason_code"] == "ir_task_unresolved"
    assert failed.action_id == pres.action_id
    assert await k.store.list_steps(TENANT, run.run_id) == []


def _raise_sentinel(*_a: Any, **_kw: Any) -> Any:
    raise RuntimeError(SENTINEL)


def _sentinel_finding(*_a: Any, **_kw: Any) -> tuple[Finding, ...]:
    return (
        Finding(
            rule_id="KERNEL-PLAN-TASK",
            rule_version="1",
            status=ValidationStatus.FAIL,
            message=SENTINEL,
        ),
    )


STAGE_FAULTS = [
    ("compile", "compile_proposal", _raise_sentinel),
    ("validate", "validate_plan", _sentinel_finding),
    ("validate", "validate_plan", _raise_sentinel),
    ("validate", "plan_digest_input", _raise_sentinel),
]


@pytest.mark.parametrize(("stage", "target", "fault"), STAGE_FAULTS)
async def test_shadow_compile_error_records_shadow_failed_and_run_unchanged(
    make_kernel: MakeKernel,
    monkeypatch: pytest.MonkeyPatch,
    stage: str,
    target: str,
    fault: Callable[..., Any],
) -> None:
    off = make_kernel(features=OFF)
    with deterministic_ids():
        off_run = await _start(off)
    off_pres = await off.coordinator.pending_approval(TENANT, off_run.run_id)
    off_types = await _types(off, off_run.run_id)
    await _reset(off.store)
    k = make_kernel(features=SHADOW)
    monkeypatch.setattr(features_module, target, fault)
    with deterministic_ids():
        run = await _start(k)
    pres = await k.coordinator.pending_approval(TENANT, run.run_id)

    (failed,) = await _of(k, run.run_id, RunEventType.IR_SHADOW_FAILED)
    assert failed.payload == {"stage": stage, "message": SHADOW_MESSAGES[stage]}
    assert failed.action_id == pres.action_id
    assert not await _of(k, run.run_id, RunEventType.IR_PLAN_COMPILED)
    assert await k.store.list_steps(TENANT, run.run_id) == []
    # The run acts exactly as off: state, stream, revision and the approval presentation.
    assert run.state is off_run.state is RunState.WAITING_APPROVAL
    assert _without_ir(await _types(k, run.run_id)) == off_types
    assert run.revision == off_run.revision
    assert pres == off_pres
    run = await _approve(k, run.run_id)
    assert run.state is RunState.SUCCEEDED


@pytest.mark.parametrize(("stage", "target", "fault"), STAGE_FAULTS)
async def test_shadow_failed_carries_no_exception_text(
    make_kernel: MakeKernel,
    monkeypatch: pytest.MonkeyPatch,
    stage: str,
    target: str,
    fault: Callable[..., Any],
) -> None:
    k = make_kernel(features=SHADOW)
    monkeypatch.setattr(features_module, target, fault)
    run = await _start(k)
    run = await _approve(k, run.run_id)
    events = await k.store.list_events(TENANT, run.run_id)
    assert [e.payload["stage"] for e in events if e.type is RunEventType.IR_SHADOW_FAILED] == [
        stage
    ]
    stored = json.dumps([e.model_dump(mode="json") for e in events])
    stored += json.dumps(
        [s.model_dump(mode="json") for s in await k.store.list_steps(TENANT, run.run_id)]
    )
    assert SENTINEL not in stored


async def test_shadow_store_errors_propagate(
    make_kernel: MakeKernel, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only IR stage errors become `ir.shadow_failed`; a store failure is never swallowed."""
    k = make_kernel(features=SHADOW)

    async def broken(*_a: Any, **_kw: Any) -> None:
        raise ConnectionError("store down")

    monkeypatch.setattr(k.store, "put_plan", broken)
    with pytest.raises(ConnectionError):
        await _start(k)


# -- no cost, same outcome ---------------------------------------------------------------
def _budget(k: Kernel, run_id: str) -> dict[str, Any]:
    cont = k.coordinator._runs[run_id]
    return {
        "driver_calls": k.driver.calls,
        "provider_reads": k.backend.read_calls,
        "provider_writes": k.backend.create_calls,
        "turns": cont.turns,
        "read_calls": cont.read_calls,
        "writes": cont.writes,
        "repairs": cont.repairs,
        "active_seconds": cont.active_seconds,
    }


async def test_shadow_adds_no_driver_calls_reads_or_budget(
    make_kernel: MakeKernel, monkeypatch: pytest.MonkeyPatch
) -> None:
    counted: dict[str, list[dict[str, Any]]] = {}
    for name, mode in (("off", OFF), ("shadow", SHADOW)):
        # Each timed (budgeted) call reads the timer twice, one second apart, so
        # `active_seconds` counts timed calls exactly instead of wall time.
        ticks = iter(range(1 << 20))
        monkeypatch.setattr(
            continuation_module, "time", SimpleNamespace(perf_counter=lambda: float(next(ticks)))
        )
        k = make_kernel(features=mode)
        run = await _start(k)
        waiting = _budget(k, run.run_id)
        await _approve(k, run.run_id)
        counted[name] = [waiting, _budget(k, run.run_id)]
    assert counted["shadow"] == counted["off"]
    final = counted["off"][1]
    assert final["driver_calls"] > 0 and final["provider_reads"] > 0 and final["active_seconds"] > 0


async def test_shadow_outcome_equals_off(make_kernel: MakeKernel) -> None:
    seen = {}
    for name, mode in (("off", OFF), ("shadow", SHADOW)):
        k = make_kernel(features=mode)
        with deterministic_ids():
            run = await _start(k)
            pres = await k.coordinator.pending_approval(TENANT, run.run_id)
            run = await _approve(k, run.run_id)
        (outcome,) = await _of(k, run.run_id, RunEventType.OUTCOME_REPORTED)
        (action,) = await k.store.list_actions(TENANT, run.run_id)
        seen[name] = {
            "state": run.state,
            "reason_code": run.reason_code,
            "presentation": pres,
            "outcome": (outcome.payload["status"], outcome.payload["checks"]),
            "action": (action.state, action.digest, dict(action.arguments)),
            "notes": [n["text"] for n in k.backend.notes.values()],
            "stream": _without_ir(await _types(k, run.run_id)),
        }
        await _reset(k.store)
    assert seen["shadow"] == seen["off"]
    assert seen["off"]["state"] is RunState.SUCCEEDED
    assert seen["off"]["presentation"].digest == seen["off"]["action"][1]


async def test_shadow_digest_mismatch_is_recorded_and_changes_nothing(
    make_kernel: MakeKernel, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A perturbed shadow digest input is recorded as `digest_matches: false`; the run acts on
    today's digest regardless, so its approval and outcome equal `off`."""
    real = features_module.plan_digest_input

    def perturbed(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {**real(*args, **kwargs), "perturbed": "yes"}

    seen = {}
    for name, mode in (("off", OFF), ("shadow", SHADOW)):
        if mode is SHADOW:
            monkeypatch.setattr(features_module, "plan_digest_input", perturbed)
        k = make_kernel(features=mode)
        with deterministic_ids():
            run = await _start(k)
            pres = await k.coordinator.pending_approval(TENANT, run.run_id)
            compiled = await _of(k, run.run_id, RunEventType.IR_PLAN_COMPILED)
            run = await _approve(k, run.run_id)
        (outcome,) = await _of(k, run.run_id, RunEventType.OUTCOME_REPORTED)
        seen[name] = {
            "compare": (run.state, run.reason_code, pres, outcome.payload["status"]),
            "compiled": [c.payload for c in compiled],
            "stream": _without_ir(await _types(k, run.run_id)),
        }
        await _reset(k.store)
    off, shadow = seen["off"], seen["shadow"]

    (compiled,) = shadow["compiled"]
    assert compiled["digest_matches"] is False
    assert compiled["plan_digest"] != off["compare"][2].digest
    assert shadow["compare"] == off["compare"]
    assert shadow["stream"] == off["stream"]
    assert off["compare"][0] is RunState.SUCCEEDED


# -- off and on --------------------------------------------------------------------------
async def test_off_ignores_the_task_kind(make_kernel: MakeKernel) -> None:
    k = make_kernel(features=OFF)
    run = await _start(k)
    await _approve(k, run.run_id)
    stored = await k.store.get_run(TENANT, run.run_id)
    assert (stored.task_id, stored.task_version) == (None, None)
    assert not IR_EVENTS & set(await _types(k, run.run_id))
    assert await k.store.list_steps(TENANT, run.run_id) == []


def test_execution_ir_on_refused_until_implemented() -> None:
    with pytest.raises(KernelError) as caught:
        RunCoordinator(
            store=InMemoryRunStore(),
            registry=PluginRegistry({}),
            connections=ConnectionCatalog([]),
            policy=DefaultPolicy(),
            driver=NotesDriver(texts=[]),
            features=Features(execution_ir=FeatureMode.ON),
        )
    assert caught.value.code is ErrorCode.STARTUP_REJECTED
    assert "not available yet" in str(caught.value)
