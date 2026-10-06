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
    assert [f["path"] for f in pres["material_fields"]][:2] == ["currency", "demand_ref"]
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
