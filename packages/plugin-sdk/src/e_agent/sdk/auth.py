"""Integration auth SDK, MVP subset (ADR 0013).

Provider adapters receive an AuthContext for exactly one connection and one
invocation. They never see secret references, the secret store or other
connections. Secret material is applied to outgoing requests and is redacted
from repr/str so it cannot leak through logs or exceptions.
"""

from __future__ import annotations

from collections.abc import Mapping, MutableMapping
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from e_agent.contracts.connection import ConnectionOwnership
from e_agent.contracts.context import TaskContext


class AuthError(Exception):
    """Base class; messages never contain secret material."""


class AuthRequired(AuthError):
    def __init__(self, integration_id: str, reason: str) -> None:
        super().__init__(f"{integration_id}: {reason}")
        self.integration_id = integration_id
        self.reason = reason


class ScopeMissing(AuthError):
    def __init__(self, required: frozenset[str], granted: frozenset[str]) -> None:
        super().__init__(f"missing scopes: {sorted(required - granted)}")
        self.required = required
        self.granted = granted


class ReauthRequired(AuthError):
    pass


class CredentialRevoked(AuthError):
    pass


class AuthProviderUnavailable(AuthError):
    pass


class Secret:
    """Opaque secret value with a redacted representation."""

    __slots__ = ("_value",)

    def __init__(self, value: str) -> None:
        self._value = value

    def reveal(self) -> str:
        return self._value

    def __repr__(self) -> str:
        return "Secret(***)"

    __str__ = __repr__


@dataclass(frozen=True)
class AuthContext:
    """Credential view for one connection and one invocation."""

    connection_id: str
    connection_version: int
    ownership: ConnectionOwnership
    provider_subject: str | None
    method: str
    granted_scopes: frozenset[str] = frozenset()
    _secret: Secret | None = field(default=None, repr=False)
    _placement: Mapping[str, str] = field(default_factory=dict, repr=False)

    def require_scopes(self, scopes: frozenset[str]) -> None:
        if not scopes <= self.granted_scopes:
            raise ScopeMissing(scopes, self.granted_scopes)

    def apply(self, headers: MutableMapping[str, str]) -> MutableMapping[str, str]:
        """Attach the credential to outgoing request headers (api_key/bearer methods)."""
        if self.method == "none":
            return headers
        if self._secret is None:
            raise AuthRequired(self.connection_id, "no credential configured")
        header = self._placement.get("header", "Authorization")
        prefix = self._placement.get("prefix", "Bearer ")
        headers[header] = f"{prefix}{self._secret.reveal()}"
        return headers


@runtime_checkable
class SecretStore(Protocol):
    """Write-only from the outside; values are resolved only for AuthContexts."""

    async def put(self, secret_ref: str, value: Secret) -> None: ...

    async def get(self, secret_ref: str) -> Secret: ...

    async def delete(self, secret_ref: str) -> None: ...


@runtime_checkable
class CredentialResolver(Protocol):
    """Host service given to provider adapters, scoped to their own integration."""

    async def context_for(self, ctx: TaskContext, connection_id: str) -> AuthContext: ...
