"""RunStore port: durable run/action ledger with atomic business operations.

Each method is one local transaction. Implementations must never hold a
transaction open across model or provider calls (AGENTS.md, ADR 0003).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from contextlib import AbstractAsyncContextManager
from typing import Any, Protocol, runtime_checkable

from e_agent.contracts.action import ActionRecord
from e_agent.contracts.approval import ApprovalRecord
from e_agent.contracts.events import RunEvent, RunEventType
from e_agent.contracts.outcome import OutcomeReport
from e_agent.contracts.receipt import ExecutionReceipt
from e_agent.contracts.run import RunRecord


class ConcurrencyConflict(Exception):
    """Compare-and-swap failed: the record changed since it was read."""


class DuplicateOperation(Exception):
    """A reservation for this logical operation already exists."""


class NotFound(Exception):
    pass


EventSpec = tuple[RunEventType, Mapping[str, Any], str | None]
"""(event type, payload, action_id) appended atomically with a state change."""


@runtime_checkable
class RunStore(Protocol):
    async def create_run(self, run: RunRecord, events: Sequence[EventSpec]) -> None: ...

    async def get_run(self, tenant_id: str, run_id: str) -> RunRecord: ...

    async def update_run(
        self, run: RunRecord, expected_revision: int, events: Sequence[EventSpec]
    ) -> RunRecord: ...

    async def put_action(
        self, action: ActionRecord, expected_revision: int | None, events: Sequence[EventSpec]
    ) -> ActionRecord: ...

    async def get_action(self, tenant_id: str, action_id: str) -> ActionRecord: ...

    async def reserve_operation(
        self,
        action: ActionRecord,
        expected_revision: int,
        events: Sequence[EventSpec],
    ) -> ActionRecord:
        """Atomically create the unique (tenant, connection, logical op) reservation
        and move the action to RESERVED. Raises DuplicateOperation if one exists."""
        ...

    async def record_approval(
        self, approval: ApprovalRecord, events: Sequence[EventSpec]
    ) -> None: ...

    async def record_receipt(
        self,
        receipt: ExecutionReceipt,
        action: ActionRecord,
        expected_revision: int,
        events: Sequence[EventSpec],
    ) -> ActionRecord: ...

    async def record_outcome(
        self,
        tenant_id: str,
        outcome: OutcomeReport,
        action: ActionRecord | None,
        expected_revision: int | None,
        events: Sequence[EventSpec],
    ) -> None: ...

    async def list_events(
        self, tenant_id: str, run_id: str, after_sequence: int = 0
    ) -> list[RunEvent]: ...

    async def list_actions(self, tenant_id: str, run_id: str) -> list[ActionRecord]: ...

    async def list_receipts(self, tenant_id: str, action_id: str) -> list[ExecutionReceipt]: ...

    async def list_approvals(self, tenant_id: str, action_id: str) -> list[ApprovalRecord]: ...

    async def claim_idempotency(
        self, tenant_id: str, actor_id: str, key: str, request_digest: str, run_id: str
    ) -> tuple[str, str]:
        """Atomically record (key -> run_id) or return the existing (run_id, digest)."""
        ...

    async def list_unfinished_runs(self) -> list[RunRecord]:
        """Runs not in a terminal state, for startup recovery."""
        ...

    async def save_continuation(
        self,
        tenant_id: str,
        run_id: str,
        state: Mapping[str, Any],
        driver_state: Mapping[str, Any] | None,
    ) -> None: ...

    async def load_continuation(
        self, tenant_id: str, run_id: str
    ) -> tuple[dict[str, Any], dict[str, Any] | None] | None: ...

    def writer_lock(self, tenant_id: str, connection_id: str) -> AbstractAsyncContextManager[None]:
        """Serializes writes per (tenant, connection) when the provider lacks atomic
        uniqueness (ADR 0003). Held across the provider call, never a DB transaction."""
        ...
