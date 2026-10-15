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
        # integration_id -> {"method", "header", "prefix"}. Kept by reference and read
        # per call, so the registry can fill it while it admits plugins.
        self._methods = methods if methods is not None else {}

    def scoped(self, integration_id: str) -> ScopedCredentials:
        return ScopedCredentials(self, integration_id)

    async def version(self, ctx: TaskContext, connection_id: str) -> str:
        conn = self._catalog.usable(ctx, connection_id)
        if (
            self._methods.get(conn.integration_id, {}).get("method") == "none"
            or conn.secret_ref is None
        ):
            return "none"
        if self._secrets is None:
            raise AuthRequired(conn.integration_id, "credential metadata unavailable")
        return await self._secrets.version(conn.secret_ref)

    async def _context(
        self, ctx: TaskContext, connection_id: str, integration_id: str
    ) -> AuthContext:
        conn = self._catalog.usable(ctx, connection_id)
        if conn.integration_id != integration_id:
            raise AuthRequired(integration_id, "connection belongs to another integration")
        declared = self._methods.get(integration_id)
        if declared is None:
            # A placement is never defaulted: the manifest must declare one.
            raise AuthRequired(integration_id, "integration declares no auth method")
        spec = dict(declared)
        method = spec.pop("method")
        secret = None
        if method != "none":
            if conn.secret_ref is None or self._secrets is None:
                raise AuthRequired(integration_id, "no credential configured for connection")
            expected = ctx.credential_versions.get(connection_id)
            secret = (
                await self._secrets.get(conn.secret_ref, expected_version=expected)
                if expected is not None
                else await self._secrets.get(conn.secret_ref)
            )
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
