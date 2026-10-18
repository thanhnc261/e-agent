"""`feature.fallback`: a feature in `on` mode returns to the existing path (ADR 0027).

The helper only records the event; the run keeps its state, because a fallback code never
ends a run (ADR 0025). The event carries the code and its fixed message, never caller text
(PR-25, PR-28). Runs over both stores through the `run_store` fixture (ENG-STORE-1).
"""

import inspect
import json
from collections.abc import Callable

import pytest
from e_agent.contracts.approval import ApprovalDecision
from e_agent.contracts.events import RunEventType
from e_agent.contracts.features import Features
from e_agent.contracts.run import ReasonCode, RunState
from e_agent.kernel.errors import ErrorCode, KernelError
from e_agent.kernel.evidence import build_evidence
from e_agent.kernel.features import FALLBACK_MESSAGES

from .conftest import TENANT, Kernel

MakeKernel = Callable[..., Kernel]

FALLBACK_CODES = (
    ReasonCode.IR_TASK_UNRESOLVED,
    ReasonCode.IR_COMPILE_FAILED,
    ReasonCode.IR_VALIDATION_FAILED,
)
NOT_FALLBACK_CODES = tuple(c for c in ReasonCode if c not in FALLBACK_CODES)


async def _start(k: Kernel):  # type: ignore[no-untyped-def]
    return await k.coordinator.start_run(k.requester, "write standup note", k.scope)


def test_the_fallback_codes_are_exactly_the_mapped_ones() -> None:
    assert set(FALLBACK_MESSAGES) == set(FALLBACK_CODES)
    assert all(m.strip() for m in FALLBACK_MESSAGES.values())


async def test_record_fallback_appends_event_with_reason(make_kernel: MakeKernel) -> None:
    k = make_kernel()
    run = await _start(k)
    before = await k.store.list_events(TENANT, run.run_id)

    updated = await k.coordinator.record_fallback(run, "execution_ir", ReasonCode.IR_COMPILE_FAILED)

    events = await k.store.list_events(TENANT, run.run_id)
    assert len(events) == len(before) + 1
    event = events[-1]
    assert event.type is RunEventType.FEATURE_FALLBACK
    assert event.payload == {
        "feature": "execution_ir",
        "reason_code": "ir_compile_failed",
        "message": FALLBACK_MESSAGES[ReasonCode.IR_COMPILE_FAILED],
    }
    assert event.action_id is None
    stored = await k.store.get_run(TENANT, run.run_id)
    assert updated.revision == stored.revision == run.revision + 1
    assert stored.state is run.state, "a fallback never changes the run state"
    assert stored.reason_code == run.reason_code


@pytest.mark.parametrize("reason", FALLBACK_CODES)
async def test_record_fallback_payload_is_fixed_per_reason(
    make_kernel: MakeKernel, reason: ReasonCode
) -> None:
    k = make_kernel()
    run = await _start(k)
    await k.coordinator.record_fallback(run, "execution_ir", reason)
    event = (await k.store.list_events(TENANT, run.run_id))[-1]
    assert event.payload == {
        "feature": "execution_ir",
        "reason_code": reason.value,
        "message": FALLBACK_MESSAGES[reason],
    }


@pytest.mark.parametrize("reason", NOT_FALLBACK_CODES)
async def test_record_fallback_refuses_non_fallback_reason(
    make_kernel: MakeKernel, reason: ReasonCode
) -> None:
    k = make_kernel()
    run = await _start(k)
    with pytest.raises(KernelError) as exc:
        await k.coordinator.record_fallback(run, "execution_ir", reason)
    assert exc.value.code is ErrorCode.INVALID_REQUEST
    types = [e.type for e in await k.store.list_events(TENANT, run.run_id)]
    assert RunEventType.FEATURE_FALLBACK not in types


async def test_record_fallback_refuses_unknown_feature(make_kernel: MakeKernel) -> None:
    k = make_kernel()
    run = await _start(k)
    with pytest.raises(KernelError) as exc:
        await k.coordinator.record_fallback(run, "no_such_feature", ReasonCode.IR_COMPILE_FAILED)
    assert exc.value.code is ErrorCode.INVALID_REQUEST
    types = [e.type for e in await k.store.list_events(TENANT, run.run_id)]
    assert RunEventType.FEATURE_FALLBACK not in types


async def test_record_fallback_refuses_a_terminal_run(make_kernel: MakeKernel) -> None:
    k = make_kernel()
    run = await _start(k)
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
        await k.coordinator.record_fallback(run, "execution_ir", ReasonCode.IR_COMPILE_FAILED)
    assert exc.value.code is ErrorCode.CONFLICT


async def test_fallback_event_and_evidence_carry_no_caller_text(make_kernel: MakeKernel) -> None:
    # The API has no parameter for caller text, positional or keyword.
    params = inspect.signature(type(make_kernel().coordinator).record_fallback).parameters
    assert list(params) == ["self", "run", "feature", "reason"]
    assert all(
        p.kind is not p.VAR_POSITIONAL and p.kind is not p.VAR_KEYWORD for p in params.values()
    )

    k = make_kernel()
    run = await _start(k)
    secret = "sk-synthetic-0123456789"
    with pytest.raises(TypeError):
        await k.coordinator.record_fallback(  # type: ignore[call-arg]
            run, "execution_ir", ReasonCode.IR_VALIDATION_FAILED, secret
        )
    with pytest.raises(TypeError):
        await k.coordinator.record_fallback(  # type: ignore[call-arg]
            run, "execution_ir", ReasonCode.IR_VALIDATION_FAILED, detail=secret
        )
    await k.coordinator.record_fallback(run, "execution_ir", ReasonCode.IR_VALIDATION_FAILED)

    bundle = await build_evidence(
        k.store, TENANT, run.run_id, environment="fixture", versions={}, features=Features()
    )
    exported = [e for e in bundle["events"] if e["type"] == "feature.fallback"]
    assert [e["payload"] for e in exported] == [
        {
            "feature": "execution_ir",
            "reason_code": "ir_validation_failed",
            "message": FALLBACK_MESSAGES[ReasonCode.IR_VALIDATION_FAILED],
        }
    ]
    assert secret not in json.dumps(bundle)
