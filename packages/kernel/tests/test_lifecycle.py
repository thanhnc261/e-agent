"""Kernel safety and lifecycle behaviour with a non-ERP domain (MVP design §7-9, §13)."""

from collections.abc import Callable

import pytest
from e_agent.contracts.action import ActionState
from e_agent.contracts.approval import ApprovalDecision
from e_agent.contracts.connection import ConnectionDescriptor, ConnectionOwnership
from e_agent.contracts.context import Budgets
from e_agent.contracts.events import RunEventType
from e_agent.contracts.run import ReasonCode, RunState
from e_agent.kernel.errors import ErrorCode, KernelError

from .conftest import CONN, TENANT, Kernel, principal

pytestmark = pytest.mark.asyncio
MakeKernel = Callable[..., Kernel]


async def _start(k: Kernel, task: str = "write standup note"):
    return await k.coordinator.start_run(k.requester, task, k.scope)


async def _approve(k: Kernel, run_id: str, decision=ApprovalDecision.APPROVED):
    pres = await k.coordinator.pending_approval(TENANT, run_id)
    return await k.coordinator.decide(
        actor=k.approver,
        run_id=run_id,
        action_id=pres.action_id,
        action_digest=pres.digest,
        expected_run_revision=pres.run_revision,
        decision=decision,
    )


async def _types(k: Kernel, run_id: str) -> list[RunEventType]:
    return [e.type for e in await k.store.list_events(TENANT, run_id)]


async def test_happy_path_requires_approval_then_verifies(make_kernel: MakeKernel) -> None:
    k = make_kernel()
    run = await _start(k)
    assert run.state is RunState.WAITING_APPROVAL
    assert k.backend.create_calls == 0, "nothing executes before approval"
    pres = await k.coordinator.pending_approval(TENANT, run.run_id)
    assert pres.digest.startswith("jcs-sha256-v1:")
    assert pres.credential_subject == f"{CONN}@1/svc"
    assert [f.path for f in pres.material_fields] == ["text"]
    run = await _approve(k, run.run_id)
    assert run.state is RunState.SUCCEEDED
    assert k.backend.create_calls == 1
    types = await _types(k, run.run_id)
    assert types.index(RunEventType.ACTION_RESERVED) < types.index(RunEventType.ACTION_DISPATCHING)
    assert RunEventType.OUTCOME_REPORTED in types
    actions = await k.store.list_actions(TENANT, run.run_id)
    assert [a.state for a in actions] == [ActionState.VERIFIED]


async def test_events_are_sequenced_without_gaps(make_kernel: MakeKernel) -> None:
    k = make_kernel()
    run = await _approve(k, (await _start(k)).run_id)
    seqs = [e.sequence for e in await k.store.list_events(TENANT, run.run_id)]
    assert seqs == list(range(1, len(seqs) + 1))


async def test_requester_cannot_approve(make_kernel: MakeKernel) -> None:
    k = make_kernel()
    run = await _start(k)
    pres = await k.coordinator.pending_approval(TENANT, run.run_id)
    with pytest.raises(KernelError) as err:
        await k.coordinator.decide(
            actor=k.requester,
            run_id=run.run_id,
            action_id=pres.action_id,
            action_digest=pres.digest,
            expected_run_revision=pres.run_revision,
            decision=ApprovalDecision.APPROVED,
        )
    assert err.value.code is ErrorCode.FORBIDDEN


async def test_wrong_digest_is_stale(make_kernel: MakeKernel) -> None:
    k = make_kernel()
    run = await _start(k)
    pres = await k.coordinator.pending_approval(TENANT, run.run_id)
    with pytest.raises(KernelError) as err:
        await k.coordinator.decide(
            actor=k.approver,
            run_id=run.run_id,
            action_id=pres.action_id,
            action_digest="jcs-sha256-v1:" + "0" * 64,
            expected_run_revision=pres.run_revision,
            decision=ApprovalDecision.APPROVED,
        )
    assert err.value.code is ErrorCode.APPROVAL_STALE
    assert k.backend.create_calls == 0


async def test_outdated_run_revision_conflicts(make_kernel: MakeKernel) -> None:
    k = make_kernel()
    run = await _start(k)
    pres = await k.coordinator.pending_approval(TENANT, run.run_id)
    with pytest.raises(KernelError) as err:
        await k.coordinator.decide(
            actor=k.approver,
            run_id=run.run_id,
            action_id=pres.action_id,
            action_digest=pres.digest,
            expected_run_revision=pres.run_revision - 1,
            decision=ApprovalDecision.APPROVED,
        )
    assert err.value.code is ErrorCode.CONFLICT


async def test_expired_approval_blocks_dispatch(make_kernel: MakeKernel) -> None:
    k = make_kernel()
    run = await _start(k)
    k.clock.advance(minutes=16)
    with pytest.raises(KernelError) as err:
        await _approve(k, run.run_id)
    assert err.value.code is ErrorCode.APPROVAL_STALE
    assert (await k.store.get_run(TENANT, run.run_id)).state is RunState.FAILED
    assert k.backend.create_calls == 0


async def test_rejection_never_dispatches(make_kernel: MakeKernel) -> None:
    k = make_kernel()
    run = await _approve(k, (await _start(k)).run_id, ApprovalDecision.REJECTED)
    assert run.state is RunState.FAILED
    assert k.backend.create_calls == 0


async def test_changed_source_after_approval_forces_new_proposal(make_kernel: MakeKernel) -> None:
    k = make_kernel(["first", "second"])
    run = await _start(k)
    first = await k.coordinator.pending_approval(TENANT, run.run_id)
    k.backend.revision += 1  # material fact changes while waiting
    run = await _approve(k, run.run_id)
    assert run.state is RunState.WAITING_APPROVAL, "stale approval must not dispatch"
    assert k.backend.create_calls == 0
    second = await k.coordinator.pending_approval(TENANT, run.run_id)
    assert second.digest != first.digest
    assert (await k.store.get_action(TENANT, first.action_id)).state is ActionState.BLOCKED
    assert run.reason is None and run.reason_code is None, "stale code must not leak"
    assert (await k.store.get_run(TENANT, run.run_id)).reason_code is None
    changed = [
        e
        for e in await k.store.list_events(TENANT, run.run_id)
        if e.type is RunEventType.RUN_STATE_CHANGED
    ]
    assert changed[-1].payload["to"] == "WAITING_APPROVAL"
    assert changed[-1].payload["reason_code"] is None
    assert any(e.payload.get("reason_code") == "stale" for e in changed)
    run = await _approve(k, run.run_id)
    assert run.state is RunState.SUCCEEDED and k.backend.create_calls == 1


async def test_connection_change_after_approval_request_is_stale(make_kernel: MakeKernel) -> None:
    k = make_kernel(["first", "second"])
    run = await _start(k)
    k.connections.update(
        ConnectionDescriptor(
            tenant_id=TENANT,
            connection_id=CONN,
            version=2,
            integration_id="notes-mem",
            ownership=ConnectionOwnership.TENANT_SHARED,
            provider_subject="svc-rotated",
        )
    )
    run = await _approve(k, run.run_id)
    assert run.state is RunState.WAITING_APPROVAL
    assert k.backend.create_calls == 0
    pres = await k.coordinator.pending_approval(TENANT, run.run_id)
    assert pres.credential_subject == f"{CONN}@2/svc-rotated"


async def test_invalid_proposal_is_blocked_then_repaired(make_kernel: MakeKernel) -> None:
    k = make_kernel(["", "fixed text"])
    run = await _start(k)
    assert run.state is RunState.WAITING_APPROVAL
    actions = sorted(await k.store.list_actions(TENANT, run.run_id), key=lambda a: a.revision)
    states = {a.state for a in actions}
    assert ActionState.BLOCKED in states and ActionState.AWAITING_APPROVAL in states
    repaired = next(a for a in actions if a.state is ActionState.AWAITING_APPROVAL)
    assert repaired.supersedes_action_id is not None
    assert repaired.logical_operation_id == actions[0].logical_operation_id
    pres = await k.coordinator.pending_approval(TENANT, run.run_id)
    changed = [f for f in pres.material_fields if f.changed]
    assert [(f.previous_value, f.value) for f in changed] == [("", "fixed text")]


async def test_repair_budget_exhaustion_fails_run(make_kernel: MakeKernel) -> None:
    k = make_kernel(["", "", "", ""], budgets=Budgets(max_validation_repairs=1))
    run = await _start(k)
    assert run.state is RunState.FAILED and run.reason == "validation blocked"


async def test_validator_error_blocks_write(make_kernel: MakeKernel) -> None:
    k = make_kernel(budgets=Budgets(max_validation_repairs=0))
    k.validator.explode = True
    run = await _start(k)
    assert run.state is RunState.FAILED
    assert k.backend.create_calls == 0


async def test_lost_response_goes_unknown_and_reconciles_without_resend(
    make_kernel: MakeKernel,
) -> None:
    k = make_kernel()
    k.backend.fail_mode = "timeout"
    run = await _approve(k, (await _start(k)).run_id)
    assert run.state is RunState.NEEDS_RECONCILIATION
    action = (await k.store.list_actions(TENANT, run.run_id))[0]
    assert action.state is ActionState.UNKNOWN
    run = await k.coordinator.reconcile(k.approver, run.run_id)
    assert run.state is RunState.SUCCEEDED
    assert k.backend.create_calls == 1, "reconciliation must never re-send the write"


async def test_unknown_with_no_effect_stays_unresolved(make_kernel: MakeKernel) -> None:
    k = make_kernel()
    k.backend.fail_mode = "timeout-no-commit"
    run = await _approve(k, (await _start(k)).run_id)
    run = await k.coordinator.reconcile(k.approver, run.run_id)
    assert run.state is RunState.NEEDS_RECONCILIATION
    assert k.backend.create_calls == 1


async def test_known_rejection_is_failed_not_unknown(make_kernel: MakeKernel) -> None:
    k = make_kernel()
    k.backend.fail_mode = "reject"
    run = await _approve(k, (await _start(k)).run_id)
    assert run.state is RunState.FAILED
    assert (await k.store.list_actions(TENANT, run.run_id))[0].state is ActionState.FAILED


async def test_verification_mismatch_never_reports_verified(make_kernel: MakeKernel) -> None:
    k = make_kernel()
    k.verifier.tamper = True
    run = await _approve(k, (await _start(k)).run_id)
    assert run.state is RunState.FAILED
    assert (await k.store.list_actions(TENANT, run.run_id))[0].state is (
        ActionState.VERIFICATION_FAILED
    )


async def test_out_of_scope_connection_is_forbidden(make_kernel: MakeKernel) -> None:
    k = make_kernel()
    with pytest.raises(KernelError) as err:
        await k.coordinator.start_run(k.requester, "x", frozenset())
    assert err.value.code is ErrorCode.FORBIDDEN
    assert k.backend.create_calls == 0


async def test_other_tenant_cannot_use_connection(make_kernel: MakeKernel) -> None:
    k = make_kernel()
    intruder = principal("mallory", {"requester"}, tenant="tenant-b")
    with pytest.raises(KernelError) as err:
        await k.coordinator.start_run(intruder, "x", k.scope)
    assert err.value.code is ErrorCode.FORBIDDEN


async def test_user_delegated_connection_only_for_its_owner(make_kernel: MakeKernel) -> None:
    delegated = ConnectionDescriptor(
        tenant_id=TENANT,
        connection_id=CONN,
        version=1,
        integration_id="notes-mem",
        ownership=ConnectionOwnership.USER_DELEGATED,
        owner_principal="carol",
        provider_subject="carol@notes",
    )
    k = make_kernel(connections=[delegated])
    with pytest.raises(KernelError) as err:
        await _start(k)  # alice requests with carol's connection
    assert err.value.code is ErrorCode.FORBIDDEN
    carol = principal("carol", {"requester"})
    run = await k.coordinator.start_run(carol, "x", k.scope)
    assert run.state is RunState.WAITING_APPROVAL


async def test_cancel_before_dispatch(make_kernel: MakeKernel) -> None:
    k = make_kernel()
    run = await _start(k)
    run = await k.coordinator.cancel(k.requester, run.run_id)
    assert run.state is RunState.CANCELLED
    assert k.backend.create_calls == 0


async def test_write_budget_limits_admitted_writes(make_kernel: MakeKernel) -> None:
    k = make_kernel(budgets=Budgets(max_admitted_writes=0))
    run = await _start(k)
    assert run.state is RunState.FAILED
    assert "budget" in (run.reason or "")


async def test_capability_surface_change_blocks_resume(make_kernel: MakeKernel) -> None:
    """Threat model T17: schemas/bindings changed between proposal and approval."""
    k = make_kernel()
    run = await _start(k)
    assert run.state is RunState.WAITING_APPROVAL
    registry = k.coordinator._registry
    # a plugin was upgraded while the approval was pending
    registry.bindings[0] = registry.bindings[0].model_copy(update={"plugin_version": "9.9.9"})
    with pytest.raises(KernelError) as err:
        await _approve(k, run.run_id)
    assert err.value.code is ErrorCode.APPROVAL_STALE
    run = await k.coordinator.get_run(TENANT, run.run_id)
    assert run.state is RunState.FAILED and run.reason == "capability surface changed"
    assert k.backend.create_calls == 0


async def test_policy_version_change_requires_new_approval(make_kernel: MakeKernel) -> None:
    k = make_kernel()
    run = await _start(k)
    k.coordinator._policy.version = "policy-mvp-2"
    await _approve(k, run.run_id)
    assert k.backend.create_calls == 0
    assert (await k.store.list_actions(TENANT, run.run_id))[0].state is ActionState.BLOCKED


async def test_validator_unavailable_at_dispatch_blocks_write(make_kernel: MakeKernel) -> None:
    k = make_kernel()
    run = await _start(k)
    k.validator.explode = True
    await _approve(k, run.run_id)
    assert k.backend.create_calls == 0


async def test_unversioned_material_facts_require_new_approval(make_kernel: MakeKernel) -> None:
    from dataclasses import replace

    k = make_kernel()
    original = k.backend.read

    async def unversioned(*args):
        observation = await original(*args)
        return replace(
            observation, evidence=observation.evidence.model_copy(update={"revision": None})
        )

    k.backend.read = unversioned
    run = await _start(k)
    pres = await k.coordinator.pending_approval(TENANT, run.run_id)
    assert pres.canonical_proposal["evidence"][0]["fact_digest"].startswith("facts-json-v1:")
    k.backend.notes["preexisting"] = {"key": "preexisting", "text": "changed facts"}
    await _approve(k, run.run_id)
    assert k.backend.create_calls == 0


async def test_cancel_interrupts_inference_before_any_effect(make_kernel: MakeKernel) -> None:
    import asyncio

    k = make_kernel()
    entered = asyncio.Event()

    async def blocked(ctx, step_input):
        entered.set()
        await asyncio.Event().wait()

    k.driver.advance = blocked
    work = asyncio.create_task(_start(k))
    await asyncio.wait_for(entered.wait(), 1)
    [run] = await k.store.list_unfinished_runs()
    cancelled = await k.coordinator.cancel(k.requester, run.run_id)
    assert cancelled.state is RunState.CANCELLED
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(work, 1)
    assert k.backend.create_calls == 0


async def test_model_deadline_stops_without_dispatch(make_kernel: MakeKernel) -> None:
    import asyncio

    k = make_kernel(budgets=Budgets(model_timeout_seconds=1))

    async def blocked(ctx, step_input):
        await asyncio.Event().wait()

    k.driver.advance = blocked
    run = await _start(k)
    assert run.state is RunState.FAILED
    assert "deadline" in run.reason
    assert k.backend.create_calls == 0


async def test_credential_rotation_invalidates_approval_without_connection_edit(
    make_kernel: MakeKernel,
) -> None:
    k = make_kernel()

    class CredentialMetadata:
        revision = "credential-1"

        async def version(self, ctx, connection_id):
            return self.revision

    credentials = CredentialMetadata()
    k.coordinator._credentials = credentials
    run = await _start(k)
    before = await k.coordinator.pending_approval(TENANT, run.run_id)
    assert before.canonical_proposal["credential_version"] == "credential-1"
    credentials.revision = "credential-2"
    await _approve(k, run.run_id)
    assert k.backend.create_calls == 0


async def test_driver_usage_limit_is_persisted_as_budget_failure_without_dispatch(make_kernel):
    from e_agent.sdk.errors import DriverBudgetExceeded

    k = make_kernel()

    async def exhausted(*args):
        raise DriverBudgetExceeded("model usage limit")

    k.driver.advance = exhausted
    run = await k.coordinator.start_run(k.requester, "x", k.scope)
    assert run.state is RunState.FAILED
    assert k.backend.create_calls == 0
    events = await k.store.list_events(TENANT, run.run_id)
    assert any(e.type == "budget.exhausted" for e in events)


async def test_plain_model_text_cannot_mark_a_business_task_succeeded(make_kernel):
    from e_agent.sdk.ports import FinalAnswer

    k = make_kernel()

    async def unverified(*args):
        return FinalAnswer(text="I completed the business task.")

    k.driver.advance = unverified
    run = await k.coordinator.start_run(k.requester, "x", k.scope)
    assert run.state is RunState.FAILED and k.backend.create_calls == 0
    assert run.reason == "no independently verified outcome"
    events = await k.store.list_events(TENANT, run.run_id)
    assert not any(e.type == "message.final" for e in events)


async def test_rule_bundle_change_requires_new_approval_even_when_validation_passes(make_kernel):
    k = make_kernel()
    run = await _start(k)
    original = k.validator.validate

    async def changed_bundle(*args):
        validation = await original(*args)
        return validation.model_copy(update={"rule_bundle_version": "notes@2"})

    k.validator.validate = changed_bundle
    await _approve(k, run.run_id)
    assert k.backend.create_calls == 0
    assert (await k.store.list_actions(TENANT, run.run_id))[0].state is ActionState.BLOCKED
    events = await k.store.list_events(TENANT, run.run_id)
    assert any(event.payload.get("reason") == "rules changed since approval" for event in events)


async def test_terminal_run_rejects_further_transitions(make_kernel: MakeKernel) -> None:
    k = make_kernel()
    run = await _approve(k, (await _start(k)).run_id)
    assert run.state is RunState.SUCCEEDED
    with pytest.raises(KernelError) as err:
        await k.coordinator._set_run_state(run, RunState.RUNNING, "must not happen")
    assert err.value.code is ErrorCode.CONFLICT
    assert (await k.coordinator.get_run(TENANT, run.run_id)).state is RunState.SUCCEEDED


async def test_requester_with_approver_role_cannot_approve_own_run(make_kernel: MakeKernel) -> None:
    k = make_kernel()
    carol = principal("carol", {"requester", "approver"})
    run = await k.coordinator.start_run(carol, "write standup note", k.scope)
    assert run.state is RunState.WAITING_APPROVAL
    pres = await k.coordinator.pending_approval(TENANT, run.run_id)
    with pytest.raises(KernelError) as err:
        await k.coordinator.decide(
            actor=carol,
            run_id=run.run_id,
            action_id=pres.action_id,
            action_digest=pres.digest,
            expected_run_revision=pres.run_revision,
            decision=ApprovalDecision.APPROVED,
        )
    assert err.value.code is ErrorCode.FORBIDDEN
    assert (await k.coordinator.get_run(TENANT, run.run_id)).state is RunState.WAITING_APPROVAL


async def test_profile_may_allow_self_approval_for_local_demo(make_kernel: MakeKernel) -> None:
    k = make_kernel(allow_self_approval=True)
    carol = principal("carol", {"requester", "approver"})
    run = await k.coordinator.start_run(carol, "write standup note", k.scope)
    pres = await k.coordinator.pending_approval(TENANT, run.run_id)
    run = await k.coordinator.decide(
        actor=carol,
        run_id=run.run_id,
        action_id=pres.action_id,
        action_digest=pres.digest,
        expected_run_revision=pres.run_revision,
        decision=ApprovalDecision.APPROVED,
    )
    assert run.state is RunState.SUCCEEDED


async def test_rejected_approval_records_a_reason_code(make_kernel: MakeKernel) -> None:
    k = make_kernel()
    run = await _approve(k, (await _start(k)).run_id, ApprovalDecision.REJECTED)
    assert run.state is RunState.FAILED
    assert run.reason_code is ReasonCode.APPROVAL_REJECTED
    assert run.reason == "rejected by approver"
    changed = [
        e
        for e in await k.store.list_events(TENANT, run.run_id)
        if e.type is RunEventType.RUN_STATE_CHANGED
    ]
    assert changed[-1].payload["reason_code"] == "approval_rejected"


async def test_expired_approval_is_swept_to_failed_without_a_decision(
    make_kernel: MakeKernel,
) -> None:
    k = make_kernel()
    run = await _start(k)
    assert await k.coordinator.sweep_expired_approvals() == 0, "not expired yet"
    k.clock.advance(minutes=16)
    assert await k.coordinator.sweep_expired_approvals() == 1
    assert await k.coordinator.sweep_expired_approvals() == 0, "idempotent while queued"
    claim = await k.store.claim_work("sweeper-test")
    assert claim is not None and claim.kind == "expire", claim
    async with k.store.work_scope(claim):
        run = await k.coordinator.expire_approval(TENANT, run.run_id, claim.payload["action_id"])
        await k.store.finish_work(claim)
    assert run.state is RunState.FAILED
    assert run.reason_code is ReasonCode.APPROVAL_EXPIRED
    actions = await k.store.list_actions(TENANT, run.run_id)
    assert actions[-1].state is ActionState.BLOCKED
    decided = [
        e
        for e in await k.store.list_events(TENANT, run.run_id)
        if e.type is RunEventType.APPROVAL_DECIDED
    ]
    assert decided[-1].payload == {"decision": "expired"}
    with pytest.raises(KernelError) as err:
        await _approve(k, run.run_id)
    assert err.value.code is ErrorCode.NOT_FOUND  # no pending approval any more


async def test_late_decision_after_sweep_sees_stale_not_double_change(
    make_kernel: MakeKernel,
) -> None:
    k = make_kernel()
    run = await _start(k)
    k.clock.advance(minutes=16)
    assert await k.coordinator.sweep_expired_approvals() == 1
    # The approver's decision arrives first and is itself rejected as expired.
    with pytest.raises(KernelError) as err:
        await _approve(k, run.run_id)
    assert err.value.code is ErrorCode.APPROVAL_STALE
    failed = await k.coordinator.get_run(TENANT, run.run_id)
    assert failed.state is RunState.FAILED
    # The queued expire claim then finds nothing to do and changes nothing.
    claim = await k.store.claim_work("sweeper-test")
    assert claim is not None and claim.kind == "expire"
    async with k.store.work_scope(claim):
        again = await k.coordinator.expire_approval(TENANT, run.run_id, claim.payload["action_id"])
        await k.store.finish_work(claim)
    assert again.revision == failed.revision


async def test_sweep_only_enqueues_and_expire_resumes_after_an_interrupted_attempt(
    make_kernel: MakeKernel,
) -> None:
    k = make_kernel()
    run = await _start(k)
    k.clock.advance(minutes=16)
    before = await k.store.list_events(TENANT, run.run_id)
    assert await k.coordinator.sweep_expired_approvals() == 1
    assert await k.coordinator.get_run(TENANT, run.run_id) == run, "the sweeper never mutates"
    assert await k.store.list_events(TENANT, run.run_id) == before
    claim = await k.store.claim_work("sweeper-test")
    assert claim is not None and claim.kind == "expire"
    # Simulate a worker that died after blocking the action but before failing the run.
    action_id = claim.payload["action_id"]
    async with k.store.work_scope(claim):
        action = await k.store.get_action(TENANT, action_id)
        await k.store.put_action(
            action.model_copy(
                update={"state": ActionState.BLOCKED, "revision": action.revision + 1}
            ),
            action.revision,
            [(RunEventType.APPROVAL_DECIDED, {"decision": "expired"}, action_id)],
        )
        resumed = await k.coordinator.expire_approval(TENANT, run.run_id, action_id)
        await k.store.finish_work(claim)
    assert resumed.state is RunState.FAILED
    assert resumed.reason_code is ReasonCode.APPROVAL_EXPIRED
    decided = [
        e
        for e in await k.store.list_events(TENANT, run.run_id)
        if e.type is RunEventType.APPROVAL_DECIDED and e.payload == {"decision": "expired"}
    ]
    assert len(decided) == 1, "the resume must not record the expiry twice"


async def test_one_unreadable_continuation_does_not_block_sweeping_other_runs(
    make_kernel: MakeKernel, monkeypatch: pytest.MonkeyPatch
) -> None:
    k = make_kernel(["first", "second"])
    bad = await _start(k, "write standup note one")
    good = await _start(k, "write standup note two")
    k.clock.advance(minutes=16)
    original = k.coordinator._peek_cont

    async def peek(tenant_id: str, run_id: str):
        if run_id == bad.run_id:
            raise ValueError("malformed continuation")  # not a KernelError
        return await original(tenant_id, run_id)

    monkeypatch.setattr(k.coordinator, "_peek_cont", peek)
    k.coordinator._runs.pop(bad.run_id, None)
    assert await k.coordinator.sweep_expired_approvals() == 1
    claim = await k.store.claim_work("sweeper-test")
    assert claim is not None and claim.kind == "expire" and claim.run_id == good.run_id
    assert await k.store.claim_work("sweeper-test-2") is None, "the bad run was not enqueued"


async def test_second_write_on_a_busy_connection_is_refused_with_a_typed_reason(
    make_kernel: MakeKernel,
) -> None:
    k = make_kernel(["first note", "second note"])
    first = await _start(k)
    # Simulate a write whose outcome is unknown: the earlier run's action is stuck in UNKNOWN.
    pres = await k.coordinator.pending_approval(TENANT, first.run_id)
    stuck = await k.store.get_action(TENANT, pres.action_id)
    await k.store.put_action(
        stuck.model_copy(update={"state": ActionState.UNKNOWN, "revision": stuck.revision + 1}),
        stuck.revision,
        [],
    )
    second = await _start(k, "write another note")
    run = await _approve(k, second.run_id)
    assert run.state is RunState.FAILED
    assert run.reason_code is ReasonCode.CONNECTION_BUSY
    assert k.backend.create_calls == 0, "nothing was dispatched behind the unresolved write"
    actions = await k.store.list_actions(TENANT, second.run_id)
    assert actions[-1].state is ActionState.BLOCKED


async def test_rejected_read_is_fed_back_and_the_run_continues(make_kernel: MakeKernel) -> None:
    k = make_kernel()
    k.backend.fail_mode = "read-reject-once"
    seen: list[dict[str, str]] = []
    original = k.driver.advance

    async def spy(ctx, step_input):  # type: ignore[no-untyped-def]
        seen.append(dict(step_input.read_errors))
        return await original(ctx, step_input)

    k.driver.advance = spy  # type: ignore[method-assign]
    run = await _start(k)
    assert run.state is RunState.WAITING_APPROVAL
    assert {"r1": "E_AGENT_INVALID_REF: Odoo rejected the request"} in seen
    assert "r1" not in seen[-1], "an observation supersedes the earlier error"
    rejected = [
        e
        for e in await k.store.list_events(TENANT, run.run_id)
        if e.type is RunEventType.READ_REJECTED
    ]
    assert rejected and rejected[0].payload["code"] == "E_AGENT_INVALID_REF"
    assert rejected[0].payload["message"] == "Odoo rejected the request"


async def test_repeated_rejected_reads_exhaust_the_read_budget(make_kernel: MakeKernel) -> None:
    k = make_kernel(budgets=Budgets(max_read_calls=3))
    k.backend.fail_mode = "read-reject"
    run = await _start(k)
    assert run.state is RunState.FAILED
    assert run.reason_code is ReasonCode.BUDGET_EXHAUSTED
    assert run.reason == "budget exhausted: read calls"


async def test_read_auth_failure_fails_the_run_without_model_feedback(
    make_kernel: MakeKernel,
) -> None:
    k = make_kernel()
    k.backend.fail_mode = "read-auth"
    run = await _start(k)
    assert run.state is RunState.FAILED
    assert run.reason_code is ReasonCode.PROVIDER_ERROR
    assert run.reason == "provider authentication required"
    assert RunEventType.READ_REJECTED not in await _types(k, run.run_id)
    assert k.driver.calls == 1, "the model is not asked to fix credentials"
