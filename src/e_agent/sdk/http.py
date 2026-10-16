"""Authenticated HTTP helper for provider plugins (ADR 0026, common-SDK amendment).

Install with the ``e-agent-plugin-sdk[http]`` extra; no other SDK module imports
httpx. The helper sends JSON to one connection's base URL with the host-provided
AuthContext and classifies the outcome:

- 2xx with a JSON body: the parsed body is returned.
- 4xx: ``HttpRejected``, with a code from the caller's allow-list (otherwise
  ``REJECTED``) and a fixed message. It rejects this call; it does not prove that a
  previous call with the same operation identity had no effect.
- anything else (5xx, a redirect, a body that is not JSON, a timeout or a transport
  error): ``HttpAmbiguous``. For a write the effect is unknown.

A request to any other host is refused before it is sent. Headers and response
bodies are never logged, kept on an exception or chained into one: the exceptions
are raised outside the handler of the underlying httpx error.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

import httpx
from e_agent.sdk.auth import AuthContext

REJECTED = "REJECTED"


class HostNotAllowed(ValueError):
    """The request would leave the connection's base-URL host; nothing was sent."""

    def __init__(self) -> None:
        super().__init__("request refused: target is not the connection's base-URL host")


class HttpRejected(Exception):
    """The provider rejected this call with a 4xx answer."""

    def __init__(self, status: int, code: str) -> None:
        super().__init__(f"{status} {code}")
        self.status = status
        self.code = code
        self.safe_message = "the provider rejected the request"


class HttpAmbiguous(Exception):
    """The outcome of the call is unknown; a write may or may not have committed."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _origin(url: httpx.URL) -> tuple[str, str, int | None]:
    return url.scheme, url.host, url.port


class PluginHttpClient:
    """JSON over HTTP to one connection's base URL; credentials applied per request."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 20.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._origin = _origin(httpx.URL(self._base))
        self._timeout = timeout
        self._transport = transport

    def _url(self, path: str) -> httpx.URL:
        if not path.startswith("/") or path.startswith("//"):
            raise HostNotAllowed()
        try:
            url = httpx.URL(f"{self._base}{path}")
        except httpx.InvalidURL:
            url = None
        if url is None or _origin(url) != self._origin:
            raise HostNotAllowed()
        return url

    async def post_json(
        self,
        auth: AuthContext,
        path: str,
        body: Any,
        *,
        headers: Mapping[str, str] | None = None,
        allowed_codes: frozenset[str] = frozenset(),
        rejection_code: Callable[[Any], object] | None = None,
    ) -> Any:
        """POST ``body`` as JSON to ``path`` under the base URL and return the JSON answer.

        ``rejection_code`` reads a code from a parsed 4xx body; only codes in
        ``allowed_codes`` leave the helper. The body itself never does.
        """
        url = self._url(path)
        sent: dict[str, str] = dict(headers or {})
        if any(name.lower() == "host" for name in sent):
            raise HostNotAllowed()
        sent["Content-Type"] = "application/json"
        auth.apply(sent)
        failure: str | None = None
        response: httpx.Response | None = None
        async with httpx.AsyncClient(
            timeout=self._timeout, transport=self._transport, follow_redirects=False
        ) as http:
            request = http.build_request("POST", url, json=body, headers=sent)
            if _origin(request.url) != self._origin:
                raise HostNotAllowed()
            try:
                response = await http.send(request)
            except httpx.TimeoutException:
                failure = "the provider did not answer in time"
            except httpx.HTTPError:
                failure = "the provider could not be reached"
        if response is None:
            raise HttpAmbiguous(failure or "the provider could not be reached")
        status = response.status_code
        if 400 <= status < 500:
            raise HttpRejected(status, self._code(response, allowed_codes, rejection_code))
        if not 200 <= status < 300:
            raise HttpAmbiguous(f"the provider answered HTTP {status}")
        parsed, readable = _json(response)
        if not readable:
            raise HttpAmbiguous("the provider answer is not JSON")
        return parsed

    @staticmethod
    def _code(
        response: httpx.Response,
        allowed_codes: frozenset[str],
        rejection_code: Callable[[Any], object] | None,
    ) -> str:
        parsed, readable = _json(response)
        if not readable or rejection_code is None:
            return REJECTED
        try:
            code = rejection_code(parsed)
        except Exception:  # a body without the expected shape carries no code
            return REJECTED
        return code if isinstance(code, str) and code in allowed_codes else REJECTED


def _json(response: httpx.Response) -> tuple[Any, bool]:
    """The parsed body and whether it parsed; the decode error (which holds the body) is dropped."""
    try:
        return response.json(), True
    except ValueError:
        return None, False
