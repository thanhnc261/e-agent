"""Host-side connection catalog and resolution (ADR 0012/0013).

The model may name a connection as a hint; only the host decides whether that
connection is usable by this requester in this tenant.
"""

from __future__ import annotations

from collections.abc import Iterable

from e_agent.contracts.connection import (
    ConnectionDescriptor,
    ConnectionOwnership,
    ConnectionStatus,
)
from e_agent.contracts.context import TaskContext

from .errors import ErrorCode, KernelError


class ConnectionCatalog:
    def __init__(self, connections: Iterable[ConnectionDescriptor]) -> None:
        self._by_id: dict[tuple[str, str], ConnectionDescriptor] = {}
        for conn in connections:
            key = (conn.tenant_id, conn.connection_id)
            if key in self._by_id:
                raise KernelError(ErrorCode.STARTUP_REJECTED, f"duplicate connection {key}")
            self._by_id[key] = conn

    def update(self, conn: ConnectionDescriptor) -> None:
        """Replace a connection with a newer version (admin change)."""
        key = (conn.tenant_id, conn.connection_id)
        current = self._by_id.get(key)
        if current is not None and conn.version <= current.version:
            raise KernelError(ErrorCode.CONFLICT, "connection version must increase")
        self._by_id[key] = conn

    def usable(self, ctx: TaskContext, connection_id: str) -> ConnectionDescriptor:
        conn = self._by_id.get((ctx.tenant_id, connection_id))
        # Same error for "absent" and "other tenant": never reveal existence.
        if conn is None or connection_id not in ctx.resource_scope:
            raise KernelError(ErrorCode.FORBIDDEN, "connection not available")
        if conn.status is not ConnectionStatus.ACTIVE:
            raise KernelError(ErrorCode.DEPENDENCY_UNAVAILABLE, "connection not active")
        if (
            conn.ownership is ConnectionOwnership.USER_DELEGATED
            and conn.owner_principal != ctx.principal.principal_id
        ):
            raise KernelError(ErrorCode.FORBIDDEN, "connection not available")
        return conn

    def for_tenant(self, tenant_id: str) -> list[ConnectionDescriptor]:
        return [c for (t, _), c in self._by_id.items() if t == tenant_id]
