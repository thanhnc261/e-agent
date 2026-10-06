"""Host credential resolution (ADR 0012/0013, MVP subset).

Resolves a connection to a short-lived AuthContext for one invocation, after
the same scope/ownership checks the gateway applies. Adapters receive a
resolver scoped to their own integration and never see secret references.
"""

from __future__ import annotations

from collections.abc import Mapping

from e_agent.contracts.context import TaskContext
from e_agent.sdk.auth import AuthContext, AuthRequired, SecretStore

from .connections import ConnectionCatalog


class CredentialService:
    def __init__(
        self,
        catalog: ConnectionCatalog,
        secrets: SecretStore | None,
        methods: Mapping[str, Mapping[str, str]] | None = None,
    ) -> None:
        self._catalog = catalog
        self._secrets = secrets
        self._methods = dict(methods or {})  # integration_id -> {"method", "header", "prefix"}

    def scoped(self, integration_id: str) -> ScopedCredentials:
        return ScopedCredentials(self, integration_id)

    async def _context(
        self, ctx: TaskContext, connection_id: str, integration_id: str
    ) -> AuthContext:
        conn = self._catalog.usable(ctx, connection_id)
        if conn.integration_id != integration_id:
            raise AuthRequired(integration_id, "connection belongs to another integration")
        spec = dict(self._methods.get(integration_id, {"method": "api_key"}))
        method = spec.pop("method", "api_key")
        secret = None
        if method != "none":
            if conn.secret_ref is None or self._secrets is None:
                raise AuthRequired(integration_id, "no credential configured for connection")
            secret = await self._secrets.get(conn.secret_ref)
        return AuthContext(
            connection_id=conn.connection_id,
            connection_version=conn.version,
            ownership=conn.ownership,
            provider_subject=conn.provider_subject,
            method=method,
            _secret=secret,
            _placement=spec,
        )


class ScopedCredentials:
    def __init__(self, service: CredentialService, integration_id: str) -> None:
        self._service = service
        self._integration_id = integration_id

    async def context_for(self, ctx: TaskContext, connection_id: str) -> AuthContext:
        return await self._service._context(ctx, connection_id, self._integration_id)
