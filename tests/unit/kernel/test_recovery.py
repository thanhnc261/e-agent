"""Restart and crash-boundary recovery (MVP design §9 crash/retry rules)."""

from collections.abc import Callable
from typing import Any

import pytest
from e_agent.contracts.action import ActionState
from e_agent.contracts.approval import ApprovalDecision
from e_agent.contracts.events import RunEventType
from e_agent.contracts.features import FeatureMode, Features
from e_agent.contracts.run import ReasonCode, RunState
from e_agent.contracts.task import AcceptanceSpec, RequiredEffect
from e_agent.kernel.coordinator import RunCoordinator
from e_agent.kernel.policy import DefaultPolicy

from .conftest import (
    CREATE,
    NOTE_INPUT,
    NOTES_TASK,
    PLAN_BUDGETS,
    TENANT,
    Kernel,
    NotesDriver,
    NotesPlanDriver,
    run_resume_work,
)

pytestmark = pytest.mark.asyncio
MakeKernel = Callable[..., Kernel]


class Crash(BaseException):
    """Simulates the process dying (not an Exception, so nothing catches it)."""


def restart(k: Kernel, features: Features | None = None) -> RunCoordinator:
    """A new process: same durable store, fresh coordinator and driver instances."""
    return RunCoordinator(
        store=k.store,
        registry=k.coordinator._registry,
        connections=k.connections,
        policy=DefaultPolicy(),
        driver=NotesDriver(texts=[]),
        clock=k.clock,
        features=features,
    )


async def _approve(coordinator: RunCoordinator, k: Kernel, run_id: str):  # type: ignore[no-untyped-def]
    pres = await coordinator.pending_approval(TENANT, run_id)
    return await coordinator.decide(
        actor=k.approver,
        run_id=run_id,
        action_id=pres.action_id,
        action_digest=pres.digest,
        expected_run_revision=pres.run_revision,
        decision=ApprovalDecision.APPROVED,
    )


async def test_waiting_approval_survives_restart(make_kernel: MakeKernel) -> None:
    k = make_kernel()
    run = await k.coordinator.start_run(k.requester, "x", k.scope)
    fresh = restart(k)
    await fresh.recover()
    run = await _approve(fresh, k, run.run_id)
    assert run.state is RunState.SUCCEEDED
    assert k.backend.create_calls == 1


async def test_crash_during_provider_call_becomes_unknown(make_kernel: MakeKernel) -> None:
    k = make_kernel()
    run = await k.coordinator.start_run(k.requester, "x", k.scope)
    original = k.backend.execute

    async def commit_then_die(*args: Any) -> Any:
        await original(*args)
        raise Crash

    k.backend.execute = commit_then_die  # type: ignore[method-assign]
    with pytest.raises(Crash):
        await _approve(k.coordinator, k, run.run_id)
    k.backend.execute = original  # type: ignore[method-assign]
    fresh = restart(k)
    [recovered] = await fresh.recover()
    assert recovered.state is RunState.NEEDS_RECONCILIATION
    run = await fresh.reconcile(k.approver, run.run_id)
    assert run.state is RunState.SUCCEEDED
    assert k.backend.create_calls == 1, "recovery never re-sends a write"


async def test_crash_after_reservation_before_dispatch_blocks(make_kernel: MakeKernel) -> None:
    k = make_kernel()
    run = await k.coordinator.start_run(k.requester, "x", k.scope)
    original = k.store.put_action

    async def die_on_dispatching(action, expected, events):  # type: ignore[no-untyped-def]
        if action.state is ActionState.DISPATCHING:
            raise Crash
        return await original(action, expected, events)

    k.store.put_action = die_on_dispatching  # type: ignore[method-assign]
    with pytest.raises(Crash):
        await _approve(k.coordinator, k, run.run_id)
    k.store.put_action = original  # type: ignore[method-assign]
    [recovered] = await restart(k).recover()
    assert recovered.state is RunState.FAILED
    assert k.backend.create_calls == 0
    states = [a.state for a in await k.store.list_actions(TENANT, run.run_id)]
    assert states == [ActionState.BLOCKED]


async def test_crash_before_receipt_persisted_reconciles_by_operation(
    make_kernel: MakeKernel,
) -> None:
    k = make_kernel()
    run = await k.coordinator.start_run(k.requester, "x", k.scope)
    original = k.store.record_receipt

    async def die(*args: Any) -> Any:
        raise Crash

    k.store.record_receipt = die  # type: ignore[method-assign]
    with pytest.raises(Crash):
        await _approve(k.coordinator, k, run.run_id)
    k.store.record_receipt = original  # type: ignore[method-assign]
    assert k.backend.create_calls == 1  # the provider committed
    fresh = restart(k)
    await fresh.recover()
    run = await fresh.reconcile(k.approver, run.run_id)
    assert run.state is RunState.SUCCEEDED
    assert k.backend.create_calls == 1


async def test_crash_during_driver_turn_fails_without_effects(make_kernel: MakeKernel) -> None:
    k = make_kernel()

    async def die(*args: Any) -> Any:
        raise Crash

    k.backend.read = die  # type: ignore[method-assign]
    with pytest.raises(Crash):
        await k.coordinator.start_run(k.requester, "x", k.scope)
    [recovered] = await restart(k).recover()
    assert recovered.state is RunState.FAILED
    assert k.backend.create_calls == 0


async def _crash_two_runs(k: Kernel) -> None:
    async def die(*args: Any) -> Any:
        raise Crash

    k.backend.read = die  # type: ignore[method-assign]
    for _ in range(2):
        with pytest.raises(Crash):
            await k.coordinator.start_run(k.requester, "x", k.scope)


async def test_one_failing_run_does_not_stop_recovery_of_the_others(
    make_kernel: MakeKernel, caplog: pytest.LogCaptureFixture
) -> None:
    k = make_kernel()
    await _crash_two_runs(k)
    first, second = (r.run_id for r in await k.store.list_unfinished_runs())
    fresh = restart(k)
    real = fresh._recover_run

    async def flaky(run: Any) -> Any:
        if run.run_id == first:
            raise RuntimeError("corrupt continuation")
        return await real(run)

    fresh._recover_run = flaky  # type: ignore[method-assign]
    with caplog.at_level("WARNING"):
        recovered = await fresh.recover()
    assert [r.run_id for r in recovered] == [second]
    assert recovered[0].state is RunState.FAILED
    assert (await k.store.get_run(TENANT, first)).state is RunState.RUNNING
    [record] = [r for r in caplog.records if "skipped run" in r.getMessage()]
    assert first in record.getMessage() and record.exc_info is not None


async def test_cancellation_is_not_swallowed_by_the_per_run_guard(make_kernel: MakeKernel) -> None:
    import asyncio

    k = make_kernel()
    await _crash_two_runs(k)
    fresh = restart(k)

    async def cancelled(run: Any) -> Any:
        raise asyncio.CancelledError

    fresh._recover_run = cancelled  # type: ignore[method-assign]
    with pytest.raises(asyncio.CancelledError):
        await fresh.recover()


@pytest.mark.parametrize("boundary", ["record_receipt", "record_outcome"])
async def test_recovery_uses_durable_effect_when_run_state_lags(
    make_kernel: MakeKernel,
    boundary: str,
) -> None:
    k = make_kernel()
    run = await k.coordinator.start_run(k.requester, "x", k.scope)
    original = getattr(k.store, boundary)

    async def commit_then_die(*args: Any) -> Any:
        await original(*args)
        raise Crash

    setattr(k.store, boundary, commit_then_die)
    with pytest.raises(Crash):
        await _approve(k.coordinator, k, run.run_id)
    setattr(k.store, boundary, original)
    [recovered] = await restart(k).recover()
    assert recovered.state is RunState.SUCCEEDED
    assert k.backend.create_calls == 1
    assert [a.state for a in await k.store.list_actions(TENANT, run.run_id)] == [
        ActionState.VERIFIED
    ]


async def test_verified_earlier_answer_cannot_hide_unknown_write(make_kernel: MakeKernel) -> None:
    from e_agent.contracts.common import new_id

    k = make_kernel()
    k.backend.fail_mode = "timeout"
    run = await k.coordinator.start_run(k.requester, "x", k.scope)
    run = await _approve(k.coordinator, k, run.run_id)
    assert run.state is RunState.NEEDS_RECONCILIATION
    [write] = await k.store.list_actions(TENANT, run.run_id)
    answer = write.model_copy(
        update={
            "action_id": new_id("act"),
            "contract_id": "notes.answer.v1",
            "state": ActionState.VERIFIED,
            "revision": 1,
        }
    )
    await k.store.put_action(answer, None, [])
    recovered = await restart(k).recover_run(TENANT, run.run_id)
    assert recovered.state is RunState.NEEDS_RECONCILIATION
    assert k.backend.create_calls == 1


class _AskDriver:
    driver_id = "ask-driver"

    async def advance(self, ctx: Any, step_input: Any) -> Any:
        from e_agent.sdk.ports import AskClarification

        return AskClarification(question="which note?")


async def test_waiting_input_run_with_failed_answer_verification_recovers_to_failed(
    make_kernel: MakeKernel,
) -> None:
    """`_recover_run` fails a run whose latest action is VERIFICATION_FAILED even while the
    run waits for input (an answer failed verification with repairs left, then the driver
    asked a question). That WAITING_INPUT->FAILED pair must stay in the transition table,
    otherwise one such run raises CONFLICT and aborts startup recovery."""
    from e_agent.contracts.common import new_id
    from e_agent.contracts.events import RunEventType

    k = make_kernel()
    template_run = await k.coordinator.start_run(k.requester, "x", k.scope)
    [template] = await k.store.list_actions(TENANT, template_run.run_id)
    k.coordinator._driver = _AskDriver()  # type: ignore[assignment]
    run = await k.coordinator.start_run(k.requester, "y", k.scope)
    assert run.state is RunState.WAITING_INPUT
    failed_answer = template.model_copy(
        update={
            "action_id": new_id("act"),
            "run_id": run.run_id,
            "state": ActionState.VERIFICATION_FAILED,
            "revision": 1,
        }
    )
    await k.store.put_action(
        failed_answer,
        None,
        [(RunEventType.PROPOSAL_CREATED, {}, failed_answer.action_id)],
    )
    recovered = await restart(k).recover_run(TENANT, run.run_id)
    assert recovered.state is RunState.FAILED
    assert recovered.reason == "outcome verification failed"


# -- execution IR `on`: acceptance at run end (Task 2c.6 fix round 1, ADR 0028) ----------
ON = Features(execution_ir=FeatureMode.ON)
# The notes stand-in for a positive-shortage answer: a verified outcome that does not meet
# the definition's spec (two verified notes required, one written).
UNMET_TASK = NOTES_TASK.model_copy(
    update={
        "acceptance": AcceptanceSpec(
            required_effects=(RequiredEffect(contract_id=CREATE.contract_id, min_verified=2),)
        )
    }
)


async def _crash_after(k: Kernel, run_id: str, boundary: str) -> None:
    original = getattr(k.store, boundary)

    async def commit_then_die(*args: Any) -> Any:
        await original(*args)
        raise Crash

    setattr(k.store, boundary, commit_then_die)
    with pytest.raises(Crash):
        await _approve(k.coordinator, k, run_id)
    setattr(k.store, boundary, original)


@pytest.mark.parametrize("boundary", ["record_receipt", "record_outcome"])
@pytest.mark.parametrize(
    ("task", "state", "code"),
    [
        (UNMET_TASK, RunState.FAILED, ReasonCode.ACCEPTANCE_UNMET),
        (NOTES_TASK, RunState.SUCCEEDED, ReasonCode.VERIFIED),
    ],
)
async def test_recovery_checks_acceptance_before_success(
    make_kernel: MakeKernel, boundary: str, task: Any, state: RunState, code: ReasonCode
) -> None:
    """A run recovered after its outcome (or receipt) was stored reaches the live path's
    acceptance decision: SUCCEEDED when the spec is met, ACCEPTANCE_UNMET when it is not."""
    k = make_kernel(features=ON, task=task)
    run = await k.coordinator.start_run(k.requester, "x", k.scope, task_kind=task.task_id)
    await _crash_after(k, run.run_id, boundary)
    [recovered] = await restart(k, ON).recover()
    assert (recovered.state, recovered.reason_code) == (state, code)
    findings = [
        f["rule_id"]
        for e in await k.store.list_events(TENANT, run.run_id)
        if e.type is RunEventType.VALIDATION_COMPLETED
        for f in e.payload["findings"]
    ]
    # The unmet run records the kernel's acceptance finding on recovery too (Codex C-2).
    assert ("KERNEL-ACCEPTANCE" in findings) is (code is ReasonCode.ACCEPTANCE_UNMET)
    assert k.backend.create_calls == 1
    assert [a.state for a in await k.store.list_actions(TENANT, run.run_id)] == [
        ActionState.VERIFIED
    ]


@pytest.mark.parametrize("boundary", ["record_receipt", "record_outcome"])
async def test_recovery_success_unchanged_in_off(make_kernel: MakeKernel, boundary: str) -> None:
    """`off` ignores acceptance on recovery, as today, even for a definition it would fail."""
    k = make_kernel(task=UNMET_TASK)
    run = await k.coordinator.start_run(k.requester, "x", k.scope, task_kind=UNMET_TASK.task_id)
    await _crash_after(k, run.run_id, boundary)
    [recovered] = await restart(k).recover()
    assert (recovered.state, recovered.reason_code) == (RunState.SUCCEEDED, ReasonCode.VERIFIED)
    assert recovered.reason == "outcome verified"
    assert k.backend.create_calls == 1


# -- execution IR `on`: a multi-step plan resumes after a crash (Task 2c.8, ADR 0025) -----
PLAN_CRASH_POINTS = ["record_receipt", "record_outcome", "_after_step_verified", "_start_step"]


def _plan_kernel(make_kernel: MakeKernel) -> Kernel:
    return make_kernel(
        features=ON,
        budgets=PLAN_BUDGETS,
        driver=NotesPlanDriver(),
        input_schemas={"c": NOTE_INPUT, "p": NOTE_INPUT},
    )


def _restart_plan(k: Kernel, features: Features = ON, policy: Any = None) -> RunCoordinator:
    """A new process for a plan run: same store and registry, fresh coordinator."""
    return RunCoordinator(
        store=k.store,
        registry=k.coordinator._registry,
        connections=k.connections,
        policy=policy or DefaultPolicy(),
        driver=NotesDriver(texts=[]),
        clock=k.clock,
        features=features,
    )


async def _crash_between_steps(k: Kernel, point: str) -> str:
    """Start and approve the two-step notes plan; the process dies at ``point``, after
    step 1's provider call committed and before step 2 exists. Returns the run id."""
    run = await k.coordinator.start_run(
        k.requester, "write standup note", k.scope, task_kind=NOTES_TASK.task_id
    )
    if point.startswith("_"):

        async def die(*_a: Any) -> Any:
            raise Crash

        setattr(k.coordinator, point, die)
    else:
        original = getattr(k.store, point)

        async def commit_then_die(*args: Any) -> Any:
            await original(*args)
            setattr(k.store, point, original)
            raise Crash

        setattr(k.store, point, commit_then_die)
    with pytest.raises(Crash):
        await _approve(k.coordinator, k, run.run_id)
    assert [a.step_index for a in await k.store.list_actions(TENANT, run.run_id)] == [0]
    return run.run_id


def _plan_actions(actions: list[Any]) -> list[Any]:
    return sorted(actions, key=lambda a: a.step_index)


@pytest.mark.parametrize("point", PLAN_CRASH_POINTS)
async def test_recovery_resumes_plan_without_replaying_committed_steps(
    make_kernel: MakeKernel, point: str
) -> None:
    """The process dies between the steps (after step 1's commit, its read-back, the
    ``VERIFYING -> RUNNING`` pair, or inside step 2's start). A restart's recovery verifies
    step 1 when its outcome was not stored and queues the resume; the resume claim runs
    step 2 after its revalidation. Step 1 is never sent again (ENG-TRUST-5, §6.4.6)."""
    k = _plan_kernel(make_kernel)
    run_id = await _crash_between_steps(k, point)
    assert k.backend.create_calls == 1
    coordinator = _restart_plan(k)
    [queued] = await coordinator.recover()
    assert queued.state in {RunState.VERIFYING, RunState.RUNNING}
    recovered = await run_resume_work(k.store, coordinator)
    assert (recovered.state, recovered.reason_code) == (RunState.SUCCEEDED, ReasonCode.VERIFIED)
    first, second = _plan_actions(await k.store.list_actions(TENANT, run_id))
    assert (first.state, second.state) == (ActionState.VERIFIED, ActionState.VERIFIED)
    assert k.backend.create_calls == 2
    events = await k.store.list_events(TENANT, run_id)
    reserved = [e.action_id for e in events if e.type is RunEventType.ACTION_RESERVED]
    assert reserved == [first.action_id, second.action_id]
    dispatched = [e.action_id for e in events if e.type is RunEventType.ACTION_DISPATCHING]
    assert dispatched == [first.action_id, second.action_id]
    # Step 2's parent is step 1's verified key, read back before the crash or on recovery.
    (lineage,) = [e for e in events if e.type is RunEventType.IR_LINEAGE_RESOLVED]
    assert second.arguments["parent"] == first.logical_operation_id
    assert [v["value"] for v in lineage.payload["values"]] == [first.logical_operation_id]


RESUME_GUARDS = [
    "approval-expired",
    "step-changed",
    "rules-changed",
    "policy-changed",
    "fact-changed",
    "validation-blocks",
    "no-read-back",
]


@pytest.mark.parametrize("guard", RESUME_GUARDS)
async def test_resumed_step_passes_every_guard_before_reserving(
    make_kernel: MakeKernel, guard: str
) -> None:
    """A resumed step passes every guard the live path applies before its reservation: the
    approval's lifetime, the stored step against its approved input, rule, policy and fact
    staleness, domain validation of its resolved values, and lineage only from the verified
    read-back. Each one stops the plan before step 2 reserves; step 1 stays verified."""
    from e_agent.contracts.outcome import OutcomeReport
    from e_agent.contracts.validation import Finding, ValidationResult, ValidationStatus

    k = _plan_kernel(make_kernel)
    if guard == "no-read-back":
        verify = k.verifier.verify

        async def no_values(*args: Any) -> OutcomeReport:
            report = await verify(*args)
            return report.model_copy(update={"verified_values": None})

        k.verifier.verify = no_values  # type: ignore[method-assign]
    run_id = await _crash_between_steps(k, "record_outcome")
    policy: Any = None
    if guard == "approval-expired":
        k.clock.advance(minutes=30)  # past the default 15-minute approval
    elif guard == "step-changed":
        get_plan = k.store.get_plan

        async def tampered(tenant_id: str, plan_id: str) -> Any:
            plan = await get_plan(tenant_id, plan_id)
            step = plan.steps[1]
            changed = {**step.proposal.arguments, "text": "rewritten"}
            proposal = step.proposal.model_copy(update={"arguments": changed})
            steps = (plan.steps[0], step.model_copy(update={"proposal": proposal}))
            return plan.model_copy(update={"steps": steps})

        k.store.get_plan = tampered
    elif guard == "rules-changed":
        k.validator.bundle = "notes@2"
    elif guard == "policy-changed":
        import dataclasses

        class Changed(DefaultPolicy):
            def evaluate(self, ctx: Any, descriptor: Any, connection_id: str) -> Any:
                decision = super().evaluate(ctx, descriptor, connection_id)
                return dataclasses.replace(decision, policy_version="changed")

        policy = Changed()
    elif guard == "fact-changed":
        k.backend.revision += 1
    elif guard == "validation-blocks":
        validate = k.validator.validate

        async def block_resolved(ctx: Any, item: Any) -> ValidationResult:
            if not isinstance(item.proposal.arguments.get("parent"), str):
                return await validate(ctx, item)
            finding = Finding(
                rule_id="NOTE-002", rule_version="1", status=ValidationStatus.FAIL, message="p"
            )
            return ValidationResult(
                status=ValidationStatus.FAIL,
                findings=(finding,),
                rule_bundle_version="notes@1",
                validator_id="notes-rules",
            )

        k.validator.validate = block_resolved  # type: ignore[method-assign]
    coordinator = _restart_plan(k, policy=policy)
    await coordinator.recover()
    recovered = await run_resume_work(k.store, coordinator)  # the guards run under the claim
    expected = ReasonCode.PLAN_LINEAGE_REJECTED if guard == "no-read-back" else ReasonCode.STALE
    assert (recovered.state, recovered.reason_code) == (RunState.FAILED, expected)
    actions = _plan_actions(await k.store.list_actions(TENANT, run_id))
    assert actions[0].state is ActionState.VERIFIED
    if guard in {"step-changed", "no-read-back"}:  # stopped before step 2's action exists
        assert len(actions) == 1
    else:
        assert actions[1].state is ActionState.BLOCKED
    events = await k.store.list_events(TENANT, run_id)
    reserved = [e.action_id for e in events if e.type is RunEventType.ACTION_RESERVED]
    assert reserved == [actions[0].action_id]
    assert k.backend.create_calls == 1


@pytest.mark.parametrize("point", ["record_receipt", "record_outcome"])
async def test_plan_never_resumes_outside_on(make_kernel: MakeKernel, point: str) -> None:
    """A process restarted with ``execution_ir`` no longer ``on`` cannot run the rest of a
    plan on today's path (no fallback after the first reservation): the run fails
    ``INTERRUPTED`` and nothing is sent, whether recovery re-verifies step 1
    (`_after_step_verified`) or finds it verified (`_resume_plan`, then `_succeed`)."""
    k = _plan_kernel(make_kernel)
    run_id = await _crash_between_steps(k, point)
    [recovered] = await _restart_plan(k, features=Features()).recover()
    assert (recovered.state, recovered.reason_code) == (RunState.FAILED, ReasonCode.INTERRUPTED)
    assert [a.state for a in await k.store.list_actions(TENANT, run_id)] == [ActionState.VERIFIED]
    assert k.backend.create_calls == 1


# -- the resume is fenced work, never a write inside recovery (ADR 0025 amendment, R-1) ----
@pytest.mark.parametrize("point", PLAN_CRASH_POINTS)
async def test_recovery_only_enqueues_one_resume(make_kernel: MakeKernel, point: str) -> None:
    """Startup recovery of a resumable plan makes no provider call and no reservation: it
    enqueues one ``resume`` item, keyed by the verified step. A second process recovering
    the same ledger skips the run (`has_pending_work`), so the item is queued once."""
    k = _plan_kernel(make_kernel)
    run_id = await _crash_between_steps(k, point)
    reserved_before = [
        e
        for e in await k.store.list_events(TENANT, run_id)
        if e.type is RunEventType.ACTION_RESERVED
    ]
    [queued] = await _restart_plan(k).recover()
    assert queued.state in {RunState.VERIFYING, RunState.RUNNING}
    assert k.backend.create_calls == 1
    events = await k.store.list_events(TENANT, run_id)
    assert [e for e in events if e.type is RunEventType.ACTION_RESERVED] == reserved_before
    assert len(await k.store.list_actions(TENANT, run_id)) == 1
    assert await _restart_plan(k).recover() == []  # the other process: pending work, skipped
    claim = await k.store.claim_work("probe")
    assert claim is not None and claim.kind == "resume" and claim.run_id == run_id
    (first,) = await k.store.list_actions(TENANT, run_id)
    assert claim.payload == {"action_id": first.action_id}
    async with k.store.work_scope(claim):
        await k.store.finish_work(claim)
    assert await k.store.claim_work("probe") is None  # exactly one item was queued
    assert k.backend.create_calls == 1


async def test_resume_claim_on_a_finished_or_planless_run_does_nothing(
    make_kernel: MakeKernel,
) -> None:
    """A resume claim re-checks the run under the claim: a finished plan run, or a run in
    VERIFYING without plan state, is left as it is and nothing is sent."""
    k = _plan_kernel(make_kernel)
    run = await k.coordinator.start_run(
        k.requester, "write standup note", k.scope, task_kind=NOTES_TASK.task_id
    )
    done = await _approve(k.coordinator, k, run.run_id)
    assert done.state is RunState.SUCCEEDED
    payload = {"action_id": "act_any"}
    await k.store.enqueue_work(TENANT, done.run_id, "resume", payload, "resume-finished")
    again = await run_resume_work(k.store, _restart_plan(k))
    assert (again.state, again.revision) == (done.state, done.revision)

    single = make_kernel(features=ON)  # a 1-step run left VERIFYING: no plan state
    single.verifier.verify = _unavailable  # type: ignore[method-assign]
    one = await single.coordinator.start_run(single.requester, "x", single.scope)
    one = await _approve(single.coordinator, single, one.run_id)
    assert one.state is RunState.VERIFYING
    await single.store.enqueue_work(TENANT, one.run_id, "resume", payload, "resume-planless")
    left = await run_resume_work(single.store, _restart_plan(single))
    assert (left.state, left.revision) == (one.state, one.revision)
    assert (k.backend.create_calls, single.backend.create_calls) == (2, 1)


async def _unavailable(*_a: Any) -> Any:
    raise RuntimeError("verifier down")


async def test_stray_later_step_action_never_lets_the_plan_resume(make_kernel: MakeKernel) -> None:
    """The contiguity guard of `_resume_plan` (2c.8 review R-2): the kernel never writes a
    later step's action without its ``proposal.created``, so only a ledger whose action
    table and event log disagree reaches it. Such a plan is not resumed: no resume is
    queued, nothing is sent, and the run fails INTERRUPTED."""
    from e_agent.contracts.common import new_id

    k = _plan_kernel(make_kernel)
    run_id = await _crash_between_steps(k, "record_outcome")
    (first,) = await k.store.list_actions(TENANT, run_id)
    stray = first.model_copy(
        update={
            "action_id": new_id("act"),
            "step_index": 1,
            "state": ActionState.BLOCKED,
            "revision": 1,
            "logical_operation_id": new_id("op"),
        }
    )
    await k.store.put_action(stray, None, [])  # no proposal.created: `latest` stays step 1
    [recovered] = await _restart_plan(k).recover()
    assert (recovered.state, recovered.reason_code) == (RunState.FAILED, ReasonCode.INTERRUPTED)
    assert await k.store.claim_work("probe") is None
    assert k.backend.create_calls == 1


@pytest.mark.parametrize("boundary", ["put_action", "reserve_operation"])
async def test_crash_after_a_later_step_exists_ends_interrupted_before_it_reserved(
    make_kernel: MakeKernel, boundary: str
) -> None:
    """The process dies inside step 2's start, after its action was stored (PROPOSED) or
    revalidated (VALIDATED) and before it reserved (2c.8 review R-3). Recovery fails the run
    closed, INTERRUPTED with a plan-specific reason, and sends nothing; the evidence lists
    step 2 as unstarted, since no reservation or provider call was made for it."""
    from e_agent.kernel.evidence import build_evidence

    k = _plan_kernel(make_kernel)
    run = await k.coordinator.start_run(
        k.requester, "write standup note", k.scope, task_kind=NOTES_TASK.task_id
    )
    original = getattr(k.store, boundary)

    async def die_at_step_two(action: Any, expected: Any, events: Any) -> Any:
        if action.step_index != 1:
            return await original(action, expected, events)
        if boundary == "put_action":
            await original(action, expected, events)  # stored PROPOSED, then the process dies
        raise Crash

    setattr(k.store, boundary, die_at_step_two)
    with pytest.raises(Crash):
        await _approve(k.coordinator, k, run.run_id)
    setattr(k.store, boundary, original)
    [recovered] = await _restart_plan(k).recover()
    assert (recovered.state, recovered.reason_code) == (RunState.FAILED, ReasonCode.INTERRUPTED)
    assert recovered.reason == "interrupted before plan step 2 reserved"
    first, second = _plan_actions(await k.store.list_actions(TENANT, run.run_id))
    assert first.state is ActionState.VERIFIED
    assert second.state is (
        ActionState.PROPOSED if boundary == "put_action" else ActionState.VALIDATED
    )
    assert k.backend.create_calls == 1
    assert await k.store.claim_work("probe") is None
    bundle = await build_evidence(
        k.store, TENANT, run.run_id, environment="fixture", versions={}, features=ON
    )
    assert [s["status"] for s in bundle["plan"]["steps"]] == ["verified", "unstarted"]


async def test_racing_recoveries_queue_one_resume(make_kernel: MakeKernel) -> None:
    """Two processes recover the same ledger and the second one passes `has_pending_work`
    before the first one's enqueue is visible (2c.8 review R2-2): the resume item is keyed
    by the verified step, so exactly one item exists and only one resume can run."""
    k = _plan_kernel(make_kernel)
    run_id = await _crash_between_steps(k, "record_outcome")
    [first_pass] = await _restart_plan(k).recover()
    assert first_pass.state is RunState.VERIFYING

    async def not_visible_yet(*_a: Any) -> bool:
        return False

    k.store.has_pending_work = not_visible_yet  # the second process races the first
    [second_pass] = await _restart_plan(k).recover()
    assert second_pass.state is RunState.VERIFYING
    claim = await k.store.claim_work("probe")
    assert claim is not None and claim.kind == "resume" and claim.run_id == run_id
    async with k.store.work_scope(claim):
        await k.store.finish_work(claim)
    assert await k.store.claim_work("probe") is None  # one item, not two
    assert k.backend.create_calls == 1
