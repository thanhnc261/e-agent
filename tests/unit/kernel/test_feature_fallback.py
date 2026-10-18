"""`feature.fallback`: a feature in `on` mode returns to the existing path (ADR 0027).

The helper only records the event; the run keeps its state, because a fallback code never
ends a run (ADR 0025). Runs over both stores through the `run_store` fixture (ENG-STORE-1).
"""

from collections.abc import Callable

import pytest
from e_agent.contracts.approval import ApprovalDecision
from e_agent.contracts.events import RunEventType
from e_agent.contracts.run import ReasonCode, RunState
from e_agent.kernel.errors import ErrorCode, KernelError

from .conftest import TENANT, Kernel

pytestmark = pytest.mark.asyncio
MakeKernel = Callable[..., Kernel]

FALLBACK_CODES = ("IR_TASK_UNRESOLVED", "IR_COMPILE_FAILED", "IR_VALIDATION_FAILED")


async def test_record_fallback_appends_event_with_reason(make_kernel: MakeKernel) -> None:
    k = make_kernel()
    run = await k.coordinator.start_run(k.requester, "write standup note", k.scope)
    before = await k.store.list_events(TENANT, run.run_id)

    updated = await k.coordinator.record_fallback(
        run, "execution_ir", ReasonCode.IR_COMPILE_FAILED, "step 1 has no binding"
    )

    events = await k.store.list_events(TENANT, run.run_id)
    assert len(events) == len(before) + 1
    event = events[-1]
    assert event.type is RunEventType.FEATURE_FALLBACK
    assert event.payload == {
        "feature": "execution_ir",
        "reason_code": "ir_compile_failed",
        "detail": "step 1 has no binding",
    }
    assert event.action_id is None
    stored = await k.store.get_run(TENANT, run.run_id)
    assert updated.revision == stored.revision == run.revision + 1
    assert stored.state is run.state, "a fallback never changes the run state"
    assert stored.reason_code == run.reason_code


@pytest.mark.parametrize("name", FALLBACK_CODES)
async def test_record_fallback_accepts_each_fallback_code(
    make_kernel: MakeKernel, name: str
) -> None:
    k = make_kernel()
    run = await k.coordinator.start_run(k.requester, "write standup note", k.scope)
    await k.coordinator.record_fallback(run, "execution_ir", ReasonCode[name], "detail")
    event = (await k.store.list_events(TENANT, run.run_id))[-1]
    assert event.payload["reason_code"] == ReasonCode[name].value


async def test_record_fallback_refuses_a_code_that_is_not_a_fallback_code(
    make_kernel: MakeKernel,
) -> None:
    k = make_kernel()
    run = await k.coordinator.start_run(k.requester, "write standup note", k.scope)
    with pytest.raises(KernelError) as exc:
        await k.coordinator.record_fallback(run, "execution_ir", ReasonCode.STALE, "x")
    assert exc.value.code is ErrorCode.INVALID_REQUEST
    types = [e.type for e in await k.store.list_events(TENANT, run.run_id)]
    assert RunEventType.FEATURE_FALLBACK not in types


async def test_record_fallback_refuses_an_unknown_feature(make_kernel: MakeKernel) -> None:
    k = make_kernel()
    run = await k.coordinator.start_run(k.requester, "write standup note", k.scope)
    with pytest.raises(KernelError) as exc:
        await k.coordinator.record_fallback(
            run, "no_such_feature", ReasonCode.IR_COMPILE_FAILED, "x"
        )
    assert exc.value.code is ErrorCode.INVALID_REQUEST


async def test_record_fallback_refuses_a_terminal_run(make_kernel: MakeKernel) -> None:
    k = make_kernel()
    run = await k.coordinator.start_run(k.requester, "write standup note", k.scope)
    pres = await k.coordinator.pending_approval(TENANT, run.run_id)
    run = await k.coordinator.decide(
        actor=k.approver,
        run_id=run.run_id,
        action_id=pres.action_id,
        action_digest=pres.digest,
        expected_run_revision=pres.run_revision,
        decision=ApprovalDecision.REJECTED,
    )
    assert run.state is RunState.FAILED
    with pytest.raises(KernelError) as exc:
        await k.coordinator.record_fallback(run, "execution_ir", ReasonCode.IR_COMPILE_FAILED, "x")
    assert exc.value.code is ErrorCode.CONFLICT
