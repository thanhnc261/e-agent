"""A conversation's run through an UNKNOWN write and a crash (Phase 4 review KB-1).

A run linked to a conversation keeps its ``conversation_id`` while it waits in
NEEDS_RECONCILIATION; the next message is refused (``WAIT_FOR_RUN``) until reconcile ends the
run, and the run started after that carries the reconciled one. Every test runs on both
stores (``E_AGENT_TEST_STORE=postgres``, PR-30).
"""

from __future__ import annotations

import importlib
import os
from collections.abc import AsyncIterator, Callable
from typing import Any

import pytest
from e_agent.contracts.events import RunEventType
from e_agent.contracts.features import FeatureMode, Features
from e_agent.contracts.run import RunState
from e_agent.kernel.conversation import WAIT_FOR_RUN
from e_agent.kernel.errors import ErrorCode, KernelError
from e_agent.kernel.memory_conversations import InMemoryConversationStore

from .conftest import TENANT, Kernel
from .test_carried_context import _admit, _approve, _events, _kernel, _of
from .test_conversation_routing import _post
from .test_recovery import Crash, restart

MakeKernel = Callable[..., Kernel]
ON = Features(conversations=FeatureMode.ON, context_assembler=FeatureMode.ON)
CARRIED = RunEventType.CONVERSATION_CONTEXT_CARRIED


@pytest.fixture
async def run_store() -> AsyncIterator[Any]:
    """The kernel suite's store switch, with the conversation store in memory."""
    if os.environ.get("E_AGENT_TEST_STORE") != "postgres":
        yield InMemoryConversationStore()
        return
    pg = importlib.import_module("e_agent.adapters.postgres")
    dsn = os.environ["E_AGENT_TEST_PG_DSN"]
    await pg.apply_migrations(dsn)
    store = await pg.PostgresRunStore.open(dsn)
    await store.truncate_for_tests()
    try:
        yield store
    finally:
        await store.close()


async def _waiting_write(k: Kernel) -> tuple[str, str]:
    conv = await k.coordinator.create_conversation(k.requester)
    run_id = await _admit(k, conv.conversation_id, "write the standup note")
    run = await k.coordinator.start_admitted_run(TENANT, run_id)
    assert run.state is RunState.WAITING_APPROVAL
    return conv.conversation_id, run_id


async def _assert_held(k: Kernel, cid: str, run_id: str) -> None:
    """The unreconciled run keeps its link, and a message is refused with ``WAIT_FOR_RUN``."""
    held = await k.store.get_run(TENANT, run_id)
    assert held.state is RunState.NEEDS_RECONCILIATION
    assert held.conversation_id == cid
    with pytest.raises(KernelError) as caught:
        await _post(k, cid, "write another note")
    assert caught.value.code is ErrorCode.CONFLICT
    assert caught.value.safe_message == WAIT_FOR_RUN


async def _assert_carries(k: Kernel, coordinator: Any, cid: str, earlier: str) -> None:
    """After reconcile the next message starts a run that carries the reconciled one."""
    _, next_id = await _post(k, cid, "write the next note")
    assert next_id != earlier
    run = await coordinator.start_admitted_run(TENANT, next_id)
    assert run.conversation_id == cid
    (carried,) = _of(await _events(k, next_id), CARRIED)
    assert carried.payload["carried_run_ids"] == [earlier]


async def test_unknown_write_holds_the_conversation_until_reconcile(
    make_kernel: MakeKernel,
) -> None:
    k = _kernel(make_kernel, ON)
    k.backend.fail_mode = "timeout"
    cid, run_id = await _waiting_write(k)

    run = await _approve(k, run_id)
    assert run.state is RunState.NEEDS_RECONCILIATION
    assert k.backend.create_calls == 1
    await _assert_held(k, cid, run_id)

    reconciled = await k.coordinator.reconcile(k.approver, run_id)
    assert reconciled.state is RunState.SUCCEEDED
    assert reconciled.conversation_id == cid
    assert k.backend.create_calls == 1, "reconcile never re-sends a write"

    k.backend.fail_mode = None
    await _assert_carries(k, k.coordinator, cid, run_id)


async def test_crash_after_the_provider_committed_keeps_the_link(
    make_kernel: MakeKernel,
) -> None:
    k = _kernel(make_kernel, ON)
    cid, run_id = await _waiting_write(k)
    original = k.backend.execute

    async def commit_then_die(*args: Any) -> Any:
        await original(*args)
        raise Crash

    k.backend.execute = commit_then_die  # type: ignore[method-assign]
    with pytest.raises(Crash):
        await _approve(k, run_id)
    k.backend.execute = original  # type: ignore[method-assign]
    assert k.backend.create_calls == 1  # the provider committed

    fresh = restart(k, ON)
    recovered = await fresh.recover_run(TENANT, run_id)
    assert recovered.state is RunState.NEEDS_RECONCILIATION
    assert recovered.conversation_id == cid
    await _assert_held(k, cid, run_id)

    reconciled = await fresh.reconcile(k.approver, run_id)
    assert reconciled.state is RunState.SUCCEEDED
    assert reconciled.conversation_id == cid
    assert k.backend.create_calls == 1, "recovery never re-sends a write"

    await _assert_carries(k, k.coordinator, cid, run_id)
    assert k.backend.create_calls == 1  # the next run waits for approval; no new write
