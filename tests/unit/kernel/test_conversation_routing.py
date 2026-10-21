"""Conversation message routing in the kernel facade (ADR 0023 §4, D2, Task 4d.1).

The router looks only at the conversation's latest run. An answer is bound to the question
the user saw (``reply_to``: the waiting run and its revision), never to the conversation
revision. A message is never a decision (PR-13): no route reaches the approval flow. Every
test runs on both stores (``E_AGENT_TEST_STORE=postgres``, ENG-STORE-1).
"""

from __future__ import annotations

import importlib
import os
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from typing import Any

import pytest
from e_agent.contracts.approval import ApprovalDecision
from e_agent.contracts.common import new_id, utc_now
from e_agent.contracts.context import HostContext, Principal, ResourceHint, TaskContext
from e_agent.contracts.conversation import Conversation, MessageRoute, ReplyTo, RouteKind
from e_agent.contracts.events import RunEventType
from e_agent.contracts.features import FeatureMode, Features, MemberFeatures
from e_agent.contracts.run import TERMINAL_RUN_STATES, RunRecord, RunState
from e_agent.kernel.conversation import CONVERSATIONS_OFF, message_digest, route_message
from e_agent.kernel.errors import ErrorCode, KernelError
from e_agent.kernel.memory_conversations import InMemoryConversationStore
from e_agent.sdk.ports import AskClarification, DriverInput, DriverStep
from e_agent.sdk.store import NotFound

from .conftest import TENANT, Kernel, principal

MakeKernel = Callable[..., Kernel]
QUESTION_CHANGED = "the question changed; read it again"
WAIT = "wait, decide the approval, or stop the run"
ACTIVE = (
    RunState.CREATED,
    RunState.RUNNING,
    RunState.VERIFYING,
    RunState.WAITING_APPROVAL,
    RunState.NEEDS_RECONCILIATION,
)


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


ON = Features(conversations=FeatureMode.ON, context_assembler=FeatureMode.ON)
"""The routing under test: ``off`` refuses every conversation call (Task 4d.4), and ``on``
needs ``context_assembler`` ``on`` at startup (ADR 0023 §9)."""


@pytest.fixture
def make_kernel(make_kernel: MakeKernel) -> MakeKernel:
    """The suite's kernel with ``conversations: on`` unless a test names other features."""

    def _make(*args: Any, **kw: Any) -> Kernel:
        kw.setdefault("features", ON)
        return make_kernel(*args, **kw)

    return _make


@dataclass
class ClarifyDriver:
    """Asks Q1, then Q2 after any answer."""

    driver_id: str = "clarify-driver"

    async def advance(self, ctx: TaskContext, step_input: DriverInput) -> DriverStep:
        if step_input.user_input is None:
            return AskClarification(question="Q1: which note?")
        return AskClarification(question="Q2: anything else?")


def _digest(
    conversation_id: str,
    text: str,
    reply_to: ReplyTo | None = None,
    host_context: HostContext | None = None,
) -> str:
    """The kernel's one request digest (`message_digest`, Task 4d.4 B1-2): the conversation
    id, the text, ``reply_to`` and ``host_context`` (ADR 0023 §4)."""
    return message_digest(conversation_id, text, reply_to, host_context)


async def _post(
    k: Kernel,
    conversation_id: str,
    text: str,
    *,
    reply_to: ReplyTo | None = None,
    key: str | None = None,
    who: Principal | None = None,
    host_context: HostContext | None = None,
    request_digest: str | None = None,
) -> tuple[MessageRoute, str]:
    return await k.coordinator.post_message(
        who or k.requester,
        conversation_id,
        text,
        reply_to=reply_to,
        host_context=host_context,
        idempotency_key=key or new_id("key"),
        request_digest=request_digest or _digest(conversation_id, text, reply_to, host_context),
        resource_scope=k.scope,
    )


async def _conflict(k: Kernel, conversation_id: str, text: str, **kw: Any) -> KernelError:
    with pytest.raises(KernelError) as caught:
        await _post(k, conversation_id, text, **kw)
    assert caught.value.code is ErrorCode.CONFLICT
    return caught.value


async def _waiting(k: Kernel) -> tuple[str, RunRecord]:
    """A conversation whose one run waits on Q1."""
    conv = await k.coordinator.create_conversation(k.requester)
    route, run_id = await _post(k, conv.conversation_id, "write a note")
    assert route.kind is RouteKind.START
    run = await k.coordinator.start_admitted_run(TENANT, run_id)
    assert run.state is RunState.WAITING_INPUT
    return conv.conversation_id, run


async def _received(k: Kernel, run_id: str) -> int:
    events = await k.store.list_events(TENANT, run_id)
    return sum(e.type is RunEventType.INPUT_RECEIVED for e in events)


def _record(state: RunState, revision: int = 3) -> RunRecord:
    return RunRecord(
        run_id="run_1",
        tenant_id=TENANT,
        requester_id="alice",
        task="t",
        state=state,
        revision=revision,
        logical_operation_id="op_1",
        created_at=utc_now(),
        conversation_id="conv_1",
    )


# ------------------------------------------------------------------- the pure router
def test_route_message_follows_the_table() -> None:
    """ADR 0023 §4, every state: terminal or none starts, a waiting run answers only its
    own question, an active run refuses with the fixed hint."""
    assert route_message(None, None).kind is RouteKind.START
    checked = 0
    for state in RunState:
        latest = _record(state)
        for reply_to in (None, ReplyTo(run_id="run_1", run_revision=3)):
            route = route_message(latest, reply_to)
            if state in TERMINAL_RUN_STATES:
                assert route.kind is RouteKind.START, state
            elif state is RunState.WAITING_INPUT and reply_to is not None:
                assert route == MessageRoute(kind=RouteKind.ANSWER, run_id="run_1", run_revision=3)
            elif state is RunState.WAITING_INPUT:
                assert (route.kind, route.hint) == (RouteKind.REFUSE, QUESTION_CHANGED)
            else:
                assert state in ACTIVE, state
                assert (route.kind, route.hint) == (RouteKind.REFUSE, WAIT), state
            checked += 1
    assert checked == 2 * len(RunState)
    waiting = _record(RunState.WAITING_INPUT)
    for stale in (ReplyTo(run_id="run_1", run_revision=1), ReplyTo(run_id="run_0", run_revision=3)):
        assert route_message(waiting, stale).hint == QUESTION_CHANGED


# ------------------------------------------------------------------------ answering
async def test_waiting_input_message_answers_the_run(make_kernel: MakeKernel) -> None:
    k = make_kernel(driver=ClarifyDriver())
    cid, run = await _waiting(k)
    reply_to = ReplyTo(run_id=run.run_id, run_revision=run.revision)
    route, run_id = await _post(k, cid, "the standup note", reply_to=reply_to)
    assert route == MessageRoute(
        kind=RouteKind.ANSWER, run_id=run.run_id, run_revision=run.revision
    )
    assert run_id == run.run_id
    assert (await k.store.get_run(TENANT, run_id)).state is RunState.RUNNING
    assert await _received(k, run_id) == 1
    resumed = await k.coordinator.continue_input(TENANT, run_id)
    assert resumed.state is RunState.WAITING_INPUT  # Q2


async def test_answer_for_an_earlier_question_conflicts(make_kernel: MakeKernel) -> None:
    k = make_kernel(driver=ClarifyDriver())
    cid, q1 = await _waiting(k)
    n = q1.revision
    await _post(k, cid, "the standup note", reply_to=ReplyTo(run_id=q1.run_id, run_revision=n))
    q2 = await k.coordinator.continue_input(TENANT, q1.run_id)
    assert q2.state is RunState.WAITING_INPUT and q2.revision > n
    stale = ReplyTo(run_id=q1.run_id, run_revision=n)
    error = await _conflict(k, cid, "typed for Q1", reply_to=stale)
    assert error.safe_message == QUESTION_CHANGED
    still = await k.store.get_run(TENANT, q1.run_id)
    assert (still.state, still.revision) == (RunState.WAITING_INPUT, q2.revision)
    assert await _received(k, q1.run_id) == 1


async def test_message_without_reply_to_while_waiting_conflicts(make_kernel: MakeKernel) -> None:
    k = make_kernel(driver=ClarifyDriver())
    cid, run = await _waiting(k)
    error = await _conflict(k, cid, "the standup note")
    assert error.safe_message == QUESTION_CHANGED
    still = await k.store.get_run(TENANT, run.run_id)
    assert (still.state, still.revision) == (RunState.WAITING_INPUT, run.revision)
    assert len(await k.store.list_conversation_runs(TENANT, "alice", cid)) == 1


async def test_retried_answer_is_accepted_once(make_kernel: MakeKernel) -> None:
    k = make_kernel(driver=ClarifyDriver())
    cid, run = await _waiting(k)
    reply_to = ReplyTo(run_id=run.run_id, run_revision=run.revision)
    first = await _post(k, cid, "the standup note", reply_to=reply_to, key="answer-1")
    # The run left WAITING_INPUT (RUNNING, input accepted): the retry is still the answer.
    assert (await k.store.get_run(TENANT, run.run_id)).state is RunState.RUNNING
    assert await _post(k, cid, "the standup note", reply_to=reply_to, key="answer-1") == first
    # ... and after the run moved on to Q2, at another revision.
    await k.coordinator.continue_input(TENANT, run.run_id)
    assert await _post(k, cid, "the standup note", reply_to=reply_to, key="answer-1") == first
    assert first == (
        MessageRoute(kind=RouteKind.ANSWER, run_id=run.run_id, run_revision=run.revision),
        run.run_id,
    )
    assert await _received(k, run.run_id) == 1


# ------------------------------------------------------------------------- starting
async def test_terminal_run_message_starts_a_new_run(make_kernel: MakeKernel) -> None:
    k = make_kernel(driver=ClarifyDriver())
    cid, run = await _waiting(k)
    cancelled = await k.coordinator.cancel(k.requester, run.run_id)
    assert cancelled.state is RunState.CANCELLED
    k.clock.advance(seconds=1)  # the thread is ordered by `created_at`
    route, run_id = await _post(k, cid, "another note")
    assert route == MessageRoute(kind=RouteKind.START, run_id=run_id)
    assert run_id != run.run_id
    second = await k.store.get_run(TENANT, run_id)
    assert (second.conversation_id, second.task, second.state) == (
        cid,
        "another note",
        RunState.CREATED,
    )
    runs = await k.store.list_conversation_runs(TENANT, "alice", cid)
    assert [r.run_id for r in runs] == [run.run_id, run_id]


async def test_empty_conversation_message_starts_a_run(make_kernel: MakeKernel) -> None:
    k = make_kernel()
    conv = await k.coordinator.create_conversation(k.requester)
    assert (conv.tenant_id, conv.owner_id, conv.revision) == (TENANT, "alice", 1)
    route, run_id = await _post(k, conv.conversation_id, "write standup note")
    assert route == MessageRoute(kind=RouteKind.START, run_id=run_id)
    run = await k.store.get_run(TENANT, run_id)
    assert (run.conversation_id, run.requester_id) == (conv.conversation_id, "alice")
    events = await k.store.list_events(TENANT, run_id)
    assert events[0].payload["conversation_id"] == conv.conversation_id
    after = await k.store.get_conversation(TENANT, "alice", conv.conversation_id)
    assert after.revision == 2
    # PR-17: the post admitted the run and made no driver call; the worker starts it.
    assert run.state is RunState.CREATED and k.driver.calls == 0


async def test_running_run_message_is_refused(make_kernel: MakeKernel) -> None:
    k = make_kernel(driver=ClarifyDriver())
    cid, run = await _waiting(k)
    await k.coordinator.accept_input(
        k.requester, run.run_id, "the note", run.revision, enqueue=True
    )
    running = await k.store.get_run(TENANT, run.run_id)
    assert running.state is RunState.RUNNING
    error = await _conflict(k, cid, "and one more")
    assert error.safe_message == WAIT
    assert (await k.store.get_run(TENANT, run.run_id)).revision == running.revision
    assert len(await k.store.list_conversation_runs(TENANT, "alice", cid)) == 1


async def test_created_run_message_is_refused(make_kernel: MakeKernel) -> None:
    k = make_kernel()
    conv = await k.coordinator.create_conversation(k.requester)
    await _post(k, conv.conversation_id, "write standup note")
    error = await _conflict(k, conv.conversation_id, "write another")
    assert error.safe_message == WAIT


async def _waiting_approval(k: Kernel) -> tuple[str, RunRecord]:
    conv = await k.coordinator.create_conversation(k.requester)
    _, run_id = await _post(k, conv.conversation_id, "write standup note")
    run = await k.coordinator.start_admitted_run(TENANT, run_id)
    assert run.state is RunState.WAITING_APPROVAL
    return conv.conversation_id, run


async def test_message_while_waiting_approval_never_touches_the_action(
    make_kernel: MakeKernel,
) -> None:
    """Review Focus 1: the action's revision, the approval rows and the events stay."""
    k = make_kernel()
    cid, run = await _waiting_approval(k)
    pres = await k.coordinator.pending_approval(TENANT, run.run_id)
    action = await k.store.get_action(TENANT, pres.action_id)
    approvals = await k.store.list_approvals(TENANT, pres.action_id)
    events = await k.store.list_events(TENANT, run.run_id)
    for text in ("approve it", "yes", "reject"):
        error = await _conflict(k, cid, text)
        assert error.safe_message == WAIT
    after = await k.store.get_action(TENANT, pres.action_id)
    assert (after.revision, after.state) == (action.revision, action.state)
    assert await k.store.list_approvals(TENANT, pres.action_id) == approvals
    assert await k.store.list_events(TENANT, run.run_id) == events
    assert (await k.store.get_run(TENANT, run.run_id)).revision == run.revision
    assert (await k.coordinator.pending_approval(TENANT, run.run_id)) == pres


async def test_message_text_is_never_a_decision(make_kernel: MakeKernel) -> None:
    """PR-13: "approve", "yes" and "reject" route like any other text, in every state."""
    k = make_kernel()
    cid, run = await _waiting_approval(k)
    hints = set()
    for text in ("approve", "yes", "reject", "the weather is nice"):
        hints.add((await _conflict(k, cid, text)).safe_message)
    assert hints == {WAIT}
    await k.coordinator.cancel(k.requester, run.run_id)
    routes = set()
    for text in ("approve", "yes", "reject", "the weather is nice"):
        route, started = await _post(k, cid, text)
        routes.add(route.kind)
        await k.coordinator.cancel(k.requester, started)
    assert routes == {RouteKind.START}


# ---------------------------------------------------------------------- idempotency
async def test_retried_message_starts_one_run(make_kernel: MakeKernel) -> None:
    k = make_kernel(driver=ClarifyDriver())
    conv = await k.coordinator.create_conversation(k.requester)
    cid = conv.conversation_id
    first = await _post(k, cid, "write a note", key="message-1")
    run = await k.coordinator.start_admitted_run(TENANT, first[1])
    await k.coordinator.accept_input(
        k.requester, run.run_id, "the note", run.revision, enqueue=True
    )
    assert (await k.store.get_run(TENANT, run.run_id)).state is RunState.RUNNING
    assert await _post(k, cid, "write a note", key="message-1") == first
    assert first[0] == MessageRoute(kind=RouteKind.START, run_id=run.run_id)
    assert len(await k.store.list_conversation_runs(TENANT, "alice", cid)) == 1


async def test_reused_key_with_other_text_conflicts(make_kernel: MakeKernel) -> None:
    k = make_kernel()
    conv = await k.coordinator.create_conversation(k.requester)
    cid = conv.conversation_id
    await _post(k, cid, "write a note", key="message-2")
    error = await _conflict(k, cid, "write another note", key="message-2")
    assert error.safe_message == "idempotency key reused with another request"
    assert len(await k.store.list_conversation_runs(TENANT, "alice", cid)) == 1


async def test_start_conflict_from_the_store_is_a_fixed_conflict(
    make_kernel: MakeKernel, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A conversation that moved between the read and the insert (``ConcurrencyConflict``)
    is ``CONFLICT`` with the fixed hint, never an unhandled error."""
    k = make_kernel()
    conv = await k.coordinator.create_conversation(k.requester)
    cid = conv.conversation_id
    store = k.store
    original = store.get_conversation

    async def stale(tenant_id: str, owner_id: str, conversation_id: str) -> Any:
        found = await original(tenant_id, owner_id, conversation_id)
        return found.model_copy(update={"revision": found.revision - 1})

    _, first = await _post(k, cid, "write a note")
    await k.coordinator.cancel(k.requester, first)
    monkeypatch.setattr(store, "get_conversation", stale)
    error = await _conflict(k, cid, "write another note")
    monkeypatch.undo()
    assert error.safe_message == WAIT
    assert len(await k.store.list_conversation_runs(TENANT, "alice", cid)) == 1


# -------------------------------------------------------------------- authorization
async def test_other_requester_sees_not_found(make_kernel: MakeKernel) -> None:
    k = make_kernel()
    conv = await k.coordinator.create_conversation(k.requester)
    cid = conv.conversation_id
    for who in (principal("carol", {"requester"}), principal("alice", {"requester"}, "tenant-b")):
        with pytest.raises(KernelError) as caught:
            await _post(k, cid, "write a note", who=who)
        assert caught.value.code is ErrorCode.NOT_FOUND
        with pytest.raises(NotFound):
            await k.store.get_conversation(who.tenant_id, who.principal_id, cid)
        listed = await k.store.list_conversations(
            who.tenant_id, who.principal_id, after=None, limit=10
        )
        assert listed.items == ()
    with pytest.raises(KernelError) as missing:
        await _post(k, "conv_absent", "write a note")
    assert missing.value.code is ErrorCode.NOT_FOUND
    # The same message whether the conversation exists for someone else or not at all.
    assert missing.value.safe_message == caught.value.safe_message
    assert await k.store.list_conversation_runs(TENANT, "alice", cid) == ()


async def test_reply_to_foreign_run_is_not_found(
    make_kernel: MakeKernel, monkeypatch: pytest.MonkeyPatch
) -> None:
    k = make_kernel(driver=ClarifyDriver())
    cid, own = await _waiting(k)
    other_cid, elsewhere = await _waiting(k)  # the caller's run in another conversation
    bob = principal("bob", {"requester"})
    bob_conv = await k.coordinator.create_conversation(bob)
    _, bob_run_id = await _post(k, bob_conv.conversation_id, "bob's note", who=bob)
    bob_run = await k.coordinator.start_admitted_run(TENANT, bob_run_id)

    calls: list[tuple[Any, ...]] = []

    async def spy(*args: Any, **kw: Any) -> bool:
        calls.append(args)
        raise AssertionError("no replay check may run for a foreign reply_to")

    monkeypatch.setattr(k.coordinator, "input_replayed", spy)
    for foreign in (bob_run, elsewhere):
        reply_to = ReplyTo(run_id=foreign.run_id, run_revision=foreign.revision)
        with pytest.raises(KernelError) as caught:
            await _post(k, cid, "the note", reply_to=reply_to)
        assert caught.value.code is ErrorCode.NOT_FOUND
    absent = ReplyTo(run_id="run_absent", run_revision=1)
    with pytest.raises(KernelError) as missing:
        await _post(k, cid, "the note", reply_to=absent)
    assert missing.value.safe_message == caught.value.safe_message
    assert calls == []
    for run in (own, elsewhere, bob_run):
        assert await _received(k, run.run_id) == 0
    assert other_cid != cid


async def test_input_replayed_refuses_a_non_requester(
    make_kernel: MakeKernel, monkeypatch: pytest.MonkeyPatch
) -> None:
    k = make_kernel(driver=ClarifyDriver())
    _, run = await _waiting(k)
    reads: list[str] = []

    async def no_events(*args: Any, **kw: Any) -> Any:
        reads.append("list_events")
        raise AssertionError("events read before the requester check")

    monkeypatch.setattr(k.store, "list_events", no_events)
    with pytest.raises(KernelError) as caught:
        await k.coordinator.input_replayed(k.approver, TENANT, run.run_id, 1, "the note")
    assert caught.value.code is ErrorCode.FORBIDDEN
    assert caught.value.safe_message == "only the requester may answer"
    assert reads == []
    # The requester at the pending revision: no replay, and no event read.
    assert not await k.coordinator.input_replayed(
        k.requester, TENANT, run.run_id, run.revision, "the note"
    )
    assert reads == []


async def test_input_replayed_finds_only_the_accepted_text(make_kernel: MakeKernel) -> None:
    k = make_kernel(driver=ClarifyDriver())
    _, run = await _waiting(k)
    await k.coordinator.accept_input(k.requester, run.run_id, "the note", run.revision)
    replayed = k.coordinator.input_replayed
    assert await replayed(k.requester, TENANT, run.run_id, run.revision, "the note")
    assert not await replayed(k.requester, TENANT, run.run_id, run.revision, "another")
    assert not await replayed(k.requester, TENANT, run.run_id, run.revision - 1, "the note")


# ------------------------------------------------------------------ the started run
async def test_start_passes_host_context_to_the_run(make_kernel: MakeKernel) -> None:
    k = make_kernel()
    conv = await k.coordinator.create_conversation(k.requester)
    host = HostContext(
        host_kind="embedded",
        page_url_origin="https://notes.example",
        locale="en",
        resource_hints=(
            ResourceHint(system_hint="notes-mem", resource_type_hint="note", external_id_hint="n1"),
        ),
        selection_text="never persisted",
    )
    _, run_id = await _post(k, conv.conversation_id, "write standup note", host_context=host)
    created = (await k.store.list_events(TENANT, run_id))[0]
    assert created.type is RunEventType.RUN_CREATED
    recorded = created.payload["host_context"]
    assert (recorded["host_kind"], recorded["page_url_origin"], recorded["locale"]) == (
        "embedded",
        "https://notes.example",
        "en",
    )
    assert [h["connection_id"] for h in recorded["resolved_hints"]] == ["conn-notes"]
    assert recorded["dropped_hints"] == 0
    assert "never persisted" not in str(created.payload)


async def test_new_run_cannot_reuse_an_earlier_approval(make_kernel: MakeKernel) -> None:
    """Run 2 proposes the same action as run 1: a new digest and a new pending approval."""
    k = make_kernel(texts=["standup notes", "standup notes"])
    cid, first = await _waiting_approval(k)
    pres1 = await k.coordinator.pending_approval(TENANT, first.run_id)
    await k.coordinator.cancel(k.requester, first.run_id)
    _, second_id = await _post(k, cid, "write standup note")
    second = await k.coordinator.start_admitted_run(TENANT, second_id)
    assert second.state is RunState.WAITING_APPROVAL
    pres2 = await k.coordinator.pending_approval(TENANT, second_id)
    action1 = await k.store.get_action(TENANT, pres1.action_id)
    action2 = await k.store.get_action(TENANT, pres2.action_id)
    assert action1.arguments == action2.arguments
    assert pres2.action_id != pres1.action_id
    assert pres2.digest != pres1.digest
    assert await k.store.list_approvals(TENANT, pres2.action_id) == []
    # Run 1's digest does not decide run 2's action (review A1-4).
    with pytest.raises(KernelError) as caught:
        await k.coordinator.decide(
            actor=k.approver,
            run_id=second_id,
            action_id=pres2.action_id,
            action_digest=pres1.digest,
            expected_run_revision=pres2.run_revision,
            decision=ApprovalDecision.APPROVED,
        )
    assert caught.value.code is ErrorCode.APPROVAL_STALE
    assert await k.store.list_approvals(TENANT, pres2.action_id) == []


async def test_latest_run_does_not_depend_on_created_at_order(
    make_kernel: MakeKernel, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two runs with one ``created_at`` (the kernel suite's clock is frozen) are ordered by run
    id; the waiting run 2 sorts first, and is still the run the message answers
    (`latest_run`, ruling R2)."""
    import e_agent.kernel.conversation as conversation_module

    run_ids = iter(["run_b", "run_a"])
    monkeypatch.setattr(
        conversation_module,
        "new_id",
        lambda prefix: next(run_ids) if prefix == "run" else new_id(prefix),
    )
    k = make_kernel(driver=ClarifyDriver())
    cid, first = await _waiting(k)
    await k.coordinator.cancel(k.requester, first.run_id)
    _, second_id = await _post(k, cid, "another note")
    second = await k.coordinator.start_admitted_run(TENANT, second_id)
    runs = await k.store.list_conversation_runs(TENANT, "alice", cid)
    assert [r.run_id for r in runs] == ["run_a", "run_b"]  # the active run sorts first
    reply_to = ReplyTo(run_id="run_a", run_revision=second.revision)
    route, run_id = await _post(k, cid, "the note", reply_to=reply_to)
    assert (route.kind, run_id) == (RouteKind.ANSWER, "run_a")


async def test_concurrent_retry_replays_instead_of_refusing(
    make_kernel: MakeKernel, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Review A1-1: a retry that missed step (0) because the first request had not committed
    yet, and then sees that request's run as the active one, still replays (START, run 1)."""
    k = make_kernel()
    conv = await k.coordinator.create_conversation(k.requester)
    cid = conv.conversation_id
    first = await _post(k, cid, "write a note", key="message-race")
    original = k.store.lookup_idempotent
    misses = [None]

    async def miss_once(tenant_id: str, actor_id: str, key: str) -> Any:
        if misses:
            return misses.pop()  # the first request had not committed at step (0)
        return await original(tenant_id, actor_id, key)

    monkeypatch.setattr(k.store, "lookup_idempotent", miss_once)
    assert await _post(k, cid, "write a note", key="message-race") == first
    assert misses == []
    assert first[0] == MessageRoute(kind=RouteKind.START, run_id=first[1])
    assert len(await k.store.list_conversation_runs(TENANT, "alice", cid)) == 1
    misses.append(None)
    error = await _conflict(k, cid, "write another note", key="message-race")
    assert error.safe_message == "idempotency key reused with another request"


async def test_off_refuses_every_conversation_call(make_kernel: MakeKernel) -> None:
    """ADR 0023 §9, Task 4d.4: in ``off`` the facade refuses every conversation call with
    ``NOT_FOUND`` "conversations are off" before any store read, so nothing is written;
    the member features answer in every mode."""
    k = make_kernel(features=Features())
    owned = await k.store.create_conversation(  # a row the refusal must not reveal
        Conversation(
            tenant_id=TENANT,
            conversation_id="conv_kept",
            owner_id=k.requester.principal_id,
            revision=1,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
    )
    assert owned is None
    calls = (
        k.coordinator.create_conversation(k.requester),
        k.coordinator.list_conversations(k.requester, after=None, limit=10),
        k.coordinator.get_conversation(k.requester, "conv_kept"),
        _post(k, "conv_kept", "write a note", key="key-off-0001"),
    )
    for call in calls:
        with pytest.raises(KernelError) as refused:
            await call
        assert (refused.value.code, refused.value.safe_message) == (
            ErrorCode.NOT_FOUND,
            CONVERSATIONS_OFF,
        )
    page = await k.store.list_conversations(TENANT, k.requester.principal_id, after=None, limit=10)
    assert [c.conversation_id for c in page.items] == ["conv_kept"]
    assert await k.store.list_conversation_runs(TENANT, k.requester.principal_id, "conv_kept") == ()
    assert await k.store.lookup_idempotent(TENANT, k.requester.principal_id, "key-off-0001") is None
    assert k.coordinator.member_features() == MemberFeatures(conversations=FeatureMode.OFF)
    assert make_kernel().coordinator.member_features() == MemberFeatures(
        conversations=FeatureMode.ON
    )
