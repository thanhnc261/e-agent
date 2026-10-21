"""A fixture conversation thread end to end through the HTTP routes (Task 4d.5).

"hi" → "which products are short?" → "draft a PO for it", with the ERP fixture profile and
``conversations`` ``on`` (with ``context_assembler`` ``on``, ADR 0023 §9), then the same thread
in ``shadow``. Run 1 is the greeting's reply run (ADR 0023 §5), answered by the question: it
reads the demand, the stock and the offers and ends with a ``VERIFIED`` shortage answer. Run 2
starts after run 1 ends, carries run 1's checked facts in its pack's ``recent_turns`` layer
(ADR 0023 §6-§8, D17), reads again and proposes the draft PO, which is decided through
``/v1/runs/{id}/approvals`` only (ADR 0023 §4).

The plugin's scripted driver plays one task kind per runtime, so `ThreadDriver` stands in for
the model's choice of task: it composes the plugin's own scripted procurement drivers (the
shortage answer and the draft PO, default refs) by the run's task text, and keeps every driver
input so the tests can read the packs the model would see. It keeps no state between turns.

Every test runs on both stores: ``E_AGENT_TEST_STORE=postgres`` gives the server a
PostgreSQL ledger at ``E_AGENT_TEST_PG_DSN``, truncated per app (ENG-STORE-1, PL-5).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest
from e_agent.contracts.common import new_id
from e_agent.contracts.context import TaskContext
from e_agent.contracts.context_pack import ContextLayer, ContextPack
from e_agent.contracts.features import FeatureMode, Features
from e_agent.kernel.continuation import _Continuation
from e_agent.kernel.conversation import WAIT_FOR_RUN
from e_agent.plugins.erp.domain.procurement import (
    CREATE_DRAFT_PO,
    DEMAND_READ,
    SHORTAGE_ANSWER,
)
from e_agent.plugins.erp.domain.testing.scripted_driver import ScriptedProcurementDriver
from e_agent.sdk.ports import DriverInput, DriverStep, FinalAnswer

from .test_conversation_api import Api, _api, _bundle, _events, _reply_to

ON = Features(conversations=FeatureMode.ON, context_assembler=FeatureMode.ON)
SHADOW = Features(conversations=FeatureMode.SHADOW, context_assembler=FeatureMode.ON)
PER_RUN = Features(context_assembler=FeatureMode.ON)
CONN = "conn-fixture-erp"
GREETING, QUESTION, DRAFT, APPROVE_TEXT = (
    "hi",
    "which products are short?",
    "draft a PO for it",
    "approve it",
)
GREETING_REPLY = "Hello. What would you like to know about procurement?"
DONE = {"SUCCEEDED", "FAILED", "CANCELLED"}


@dataclass
class ThreadDriver:
    """By the run's task text, as the model would choose: a task that asks for a draft PO is
    the scripted draft-PO driver; a fresh turn of any other task with nothing to work on (no
    user input, read, finding or result) is a plain reply, which the kernel turns into a reply
    run waiting for input (ADR 0022); every later turn of it is the scripted shortage driver,
    since the kernel passes no ``user_input`` after reads. Keeps every driver input."""

    driver_id: str = "conversation-thread-driver"
    seen: list[tuple[str, DriverInput]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._draft = ScriptedProcurementDriver(connection_id=CONN, task_kind="draft-po")
        self._shortage = ScriptedProcurementDriver(connection_id=CONN, task_kind="shortage")

    async def advance(self, ctx: TaskContext, step_input: DriverInput) -> DriverStep:
        self.seen.append((ctx.run_id, step_input))
        if "draft a po" in step_input.task.lower():
            return await self._draft.advance(ctx, step_input)
        fresh = not (
            step_input.user_input
            or step_input.observations
            or step_input.findings
            or step_input.action_result is not None
        )
        if fresh or (step_input.user_input and "short" not in step_input.user_input):
            return FinalAnswer(text=GREETING_REPLY)
        return await self._shortage.advance(ctx, step_input)

    def packs(self, run_id: str) -> list[ContextPack]:
        return [i.context for r, i in self.seen if r == run_id and i.context is not None]

    def inputs(self, run_id: str) -> list[DriverInput]:
        return [i for r, i in self.seen if r == run_id]


# ------------------------------------------------------------------------------ helpers
def _types(api: Api, run_id: str) -> list[str]:
    return [e["type"] for e in _events(api, run_id)]


def _of(api: Api, run_id: str, kind: str) -> list[dict[str, Any]]:
    return [e for e in _events(api, run_id) if e["type"] == kind]


def _run(api: Api, run_id: str) -> dict[str, Any]:
    body: dict[str, Any] = api.client.get(f"/v1/runs/{run_id}").json()
    return body


def _actions(api: Api, run_id: str) -> list[Any]:
    return list(api.call(api.runtime.store.list_actions, api.runtime.operator.tenant_id, run_id))


def _carried(api: Api, run_id: str) -> tuple[Any, ...]:
    stored = api.call(api.runtime.store.load_continuation, api.runtime.operator.tenant_id, run_id)
    assert stored is not None
    return _Continuation.model_validate(stored[0]["data"]).carried


def _approve(api: Api, run_id: str) -> dict[str, Any]:
    """Decide the pending approval through ``/v1/runs/{id}/approvals`` and wait for the end."""
    pres = _run(api, run_id)["pending_approval"]
    r = api.post(
        f"/v1/runs/{run_id}/approvals",
        {
            "action_id": pres["action_id"],
            "digest": pres["digest"],
            "expected_revision": pres["run_revision"],
            "decision": "approved",
        },
    )
    assert r.status_code == 202, r.text
    done: dict[str, Any] = api.wait(run_id, DONE)["run"]
    return done


def _start(api: Api, cid: str, text: str, **body: Any) -> str:
    r = api.message(cid, text, **body)
    assert r.status_code == 202, r.text
    assert r.json()["route"] == "start", r.json()
    return str(r.json()["run_id"])


def _first_run(api: Api, cid: str) -> dict[str, Any]:
    """Run 1: "hi" waits for input as a reply run; the question answers it."""
    first = _start(api, cid, GREETING)
    waiting = api.wait(first, {"WAITING_INPUT"})["run"]
    (asked,) = _of(api, first, "input.requested")
    assert asked["payload"] == {"question": GREETING_REPLY, "kind": "reply"}
    r = api.message(cid, QUESTION, reply_to=_reply_to(waiting))
    assert (r.status_code, r.json()) == (202, {"route": "answer", "run_id": first})
    done: dict[str, Any] = api.wait(first, DONE, after_revision=waiting["revision"])["run"]
    return done


def _verified_answer(api: Api, run_id: str) -> Any:
    (answer,) = [a for a in _actions(api, run_id) if a.contract_id == SHORTAGE_ANSWER]
    assert answer.state == "VERIFIED", answer.state
    return answer


def _outcome(api: Api, run_id: str) -> dict[str, Any]:
    """What a run ended with: its state and reason code, its actions' contracts, states and
    arguments, and its event types without the conversation's own events."""
    run = _run(api, run_id)["run"]
    return {
        "state": run["state"],
        "reason_code": run.get("reason_code"),
        "actions": [
            (a.contract_id, str(a.state), dict(a.arguments)) for a in _actions(api, run_id)
        ],
        "events": [t for t in _types(api, run_id) if not t.startswith("conversation.")],
    }


@pytest.fixture
def driver() -> ThreadDriver:
    return ThreadDriver()


# --------------------------------------------------------------------------------- on
def test_two_run_thread_carries_first_run_findings(
    driver: ThreadDriver, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two runs in one conversation. Run 2's carried layer holds run 1's ``VERIFIED``
    shortage answer: its ``shortage`` equals run 1's and its ``demand_ref`` is the demand run 1
    read with ``procurement.demand.read.v1`` (D17 (a), ADR 0023 §7). Run 2 never asks the user
    anything, reads before it proposes, and its approval is decided through the approvals
    route only: "approve it" as a message is refused and writes no decision."""
    with _api(ON, driver) as api:
        decided: list[str] = []
        enqueue = api.runtime.store.enqueue_work

        async def spy(tenant_id: str, run_id: str, kind: str, *args: Any, **kw: Any) -> Any:
            decided.extend([run_id] if kind == "decide" else [])
            return await enqueue(tenant_id, run_id, kind, *args, **kw)

        monkeypatch.setattr(api.runtime.store, "enqueue_work", spy)
        cid = api.create()

        first = _first_run(api, cid)
        assert (first["state"], first["reason_code"]) == ("SUCCEEDED", "answered")
        answer = _verified_answer(api, first["run_id"])

        second = _start(api, cid, DRAFT)
        waiting_body = api.wait(second, {"WAITING_APPROVAL"})
        waiting, pending = waiting_body["run"], waiting_body["pending_approval"]

        # two runs, run 2 carrying run 1
        snapshot = api.client.get(f"/v1/conversations/{cid}").json()
        assert [r["run_id"] for r in snapshot["runs"]] == [first["run_id"], second]
        (carried_event,) = _of(api, second, "conversation.context_carried")
        assert carried_event["payload"]["carried_run_ids"] == [first["run_id"]]

        # the carried layer: run 1's verified shortage answer, its shortage and its demand
        (item,) = _carried(api, second)
        assert item.run_id == first["run_id"]
        assert item.user_messages == (GREETING, QUESTION)
        (carried_answer,) = item.answers
        assert carried_answer.contract_id == SHORTAGE_ANSWER
        shortage = carried_answer.arguments["shortage"]
        demand_ref = carried_answer.arguments["demand_ref"]
        assert (shortage, demand_ref) == (
            answer.arguments["shortage"],
            answer.arguments["demand_ref"],
        )
        assert shortage != "0"
        demand_reads = [r for r in item.refs if r.contract_id == DEMAND_READ]
        assert [r.source_ref for r in demand_reads] == [demand_ref]
        opening = driver.inputs(second)[0]  # run 2's first turn, before it read anything
        assert opening.observations == () and opening.context is not None
        packs = driver.packs(second)
        assert packs[0] is opening.context
        for pack in packs:  # every pack of run 2 renders it
            layer = pack.dynamic_suffix[ContextLayer.RECENT_TURNS]
            assert first["run_id"] in layer and demand_ref in layer and shortage in layer

        # run 2 never re-asks: no question event at all, so none names the shortage
        assert not _of(api, second, "input.requested")
        assert all(i.user_input is None for i in driver.inputs(second))

        # run 2 reads before it proposes, and proposes from its own reads
        reads = [e["sequence"] for e in _of(api, second, "read.recorded")]
        (proposed,) = [e["sequence"] for e in _of(api, second, "proposal.created")]
        assert reads and max(reads) < proposed
        assert {e["payload"]["contract_id"] for e in _of(api, second, "read.recorded")} >= {
            DEMAND_READ
        }
        cited = {e["id"] for e in pending["canonical_proposal"]["evidence"]}
        own = {e["payload"]["evidence_id"] for e in _of(api, second, "read.recorded")}
        earlier = {e["payload"]["evidence_id"] for e in _of(api, first["run_id"], "read.recorded")}
        assert cited and cited <= own and not cited & earlier  # carried facts are no evidence
        (po,) = [a for a in _actions(api, second) if a.contract_id == CREATE_DRAFT_PO]
        assert po.arguments["demand_ref"] == demand_ref
        assert po.arguments["quantity"] == shortage

        # a message is never a decision; the approvals route is
        r = api.message(cid, APPROVE_TEXT)
        assert r.status_code == 409
        assert (r.json()["code"], r.json()["message"]) == ("CONFLICT", WAIT_FOR_RUN)
        assert _run(api, second)["run"]["revision"] == waiting["revision"]
        assert not _of(api, second, "approval.decided") and decided == []
        assert len(api.client.get(f"/v1/conversations/{cid}").json()["runs"]) == 2

        done = _approve(api, second)
        assert done["state"] == "SUCCEEDED", done
        assert decided == [second]
        (decision,) = _of(api, second, "approval.decided")
        assert decision["payload"]["decision"] == "approved"
        assert [(a.action_id, a.state) for a in _actions(api, second)] == [
            (po.action_id, "VERIFIED")
        ]
        states = [e["payload"]["to"] for e in _of(api, second, "run.state_changed")]
        assert "WAITING_APPROVAL" in states and "WAITING_INPUT" not in states
        assert not _of(api, second, "input.requested")


# ----------------------------------------------------------------------------- shadow
def _per_run_thread(api: Api) -> tuple[str, str, str]:
    """The thread as today's per-run client runs it: ``POST /v1/runs``, ``/inputs`` and the
    approvals route, "approve it" posted as its own run while run 2 waits for approval."""

    def start(text: str) -> str:
        r = api.post("/v1/runs", {"task": text}, key=new_id("key"))
        assert r.status_code == 202, r.text
        return str(r.json()["run_id"])

    first = start(GREETING)
    waiting = api.wait(first, {"WAITING_INPUT"})["run"]
    body = {"input": QUESTION, "expected_revision": waiting["revision"]}
    assert api.post(f"/v1/runs/{first}/inputs", body).status_code == 202
    api.wait(first, DONE, after_revision=waiting["revision"])
    second = start(DRAFT)
    api.wait(second, {"WAITING_APPROVAL"})
    third = start(APPROVE_TEXT)
    api.wait(third, {"WAITING_INPUT"})
    _approve(api, second)
    return first, second, third


def test_thread_in_shadow_matches_per_run_behaviour(driver: ThreadDriver) -> None:
    """``conversations: shadow`` gives the per-run outcomes: the same states, reason codes,
    actions and events as the thread run through ``/v1/runs``, plus ``conversation.compared``
    and no carried item for the driver. "approve it" while run 2 waits for approval starts an
    unlinked run (``route: refuse``) and changes nothing in run 2."""
    with _api(PER_RUN, ThreadDriver()) as api:
        baseline = [_outcome(api, run_id) for run_id in _per_run_thread(api)]

    with _api(SHADOW, driver) as api:
        cid = api.create()
        first = _first_run(api, cid)["run_id"]
        second = _start(api, cid, DRAFT)
        waiting = api.wait(second, {"WAITING_APPROVAL"})
        before = (waiting["run"]["revision"], waiting["pending_approval"], _types(api, second))

        r = api.message(cid, APPROVE_TEXT)
        assert r.status_code == 202 and r.json()["route"] == "start", r.text
        third = r.json()["run_id"]
        api.wait(third, {"WAITING_INPUT"})
        after = _run(api, second)
        assert (after["run"]["revision"], after["pending_approval"], _types(api, second)) == before
        assert _approve(api, second)["state"] == "SUCCEEDED"

        assert [_outcome(api, run_id) for run_id in (first, second, third)] == baseline

        # linked runs, the refused message's run unlinked
        snapshot = api.client.get(f"/v1/conversations/{cid}").json()
        assert [r["run_id"] for r in snapshot["runs"]] == [first, second]
        assert _bundle(api, third)["conversation"]["conversation_id"] is None

        # conversation.compared, and nothing carried for the driver
        assert not _of(api, first, "conversation.compared")
        (compared,) = _of(api, second, "conversation.compared")
        assert compared["payload"]["route"] == "start"
        assert compared["payload"]["carried_run_ids"] == [first]
        assert compared["payload"]["items"]["answers"] == 1
        (refused,) = _of(api, third, "conversation.compared")
        assert refused["payload"]["route"] == "refuse"
        assert refused["payload"]["conversation_id"] == cid
        for run_id in (first, second, third):
            assert not _of(api, run_id, "conversation.context_carried")
            assert _carried(api, run_id) == ()
            packs = driver.packs(run_id)
            assert packs and all(ContextLayer.RECENT_TURNS not in p.dynamic_suffix for p in packs)
