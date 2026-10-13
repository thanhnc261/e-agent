"""Connections and credential subjects (ADR 0012, ADR 0013)."""

from __future__ import annotations

from enum import StrEnum

from pydantic import model_validator

from .common import Record


class ConnectionOwnership(StrEnum):
    TENANT_SHARED = "tenant_shared"
    USER_DELEGATED = "user_delegated"


class ConnectionStatus(StrEnum):
    DRAFT = "draft"
    VERIFYING = "verifying"
    ACTIVE = "active"
    DEGRADED = "degraded"
    REAUTH_REQUIRED = "reauth_required"
    DISABLED = "disabled"
    REVOKED = "revoked"


class ConnectionDescriptor(Record):
    """Non-secret description of one connection. Secret material is only a reference."""

    tenant_id: str
    connection_id: str
    version: int
    integration_id: str
    ownership: ConnectionOwnership
    owner_principal: str | None = None
    provider_subject: str | None = None
    allowed_resources: frozenset[str] = frozenset()
    secret_ref: str | None = None
    status: ConnectionStatus = ConnectionStatus.ACTIVE

    @model_validator(mode="after")
    def _owner_matches_ownership(self) -> ConnectionDescriptor:
        delegated = self.ownership is ConnectionOwnership.USER_DELEGATED
        if delegated and not self.owner_principal:
            raise ValueError("user_delegated connections require owner_principal")
        if not delegated and self.owner_principal:
            raise ValueError("tenant_shared connections must not have owner_principal")
        if self.version < 1:
            raise ValueError("connection version starts at 1")
        return self

    def credential_subject(self) -> str:
        """Stable identity of whose credential executes: connection@version/subject."""
        subject = self.provider_subject or "unknown"
        return f"{self.connection_id}@{self.version}/{subject}"
