"""Minimal Odoo 19 JSON-2 client.

POST /json/2/<model>/<method> with named arguments; bearer API key via the
host-provided AuthContext; one SQL transaction per call on the Odoo side.
HTTP 4xx responses are authoritative rejections; transport errors and 5xx
are ambiguous for writes (the kernel records UNKNOWN and reconciles).
"""

from __future__ import annotations

from typing import Any

import httpx
from e_agent.sdk.auth import AuthContext


class OdooRejected(Exception):
    """Odoo answered with a 4xx: the call had no effect."""

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
    ) -> None:
        self._base = base_url.rstrip("/")
        self._db = database
        self._timeout = timeout
        self._transport = transport

    async def call(self, auth: AuthContext, model: str, method: str, **kwargs: Any) -> Any:
        headers: dict[str, str] = {"X-Odoo-Database": self._db, "Content-Type": "application/json"}
        auth.apply(headers)
        async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as http:
            resp = await http.post(
                f"{self._base}/json/2/{model}/{method}", json=kwargs, headers=headers
            )
        if 400 <= resp.status_code < 500:
            code, message = "REJECTED", resp.text
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
            raise OdooRejected(resp.status_code, str(code), message)
        resp.raise_for_status()  # 5xx -> ambiguous, propagates as an exception
        return resp.json()
