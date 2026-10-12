"""HTTP API: session/CSRF, idempotency, approvals, SSE resume, scoping (I08)."""

import json
import time
from typing import Any

import pytest
from e_agent.server.api import create_app
from e_agent.server.bootstrap import build_runtime
from e_agent.server.profile import load_profile
from fastapi.testclient import TestClient


@pytest.fixture
def client() -> Any:
    app = create_app(lambda: build_runtime(load_profile()))
    with TestClient(app) as c:
        yield c


def _login(c: TestClient) -> dict[str, str]:
    r = c.post("/v1/local/session")
    assert r.status_code == 200
    return {"X-CSRF-Token": r.json()["csrf_token"]}


def _wait(c: TestClient, run_id: str, states: set[str]) -> dict[str, Any]:
    for _ in range(100):
        body = c.get(f"/v1/runs/{run_id}").json()
        if body["run"]["state"] in states:
            return body  # type: ignore[no-any-return]
        time.sleep(0.05)
    raise AssertionError(body)


def test_requests_without_session_or_csrf_are_rejected(client: TestClient) -> None:
    assert (
        client.post(
            "/v1/runs", json={"task": "x"}, headers={"Idempotency-Key": "k" * 10}
        ).status_code
        == 404
    )
    _login(client)
    r = client.post("/v1/runs", json={"task": "x"}, headers={"Idempotency-Key": "k" * 10})
    assert r.status_code == 404 and r.json()["code"] == "FORBIDDEN"


def test_full_run_with_approval_over_http(client: TestClient) -> None:
    h = _login(client)
    r = client.post(
        "/v1/runs",
        json={"task": "restock widget-a"},
        headers={**h, "Idempotency-Key": "run-key-0001"},
    )
    assert r.status_code == 202
    run_id = r.json()["run_id"]
    body = _wait(client, run_id, {"WAITING_APPROVAL"})
    pres = body["pending_approval"]
    assert pres["digest"].startswith("jcs-sha256-v1:")
    assert [f["path"] for f in pres["material_fields"]][:2] == ["demand_ref", "product_ref"]
    r = client.post(
        f"/v1/runs/{run_id}/approvals",
        headers=h,
        json={
            "action_id": pres["action_id"],
            "digest": pres["digest"],
            "expected_revision": pres["run_revision"],
            "decision": "approved",
        },
    )
    assert r.status_code == 202
    assert _wait(client, run_id, {"SUCCEEDED", "FAILED"})["run"]["state"] == "SUCCEEDED"
    evidence = client.get(f"/v1/runs/{run_id}/evidence").json()
    assert evidence["classification"] == "fixture:succeeded"
    assert (
        client.get(f"/v1/runs/{run_id}")
        .headers["Content-Security-Policy"]
        .startswith("default-src 'self'")
    )


def test_idempotency_key_returns_same_run_and_conflicts_on_new_payload(client: TestClient) -> None:
    h = {**_login(client), "Idempotency-Key": "same-key-123"}
    a = client.post("/v1/runs", json={"task": "restock"}, headers=h).json()
    b = client.post("/v1/runs", json={"task": "restock"}, headers=h).json()
    assert a["run_id"] == b["run_id"] and a["created"] and not b["created"]
    c = client.post("/v1/runs", json={"task": "something else"}, headers=h)
    assert c.status_code == 409


def test_stale_digest_is_rejected(client: TestClient) -> None:
    h = _login(client)
    run_id = client.post(
        "/v1/runs", json={"task": "restock"}, headers={**h, "Idempotency-Key": "stale-key-1"}
    ).json()["run_id"]
    pres = _wait(client, run_id, {"WAITING_APPROVAL"})["pending_approval"]
    r = client.post(
        f"/v1/runs/{run_id}/approvals",
        headers=h,
        json={
            "action_id": pres["action_id"],
            "digest": "jcs-sha256-v1:" + "0" * 64,
            "expected_revision": pres["run_revision"],
            "decision": "approved",
        },
    )
    assert r.status_code == 409 and r.json()["code"] == "APPROVAL_STALE"


def test_sse_stream_replays_and_resumes_after_last_event_id(client: TestClient) -> None:
    h = _login(client)
    run_id = client.post(
        "/v1/runs", json={"task": "restock"}, headers={**h, "Idempotency-Key": "sse-key-01"}
    ).json()["run_id"]
    pres = _wait(client, run_id, {"WAITING_APPROVAL"})["pending_approval"]
    client.post(
        f"/v1/runs/{run_id}/approvals",
        headers=h,
        json={
            "action_id": pres["action_id"],
            "digest": pres["digest"],
            "expected_revision": pres["run_revision"],
            "decision": "approved",
        },
    )
    _wait(client, run_id, {"SUCCEEDED"})

    def read_stream(last_id: str | None, query: str = "") -> list[dict[str, Any]]:
        headers = {"Last-Event-ID": last_id} if last_id else {}
        events, current = [], {}
        with client.stream("GET", f"/v1/runs/{run_id}/stream{query}", headers=headers) as r:
            assert r.headers["content-type"].startswith("text/event-stream")
            for line in r.iter_lines():
                if line.startswith("id:"):
                    current["id"] = line[3:].strip()
                elif line.startswith("event:"):
                    current["event"] = line[6:].strip()
                elif line.startswith("data:"):
                    current["data"] = json.loads(line[5:])
                elif line == "" and current:
                    events.append(current)
                    current = {}
        return events

    full = [e for e in read_stream(None) if e.get("event") == "run_event"]
    seqs = [int(e["id"]) for e in full]
    assert seqs == list(range(1, len(seqs) + 1))
    resumed = [e for e in read_stream(str(seqs[4])) if e.get("event") == "run_event"]
    assert [int(e["id"]) for e in resumed] == seqs[5:]
    by_query = [e for e in read_stream(None, "?after_sequence=3") if e.get("event") == "run_event"]
    assert [int(e["id"]) for e in by_query] == seqs[3:]


def test_unknown_or_foreign_runs_look_the_same(client: TestClient) -> None:
    _login(client)
    assert client.get("/v1/runs/run_does_not_exist").status_code == 404
    assert client.get("/v1/runs/run_does_not_exist/stream").status_code == 404


class _CrashingDriver:
    driver_id = "crashing"

    async def advance(self, ctx: Any, step_input: Any) -> Any:
        raise RuntimeError("model transport exploded")


def test_background_crash_applies_crash_rules_not_a_guess() -> None:
    app = create_app(
        lambda: build_runtime(load_profile(), driver_factory=lambda _r: _CrashingDriver())
    )
    with TestClient(app) as c:
        h = _login(c)
        r = c.post("/v1/runs", json={"task": "x"}, headers={**h, "Idempotency-Key": "crash-0001"})
        body = _wait(c, r.json()["run_id"], {"FAILED", "SUCCEEDED"})
        assert body["run"]["state"] == "FAILED"
        assert "model transport exploded" not in json.dumps(body)  # no raw error leakage


def test_host_context_hints_are_resolved_or_dropped(client: TestClient) -> None:
    h = _login(client)
    body = {
        "task": "restock",
        "host_context": {
            "host_kind": "embedded",
            "page_url_origin": "https://intranet.example",
            "selection_text": "do not persist me",
            "resource_hints": [
                {
                    "system_hint": "fixture-erp",
                    "resource_type_hint": "demand",
                    "external_id_hint": "d-001",
                },
                {"system_hint": "elsewhere", "resource_type_hint": "x", "external_id_hint": "1"},
            ],
        },
    }
    run_id = client.post(
        "/v1/runs", json=body, headers={**h, "Idempotency-Key": "host-ctx-01"}
    ).json()["run_id"]
    _wait(client, run_id, {"WAITING_APPROVAL"})
    created = client.get(f"/v1/runs/{run_id}/events").json()[0]
    ctx = created["payload"]["host_context"]
    assert ctx["resolved_hints"] == [
        {"connection_id": "conn-fixture-erp", "resource_type": "demand", "external_id": "d-001"}
    ]
    assert ctx["dropped_hints"] == 1
    assert "do not persist me" not in json.dumps(created)
    bad = {
        **body,
        "host_context": {**body["host_context"], "page_url_origin": "https://x.example/a?t=1"},
    }
    r = client.post("/v1/runs", json=bad, headers={**h, "Idempotency-Key": "host-ctx-02"})
    assert r.status_code == 422


def test_ledger_must_not_share_the_provider_database() -> None:
    from e_agent.kernel.errors import KernelError
    from e_agent.server.bootstrap import check_ledger_separation

    profile = load_profile().model_copy(
        update={
            "enabled_plugins": {
                **load_profile().enabled_plugins,
                "odoo19": load_profile()
                .enabled_plugins["domain-erp"]
                .model_copy(update={"settings": {"database": "erp_prod"}}),
            }
        }
    )
    with pytest.raises(KernelError):
        check_ledger_separation(profile, "postgresql://u@h:5432/erp_prod")
    check_ledger_separation(profile, "postgresql://u@h:5432/e_agent")


def test_clarification_resumes_same_run_and_input_replay_is_idempotent() -> None:
    from e_agent.erp.testing.scripted_tasks import ScriptedErpDriver
    from e_agent.sdk.ports import AskClarification

    class ClarifyingDriver:
        driver_id = "clarification-fixture"

        def __init__(self):
            self.received = False
            self.delegate = ScriptedErpDriver(
                connection_id="conn-fixture-erp", task_kind="draft-po"
            )

        async def advance(self, ctx, step_input):
            if step_input.user_input:
                self.received = True
            if self.received:
                return await self.delegate.advance(ctx, step_input)
            return AskClarification(question="Which demand?")

    with TestClient(
        create_app(
            lambda: build_runtime(
                load_profile(),
                driver_factory=lambda registry: ClarifyingDriver(),
            )
        )
    ) as client:
        headers = {**_login(client), "Idempotency-Key": "clarification-001"}
        rid = client.post("/v1/runs", json={"task": "draft PO"}, headers=headers).json()["run_id"]
        snapshot = _wait(client, rid, {"WAITING_INPUT"})
        body = {"input": "demand:d-001", "expected_revision": snapshot["run"]["revision"]}
        assert client.post(f"/v1/runs/{rid}/inputs", json=body, headers=headers).status_code == 202
        final = _wait(client, rid, {"WAITING_APPROVAL"})
        assert final["run"]["run_id"] == rid
        assert final["pending_approval"] is not None
        assert client.post(f"/v1/runs/{rid}/inputs", json=body, headers=headers).status_code == 202
        assert (
            client.post(
                f"/v1/runs/{rid}/inputs", json={**body, "input": "different"}, headers=headers
            ).status_code
            == 409
        )
        events = client.get(f"/v1/runs/{rid}/events").json()
        assert sum(e["type"] == "input.received" for e in events) == 1


async def test_lost_work_lease_stops_claim_without_killing_worker(monkeypatch) -> None:
    import asyncio

    from e_agent.contracts.common import utc_now
    from e_agent.contracts.work import WorkClaim
    from e_agent.server.api import ApiState

    runtime = await build_runtime(load_profile())
    state = ApiState(runtime)
    started = asyncio.Event()
    original_sleep = asyncio.sleep

    async def sleep(seconds):
        if seconds == 5:
            await started.wait()
        else:
            await original_sleep(seconds)

    async def lost(claim):
        return False

    async def stalled(*args):
        started.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(asyncio, "sleep", sleep)
    monkeypatch.setattr(runtime.store, "renew_work", lost)
    monkeypatch.setattr(runtime.coordinator, "start_admitted_run", stalled)
    claim = WorkClaim(
        work_id="work-test",
        tenant_id="tenant-demo",
        run_id="run-test",
        kind="start",
        payload={},
        owner="worker-test",
        fence=1,
        lease_until=utc_now(),
    )
    await asyncio.wait_for(state._run_work(claim), 1)
    assert asyncio.current_task().cancelling() == 0


@pytest.mark.parametrize("kind", ["start", "decide"])
async def test_takeover_executes_durable_command_that_never_started(kind):
    from e_agent.contracts.common import new_id
    from e_agent.contracts.run import RunState
    from e_agent.server.api import ApiState

    runtime = await build_runtime(load_profile())
    state = ApiState(runtime)
    if kind == "start":
        run_id, created = await runtime.coordinator.admit_run(
            runtime.operator,
            "restock",
            runtime.scope,
            run_id=new_id("run"),
            idempotency_key="takeover-start",
            request_digest="request",
        )
        assert created
    else:
        run = await runtime.coordinator.start_run(runtime.operator, "restock", runtime.scope)
        run_id = run.run_id
        p = await runtime.coordinator.pending_approval(runtime.operator.tenant_id, run_id)
        await runtime.store.enqueue_work(
            runtime.operator.tenant_id,
            run_id,
            "decide",
            {
                "actor": runtime.operator.model_dump(mode="json"),
                "action_id": p.action_id,
                "digest": p.digest,
                "expected_revision": p.run_revision,
                "decision": "approved",
            },
            "approved-command",
        )
    lost = await runtime.store.claim_work("dead-owner", lease_seconds=0)
    assert lost is not None
    claim = await runtime.store.claim_work("replacement-owner")
    assert claim is not None and claim.fence == 2
    await state._run_work(claim)
    recovered = await runtime.store.get_run(runtime.operator.tenant_id, run_id)
    assert recovered.state is (RunState.WAITING_APPROVAL if kind == "start" else RunState.SUCCEEDED)
    assert runtime.fake_erp.create_calls == (0 if kind == "start" else 1)


def test_conflicting_decision_is_rejected_before_the_worker_runs():
    admitted = {}

    async def factory():
        runtime = await build_runtime(load_profile())
        run = await runtime.coordinator.start_run(runtime.operator, "restock", runtime.scope)
        admitted["run_id"] = run.run_id

        async def no_claim(*args, **kwargs):
            return None

        runtime.store.claim_work = no_claim
        return runtime

    with TestClient(create_app(factory)) as client:
        headers = _login(client)
        run_id = admitted["run_id"]
        presentation = client.get(f"/v1/runs/{run_id}").json()["pending_approval"]
        body = {
            "action_id": presentation["action_id"],
            "digest": presentation["digest"],
            "expected_revision": presentation["run_revision"],
            "decision": "approved",
        }
        endpoint = f"/v1/runs/{run_id}/approvals"
        assert client.post(endpoint, headers=headers, json=body).status_code == 202
        assert client.post(endpoint, headers=headers, json=body).status_code == 202
        assert (
            client.post(
                endpoint, headers=headers, json={**body, "decision": "rejected"}
            ).status_code
            == 409
        )
        assert client.get(f"/v1/runs/{run_id}").json()["run"]["state"] == "WAITING_APPROVAL"


def test_member_discovery_requires_a_session(client: TestClient) -> None:
    for path in ("/v1/me/connections", "/v1/me/task-catalog"):
        r = client.get(path)
        assert r.status_code == 404 and r.json()["code"] == "FORBIDDEN"


def test_member_connections_expose_no_secret_or_administrative_field(
    client: TestClient,
) -> None:
    _login(client)
    body = client.get("/v1/me/connections").json()
    assert body["schema_version"] == "1" and body["observed_at"]
    assert body["connections"], "the fixture profile has at least one usable connection"
    for conn in body["connections"]:
        # ADR 0017: configuration status and observed health are different facts, and
        # rendering never probes a provider.
        assert conn["observed_health"] == "unknown"
        assert conn["configuration_status"] == "active"
        assert set(conn) == {
            "connection_id",
            "integration_id",
            "ownership",
            "acting_identity",
            "allowed_resources",
            "capabilities",
            "configuration_status",
            "observed_health",
            "revision",
        }
    text = json.dumps(body)
    for forbidden in ("secret", "credential", "password", "token", "api_key"):
        assert forbidden not in text.lower()


def test_task_catalog_reports_real_availability(client: TestClient) -> None:
    _login(client)
    body = client.get("/v1/me/task-catalog").json()
    assert body["schema_version"] == "1"
    templates = body["templates"]
    assert templates, "the fixture profile admits at least one task type"
    for template in templates:
        assert template["input_intent"] == "free_text"
        assert template["availability"] in {"available", "unavailable"}
        if template["availability"] == "available":
            assert template["unavailable_reason"] is None
        else:
            assert template["unavailable_reason"] in {
                "no_usable_connection",
                "ambiguous_binding",
                "no_executor",
                "no_verifier",
            }
        # A template never hands the client a binding or a connection to choose.
        assert "connection_id" not in template and "binding_id" not in template


def test_ready_reports_whether_self_approval_is_allowed(client: TestClient) -> None:
    body = client.get("/health/ready").json()
    assert body["self_approval_allowed"] is True  # fixture profile: one local operator


def test_ready_reports_self_approval_disallowed_when_the_profile_flag_is_unset() -> None:
    from e_agent.server.profile import OperatorConfig

    profile = load_profile()
    operator = OperatorConfig(  # allow_self_approval deliberately left unset
        principal_id=profile.operator.principal_id, roles=profile.operator.roles
    )
    assert operator.allow_self_approval is False
    app = create_app(lambda: build_runtime(profile.model_copy(update={"operator": operator})))
    with TestClient(app) as c:
        assert c.get("/health/ready").json()["self_approval_allowed"] is False


def test_events_name_the_principal_who_caused_them(client: TestClient) -> None:
    h = _login(client)
    r = client.post(
        "/v1/runs",
        json={"task": "restock widget-a"},
        headers={**h, "Idempotency-Key": "actor-key-0001"},
    )
    run_id = r.json()["run_id"]
    body = _wait(client, run_id, {"WAITING_APPROVAL"})
    pres = body["pending_approval"]
    client.post(
        f"/v1/runs/{run_id}/approvals",
        json={
            "action_id": pres["action_id"],
            "digest": pres["digest"],
            "expected_revision": pres["run_revision"],
            "decision": "approved",
        },
        headers=h,
    )
    _wait(client, run_id, {"SUCCEEDED", "FAILED"})
    events = client.get(f"/v1/runs/{run_id}/events").json()
    by_type = {e["type"]: e["actor"] for e in events}
    assert by_type["run.created"] == "principal:local-operator"
    assert by_type["approval.decided"] == "principal:local-operator"
    assert not any(e["actor"] == "system:kernel" for e in events), (
        "every happy-path event runs under a principal scope"
    )


@pytest.mark.parametrize("takeover", [False, True])
async def test_expired_approval_is_failed_by_the_worker_under_a_system_actor(takeover):
    from datetime import timedelta

    from e_agent.contracts.run import ReasonCode, RunState
    from e_agent.server.api import ApiState

    runtime = await build_runtime(load_profile())
    state = ApiState(runtime)
    tenant = runtime.operator.tenant_id
    run = await runtime.coordinator.start_run(runtime.operator, "restock", runtime.scope)
    assert await runtime.coordinator.sweep_expired_approvals() == 0
    real_clock = runtime.coordinator._clock
    runtime.coordinator._clock = lambda: real_clock() + timedelta(hours=1)
    assert await runtime.coordinator.sweep_expired_approvals() == 1
    assert (await runtime.store.get_run(tenant, run.run_id)).state is RunState.WAITING_APPROVAL
    if takeover:  # a dead owner held the claim: fence 2 must still just expire
        assert await runtime.store.claim_work("dead-owner", lease_seconds=0) is not None
    claim = await runtime.store.claim_work("worker-test")
    assert claim is not None and claim.kind == "expire"
    assert claim.fence == (2 if takeover else 1)
    await state._run_work(claim)
    failed = await runtime.store.get_run(tenant, run.run_id)
    assert failed.state is RunState.FAILED and failed.reason_code is ReasonCode.APPROVAL_EXPIRED
    events = await runtime.store.list_events(tenant, run.run_id)
    changed = [e for e in events if e.type.value in {"approval.decided", "run.state_changed"}]
    assert changed[-2].type.value == "approval.decided"
    assert all(e.actor == "system:worker:worker-test" for e in changed[-2:]), changed[-2:]
    assert runtime.fake_erp.create_calls == 0


async def test_sweeper_survives_a_failed_sweep_and_stops_on_cancel(monkeypatch) -> None:
    import asyncio

    from e_agent.server import api
    from e_agent.server.api import ApiState

    runtime = await build_runtime(load_profile())
    state = ApiState(runtime)
    calls: list[int] = []

    async def sweep() -> int:
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("transient store error")
        return 0

    monkeypatch.setattr(api, "APPROVAL_SWEEP_SECONDS", 0.01)
    monkeypatch.setattr(runtime.coordinator, "sweep_expired_approvals", sweep)
    task = asyncio.create_task(state.sweeper())
    for _ in range(100):
        if len(calls) >= 3:
            break
        await asyncio.sleep(0.01)
    assert len(calls) >= 3, "the loop kept sweeping after the first failure"
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


def test_events_endpoint_pages_and_caps_the_limit(client: TestClient) -> None:
    h = _login(client)
    r = client.post(
        "/v1/runs",
        json={"task": "restock widget-a"},
        headers={**h, "Idempotency-Key": "page-key-0001"},
    )
    run_id = r.json()["run_id"]
    _wait(client, run_id, {"WAITING_APPROVAL"})
    first = client.get(f"/v1/runs/{run_id}/events", params={"limit": 2}).json()
    assert [e["sequence"] for e in first] == [1, 2]
    rest = client.get(
        f"/v1/runs/{run_id}/events", params={"after_sequence": 2, "limit": 1000}
    ).json()
    assert rest and rest[0]["sequence"] == 3
    assert client.get(f"/v1/runs/{run_id}/events", params={"limit": 5000}).status_code == 422


def test_stream_delivers_every_event_across_page_boundaries(
    client: TestClient, monkeypatch: Any
) -> None:
    import e_agent.server.api as api_module

    monkeypatch.setattr(api_module, "EVENT_PAGE", 2)
    h = _login(client)
    r = client.post(
        "/v1/runs",
        json={"task": "restock widget-a"},
        headers={**h, "Idempotency-Key": "sse-page-0001"},
    )
    run_id = r.json()["run_id"]
    pres = _wait(client, run_id, {"WAITING_APPROVAL"})["pending_approval"]
    client.post(
        f"/v1/runs/{run_id}/approvals",
        headers=h,
        json={
            "action_id": pres["action_id"],
            "digest": pres["digest"],
            "expected_revision": pres["run_revision"],
            "decision": "approved",
        },
    )
    _wait(client, run_id, {"SUCCEEDED"})  # a terminal run, so the stream ends after the replay
    expected = [e["sequence"] for e in client.get(f"/v1/runs/{run_id}/events").json()]
    assert len(expected) > 4  # several pages of two
    seen: list[int] = []
    with client.stream("GET", f"/v1/runs/{run_id}/stream", headers=h) as resp:
        for line in resp.iter_lines():
            if line.startswith("id:"):
                seen.append(int(line[3:].strip()))
    assert seen == expected


def test_startup_recovery_events_are_attributed_to_the_startup_worker() -> None:
    from e_agent.contracts.action import ActionState
    from e_agent.contracts.approval import ApprovalDecision

    class Crash(BaseException):
        """The process dies between reservation and dispatch."""

    crashed: dict[str, str] = {}

    async def factory():
        runtime = await build_runtime(load_profile())
        run = await runtime.coordinator.start_run(runtime.operator, "restock", runtime.scope)
        pres = await runtime.coordinator.pending_approval(runtime.operator.tenant_id, run.run_id)
        original = runtime.store.put_action

        async def die_on_dispatching(action, expected, events):
            if action.state is ActionState.DISPATCHING:
                raise Crash
            return await original(action, expected, events)

        runtime.store.put_action = die_on_dispatching
        with pytest.raises(Crash):
            await runtime.coordinator.decide(
                actor=runtime.operator,
                run_id=run.run_id,
                action_id=pres.action_id,
                action_digest=pres.digest,
                expected_run_revision=pres.run_revision,
                decision=ApprovalDecision.APPROVED,
            )
        runtime.store.put_action = original
        crashed["run_id"] = run.run_id
        return runtime

    with TestClient(create_app(factory)) as client:  # lifespan runs startup recovery
        _login(client)
        run_id = crashed["run_id"]
        body = client.get(f"/v1/runs/{run_id}").json()
        assert body["run"]["state"] == "FAILED", body
        events = client.get(f"/v1/runs/{run_id}/events").json()
        recovery = [e for e in events if e["type"] == "run.state_changed"][-1]
        assert recovery["actor"] == "system:worker:startup"


def test_unexpected_worker_failure_is_logged_with_traceback(
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def factory() -> Any:
        runtime = await build_runtime(load_profile())

        async def boom(tenant_id: str, run_id: str) -> None:
            raise RuntimeError("boom")

        runtime.coordinator.start_admitted_run = boom  # type: ignore[method-assign]
        return runtime

    with (
        caplog.at_level("ERROR", logger="e_agent.server.api"),
        TestClient(create_app(factory)) as c,
    ):
        h = _login(c)
        r = c.post("/v1/runs", json={"task": "x"}, headers={**h, "Idempotency-Key": "boom-0001"})
        body = _wait(c, r.json()["run_id"], {"FAILED", "SUCCEEDED"})
        assert body["run"]["state"] == "FAILED"
        assert "boom" not in json.dumps(body)
    records = [rec for rec in caplog.records if "run work failed" in rec.getMessage()]
    assert records and records[0].levelname == "ERROR"
    assert records[0].exc_info is not None and records[0].exc_info[0] is RuntimeError
    assert r.json()["run_id"] in records[0].getMessage()
