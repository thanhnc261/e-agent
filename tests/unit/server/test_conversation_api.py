"""The conversation routes and ``GET /v1/me/features`` (ADR 0023 §9, §10, §12, Task 4d.4).

Every route has the session dependency (PR-27); the handlers delegate to the kernel facade
(PR-03). In ``off`` every conversation route refuses with ``NOT_FOUND`` "conversations are
off"; ``/v1/me/features`` answers in every mode. A foreign conversation, of another owner or
another tenant, is ``NOT_FOUND`` on every route, never ``FORBIDDEN`` (Review Focus 5).

Every test runs on both stores: ``E_AGENT_TEST_STORE=postgres`` gives the server a
PostgreSQL ledger at ``E_AGENT_TEST_PG_DSN``, truncated per app (ENG-STORE-1, PL-5).
"""

from __future__ import annotations

import functools
import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

import pytest
from e_agent.contracts.common import new_id
from e_agent.contracts.context import HostContext, Principal, ResourceHint
from e_agent.contracts.conversation import ReplyTo
from e_agent.contracts.digest import digest
from e_agent.contracts.features import FeatureMode, Features
from e_agent.kernel.conversation import (
    CONVERSATIONS_OFF,
    KEY_REUSED,
    NOT_FOUND_MESSAGE,
    QUESTION_CHANGED,
    WAIT_FOR_RUN,
    message_digest,
)
from e_agent.plugins.erp.simulator import fixture_profile_path
from e_agent.sdk.ports import AskClarification
from e_agent.server.api import create_app
from e_agent.server.bootstrap import Runtime, build_runtime
from e_agent.server.profile import StoreConfig, load_profile
from fastapi.testclient import TestClient

POSTGRES = os.environ.get("E_AGENT_TEST_STORE") == "postgres"
OFF = Features()
SHADOW = Features(conversations=FeatureMode.SHADOW)
ON = Features(conversations=FeatureMode.ON, context_assembler=FeatureMode.ON)
ENVELOPE = {"code", "message", "correlation_id"}


class AskTwice:
    """Asks Q1, then Q2 after any answer: a run that stays waiting for input."""

    driver_id = "ask-twice-fixture"

    async def advance(self, ctx: Any, step_input: Any) -> AskClarification:
        return AskClarification(question="Q2?" if step_input.user_input else "Q1?")


@dataclass
class Api:
    client: TestClient
    runtime: Runtime
    headers: dict[str, str]

    def call(self, fn: Any, *args: Any, **kwargs: Any) -> Any:
        """Run a kernel or store coroutine on the app's own event loop."""
        return self.client.portal.call(functools.partial(fn, *args, **kwargs))

    def post(self, path: str, body: Any = None, *, key: str | None = None) -> Any:
        headers = dict(self.headers)
        if key is not None:
            headers["Idempotency-Key"] = key
        return self.client.post(path, json=body, headers=headers)

    def create(self) -> str:
        r = self.post("/v1/conversations")
        assert r.status_code == 201, r.text
        return str(r.json()["conversation_id"])

    def message(self, cid: str, text: str, *, key: str | None = None, **body: Any) -> Any:
        return self.post(
            f"/v1/conversations/{cid}/messages", {"text": text, **body}, key=key or new_id("key")
        )

    def wait(self, run_id: str, states: set[str], *, after_revision: int = 0) -> dict[str, Any]:
        for _ in range(200):
            body: dict[str, Any] = self.client.get(f"/v1/runs/{run_id}").json()
            run = body.get("run", {})
            if run.get("state") in states and run.get("revision", 0) > after_revision:
                return body
            time.sleep(0.05)
        raise AssertionError(body)


def _profile(features: Features) -> Any:
    update: dict[str, Any] = {"features": features}
    if POSTGRES:
        update["store"] = StoreConfig(kind="postgres", dsn_env="E_AGENT_TEST_PG_DSN")
    return load_profile(fixture_profile_path()).model_copy(update=update)


@contextmanager
def _api(features: Features, driver: Any = None) -> Iterator[Api]:
    box: list[Runtime] = []

    async def factory() -> Runtime:
        factory_kw = {} if driver is None else {"driver_factory": lambda _registry: driver}
        rt = await build_runtime(_profile(features), **factory_kw)
        if POSTGRES:
            assert type(rt.store).__name__ == "PostgresRunStore"
            await rt.store.truncate_for_tests()
        box.append(rt)
        return rt

    with TestClient(create_app(factory)) as client:
        r = client.post("/v1/local/session")
        assert r.status_code == 200
        yield Api(client, box[0], {"X-CSRF-Token": r.json()["csrf_token"]})


def _refused(r: Any, code: str, message: str) -> None:
    assert r.status_code == 404, r.text
    body = r.json()
    assert set(body) == ENVELOPE
    assert (body["code"], body["message"]) == (code, message)


def _waiting(api: Api, text: str = "write a note") -> tuple[str, dict[str, Any]]:
    """A conversation whose one run waits on Q1."""
    cid = api.create()
    r = api.message(cid, text)
    assert r.status_code == 202, r.text
    assert r.json()["route"] == "start"
    return cid, api.wait(r.json()["run_id"], {"WAITING_INPUT"})["run"]


def _reply_to(run: dict[str, Any]) -> dict[str, Any]:
    return {"run_id": run["run_id"], "run_revision": run["revision"]}


def _events(api: Api, run_id: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = api.client.get(f"/v1/runs/{run_id}/events").json()
    return events


# ---------------------------------------------------------------------------- off
def test_conversation_routes_refuse_when_off() -> None:
    """ADR 0023 §9: in ``off`` the routes exist and every one refuses with ``NOT_FOUND``
    "conversations are off"; no conversation, run or idempotency record is written."""
    with _api(OFF) as api:
        key = new_id("key")
        refused = [
            api.post("/v1/conversations"),
            api.client.get("/v1/conversations"),
            api.client.get("/v1/conversations/conv_any"),
            api.message("conv_any", "write a note", key=key),
        ]
        for r in refused:
            _refused(r, "NOT_FOUND", CONVERSATIONS_OFF)
        op = api.runtime.operator
        page = api.call(
            api.runtime.store.list_conversations,
            op.tenant_id,
            op.principal_id,
            after=None,
            limit=10,
        )
        assert page.items == ()
        assert (
            api.call(api.runtime.store.lookup_idempotent, op.tenant_id, op.principal_id, key)
            is None
        )


# -------------------------------------------------------------------------- happy path
def test_create_list_get_and_post_message() -> None:
    """Create, post a start, read the snapshot (each run with its revision), list, and
    answer with ``reply_to`` from the snapshot."""
    with _api(ON, AskTwice()) as api:
        cid, run = _waiting(api)
        snapshot = api.client.get(f"/v1/conversations/{cid}").json()
        assert snapshot["conversation"]["conversation_id"] == cid
        assert snapshot["conversation"]["owner_id"] == api.runtime.operator.principal_id
        (thread_run,) = snapshot["runs"]
        assert thread_run["run_id"] == run["run_id"]
        assert thread_run["task"] == "write a note"
        assert thread_run["state"] == "WAITING_INPUT"
        assert thread_run["revision"] == run["revision"]
        (item,) = api.client.get("/v1/conversations").json()["items"]
        assert item["conversation_id"] == cid
        assert (item["title"], item["latest_state"], item["reply_pending"]) == (
            "write a note",
            "WAITING_INPUT",
            True,
        )
        r = api.message(cid, "the standup note", reply_to=_reply_to(thread_run))
        assert (r.status_code, r.json()) == (202, {"route": "answer", "run_id": run["run_id"]})
        api.wait(run["run_id"], {"WAITING_INPUT"}, after_revision=run["revision"])
        received = [e for e in _events(api, run["run_id"]) if e["type"] == "input.received"]
        assert [e["payload"]["input"] for e in received] == ["the standup note"]


# ---------------------------------------------------------------- foreign (Review Focus 5)
def test_foreign_conversation_is_not_found() -> None:
    """Another owner's and another tenant's conversation: every route is ``NOT_FOUND``
    with the one message, never ``FORBIDDEN``; the list never shows them."""
    with _api(ON, AskTwice()) as api:
        op = api.runtime.operator
        other_owner = Principal(principal_id="mallory", tenant_id=op.tenant_id, roles=op.roles)
        other_tenant = Principal(
            principal_id=op.principal_id, tenant_id="tenant-elsewhere", roles=op.roles
        )
        own = api.create()
        for who in (other_owner, other_tenant):
            foreign = api.call(api.runtime.coordinator.create_conversation, who).conversation_id
            key = new_id("key")
            for r in (
                api.client.get(f"/v1/conversations/{foreign}"),
                api.message(foreign, "write a note", key=key),
                api.client.get("/v1/conversations", params={"after": foreign}),
            ):
                _refused(r, "NOT_FOUND", NOT_FOUND_MESSAGE)
            listed = api.client.get("/v1/conversations").json()["items"]
            assert [i["conversation_id"] for i in listed] == [own]
            assert (
                api.call(api.runtime.store.lookup_idempotent, op.tenant_id, op.principal_id, key)
                is None
            )


def test_reply_to_another_users_run_is_refused_before_any_event_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """4d.1 B1-4: a ``reply_to`` naming another user's run is ``NOT_FOUND`` on the
    conversation route and ``FORBIDDEN`` on ``/v1/runs/{id}/inputs``, before either reads
    that run's events."""
    with _api(ON, AskTwice()) as api:
        op = api.runtime.operator
        other = Principal(principal_id="mallory", tenant_id=op.tenant_id, roles=op.roles)
        theirs, _ = api.call(
            api.runtime.coordinator.admit_run,
            other,
            "write a note",
            api.runtime.scope,
            run_id=new_id("run"),
            idempotency_key=new_id("key"),
            request_digest=digest({"task": "write a note"}),
        )
        run = api.wait(theirs, {"WAITING_INPUT"})["run"]
        cid = api.create()
        reads: list[str] = []
        store = api.runtime.store
        original = store.list_events

        async def spy(tenant_id: str, run_id: str, *args: Any, **kwargs: Any) -> Any:
            reads.append(run_id)
            return await original(tenant_id, run_id, *args, **kwargs)

        monkeypatch.setattr(store, "list_events", spy)
        r = api.message(cid, "the standup note", reply_to=_reply_to(run))
        _refused(r, "NOT_FOUND", NOT_FOUND_MESSAGE)
        body = {"input": "the standup note", "expected_revision": run["revision"]}
        r = api.post(f"/v1/runs/{theirs}/inputs", body)
        assert r.status_code == 404 and r.json()["code"] == "FORBIDDEN"
        assert theirs not in reads
        api.client.get(f"/v1/runs/{theirs}/events")  # the spy sees a read of that run
        assert theirs in reads
        monkeypatch.setattr(store, "list_events", original)
        assert not [e for e in _events(api, theirs) if e["type"] == "input.received"]


# ------------------------------------------------------------------- request checks
def test_post_message_requires_idempotency_key() -> None:
    with _api(ON, AskTwice()) as api:
        cid = api.create()
        url = f"/v1/conversations/{cid}/messages"
        assert api.post(url, {"text": "write a note"}).status_code == 422
        assert api.post(url, {"text": "write a note"}, key="short").status_code == 422
        assert api.client.get(f"/v1/conversations/{cid}").json()["runs"] == []


def test_message_text_has_the_create_run_bounds() -> None:
    """4d.1 B1-3: the text is 1 to 4000 characters, as ``CreateRun.task``."""
    with _api(ON, AskTwice()) as api:
        cid = api.create()
        for text in ("", "x" * 4001):
            assert api.message(cid, text).status_code == 422
            assert api.post("/v1/runs", {"task": text}, key=new_id("key")).status_code == 422
        assert api.client.get(f"/v1/conversations/{cid}").json()["runs"] == []
        assert api.message(cid, "x" * 4000).status_code == 202


def test_message_digest_covers_every_field() -> None:
    """4d.1 B1-2: one request digest over the conversation id, the text, ``reply_to`` and
    ``host_context``, in the number-free digest profile (ADR 0006): a change to any one
    changes it; the same request gives the same digest."""
    reply_to = ReplyTo(run_id="run_1", run_revision=3)
    host = HostContext(host_kind="embedded", locale="en")
    base = message_digest("conv_1", "hi", reply_to, host)
    assert base == message_digest("conv_1", "hi", reply_to, host)
    assert base == digest(
        {
            "conversation_id": "conv_1",
            "text": "hi",
            "reply_to": {"run_id": "run_1", "run_revision": "3"},
            "host_context": {"host_kind": "embedded", "locale": "en", "resource_hints": []},
        }
    )
    variants = {
        message_digest("conv_2", "hi", reply_to, host),
        message_digest("conv_1", "ho", reply_to, host),
        message_digest("conv_1", "hi", None, host),
        message_digest("conv_1", "hi", ReplyTo(run_id="run_1", run_revision=4), host),
        message_digest("conv_1", "hi", ReplyTo(run_id="run_2", run_revision=3), host),
        message_digest("conv_1", "hi", reply_to, None),
        message_digest("conv_1", "hi", reply_to, HostContext(host_kind="standalone")),
    }
    assert len(variants) == 7 and base not in variants


def test_one_key_posted_to_two_conversations_conflicts() -> None:
    """4d.1 B1-2: the digest covers the conversation id, so one Idempotency-Key posted with
    the same text to a second conversation is ``CONFLICT``; the same request replays."""
    with _api(ON, AskTwice()) as api:
        first, second = api.create(), api.create()
        key = new_id("key")
        r = api.message(first, "write a note", key=key)
        assert r.status_code == 202
        replay = api.message(first, "write a note", key=key)
        assert (replay.status_code, replay.json()) == (202, r.json())
        reused = api.message(second, "write a note", key=key)
        assert reused.status_code == 409
        assert (reused.json()["code"], reused.json()["message"]) == ("CONFLICT", KEY_REUSED)
        assert api.client.get(f"/v1/conversations/{second}").json()["runs"] == []


def test_answer_with_stale_reply_to_conflicts() -> None:
    """Review Focus 9 through the API: an answer typed for Q1 while Q2 is pending is
    ``CONFLICT`` "the question changed"; a retried answer replays; one input is recorded."""
    with _api(ON, AskTwice()) as api:
        cid, run = _waiting(api)
        q1 = _reply_to(run)
        assert api.message(cid, "the standup note", reply_to=q1).json()["route"] == "answer"
        api.wait(run["run_id"], {"WAITING_INPUT"}, after_revision=run["revision"])
        stale = api.message(cid, "something else", reply_to=q1)
        assert stale.status_code == 409
        assert (stale.json()["code"], stale.json()["message"]) == ("CONFLICT", QUESTION_CHANGED)
        retried = api.message(cid, "the standup note", reply_to=q1)
        assert (retried.status_code, retried.json()["route"]) == (202, "answer")
        received = [e for e in _events(api, run["run_id"]) if e["type"] == "input.received"]
        assert len(received) == 1


INVALID_HOST_CONTEXTS = [
    {"host_kind": "browser"},
    {"host_kind": "embedded", "page_url_origin": "ftp://example.test"},
    {"host_kind": "embedded", "unknown": "x"},
    {"host_kind": "embedded", "locale": "x" * 17},
    {
        "host_kind": "embedded",
        "resource_hints": [
            {"system_hint": "erp", "resource_type_hint": "demand", "external_id_hint": f"d{i}"}
            for i in range(11)
        ],
    },
]


def test_message_host_context_is_validated_like_create_run() -> None:
    """``host_context`` is ``CreateRun``'s type with its validation (ADR 0023 §4): every
    body ``POST /v1/runs`` refuses, the message route refuses; a valid one is recorded in
    ``run.created`` as ``/v1/runs`` records it."""
    with _api(ON, AskTwice()) as api:
        cid = api.create()
        for host in INVALID_HOST_CONTEXTS:
            run_r = api.post(
                "/v1/runs", {"task": "write a note", "host_context": host}, key=new_id("key")
            )
            message_r = api.message(cid, "write a note", host_context=host)
            assert (run_r.status_code, message_r.status_code) == (422, 422), host
        assert api.client.get(f"/v1/conversations/{cid}").json()["runs"] == []
        host = HostContext(
            host_kind="embedded",
            page_url_origin="https://erp.example.test",
            locale="en",
            resource_hints=(
                ResourceHint(
                    system_hint="erp", resource_type_hint="demand", external_id_hint="d-001"
                ),
            ),
        ).model_dump(mode="json", exclude_none=True)
        run_id = api.post(
            "/v1/runs", {"task": "write a note", "host_context": host}, key=new_id("key")
        ).json()["run_id"]
        posted = api.message(cid, "write a note", host_context=host)
        assert posted.status_code == 202

        def recorded(rid: str) -> Any:
            (created,) = [e for e in _events(api, rid) if e["type"] == "run.created"]
            return created["payload"]["host_context"]

        assert recorded(posted.json()["run_id"]) == recorded(run_id)


def test_refusal_carries_the_fixed_hint() -> None:
    """ADR 0023 §4: a message beside an active run is ``CONFLICT`` with the fixed hint, and
    one without ``reply_to`` beside a waiting run gets the question hint."""
    with _api(ON) as api:  # the ERP scripted driver waits for approval
        cid = api.create()
        run_id = api.message(cid, "restock widget-a").json()["run_id"]
        api.wait(run_id, {"WAITING_APPROVAL"})
        r = api.message(cid, "approve it")
        assert r.status_code == 409
        assert (r.json()["code"], r.json()["message"]) == ("CONFLICT", WAIT_FOR_RUN)
        assert api.client.get(f"/v1/runs/{run_id}").json()["run"]["state"] == "WAITING_APPROVAL"
    with _api(ON, AskTwice()) as api:
        cid, _ = _waiting(api)
        r = api.message(cid, "the standup note")
        assert (r.status_code, r.json()["message"]) == (409, QUESTION_CHANGED)


def test_conversation_errors_use_the_error_envelope() -> None:
    """The ``off`` refusal and a missing conversation are e-agent ``NOT_FOUND`` envelopes,
    which the UI tells apart from a route an older server never mounted (Task 4e.3)."""
    with _api(OFF) as api:
        _refused(api.client.get("/v1/conversations/conv_missing"), "NOT_FOUND", CONVERSATIONS_OFF)
        unmounted = api.client.get("/v1/not-mounted")
        assert unmounted.status_code == 404 and "code" not in unmounted.json()
    with _api(ON) as api:
        missing = api.client.get("/v1/conversations/conv_missing")
        _refused(missing, "NOT_FOUND", NOT_FOUND_MESSAGE)
        _refused(api.message("conv_missing", "hi"), "NOT_FOUND", NOT_FOUND_MESSAGE)


def test_list_is_paged() -> None:
    """Newest first; ``next_after`` only while more follow; the title is the first run's
    task cut to 80 characters, and an empty conversation's is empty (ADR 0023 §10, D4)."""
    with _api(ON, AskTwice()) as api:
        empty = api.create()
        long_text = "a" * 79 + "bcdef" + "z" * 16
        titled, _ = _waiting(api, long_text)
        newest = api.create()
        first = api.client.get("/v1/conversations", params={"limit": 2}).json()
        assert [i["conversation_id"] for i in first["items"]] == [newest, titled]
        assert first["next_after"] == titled
        second = api.client.get(
            "/v1/conversations", params={"limit": 2, "after": first["next_after"]}
        ).json()
        assert [i["conversation_id"] for i in second["items"]] == [empty]
        assert second["next_after"] is None
        by_id = {i["conversation_id"]: i for i in first["items"] + second["items"]}
        assert by_id[titled]["title"] == long_text[:80]
        assert (by_id[empty]["title"], by_id[empty]["latest_state"]) == ("", None)
        assert by_id[empty]["reply_pending"] is False
        for limit in (0, 101):
            assert api.client.get("/v1/conversations", params={"limit": limit}).status_code == 422


@pytest.mark.parametrize("features", [OFF, SHADOW, ON], ids=["off", "shadow", "on"])
def test_member_features_reports_the_mode(features: Features) -> None:
    """``GET /v1/me/features`` answers in every mode, with a session only (ADR 0023 §10)."""
    with _api(features) as api:
        r = api.client.get("/v1/me/features")
        assert (r.status_code, r.json()) == (200, {"conversations": features.conversations})
        api.client.cookies.clear()
        anonymous = api.client.get("/v1/me/features")
        assert anonymous.status_code == 404 and anonymous.json()["code"] == "FORBIDDEN"


def _bundle(api: Api, run_id: str) -> dict[str, Any]:
    bundle: dict[str, Any] = api.client.get(f"/v1/runs/{run_id}/evidence").json()
    return bundle


def _cancel(api: Api, run_id: str) -> None:
    assert api.post(f"/v1/runs/{run_id}/cancel").json()["state"] == "CANCELLED"


def test_evidence_bundle_reports_conversation() -> None:
    """ADR 0023 §12: the bundle's ``conversation`` key holds the run's conversation id, its
    pinned mode, the carried run ids and the ``conversation.compared`` counts; an ``off``
    run's bundle has no such key."""
    with _api(ON, AskTwice()) as api:
        cid, first = _waiting(api)
        assert _bundle(api, first["run_id"])["conversation"] == {
            "conversation_id": cid,
            "mode": "on",
            "carried_run_ids": [],
            "compared": {"start": 0, "refuse": 0},
        }
        _cancel(api, first["run_id"])
        second = api.message(cid, "write another note").json()["run_id"]
        api.wait(second, {"WAITING_INPUT"})
        (carried,) = [
            e for e in _events(api, second) if e["type"] == "conversation.context_carried"
        ]
        assert carried["payload"]["carried_run_ids"] == [first["run_id"]]
        assert _bundle(api, second)["conversation"] == {
            "conversation_id": cid,
            "mode": "on",
            "carried_run_ids": [first["run_id"]],
            "compared": {"start": 0, "refuse": 0},
        }
    with _api(SHADOW, AskTwice()) as api:
        cid, first = _waiting(api)
        refused = api.message(cid, "write another note").json()["run_id"]  # beside a waiting run
        _cancel(api, first["run_id"])
        second = api.message(cid, "write a third note").json()["run_id"]
        assert _bundle(api, refused)["conversation"] == {
            "conversation_id": None,  # unlinked, as POST /v1/runs would start it
            "mode": "shadow",
            "carried_run_ids": [],
            "compared": {"start": 0, "refuse": 1},
        }
        assert _bundle(api, second)["conversation"] == {
            "conversation_id": cid,
            "mode": "shadow",
            "carried_run_ids": [],
            "compared": {"start": 1, "refuse": 0},
        }
    with _api(OFF, AskTwice()) as api:
        run_id = api.post("/v1/runs", {"task": "write a note"}, key=new_id("key")).json()["run_id"]
        api.wait(run_id, {"WAITING_INPUT"})
        assert "conversation" not in _bundle(api, run_id)
