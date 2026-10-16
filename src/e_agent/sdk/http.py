"""Authenticated HTTP helper for provider plugins (ADR 0026, common-SDK amendment).

Install with the ``e-agent-plugin-sdk[http]`` extra; no other SDK module imports
httpx. The helper sends JSON to one connection's base URL with the host-provided
AuthContext and classifies the outcome:

- 2xx with a JSON body: the parsed body is returned.
- 4xx: ``HttpRejected``, with a code from the caller's allow-list (otherwise
  ``REJECTED``) and a fixed message. It rejects this call; it does not prove that a
  previous call with the same operation identity had no effect. A 4xx whose JSON
  body the caller's ``rejection_code`` cannot read is ``HttpAmbiguous`` instead: it
  may be an identity rejection the caller has to reconcile.
- anything else (5xx, a redirect, a body that is not JSON, a timeout or a transport
  error): ``HttpAmbiguous``. For a write the effect is unknown.

Before anything is sent, a request is refused (``RequestRefused``) when it would
leave the base-URL host, when the base URL carries userinfo, when a header would
set the host or the message framing, or when a header is not printable ASCII.

Headers and response bodies are never logged, kept on an exception or chained into
one: the exceptions are raised outside the handler of the underlying error, and
httpx's and httpcore's own log records are dropped while a request of this helper
is in flight (they carry response headers and the reason phrase).
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable, Mapping
from contextvars import ContextVar
from typing import Any

import httpx
from e_agent.sdk.auth import AuthContext

REJECTED = "REJECTED"

# The loggers httpx and httpcore emit records on. A logger's filter sees only its
# own records, not those propagating from children, so each one is named.
_LIBRARY_LOGGERS = (
    "httpx",
    "httpcore.connection",
    "httpcore.http11",
    "httpcore.http2",
    "httpcore.proxy",
    "httpcore.socks",
)
_IN_FLIGHT: ContextVar[bool] = ContextVar("e_agent_sdk_http_in_flight", default=False)
_RESERVED_HEADERS = frozenset({"host", "content-length", "transfer-encoding"})
_HEADER_NAME = re.compile(r"[!#$%&'*+\-.^_`|~0-9A-Za-z]+")
_HEADER_VALUE = re.compile(r"[\x20-\x7e]*")


class RequestRefused(ValueError):
    """The helper refused to build the request; nothing was sent."""

    def __init__(self, reason: str) -> None:
        super().__init__(f"request refused: {reason}")
        self.reason = reason


class HostNotAllowed(RequestRefused):
    """The request would leave the connection's base-URL host."""

    def __init__(self) -> None:
        super().__init__("target is not the connection's base-URL host")


class HeaderNotAllowed(RequestRefused):
    """A header is reserved to the helper or is not a printable-ASCII HTTP header."""

    def __init__(self) -> None:
        super().__init__("a request header is reserved or not a valid HTTP header")


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


class _DropWhileInFlight(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return not _IN_FLIGHT.get()


def _silence_library_logs_in_flight() -> None:
    for name in _LIBRARY_LOGGERS:
        logger = logging.getLogger(name)
        if not any(isinstance(f, _DropWhileInFlight) for f in logger.filters):
            logger.addFilter(_DropWhileInFlight())


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
        base: httpx.URL | None
        try:
            base = httpx.URL(self._base)
        except httpx.InvalidURL:
            base = None
        # Userinfo would make httpx send Basic auth in place of the AuthContext.
        if base is None or base.userinfo or not base.host:
            raise HostNotAllowed()
        self._origin = _origin(base)
        self._timeout = timeout
        self._transport = transport
        _silence_library_logs_in_flight()

    def _url(self, path: str) -> httpx.URL:
        if not path.startswith("/") or path.startswith("//"):
            raise HostNotAllowed()
        url: httpx.URL | None
        try:
            url = httpx.URL(f"{self._base}{path}")
        except httpx.InvalidURL:
            url = None
        if url is None or url.userinfo or _origin(url) != self._origin:
            raise HostNotAllowed()
        return url

    @staticmethod
    def _headers(auth: AuthContext, headers: Mapping[str, str] | None) -> dict[str, str]:
        """Caller headers, then the JSON content type, then the credential, which wins."""
        applied: dict[str, str] = {}
        auth.apply(applied)
        overridden = {name.lower() for name in applied} | {"content-type"}
        merged = {k: v for k, v in (headers or {}).items() if k.lower() not in overridden}
        merged["Content-Type"] = "application/json"
        merged.update(applied)
        names = {name.lower() for name in merged}
        if "host" in names:
            raise HostNotAllowed()
        if names & _RESERVED_HEADERS:
            raise HeaderNotAllowed()
        for name, value in merged.items():
            if not _HEADER_NAME.fullmatch(name) or not _HEADER_VALUE.fullmatch(value):
                raise HeaderNotAllowed()
        return merged

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

        ``rejection_code`` reads a code from a parsed 4xx body and raises when the body
        does not have the shape it knows; only codes in ``allowed_codes`` leave the
        helper. The body itself never does.
        """
        url = self._url(path)
        sent = self._headers(auth, headers)
        failure: str | None = None
        response: httpx.Response | None = None
        token = _IN_FLIGHT.set(True)
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout, transport=self._transport, follow_redirects=False
            ) as http:
                request: httpx.Request | None
                try:
                    request = http.build_request("POST", url, json=body, headers=sent)
                except (ValueError, httpx.InvalidURL):
                    request = None
                if request is None:
                    failure = "refused"
                elif _origin(request.url) != self._origin:
                    failure = "host"
                else:
                    try:
                        response = await http.send(request)
                    except httpx.TimeoutException:
                        failure = "the provider did not answer in time"
                    except httpx.HTTPError:
                        failure = "the provider could not be reached"
        finally:
            _IN_FLIGHT.reset(token)
        if failure == "refused":
            raise RequestRefused("the request could not be built")
        if failure == "host":
            raise HostNotAllowed()
        if response is None:
            raise HttpAmbiguous(failure or "the provider could not be reached")
        status = response.status_code
        if 400 <= status < 500:
            code = self._code(response, allowed_codes, rejection_code)
            if code is None:
                raise HttpAmbiguous(f"the provider rejection (HTTP {status}) could not be read")
            raise HttpRejected(status, code)
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
    ) -> str | None:
        """The allow-listed code, ``REJECTED``, or None when the caller cannot read the body."""
        parsed, readable = _json(response)
        if not readable or rejection_code is None:
            return REJECTED
        try:
            code = rejection_code(parsed)
        except Exception:  # the body does not have the shape the caller knows
            return None
        return code if isinstance(code, str) and code in allowed_codes else REJECTED


def _json(response: httpx.Response) -> tuple[Any, bool]:
    """The parsed body and whether it parsed; the decode error (which holds the body) is dropped."""
    try:
        return response.json(), True
    except ValueError:
        return None, False
