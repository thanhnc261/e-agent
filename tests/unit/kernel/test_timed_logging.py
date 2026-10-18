"""An awaited kernel call is not a background task: its handled failure is not logged (PR-38).

The caller of ``_timed`` handles the failure (a lost response becomes UNKNOWN, a model error a
failed run), so logging it again would add output, for example on the CLI's stderr.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

import pytest
from e_agent.contracts.approval import ApprovalDecision
from e_agent.contracts.run import RunState

from .conftest import TENANT, Kernel

pytestmark = pytest.mark.asyncio
MakeKernel = Callable[..., Kernel]


class _Boom(RuntimeError):
    pass


async def _waiting_run(k: Kernel) -> str:
    run = await k.coordinator.start_run(k.requester, "write standup note", k.scope)
    assert run.state is RunState.WAITING_APPROVAL
    return run.run_id


async def test_handled_kernel_call_failure_is_not_logged(
    make_kernel: MakeKernel, caplog: pytest.LogCaptureFixture
) -> None:
    k = make_kernel()
    k.backend.fail_mode = "timeout"  # the provider call raises TimeoutError after committing
    run_id = await _waiting_run(k)
    pres = await k.coordinator.pending_approval(TENANT, run_id)
    caplog.set_level(logging.WARNING)
    run = await k.coordinator.decide(
        actor=k.approver,
        run_id=run_id,
        action_id=pres.action_id,
        action_digest=pres.digest,
        expected_run_revision=pres.run_revision,
        decision=ApprovalDecision.APPROVED,
    )
    assert run.state is RunState.NEEDS_RECONCILIATION, "the caller handled the TimeoutError"
    assert k.backend.create_calls == 1
    assert [r for r in caplog.records if r.levelno >= logging.WARNING] == []


async def test_timed_call_failure_reaches_the_caller_unlogged(
    make_kernel: MakeKernel, caplog: pytest.LogCaptureFixture
) -> None:
    k = make_kernel()
    run_id = await _waiting_run(k)
    cont = await k.coordinator._load_cont(TENANT, run_id)
    sentinel = _Boom("provider detail")

    async def fail() -> None:
        raise sentinel

    caplog.set_level(logging.DEBUG)
    with pytest.raises(_Boom) as excinfo:
        await k.coordinator._timed(cont, fail, 5)
    assert excinfo.value is sentinel
    assert [r for r in caplog.records if r.levelno >= logging.WARNING] == []
    assert run_id not in k.coordinator._active_calls
