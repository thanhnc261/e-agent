"""``features.conversations: shadow`` (ADR 0023 §9, §11, ADR 0027, Task 4d.3, Review Focus 7).

``shadow`` links the runs today's client starts anyway and writes the conversation row, but
it withholds the refusal and the carried context. At admission of a run with earlier runs
it builds the carried items and the ``recent_turns`` layer ``on`` would render, records
``conversation.compared``, and gives the driver nothing. A message the router would refuse
starts an unlinked run, as ``POST /v1/runs`` would; a linked start or answer that fails in
the conversation step falls back, in the same request and under the message's own
idempotency record, to today's unlinked run or plain input, and records
``conversation.shadow_failed``. No request fails that today's path accepts; a stale
``reply_to`` is still ``CONFLICT``, as ``/inputs`` gives today.

Every test runs on both stores (``E_AGENT_TEST_STORE=postgres``, ENG-STORE-1).
"""

from __future__ import annotations

import asyncio
import dataclasses
import importlib
import json
import os
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from e_agent.contracts.approval import ApprovalDecision
from e_agent.contracts.common import new_id
from e_agent.contracts.connection import ConnectionDescriptor, ConnectionOwnership
from e_agent.contracts.context import HostContext, Principal, ResourceHint, TaskContext
from e_agent.contracts.context_pack import ContextLayer
from e_agent.contracts.conversation import MessageRoute, ReplyTo, RouteKind
from e_agent.contracts.digest import digest
from e_agent.contracts.events import RunEvent, RunEventType
from e_agent.contracts.features import FeatureMode, Features
from e_agent.contracts.plan import ActionProposal
from e_agent.contracts.run import RunRecord, RunState
from e_agent.kernel import conversation as conversation_module
from e_agent.kernel import coordinator as coordinator_module
from e_agent.kernel.context import estimate_tokens
from e_agent.kernel.continuation import _Continuation
from e_agent.kernel.conversation import SHADOW_FAILED_MESSAGES
from e_agent.kernel.errors import ErrorCode, KernelError
from e_agent.kernel.memory_conversations import InMemoryConversationStore
from e_agent.sdk.ports import (
    AskClarification,
    DriverInput,
    DriverStep,
    FinalAnswer,
    ProposeAction,
    ReadRequest,
    RequestReads,
)
from e_agent.sdk.store import ConcurrencyConflict, NotFound

from . import conftest as kernel_conftest
from .conftest import CONN, CREATE, READ, SUMMARY, TENANT, Kernel, principal
from .test_carried_context import (
    FREE_TEXT,
    TurnDriver,
    _events,
    _kernel,
    _of,
    _stored,
    _turn,
    _unlinked_turn,
)
from .test_context_assembler import UNDECLARED
from .test_conversation_routing import ClarifyDriver, _post, _waiting, _waiting_approval

MakeKernel = Callable[..., Kernel]
SHADOW = Features(conversations=FeatureMode.SHADOW, context_assembler=FeatureMode.ON)
ON = Features(conversations=FeatureMode.ON, context_assembler=FeatureMode.ON)
OFF = Features(context_assembler=FeatureMode.ON)
CORPUS = Path(__file__).parent / "fixtures" / "conversation_threads.json"
COMPARED = RunEventType.CONVERSATION_COMPARED
SHADOW_FAILED = RunEventType.CONVERSATION_SHADOW_FAILED
NO_ITEMS = {"user_messages": 0, "answers": 0, "refs": 0}
WAIT = "wait, decide the approval, or stop the run"
QUESTION_CHANGED = "the question changed; read it again"
THREAD = ("summarise the notes", "write the standup note", "summarise them again")


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


def _shadow(make_kernel: MakeKernel, **kw: Any) -> Kernel:
    return make_kernel(features=SHADOW, **kw)


def _failed(event: RunEvent, stage: str, code: ErrorCode) -> None:
    assert event.payload == {
        "stage": stage,
        "code": code.value,
        "message": SHADOW_FAILED_MESSAGES[stage],
    }


def _refused(conversation_id: str) -> dict[str, Any]:
    """``conversation.compared`` for ``route: refuse``: no carried key, no layer (ADR 0023 §11)."""
    return {
        "conversation_id": conversation_id,
        "route": "refuse",
        "carried_run_ids": [],
        "items": NO_ITEMS,
        "masked": 0,
        "dropped": 0,
    }


async def _cancelled_first(k: Kernel) -> str:
    """A conversation whose one run is cancelled, so the next message starts a run."""
    conv = await k.coordinator.create_conversation(k.requester)
    _, first = await _post(k, conv.conversation_id, "write a note")
    await k.coordinator.cancel(k.requester, first)
    k.clock.advance(seconds=1)
    return conv.conversation_id


def _stale(k: Kernel, monkeypatch: pytest.MonkeyPatch) -> None:
    """The conversation moves between the flow's read and the insert (`ConcurrencyConflict`)."""
    original = k.store.get_conversation

    async def stale(tenant_id: str, owner_id: str, conversation_id: str) -> Any:
        found = await original(tenant_id, owner_id, conversation_id)
        return found.model_copy(update={"revision": found.revision - 1})

    monkeypatch.setattr(k.store, "get_conversation", stale)


# --------------------------------------------------------------- the consumer (corpus)
ON_TENANT = "tenant-on"


@dataclass
class ThreadDriver:
    """The corpus driver, by the run's task: ``hi`` replies (an ADR 0022 reply run);
    ``question…`` asks, then reads and proposes a note; ``summarise…`` reads and answers the
    classed notes answer; anything else reads and proposes a note. Keeps every input."""

    driver_id: str = "thread-driver"
    seen: list[tuple[str, str, DriverInput]] = field(default_factory=list)

    async def advance(self, ctx: TaskContext, step_input: DriverInput) -> DriverStep:
        self.seen.append((ctx.tenant_id, ctx.run_id, step_input))
        task = step_input.task
        if step_input.action_result is not None:
            return FinalAnswer(text="done")
        if task.startswith("hi"):
            return FinalAnswer(text="hello")
        asks = task.startswith("question")
        if asks and step_input.user_input is None and not step_input.observations:
            return AskClarification(question="which one?")
        if not step_input.observations:
            read = ReadRequest(
                request_id="r1", contract_id=READ.contract_id, connection_id=CONN, arguments={}
            )
            return RequestReads(reads=(read,))
        if task.startswith("summarise"):
            count = str(step_input.observations[0].data["count"])
            arguments = {"count": count, "note_ref": "all", "comment": FREE_TEXT}
            proposal = ActionProposal(
                contract_id=SUMMARY.contract_id, connection_id=CONN, arguments=arguments
            )
            return ProposeAction(proposal=proposal)
        proposal = ActionProposal(
            contract_id=CREATE.contract_id, connection_id=CONN, arguments={"text": "corpus note"}
        )
        return ProposeAction(proposal=proposal)

    def first_layer(self, tenant_id: str, run_id: str) -> str:
        """The ``recent_turns`` layer of the run's first pack ("" when it has none)."""
        packs = [
            i.context
            for t, r, i in self.seen
            if (t, r) == (tenant_id, run_id) and i.context is not None
        ]
        assert packs, run_id
        return packs[0].dynamic_suffix.get(ContextLayer.RECENT_TURNS, "")


@dataclass
class Side:
    """One mode's kernel, in its own tenant so both modes can use the same run ids."""

    k: Kernel
    tenant: str
    requester: Principal
    approver: Principal
    driver: ThreadDriver


def _side(make_kernel: MakeKernel, features: Features, tenant: str) -> Side:
    driver = ThreadDriver()
    connection = ConnectionDescriptor(
        tenant_id=tenant,
        connection_id=CONN,
        version=1,
        integration_id="notes-mem",
        ownership=ConnectionOwnership.TENANT_SHARED,
        provider_subject="svc",
    )
    k = _kernel(make_kernel, features, driver=driver, connections=[connection])
    requester = principal("alice", {"requester"}, tenant)
    approver = principal("bob", {"approver"}, tenant)
    k = dataclasses.replace(k, requester=requester, approver=approver)
    return Side(k, tenant, requester, approver, driver)


async def _play(side: Side, thread: dict[str, Any], tag: list[str]) -> tuple[list[Any], list[str]]:
    """Play one thread; the trace of (step, route or state) and the linked started runs."""
    k, tenant = side.k, side.tenant
    shadow = k.coordinator._features.conversations is FeatureMode.SHADOW
    name = thread["name"]
    tag[0] = f"{name}-c"
    conv = await k.coordinator.create_conversation(side.requester)
    cid = conv.conversation_id
    latest: str | None = None
    trace: list[Any] = []
    started: list[str] = []
    for index, step in enumerate(thread["steps"]):
        tag[0] = f"{name}-{index:02d}"
        k.clock.advance(seconds=1)
        if "say" in step and step.get("expect") == "refuse":
            if shadow:
                route, run_id = await _post(k, cid, step["say"], who=side.requester)
                run = await k.store.get_run(tenant, run_id)
                assert route.kind is RouteKind.START and run.conversation_id is None
            else:
                with pytest.raises(KernelError) as caught:
                    await _post(k, cid, step["say"], who=side.requester)
                assert caught.value.code is ErrorCode.CONFLICT
            trace.append((index, "refused"))
            continue
        if "say" in step:
            route, run_id = await _post(k, cid, step["say"], who=side.requester)
            assert route.kind is RouteKind.START
            run = await k.coordinator.start_admitted_run(tenant, run_id)
            latest = run_id
            started.append(run_id)
        elif "answer" in step:
            assert latest is not None
            waiting = await k.store.get_run(tenant, latest)
            reply_to = ReplyTo(run_id=latest, run_revision=waiting.revision)
            route, _ = await _post(k, cid, step["answer"], reply_to=reply_to, who=side.requester)
            assert route.kind is RouteKind.ANSWER
            run = await k.coordinator.continue_input(tenant, latest)
        elif "approve" in step:
            assert latest is not None
            pres = await k.coordinator.pending_approval(tenant, latest)
            run = await k.coordinator.decide(
                actor=side.approver,
                run_id=latest,
                action_id=pres.action_id,
                action_digest=pres.digest,
                expected_run_revision=pres.run_revision,
                decision=ApprovalDecision.APPROVED,
            )
        else:
            assert step.get("cancel") and latest is not None
            run = await k.coordinator.cancel(side.requester, latest)
        if "then" in step:
            assert run.state is RunState(step["then"]), (name, index, run.reason)
        trace.append((index, run.state))
    return trace, started


def _ids(monkeypatch: pytest.MonkeyPatch, tag: list[str]) -> None:
    """Run and conversation ids named by the step that made them, the same in both modes;
    zero-padded, so listing order by id equals the step order."""

    def named(prefix: str) -> str:
        return f"{prefix}_{tag[0]}" if prefix in {"run", "conv"} else new_id(prefix)

    monkeypatch.setattr(conversation_module, "new_id", named)


async def test_shadow_layer_digest_equals_on_layer_digest(
    make_kernel: MakeKernel, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The real consumer (ADR 0027, PR-22): over the fixture thread corpus, each run admitted
    after earlier runs records, in ``shadow``, the digest and token estimate of the very
    ``recent_turns`` layer the first pack of the same run carries in ``on``. Each mode plays
    the corpus in its own tenant, with the same run ids and a frozen read time."""
    threads = json.loads(CORPUS.read_text())["threads"]
    observed = datetime(2026, 10, 21, 9, 0, tzinfo=UTC)
    monkeypatch.setattr(kernel_conftest, "utc_now", lambda: observed)
    tag = [""]
    _ids(monkeypatch, tag)
    shadow, on = _side(make_kernel, SHADOW, TENANT), _side(make_kernel, ON, ON_TENANT)

    cases = 0
    for thread in threads:
        shadow_trace, started = await _play(shadow, thread, tag)
        on_trace, on_started = await _play(on, thread, tag)
        assert shadow_trace == on_trace and started == on_started, thread["name"]
        for position, run_id in enumerate(started):
            compared = _of(await shadow.k.store.list_events(TENANT, run_id), COMPARED)
            stored = await on.k.store.load_continuation(ON_TENANT, run_id)
            assert stored is not None
            carried = _Continuation.model_validate(stored[0]["data"]).carried
            if position == 0:  # the first run of the thread has nothing to compare
                assert compared == [] and carried == ()
                continue
            (event,) = compared
            layer = on.driver.first_layer(ON_TENANT, run_id)
            assert layer, run_id
            assert event.payload["route"] == "start"
            assert event.payload["carried_run_ids"] == [c.run_id for c in carried]
            assert event.payload["layer_digest"] == digest(layer), (thread["name"], run_id)
            assert event.payload["layer_tokens"] == estimate_tokens(layer)
            assert event.payload["dropped"] == 0 and event.payload["masked"] == 0
            cases += 1
    print(f"test_shadow_layer_digest_equals_on_layer_digest: {cases} cases")
    assert cases > 0, "the corpus compared no admission"
    assert cases == 10  # hi-hi 1, hi-question 2, question-po 1, during-approval 1, six-runs 5


# ------------------------------------------------------------ what shadow never does
@pytest.mark.parametrize("assembler", [FeatureMode.ON, FeatureMode.OFF])
async def test_shadow_gives_the_driver_no_carried_item(
    make_kernel: MakeKernel, assembler: FeatureMode
) -> None:
    """Review Focus 7: a run pinned ``shadow`` with earlier runs records the comparison, and
    no ``DriverInput`` of it (pack or not) holds a carried item: no ``recent_turns`` layer,
    no earlier run id or task text; its stored continuation carries nothing."""
    features = Features(conversations=FeatureMode.SHADOW, context_assembler=assembler)
    driver = TurnDriver()
    k = _kernel(make_kernel, features, driver=driver)
    conv = await k.coordinator.create_conversation(k.requester)
    first = await _turn(k, conv.conversation_id, "summarise the notes")

    second = await _turn(k, conv.conversation_id, "write the standup note")

    (compared,) = _of(await _events(k, second.run_id), COMPARED)
    assert compared.payload["carried_run_ids"] == [first.run_id]
    inputs = [i for r, i in driver.seen if r == second.run_id]
    assert len(inputs) >= 3  # read, propose, the post-write answer
    for step_input in inputs:
        assert step_input.context is None or (
            ContextLayer.RECENT_TURNS not in step_input.context.dynamic_suffix
        )
        shown = repr(step_input)
        assert first.run_id not in shown and "summarise the notes" not in shown
    assert (assembler is FeatureMode.ON) == all(i.context is not None for i in inputs)
    stored = await k.store.load_continuation(TENANT, second.run_id)
    assert stored is not None and "carried" not in stored[0]["data"]
    types = {e.type for e in await _events(k, second.run_id)}
    assert RunEventType.CONVERSATION_CONTEXT_CARRIED not in types


async def _thread(k: Kernel) -> list[RunRecord]:
    conv = await k.coordinator.create_conversation(k.requester)
    runs = []
    for text in THREAD:
        runs.append(await _turn(k, conv.conversation_id, text))
        k.clock.advance(seconds=1)
    return runs


async def _unlinked_thread(k: Kernel) -> list[RunRecord]:
    """The thread's three tasks as today's ``POST /v1/runs`` runs: ``off`` refuses the
    conversation calls (Task 4d.4), so this is the baseline ``shadow`` is held to."""
    runs = []
    for text in THREAD:
        runs.append(await _unlinked_turn(k, text))
        k.clock.advance(seconds=1)
    return runs


async def test_shadow_adds_no_model_call_read_or_budget(make_kernel: MakeKernel) -> None:
    """ADR 0023 §9: the thread's tasks as today's unlinked runs (``off``) and as a ``shadow``
    thread make the same driver calls and provider reads and use the same budgets; the
    event logs differ only by ``conversation.compared``. The comparison reads the store,
    never a model or provider."""
    played = []
    for features in (OFF, SHADOW):
        driver = TurnDriver()
        k = _kernel(make_kernel, features, driver=driver)
        runs = await (_unlinked_thread(k) if features is OFF else _thread(k))
        calls = [sum(r == run.run_id for r, _ in driver.seen) for run in runs]
        budgets = []
        types = []
        for run in runs:
            cont = await _stored(k, run.run_id)
            budgets.append((cont.turns, cont.read_calls, cont.repairs, cont.writes))
            types.append([e.type for e in await _events(k, run.run_id) if e.type is not COMPARED])
        compared = [len(_of(await _events(k, run.run_id), COMPARED)) for run in runs]
        played.append((calls, k.backend.read_calls, k.backend.create_calls, budgets, types))
        assert compared == ([0, 0, 0] if features is OFF else [0, 1, 1])
    off, shadow = played
    assert off == shadow
    assert off[0] and all(off[0]) and off[1] > 0


async def test_shadow_failure_changes_nothing(
    make_kernel: MakeKernel, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failure building the comparison records ``conversation.shadow_failed`` with stage
    ``carry`` and a fixed message, no exception text, and changes nothing else: the run stays
    linked, carries nothing, records no ``feature.fallback``, and its event log is the
    working comparison's, with the one event swapped."""
    k = _kernel(make_kernel, SHADOW)
    working = await _thread(k)

    def broken(*args: Any) -> Any:
        raise RuntimeError("SECRET-exception-text")

    monkeypatch.setattr(coordinator_module, "carry", broken)
    failing = await _thread(k)

    for good, bad in zip(working, failing, strict=True):
        assert bad.state is good.state is RunState.SUCCEEDED
        assert bad.conversation_id is not None
        good_types = [e.type for e in await _events(k, good.run_id)]
        bad_events = await _events(k, bad.run_id)
        swapped = [SHADOW_FAILED if t is COMPARED else t for t in good_types]
        assert [e.type for e in bad_events] == swapped
        assert (await _stored(k, bad.run_id)).carried == ()
        assert not _of(bad_events, RunEventType.FEATURE_FALLBACK)
        assert "SECRET-exception-text" not in json.dumps([e.payload for e in bad_events])
    (event,) = _of(await _events(k, failing[1].run_id), SHADOW_FAILED)
    _failed(event, "carry", ErrorCode.DEPENDENCY_UNAVAILABLE)


# ------------------------------------------------------------- would-refuse messages
async def test_shadow_would_refuse_starts_an_unlinked_run_and_records_it(
    make_kernel: MakeKernel,
) -> None:
    """A message while the latest run waits for approval starts a run with
    ``conversation_id = None``, as ``POST /v1/runs`` would, and records ``route: refuse``;
    the waiting run, its action and its approval rows are untouched."""
    k = _shadow(make_kernel)
    cid, run = await _waiting_approval(k)
    pres = await k.coordinator.pending_approval(TENANT, run.run_id)
    action = await k.store.get_action(TENANT, pres.action_id)
    events = await k.store.list_events(TENANT, run.run_id)

    route, run_id = await _post(k, cid, "yes, approve it")

    assert route == MessageRoute(kind=RouteKind.START, run_id=run_id) and run_id != run.run_id
    started = await k.store.get_run(TENANT, run_id)
    assert (started.conversation_id, started.state, started.task) == (
        None,
        RunState.CREATED,
        "yes, approve it",
    )
    (compared,) = _of(await _events(k, run_id), COMPARED)
    assert compared.payload == _refused(cid)
    assert [r.run_id for r in await k.store.list_conversation_runs(TENANT, "alice", cid)] == [
        run.run_id
    ]
    after = await k.store.get_action(TENANT, pres.action_id)
    assert (after.revision, after.state) == (action.revision, action.state)
    assert await k.store.list_events(TENANT, run.run_id) == events
    assert await k.store.list_approvals(TENANT, pres.action_id) == []


async def test_shadow_message_without_reply_to_while_waiting_starts_unlinked(
    make_kernel: MakeKernel,
) -> None:
    """A message without ``reply_to`` while the latest run waits for input is a new task for
    today's client: an unlinked run with ``route: refuse``; the question stays pending."""
    k = _shadow(make_kernel, driver=ClarifyDriver())
    cid, run = await _waiting(k)
    route, run_id = await _post(k, cid, "something else entirely")
    assert route.kind is RouteKind.START
    assert (await k.store.get_run(TENANT, run_id)).conversation_id is None
    (compared,) = _of(await _events(k, run_id), COMPARED)
    assert compared.payload == _refused(cid)
    still = await k.store.get_run(TENANT, run.run_id)
    assert (still.state, still.revision) == (RunState.WAITING_INPUT, run.revision)


async def test_shadow_stale_reply_to_still_conflicts(
    make_kernel: MakeKernel, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ruling 2: a ``reply_to`` for an earlier question is ``CONFLICT``, as ``/inputs`` gives
    today; no run starts anywhere (no store method that creates a run is called, linked or
    not, and the message's key is unrecorded) and nothing is recorded."""
    k = _shadow(make_kernel, driver=ClarifyDriver())
    cid, q1 = await _waiting(k)
    n = q1.revision
    await _post(k, cid, "the standup note", reply_to=ReplyTo(run_id=q1.run_id, run_revision=n))
    q2 = await k.coordinator.continue_input(TENANT, q1.run_id)
    assert q2.state is RunState.WAITING_INPUT
    created: list[str] = []
    for name in ("create_run", "create_run_idempotent", "create_run_in_conversation"):

        async def creates(*args: Any, _name: str = name, **kw: Any) -> Any:
            created.append(_name)
            raise AssertionError(f"{_name} called for a stale reply_to")

        monkeypatch.setattr(k.store, name, creates)
    with pytest.raises(KernelError) as caught:
        await _post(
            k,
            cid,
            "typed for Q1",
            reply_to=ReplyTo(run_id=q1.run_id, run_revision=n),
            key="stale-1",
        )
    monkeypatch.undo()
    assert (caught.value.code, caught.value.safe_message) == (ErrorCode.CONFLICT, QUESTION_CHANGED)
    assert created == []
    assert await k.store.lookup_idempotent(TENANT, "alice", "stale-1") is None
    assert [r.run_id for r in await k.store.list_conversation_runs(TENANT, "alice", cid)] == [
        q1.run_id
    ]
    assert not _of(await _events(k, q1.run_id), SHADOW_FAILED)


# -------------------------------------------------------------------- start fallbacks
async def test_shadow_stale_revision_falls_back_to_an_unlinked_run(
    make_kernel: MakeKernel, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A ``ConcurrencyConflict`` from the revision check falls back, in the same request, to
    today's unlinked run, which records ``conversation.shadow_failed`` (stage ``start``,
    ``CONFLICT``); the request does not fail and the conversation gains no run."""
    k = _shadow(make_kernel)
    cid = await _cancelled_first(k)
    _stale(k, monkeypatch)

    route, run_id = await _post(k, cid, "write another note")

    assert route == MessageRoute(kind=RouteKind.START, run_id=run_id)
    run = await k.store.get_run(TENANT, run_id)
    assert (run.conversation_id, run.state) == (None, RunState.CREATED)
    events = await _events(k, run_id)
    (failed,) = _of(events, SHADOW_FAILED)
    _failed(failed, "start", ErrorCode.CONFLICT)
    assert not _of(events, COMPARED)
    assert len(await k.store.list_conversation_runs(TENANT, "alice", cid)) == 1


class StoreDown(Exception):
    """A store error with no kernel meaning."""


@pytest.mark.parametrize(
    ("raised", "code"),
    [
        (NotFound("conversation"), ErrorCode.NOT_FOUND),
        (StoreDown("SECRET-store-text"), ErrorCode.DEPENDENCY_UNAVAILABLE),
        (ConcurrencyConflict("has an active run"), ErrorCode.CONFLICT),
    ],
)
async def test_shadow_linked_start_failure_falls_back(
    make_kernel: MakeKernel, monkeypatch: pytest.MonkeyPatch, raised: Exception, code: ErrorCode
) -> None:
    """A missing conversation, a store error on the conversation row, or the active-run
    check failing at the insert: today's unlinked run, with the failure's kernel code and
    no exception text."""
    k = _shadow(make_kernel)
    cid = await _cancelled_first(k)

    async def fails(*args: Any, **kw: Any) -> Any:
        raise raised

    monkeypatch.setattr(k.store, "create_run_in_conversation", fails)
    route, run_id = await _post(k, cid, "write another note")

    assert route.kind is RouteKind.START
    assert (await k.store.get_run(TENANT, run_id)).conversation_id is None
    events = await _events(k, run_id)
    (failed,) = _of(events, SHADOW_FAILED)
    _failed(failed, "start", code)
    assert "SECRET" not in json.dumps([e.payload for e in events])


async def test_shadow_concurrent_pair_starts_two_runs_as_today(
    make_kernel: MakeKernel, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two messages that both read the conversation before either admits: one run is linked,
    the other loses the revision check and starts unlinked with ``conversation.shadow_failed``;
    neither request fails (today's client would have started both)."""
    k = _shadow(make_kernel)
    conv = await k.coordinator.create_conversation(k.requester)
    cid = conv.conversation_id
    listed = k.store.list_conversation_runs
    arrived: list[str] = []
    both = asyncio.Event()

    async def barrier(tenant_id: str, owner_id: str, conversation_id: str) -> Any:
        runs = await listed(tenant_id, owner_id, conversation_id)
        if len(arrived) < 2:  # only the two routing reads wait for each other
            arrived.append(conversation_id)
            if len(arrived) == 2:
                both.set()
            await asyncio.wait_for(both.wait(), timeout=5)
        return runs

    monkeypatch.setattr(k.store, "list_conversation_runs", barrier)
    results = await asyncio.gather(
        _post(k, cid, "write a note", key="pair-1"),
        _post(k, cid, "write another note", key="pair-2"),
    )
    monkeypatch.undo()

    assert len(arrived) == 2
    assert {route.kind for route, _ in results} == {RouteKind.START}
    runs = [await k.store.get_run(TENANT, run_id) for _, run_id in results]
    linked = [r for r in runs if r.conversation_id == cid]
    unlinked = [r for r in runs if r.conversation_id is None]
    assert len(linked) == len(unlinked) == 1
    assert not _of(await _events(k, linked[0].run_id), SHADOW_FAILED)
    (failed,) = _of(await _events(k, unlinked[0].run_id), SHADOW_FAILED)
    _failed(failed, "start", ErrorCode.CONFLICT)
    listed_runs = await k.store.list_conversation_runs(TENANT, "alice", cid)
    assert [r.run_id for r in listed_runs] == [linked[0].run_id]


async def test_shadow_fallback_reuses_the_idempotency_key(
    make_kernel: MakeKernel, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The fallback admits under the message's own key: a retry after it, with nothing
    patched any more, returns the same run; the key with another text is ``CONFLICT``. A
    would-refuse fallback replays the same way."""
    k = _shadow(make_kernel)
    cid = await _cancelled_first(k)
    _stale(k, monkeypatch)
    first = await _post(k, cid, "write another note", key="retry-1")
    monkeypatch.undo()

    assert await _post(k, cid, "write another note", key="retry-1") == first
    with pytest.raises(KernelError) as caught:
        await _post(k, cid, "a different note", key="retry-1")
    assert caught.value.safe_message == "idempotency key reused with another request"
    assert (await k.store.get_run(TENANT, first[1])).conversation_id is None
    assert len(await k.store.list_conversation_runs(TENANT, "alice", cid)) == 1

    approval_cid, _ = await _waiting_approval(k)
    refused = await _post(k, approval_cid, "yes, approve it", key="retry-2")
    assert await _post(k, approval_cid, "yes, approve it", key="retry-2") == refused
    assert len(_of(await _events(k, refused[1]), COMPARED)) == 1


async def test_shadow_start_carries_host_context_as_create_run(
    make_kernel: MakeKernel, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A shadow start, linked or fallen back, records the same ``host_context`` in
    ``run.created`` (resolved hints, no selection text) as ``admit_run``, the path of
    ``POST /v1/runs``, with the same ``host_context``."""
    k = _shadow(make_kernel)
    host = HostContext(
        host_kind="embedded",
        page_url_origin="https://notes.example",
        locale="en",
        resource_hints=(
            ResourceHint(system_hint="notes-mem", resource_type_hint="note", external_id_hint="n1"),
            ResourceHint(system_hint="elsewhere", resource_type_hint="x", external_id_hint="y"),
        ),
        selection_text="SELECTION-never-persisted",
    )
    conv = await k.coordinator.create_conversation(k.requester)
    _, linked = await _post(k, conv.conversation_id, "write a note", host_context=host)
    await k.coordinator.cancel(k.requester, linked)
    _stale(k, monkeypatch)
    _, fallen = await _post(k, conv.conversation_id, "write a note", host_context=host)
    monkeypatch.undo()
    plain, _ = await k.coordinator.admit_run(
        k.requester,
        "write a note",
        k.scope,
        run_id=new_id("run"),
        idempotency_key="create-run-1",
        request_digest="d",
        host_context=host,
    )

    recorded = []
    for run_id in (linked, fallen, plain):
        created = (await _events(k, run_id))[0]
        assert created.type is RunEventType.RUN_CREATED
        assert "SELECTION-never-persisted" not in json.dumps(created.payload)
        recorded.append(created.payload["host_context"])
    assert recorded[0] == recorded[1] == recorded[2]
    assert [h["connection_id"] for h in recorded[0]["resolved_hints"]] == [CONN]
    assert recorded[0]["dropped_hints"] == 1
    assert (await k.store.get_run(TENANT, linked)).conversation_id == conv.conversation_id
    assert (await k.store.get_run(TENANT, fallen)).conversation_id is None


# ------------------------------------------------------------------- answer fallbacks
async def test_shadow_conversation_error_falls_back_to_plain_input(
    make_kernel: MakeKernel, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A store error reading the conversation, for an answer: a plain ``accept_input``, as
    ``/inputs`` would take it, which records ``conversation.shadow_failed`` (stage ``answer``)
    and queues the input work; a retry is the same answer. Without ``reply_to`` the same
    error starts today's unlinked run."""
    k = _shadow(make_kernel, driver=ClarifyDriver())
    cid, run = await _waiting(k)
    reply_to = ReplyTo(run_id=run.run_id, run_revision=run.revision)

    async def down(*args: Any, **kw: Any) -> Any:
        raise StoreDown("SECRET-store-text")

    monkeypatch.setattr(k.store, "list_conversation_runs", down)
    answered = await _post(k, cid, "the standup note", reply_to=reply_to, key="answer-1")
    retried = await _post(k, cid, "the standup note", reply_to=reply_to, key="answer-1")
    route, started = await _post(k, cid, "a new task")
    monkeypatch.undo()

    expected = MessageRoute(kind=RouteKind.ANSWER, run_id=run.run_id, run_revision=run.revision)
    assert answered == retried == (expected, run.run_id)
    events = await _events(k, run.run_id)
    assert len(_of(events, RunEventType.INPUT_RECEIVED)) == 1
    (failed,) = _of(events, SHADOW_FAILED)
    _failed(failed, "answer", ErrorCode.DEPENDENCY_UNAVAILABLE)
    assert await k.store.has_pending_work(TENANT, run.run_id)
    _, plain = await _waiting(k)  # the same answer through `accept_input`, as /inputs takes it
    await k.coordinator.accept_input(
        k.requester, plain.run_id, "the standup note", plain.revision, enqueue=True
    )
    queued = {}
    for _ in range(12):  # one live claim per run: finish each before the next
        claim = await k.store.claim_work("test-owner")
        if claim is None:
            break
        queued[(claim.run_id, claim.kind)] = claim.payload
        await k.store.finish_work(claim)
    assert queued[(run.run_id, "input")] == queued[(plain.run_id, "input")] == {}
    resumed = await k.coordinator.continue_input(TENANT, run.run_id)
    assert resumed.state is RunState.WAITING_INPUT  # Q2: the run went on as /inputs would
    assert route.kind is RouteKind.START
    assert (await k.store.get_run(TENANT, started)).conversation_id is None
    (start_failed,) = _of(await _events(k, started), SHADOW_FAILED)
    _failed(start_failed, "start", ErrorCode.DEPENDENCY_UNAVAILABLE)
    assert "SECRET" not in json.dumps([e.payload for e in events])


async def test_shadow_conversation_error_with_foreign_reply_to_is_not_found(
    make_kernel: MakeKernel, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Plan invariant 5 (never ``FORBIDDEN``): when the conversation read fails, a
    ``reply_to`` naming another user's run, or no run, is ``NOT_FOUND`` with the fixed
    message of step (2), before any replay check, and that run receives nothing. The
    caller's own run is still a plain ``accept_input``."""
    k = _shadow(make_kernel, driver=ClarifyDriver())
    cid, own = await _waiting(k)
    carol = principal("carol", {"requester"})
    carol_conv = await k.coordinator.create_conversation(carol)
    _, carol_id = await _post(k, carol_conv.conversation_id, "carol's task", who=carol)
    carol_run = await k.coordinator.start_admitted_run(TENANT, carol_id)
    assert carol_run.state is RunState.WAITING_INPUT
    replays: list[Any] = []
    replayed = k.coordinator.input_replayed

    async def spy(*args: Any, **kw: Any) -> bool:
        replays.append(args[2])
        return await replayed(*args, **kw)

    async def down(*args: Any, **kw: Any) -> Any:
        raise StoreDown("store down")

    monkeypatch.setattr(k.coordinator, "input_replayed", spy)
    monkeypatch.setattr(k.store, "list_conversation_runs", down)
    messages = set()
    for foreign in (
        ReplyTo(run_id=carol_id, run_revision=carol_run.revision),
        ReplyTo(run_id="run_absent", run_revision=1),
    ):
        with pytest.raises(KernelError) as caught:
            await _post(k, cid, "the note", reply_to=foreign)
        assert caught.value.code is ErrorCode.NOT_FOUND
        messages.add(caught.value.safe_message)
    assert messages == {"conversation not found"}
    assert replays == []
    route, run_id = await _post(
        k, cid, "the note", reply_to=ReplyTo(run_id=own.run_id, run_revision=own.revision)
    )
    monkeypatch.undo()

    assert (route.kind, run_id, replays) == (RouteKind.ANSWER, own.run_id, [own.run_id])
    carol_events = await _events(k, carol_id)
    assert not _of(carol_events, RunEventType.INPUT_RECEIVED)
    assert not _of(carol_events, SHADOW_FAILED)
    (failed,) = _of(await _events(k, own.run_id), SHADOW_FAILED)
    _failed(failed, "answer", ErrorCode.DEPENDENCY_UNAVAILABLE)


async def test_shadow_answer_fallback_is_one_write(
    make_kernel: MakeKernel, monkeypatch: pytest.MonkeyPatch
) -> None:
    """PR-17: an answer fallback (stage ``answer``, then stage ``reply_to``) writes the run
    once: ``input.received``, its state change and ``conversation.shadow_failed`` in one
    ``update_run`` with the input work, so no failure can leave a ``RUNNING`` run without
    work or without its event."""
    k = _shadow(make_kernel, driver=ClarifyDriver())
    cid, run = await _waiting(k)
    _, unlinked_id = await _post(k, cid, "a new task")  # would refuse: unlinked
    unlinked = await k.coordinator.start_admitted_run(TENANT, unlinked_id)
    update_run = k.store.update_run
    writes: list[tuple[str, list[RunEventType], Any]] = []

    async def spy(record: RunRecord, expected: int, events: Any, **kw: Any) -> Any:
        writes.append((record.run_id, [e[0] for e in events], kw.get("work")))
        return await update_run(record, expected, events, **kw)

    async def down(*args: Any, **kw: Any) -> Any:
        raise StoreDown("store down")

    for target, stage in ((run, "answer"), (unlinked, "reply_to")):
        reply_to = ReplyTo(run_id=target.run_id, run_revision=target.revision)
        writes.clear()
        monkeypatch.setattr(k.store, "update_run", spy)
        if stage == "answer":
            monkeypatch.setattr(k.store, "list_conversation_runs", down)
        await _post(k, cid, "the note", reply_to=reply_to)
        monkeypatch.undo()

        ((run_id, types, work),) = writes
        assert run_id == target.run_id
        assert types == [
            RunEventType.INPUT_RECEIVED,
            RunEventType.RUN_STATE_CHANGED,
            SHADOW_FAILED,
        ]
        assert work is not None and work[0] == "input"
        (failed,) = _of(await _events(k, target.run_id), SHADOW_FAILED)
        _failed(
            failed,
            stage,
            ErrorCode.DEPENDENCY_UNAVAILABLE if stage == "answer" else ErrorCode.NOT_FOUND,
        )
        assert await k.store.has_pending_work(TENANT, target.run_id)


async def test_shadow_answer_to_own_unlinked_run_is_plain_input(
    make_kernel: MakeKernel, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A ``reply_to`` naming the caller's own unlinked run (made by a fallback) is a plain
    ``accept_input``, as ``/inputs`` would take it, and records ``conversation.shadow_failed``
    (stage ``reply_to``); a retry is the same answer. Another user's unlinked run is still
    ``NOT_FOUND``, before any replay check."""
    k = _shadow(make_kernel, driver=ClarifyDriver())
    cid, run = await _waiting(k)
    _, unlinked_id = await _post(k, cid, "a new task")  # would refuse: unlinked
    unlinked = await k.coordinator.start_admitted_run(TENANT, unlinked_id)
    assert (unlinked.state, unlinked.conversation_id) == (RunState.WAITING_INPUT, None)
    reply_to = ReplyTo(run_id=unlinked_id, run_revision=unlinked.revision)

    first = await _post(k, cid, "the note", reply_to=reply_to, key="own-1")
    retried = await _post(k, cid, "the note", reply_to=reply_to, key="own-1")

    expected = MessageRoute(
        kind=RouteKind.ANSWER, run_id=unlinked_id, run_revision=unlinked.revision
    )
    assert first == retried == (expected, unlinked_id)
    events = await _events(k, unlinked_id)
    assert len(_of(events, RunEventType.INPUT_RECEIVED)) == 1
    (failed,) = _of(events, SHADOW_FAILED)
    _failed(failed, "reply_to", ErrorCode.NOT_FOUND)
    assert (await k.store.get_run(TENANT, unlinked_id)).state is RunState.RUNNING
    assert await k.store.has_pending_work(TENANT, unlinked_id)
    still = await k.store.get_run(TENANT, run.run_id)
    assert (still.state, still.revision) == (RunState.WAITING_INPUT, run.revision)

    carol = principal("carol", {"requester"})
    carol_conv = await k.coordinator.create_conversation(carol)
    carol_cid = carol_conv.conversation_id
    await _post(k, carol_cid, "carol's task", who=carol)
    _, carol_unlinked = await _post(k, carol_cid, "carol's next task", who=carol)
    carol_run = await k.coordinator.start_admitted_run(TENANT, carol_unlinked)
    assert carol_run.conversation_id is None
    calls: list[Any] = []

    async def spy(*args: Any, **kw: Any) -> bool:
        calls.append(args)
        raise AssertionError("no replay check may run for a foreign reply_to")

    monkeypatch.setattr(k.coordinator, "input_replayed", spy)
    foreign = ReplyTo(run_id=carol_unlinked, run_revision=carol_run.revision)
    with pytest.raises(KernelError) as caught:
        await _post(k, cid, "the note", reply_to=foreign)
    assert caught.value.code is ErrorCode.NOT_FOUND
    assert calls == []
    assert not _of(await _events(k, carol_unlinked), RunEventType.INPUT_RECEIVED)


# --------------------------------------------------------------------------- privacy
async def test_compared_event_holds_no_value_or_text(make_kernel: MakeKernel) -> None:
    """``conversation.compared`` holds ids, counts, a digest and an estimate, never user
    text, a carried value or a fence (PR-26). On the local route the layer keeps the
    answer's values and the user's text; the payload names neither. On a hosted route
    without ``data_processing`` the earlier run's text is masked in the layer, and only the
    ``masked`` count says so."""
    k = _kernel(make_kernel, SHADOW)
    conv = await k.coordinator.create_conversation(k.requester)
    first = await _turn(k, conv.conversation_id, "summarise the PRIVATE-standup notes")
    k.clock.advance(seconds=1)
    second = await _turn(k, conv.conversation_id, "write the SECRET-follow-up note")
    (compared,) = _of(await _events(k, second.run_id), COMPARED)
    payload = compared.payload

    assert set(payload) == {
        "conversation_id",
        "route",
        "carried_run_ids",
        "items",
        "layer_digest",
        "layer_tokens",
        "masked",
        "dropped",
    }
    assert payload["conversation_id"] == conv.conversation_id
    assert payload["route"] == "start" and payload["carried_run_ids"] == [first.run_id]
    assert payload["items"] == {"user_messages": 1, "answers": 1, "refs": 1}
    assert (payload["masked"], payload["dropped"]) == (0, 0)
    assert str(payload["layer_digest"]).startswith("jcs-sha256-v1:")
    assert isinstance(payload["layer_tokens"], int) and payload["layer_tokens"] > 0
    shown = json.dumps(payload)
    for text in ("PRIVATE", "SECRET", "standup", FREE_TEXT, '"all"', '"0"', "untrusted-data"):
        assert text not in shown, text

    hosted = _kernel(make_kernel, SHADOW, route=UNDECLARED)
    conv = await hosted.coordinator.create_conversation(hosted.requester)
    _, earlier = await _post(hosted, conv.conversation_id, "PRIVATE-first-task")
    await hosted.coordinator.cancel(hosted.requester, earlier)
    hosted.clock.advance(seconds=1)
    _, run_id = await _post(hosted, conv.conversation_id, "the SECRET-next-task")
    (masked,) = _of(await _events(hosted, run_id), COMPARED)
    assert masked.payload["items"] == {"user_messages": 1, "answers": 0, "refs": 0}
    assert masked.payload["masked"] == 1
    assert "PRIVATE" not in json.dumps(masked.payload)
