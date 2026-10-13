"""Minimal Odoo 19 JSON-2 client.

POST /json/2/<model>/<method> with named arguments; bearer API key via the
host-provided AuthContext; one SQL transaction per call on the Odoo side.
HTTP 4xx responses reject this call; they do not necessarily prove that a
previous call with the same operation identity had no effect. Transport errors
and 5xx are ambiguous for writes (the kernel records UNKNOWN and reconciles).
"""

from __future__ import annotations

from typing import Any

import httpx
from e_agent.sdk.auth import AuthContext


class OdooRejected(Exception):
    """Odoo rejected this call; logical-operation uncertainty is handled by the executor."""

    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(f"{status} {code}")
        self.status = status
        self.code = code
        self.safe_message = message[:200]


class OdooJson2Client:
    def __init__(
        self,
        base_url: str,
        database: str,
        timeout: float = 20.0,
        transport: httpx.AsyncBaseTransport | None = None,
        target: dict[str, str] | None = None,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._db = database
        self._timeout = timeout
        self._transport = transport
        self._target = dict(target or {})

    async def call(self, auth: AuthContext, model: str, method: str, **kwargs: Any) -> Any:
        if "context" in kwargs:
            raise ValueError("callers cannot override the host target context")
        if self._target:
            kwargs["context"] = {"e_agent_target": self._target}
        headers: dict[str, str] = {"X-Odoo-Database": self._db, "Content-Type": "application/json"}
        auth.apply(headers)
        async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as http:
            resp = await http.post(
                f"{self._base}/json/2/{model}/{method}", json=kwargs, headers=headers
            )
        if 400 <= resp.status_code < 500:
            code, message = "REJECTED", ""
            try:
                body = resp.json()
                message = str(body.get("message", ""))
                code = (
                    message.split(":", 1)[0]
                    if message.startswith("E_AGENT_")
                    else (body.get("name", "REJECTED"))
                )
            except ValueError:
                pass
            allowed = {
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
            code = str(code) if code in allowed else "REJECTED"
            # Provider bodies may echo submitted values or credentials. Keep only known codes.
            raise OdooRejected(resp.status_code, code, "Odoo rejected the request")
        resp.raise_for_status()  # 5xx -> ambiguous, propagates as an exception
        return resp.json()
