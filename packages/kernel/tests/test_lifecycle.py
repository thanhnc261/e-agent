"""Kernel safety and lifecycle behaviour with a non-ERP domain (MVP design §7-9, §13)."""

from collections.abc import Callable

import pytest
from e_agent.contracts.action import ActionState
from e_agent.contracts.approval import ApprovalDecision
from e_agent.contracts.connection import ConnectionDescriptor, ConnectionOwnership
from e_agent.contracts.context import Budgets
from e_agent.contracts.events import RunEventType
from e_agent.contracts.run import RunState
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
