"""Minimal Odoo 19 JSON-2 client.

POST /json/2/<model>/<method> with named arguments; bearer API key via the
host-provided AuthContext; one SQL transaction per call on the Odoo side.
HTTP 4xx responses reject this call; they do not necessarily prove that a
previous call with the same operation identity had no effect. Transport errors
and 5xx are ambiguous for writes (the kernel records UNKNOWN and reconciles).
Transport, host pinning and the no-echo rule come from the SDK HTTP helper.
"""

from __future__ import annotations

from typing import Any

import httpx
from e_agent.sdk.auth import AuthContext
from e_agent.sdk.http import HttpRejected, PluginHttpClient

ALLOWED_CODES = frozenset(
    {
        "E_AGENT_CONFLICT",
        "E_AGENT_DUPLICATE_IN_FLIGHT",
        "E_AGENT_FORBIDDEN",
        "E_AGENT_INVALID",
        "E_AGENT_INVALID_REF",
        "E_AGENT_NOT_SANDBOX",
        "E_AGENT_RESET_REFUSED",
        "E_AGENT_TARGET_MISMATCH",
        "E_AGENT_TARGET_REQUIRED",
        "E_AGENT_STALE",
    }
)


class OdooRejected(Exception):
    """Odoo rejected this call; logical-operation uncertainty is handled by the executor."""

    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(f"{status} {code}")
        self.status = status
        self.code = code
        self.safe_message = message[:200]


def _rejection_code(body: Any) -> object:
    """The bridge prefixes its codes to the message; Odoo's own errors carry a name.

    A body of another shape raises, so the helper reports the call as ambiguous: it
    may hide an identity code the executor has to reconcile (review 1d.7b R-3).
    """
    if not isinstance(body, dict):
        raise TypeError("rejection body is not an object")
    message = body.get("message", "")
    name = body.get("name", "REJECTED")
    if not isinstance(message, str) or not isinstance(name, str):
        raise TypeError("rejection message or name is not a string")
    if message.startswith("E_AGENT_"):
        return message.split(":", 1)[0]
    return name


class OdooJson2Client:
    def __init__(
        self,
        base_url: str,
        database: str,
        timeout: float = 20.0,
        transport: httpx.AsyncBaseTransport | None = None,
        target: dict[str, str] | None = None,
    ) -> None:
        self._http = PluginHttpClient(base_url, timeout=timeout, transport=transport)
        self._db = database
        self._target = dict(target or {})

    async def call(self, auth: AuthContext, model: str, method: str, **kwargs: Any) -> Any:
        if "context" in kwargs:
            raise ValueError("callers cannot override the host target context")
        if self._target:
            kwargs["context"] = {"e_agent_target": self._target}
        try:
            return await self._http.post_json(
                auth,
                f"/json/2/{model}/{method}",
                kwargs,
                headers={"X-Odoo-Database": self._db},
                allowed_codes=ALLOWED_CODES,
                rejection_code=_rejection_code,
            )
        except HttpRejected as exc:
            # Provider bodies may echo submitted values or credentials. Keep only known codes.
            raise OdooRejected(exc.status, exc.code, "Odoo rejected the request") from None
