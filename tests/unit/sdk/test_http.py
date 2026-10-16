"""The plugin HTTP helper applies host credentials, pins the host and never echoes secrets."""

from __future__ import annotations

import json
import logging
import pkgutil
import subprocess
import sys

import e_agent.sdk
import httpx
import pytest
from e_agent.contracts.connection import ConnectionOwnership
from e_agent.sdk.auth import AuthContext, Secret
from e_agent.sdk.http import HostNotAllowed, HttpAmbiguous, HttpRejected, PluginHttpClient

BASE = "http://127.0.0.1:8069"
CANARY = "synthetic-credential-canary"
BODY_CANARY = "synthetic-body-canary"


def _auth(header: str = "Authorization", prefix: str = "bearer ") -> AuthContext:
    return AuthContext(
        connection_id="connection",
        connection_version=1,
        ownership=ConnectionOwnership.TENANT_SHARED,
        provider_subject="synthetic-user",
        method="api_key",
        _secret=Secret(CANARY),
        _placement={"header": header, "prefix": prefix},
    )


def _client(handler, base: str = BASE) -> PluginHttpClient:
    return PluginHttpClient(base, transport=httpx.MockTransport(handler))


def _chain(exc: BaseException | None) -> list[BaseException]:
    seen: list[BaseException] = []
    while exc is not None and exc not in seen:
        seen.append(exc)
        exc = exc.__cause__ or exc.__context__
    return seen


def _exported_text(exc: BaseException) -> str:
    """Everything an exception chain would show to a log, a trace or an evidence bundle."""
    parts = []
    for link in _chain(exc):
        parts += [str(link), repr(link), repr(link.args), repr(vars(link))]
    return "\n".join(parts)


async def test_http_applies_auth_context() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"ok": True})

    result = await _client(handler).post_json(
        _auth(), "/json/2/res.partner/search", {"a": 1}, headers={"X-Odoo-Database": "synthetic"}
    )
    assert result == {"ok": True}
    [request] = seen
    assert request.method == "POST"
    assert str(request.url) == f"{BASE}/json/2/res.partner/search"
    assert request.headers["Authorization"] == f"bearer {CANARY}"
    assert request.headers["X-Odoo-Database"] == "synthetic"
    assert request.headers["Content-Type"] == "application/json"
    assert json.loads(request.content) == {"a": 1}


async def test_http_auth_context_wins_over_caller_headers() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={})

    await _client(handler).post_json(
        _auth(), "/x", {}, headers={"Authorization": "bearer caller-chosen"}
    )
    assert seen[0].headers["Authorization"] == f"bearer {CANARY}"


@pytest.mark.parametrize(
    "path",
    [
        "http://evil.example/x",
        "https://127.0.0.1:8069/x",
        "//evil.example/x",
        "@evil.example/x",
        "evil.example/x",
        ":9999/x",
        "",
    ],
)
async def test_http_refuses_other_hosts(path: str) -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={})

    with pytest.raises(HostNotAllowed) as error:
        await _client(handler).post_json(_auth(), path, {})
    assert calls == []
    assert "evil" not in str(error.value)


async def test_http_refuses_a_caller_host_header() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={})

    with pytest.raises(HostNotAllowed):
        await _client(handler).post_json(_auth(), "/x", {}, headers={"host": "evil.example"})
    assert calls == []


async def test_http_does_not_follow_redirects_to_another_host() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(302, headers={"Location": "http://evil.example/steal"})

    with pytest.raises(HttpAmbiguous):
        await _client(handler).post_json(_auth(), "/x", {})
    assert [r.url.host for r in calls] == ["127.0.0.1"]


def _odoo_code(body: object) -> object:
    assert isinstance(body, dict)
    return str(body["message"]).split(":", 1)[0]


@pytest.mark.parametrize(
    ("message", "code"),
    [
        ("E_AGENT_STALE: facts changed", "E_AGENT_STALE"),
        (f"E_AGENT_UNKNOWN: {BODY_CANARY}", "REJECTED"),
        (f"{BODY_CANARY}: anything", "REJECTED"),
    ],
)
async def test_http_4xx_is_rejection_with_allowed_code(message: str, code: str) -> None:
    client = _client(lambda request: httpx.Response(409, json={"message": message}))
    with pytest.raises(HttpRejected) as error:
        await client.post_json(
            _auth(),
            "/x",
            {},
            allowed_codes=frozenset({"E_AGENT_STALE"}),
            rejection_code=_odoo_code,
        )
    assert error.value.status == 409
    assert error.value.code == code
    assert BODY_CANARY not in _exported_text(error.value)
    assert "facts changed" not in _exported_text(error.value)


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(400, content=b"not json " + BODY_CANARY.encode()),
        httpx.Response(400, json=[BODY_CANARY]),
        httpx.Response(400, json={"name": BODY_CANARY}),
    ],
)
async def test_http_4xx_without_a_readable_code_is_rejected(response: httpx.Response) -> None:
    with pytest.raises(HttpRejected) as error:
        await _client(lambda request: response).post_json(
            _auth(), "/x", {}, allowed_codes=frozenset({BODY_CANARY}), rejection_code=_odoo_code
        )
    assert error.value.code == "REJECTED"
    assert BODY_CANARY not in _exported_text(error.value)


def _raise(exc: Exception):
    def handler(request: httpx.Request) -> httpx.Response:
        raise exc

    return handler


@pytest.mark.parametrize(
    "handler",
    [
        lambda request: httpx.Response(500, json={"message": BODY_CANARY}),
        lambda request: httpx.Response(503, content=BODY_CANARY.encode()),
        lambda request: httpx.Response(200, content=b"<html>" + BODY_CANARY.encode()),
        _raise(httpx.ConnectError("connection refused")),
        _raise(httpx.ReadTimeout("read timed out")),
    ],
    ids=["500", "503", "200-not-json", "connect-error", "timeout"],
)
async def test_http_5xx_and_transport_errors_are_ambiguous(handler) -> None:
    with pytest.raises(HttpAmbiguous) as error:
        await _client(handler).post_json(_auth(), "/x", {})
    assert not isinstance(error.value, HttpRejected)
    assert BODY_CANARY not in _exported_text(error.value)


@pytest.mark.parametrize(
    "handler",
    [
        lambda request: httpx.Response(200, json={"ok": True}),
        lambda request: httpx.Response(400, json={"message": CANARY}),
        lambda request: httpx.Response(500, json={"message": CANARY}),
        lambda request: httpx.Response(200, content=CANARY.encode()),
        _raise(httpx.ConnectError("connection refused")),
    ],
    ids=["200", "400-echo", "500-echo", "200-not-json-echo", "connect-error"],
)
@pytest.mark.parametrize("header", ["Authorization", "X-Api-Key"])
async def test_http_never_echoes_credentials(
    handler, header: str, caplog: pytest.LogCaptureFixture
) -> None:
    # X-Api-Key is not redacted by httpx's own header repr, so a leak would show.
    caplog.set_level(logging.DEBUG)
    error: BaseException | None = None
    try:
        await _client(handler).post_json(
            _auth(header=header, prefix=""),
            "/x",
            {},
            allowed_codes=frozenset({"E_AGENT_STALE"}),
            rejection_code=lambda body: body["message"],
        )
    except Exception as exc:
        error = exc
    assert CANARY not in caplog.text
    for record in caplog.records:
        assert CANARY not in repr(vars(record))
    if error is not None:
        assert isinstance(error, HttpRejected | HttpAmbiguous)
        assert CANARY not in _exported_text(error)


def test_sdk_imports_httpx_only_in_http_module() -> None:
    names = sorted(m.name for m in pkgutil.iter_modules(e_agent.sdk.__path__))
    assert "http" in names
    modules = ["e_agent.sdk"] + [f"e_agent.sdk.{n}" for n in names if n != "http"]
    print(f"checked {len(modules)} SDK modules")
    code = "import sys\n" + "".join(f"import {m}\n" for m in modules)
    code += "assert 'httpx' not in sys.modules, 'an SDK module outside sdk.http imported httpx'\n"
    subprocess.run([sys.executable, "-c", code], check=True)
