"""The plugin HTTP helper applies host credentials, pins the host and never echoes secrets."""

from __future__ import annotations

import json
import logging
import pkgutil
import subprocess
import sys

import e_agent.sdk
import httpcore
import httpx
import pytest
from e_agent.contracts.connection import ConnectionOwnership
from e_agent.sdk.auth import AuthContext, Secret
from e_agent.sdk.http import (
    HeaderNotAllowed,
    HostNotAllowed,
    HttpAmbiguous,
    HttpRejected,
    PluginHttpClient,
    RequestRefused,
)

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


@pytest.mark.parametrize("name", ["host", "Host", "Content-Length", "transfer-encoding"])
async def test_http_refuses_caller_routing_and_framing_headers(name: str) -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={})

    with pytest.raises(RequestRefused):
        await _client(handler).post_json(_auth(), "/x", {}, headers={name: "evil.example"})
    assert calls == []


async def test_http_refuses_an_auth_placement_on_the_host_header() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={})

    with pytest.raises(HostNotAllowed) as error:
        await _client(handler).post_json(_auth(header="Host", prefix=""), "/x", {})
    assert calls == []
    assert CANARY not in _exported_text(error.value)


async def test_http_auth_context_replaces_a_caller_header_of_any_case() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={})

    await _client(handler).post_json(
        _auth(), "/x", {}, headers={"authorization": "bearer caller-chosen"}
    )
    assert seen[0].headers.get_list("authorization") == [f"bearer {CANARY}"]


def test_http_refuses_a_base_url_with_userinfo() -> None:
    with pytest.raises(HostNotAllowed) as error:
        PluginHttpClient("https://user:synthetic-password@good.example")
    assert "synthetic-password" not in _exported_text(error.value)


@pytest.mark.parametrize(
    ("secret", "caller"),
    [
        (CANARY + "\u00e9", {}),
        (CANARY + "\n", {}),
        (CANARY, {"X-Note": "a\r\nX-Injected: 1"}),
        (CANARY, {"X-Note": "caf\u00e9"}),
    ],
    ids=["non-ascii-secret", "newline-secret", "crlf-caller", "non-ascii-caller"],
)
async def test_http_refuses_header_values_that_are_not_printable_ascii(secret, caller) -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={})

    auth = AuthContext(
        connection_id="connection",
        connection_version=1,
        ownership=ConnectionOwnership.TENANT_SHARED,
        provider_subject="synthetic-user",
        method="api_key",
        _secret=Secret(secret),
        _placement={"header": "X-Api-Key", "prefix": ""},
    )
    with pytest.raises(HeaderNotAllowed) as error:
        await _client(handler).post_json(auth, "/x", {}, headers=caller)
    assert calls == []
    assert CANARY not in _exported_text(error.value)


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


async def test_http_4xx_that_is_not_json_is_rejected() -> None:
    response = httpx.Response(400, content=b"not json " + BODY_CANARY.encode())
    with pytest.raises(HttpRejected) as error:
        await _client(lambda request: response).post_json(
            _auth(), "/x", {}, allowed_codes=frozenset({BODY_CANARY}), rejection_code=_odoo_code
        )
    assert error.value.code == "REJECTED"
    assert BODY_CANARY not in _exported_text(error.value)


@pytest.mark.parametrize(
    "response",
    [httpx.Response(409, json=[BODY_CANARY]), httpx.Response(409, json={"name": BODY_CANARY})],
    ids=["list-body", "no-message"],
)
async def test_http_4xx_the_caller_cannot_classify_is_ambiguous(response: httpx.Response) -> None:
    # The body may be an identity rejection the caller must reconcile (review R-3).
    with pytest.raises(HttpAmbiguous) as error:
        await _client(lambda request: response).post_json(
            _auth(), "/x", {}, allowed_codes=frozenset({BODY_CANARY}), rejection_code=_odoo_code
        )
    assert not isinstance(error.value, HttpRejected)
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


def _real_transport(*chunks: bytes) -> httpx.AsyncHTTPTransport:
    """httpx's transport over httpcore with a scripted network; httpcore logs as in production."""
    transport = httpx.AsyncHTTPTransport()
    transport._pool = httpcore.AsyncConnectionPool(
        network_backend=httpcore.AsyncMockBackend(list(chunks))
    )
    return transport


@pytest.mark.parametrize(
    "chunks",
    [
        (
            b"HTTP/1.1 200 OK\r\n",
            b"X-Echo: " + CANARY.encode() + b"\r\n",
            b"Content-Type: application/json\r\nContent-Length: 2\r\n\r\n",
            b"{}",
        ),
        (b"HTTP/1.1 200 " + CANARY.encode() + b"\r\nContent-Length: 2\r\n\r\n{}",),
        (b"not http at all " + CANARY.encode() + b"\r\n\r\n",),
    ],
    ids=["echoed-header", "echoed-reason", "malformed"],
)
async def test_http_dependency_logs_never_echo_over_the_real_transport(
    chunks: tuple[bytes, ...], caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    client = PluginHttpClient(BASE, transport=_real_transport(*chunks))
    error: BaseException | None = None
    try:
        await client.post_json(_auth(header="X-Api-Key", prefix=""), "/x", {})
    except HttpAmbiguous as exc:
        error = exc
    if error is not None:
        assert CANARY not in _exported_text(error)
    assert CANARY not in caplog.text
    assert not [r for r in caplog.records if r.name.split(".")[0] in {"httpx", "httpcore"}]


async def test_http_reason_phrase_is_not_logged(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    response = httpx.Response(200, json={}, extensions={"reason_phrase": CANARY.encode()})
    await _client(lambda request: response).post_json(_auth(), "/x", {})
    assert CANARY not in caplog.text


async def test_http_leaves_other_httpx_logging_alone(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)
    PluginHttpClient(BASE)
    transport = httpx.MockTransport(lambda request: httpx.Response(200))
    async with httpx.AsyncClient(transport=transport) as other:
        await other.get("http://127.0.0.1:9/elsewhere")
    assert [r.name for r in caplog.records] == ["httpx"]


def test_sdk_imports_httpx_only_in_http_module() -> None:
    names = sorted(m.name for m in pkgutil.iter_modules(e_agent.sdk.__path__))
    assert "http" in names
    modules = ["e_agent.sdk"] + [f"e_agent.sdk.{n}" for n in names if n != "http"]
    print(f"checked {len(modules)} SDK modules")
    code = "import sys\n" + "".join(f"import {m}\n" for m in modules)
    code += "assert 'httpx' not in sys.modules, 'an SDK module outside sdk.http imported httpx'\n"
    subprocess.run([sys.executable, "-c", code], check=True)
