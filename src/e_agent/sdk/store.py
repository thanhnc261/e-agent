"""RunStore port: durable run/action ledger with atomic business operations.

Each method is one local transaction. Implementations must never hold a
transaction open across model or provider calls (AGENTS.md, ADR 0003).
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from contextlib import AbstractAsyncContextManager, contextmanager
from contextvars import ContextVar
from typing import Any, Protocol, runtime_checkable

from e_agent.contracts.action import ActionRecord
from e_agent.contracts.approval import ApprovalRecord
from e_agent.contracts.conversation import Conversation, ConversationPage
from e_agent.contracts.events import RunEvent, RunEventType
from e_agent.contracts.outcome import OutcomeReport
from e_agent.contracts.plan import ActionPlan
from e_agent.contracts.receipt import ExecutionReceipt
from e_agent.contracts.run import RunRecord
from e_agent.contracts.step import StepRecord
from e_agent.contracts.work import WorkClaim

current_actor: ContextVar[str] = ContextVar("e_agent_current_actor", default="system:kernel")
"""Who causes the events appended in this context (ADR 0018): ``principal:<id>``,
``system:kernel`` or ``system:worker:<owner>``. Set by the API session and the worker."""


@contextmanager
def actor_scope(actor: str) -> Iterator[None]:
    token = current_actor.set(actor)
    try:
        yield
    finally:
        current_actor.reset(token)


class ConcurrencyConflict(Exception):
    """Compare-and-swap failed: the record changed since it was read."""


class DuplicateOperation(Exception):
    """A reservation for this logical operation already exists."""


class ConnectionBusy(ConcurrencyConflict):
    """Another action on this connection is RESERVED, DISPATCHING or UNKNOWN (ADR 0020).

    Not retryable: the earlier write must resolve first. Handled in the coordinator's `_dispatch`.
    """


class NotFound(Exception):
    pass


EventSpec = tuple[RunEventType, Mapping[str, Any], str | None]
"""(event type, payload, action_id) appended atomically with a state change."""

EventBatch = Sequence[EventSpec | StepRecord]
"""Events and step records committed together with a write (ADR 0025, target §5.4).

A step record is an append-only state row: a status change appends a new row with the same
``step_id`` and a higher ``sequence``. Every step must belong to the run being written
(``ValueError`` otherwise), and its sequence must be strictly greater than the run's last
step sequence and any earlier step in the batch (``ConcurrencyConflict`` otherwise). A
refused step leaves the whole write, its events and its steps uncommitted."""


@runtime_checkable
class RunStore(Protocol):
    async def create_run(self, run: RunRecord, events: EventBatch) -> None: ...

    async def create_run_idempotent(
        self,
        run: RunRecord,
        events: EventBatch,
        state: Mapping[str, Any],
        actor_id: str,
        key: str,
        request_digest: str,
    ) -> tuple[str, str]:
        """Atomically admit the request, run, continuation and start work."""
        ...

    async def get_run(self, tenant_id: str, run_id: str) -> RunRecord: ...

    async def update_run(
        self,
        run: RunRecord,
        expected_revision: int,
        events: EventBatch,
        *,
        continuation: tuple[Mapping[str, Any], Mapping[str, Any] | None] | None = None,
        work: tuple[str, Mapping[str, Any], str] | None = None,
    ) -> RunRecord: ...

    async def put_action(
        self, action: ActionRecord, expected_revision: int | None, events: EventBatch
    ) -> ActionRecord: ...

    async def wait_for_approval(
        self,
        action: ActionRecord,
        expected_action_revision: int,
        run: RunRecord,
        expected_run_revision: int,
        continuation: tuple[Mapping[str, Any], Mapping[str, Any] | None],
        events: EventBatch,
    ) -> None:
        """Checkpoint the pending action, run, continuation and presentation events together."""
        ...

    async def get_action(self, tenant_id: str, action_id: str) -> ActionRecord: ...

    async def reserve_operation(
        self,
        action: ActionRecord,
        expected_revision: int,
        events: EventBatch,
    ) -> ActionRecord:
        """Atomically create the unique (tenant, connection, logical op) reservation
        and move the action to RESERVED. Raises DuplicateOperation if one exists."""
        ...

    async def record_approval(
        self,
        approval: ApprovalRecord,
        events: EventBatch,
        *,
        action: ActionRecord | None = None,
        expected_revision: int | None = None,
    ) -> None: ...

    async def record_receipt(
        self,
        receipt: ExecutionReceipt,
        action: ActionRecord,
        expected_revision: int,
        events: EventBatch,
    ) -> ActionRecord: ...

    async def record_outcome(
        self,
        tenant_id: str,
        outcome: OutcomeReport,
        action: ActionRecord | None,
        expected_revision: int | None,
        events: EventBatch,
    ) -> None: ...

    async def put_plan(
        self, tenant_id: str, run_id: str, plan: ActionPlan, events: EventBatch
    ) -> None:
        """Store a plan for an existing run (``NotFound`` otherwise). A plan is never
        overwritten: a second put of its ``plan_id`` in the tenant is a ``ConcurrencyConflict``.
        Arguments outside the digest profile (ADR 0006) raise ``ValueError`` before anything
        is written (`plan_to_wire`), so a literal can never return as a placeholder."""
        ...

    async def get_plan(self, tenant_id: str, plan_id: str) -> ActionPlan:
        """``NotFound`` for an unknown id or another tenant's plan."""
        ...

    async def list_events(
        self, tenant_id: str, run_id: str, after_sequence: int = 0, limit: int | None = None
    ) -> list[RunEvent]:
        """Events after `after_sequence` in order; at most `limit` when given (ADR 0018)."""
        ...

    async def list_steps(self, tenant_id: str, run_id: str) -> list[StepRecord]:
        """Step records of the run in sequence order; empty for another tenant."""
        ...

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

    async def enqueue_work(
        self,
        tenant_id: str,
        run_id: str,
        kind: str,
        payload: Mapping[str, Any],
        request_digest: str,
    ) -> None: ...

    async def claim_work(self, owner: str, lease_seconds: int = 30) -> WorkClaim | None: ...

    async def renew_work(self, claim: WorkClaim, lease_seconds: int = 30) -> bool: ...

    async def finish_work(self, claim: WorkClaim) -> None: ...

    def work_scope(self, claim: WorkClaim) -> AbstractAsyncContextManager[None]: ...

    async def has_pending_work(self, tenant_id: str, run_id: str) -> bool: ...


MAX_CONVERSATION_PAGE = 100
"""The largest ``limit`` of ``ConversationStore.list_conversations``."""
LINKED_RUN_REFUSED = "a linked run is created only by create_run_in_conversation"
LINK_CHANGE_REFUSED = "a run's conversation_id never changes"


@runtime_checkable
class ConversationStore(Protocol):
    """Conversations and the runs linked to them (ADR 0023 §3), beside ``RunStore``.

    Every read filters by tenant **and** owner: another owner's or tenant's conversation
    raises ``NotFound``, so it looks absent, never forbidden (PR-24).

    Only ``create_run_in_conversation`` creates a linked run. A store that implements this
    port refuses a run with ``conversation_id`` set in ``create_run`` and
    ``create_run_idempotent`` (``ValueError(LINKED_RUN_REFUSED)``), and a record whose
    ``conversation_id`` differs from the stored run's in ``update_run`` and
    ``wait_for_approval`` (``ValueError(LINK_CHANGE_REFUSED)``), so the active-run check
    sees every linked run."""

    async def create_conversation(self, conversation: Conversation) -> None:
        """Store a new conversation, whose revision is exactly 1 (``ValueError`` otherwise). A
        conversation is never overwritten: a second create of its id in the tenant is a
        ``ConcurrencyConflict``."""
        ...

    async def get_conversation(
        self, tenant_id: str, owner_id: str, conversation_id: str
    ) -> Conversation: ...

    async def list_conversations(
        self, tenant_id: str, owner_id: str, *, after: str | None, limit: int
    ) -> ConversationPage:
        """Newest first by ``created_at`` (then id), so a revision bump never reorders a page.
        ``after`` is the ``next_after`` of the previous page: the last conversation id it
        held; one the owner does not have raises ``NotFound``. ``limit`` outside 1 to
        ``MAX_CONVERSATION_PAGE`` raises ``ValueError``; ``next_after`` is set only when more
        conversations follow."""
        ...

    async def list_conversation_runs(
        self, tenant_id: str, owner_id: str, conversation_id: str
    ) -> tuple[RunRecord, ...]:
        """The conversation's runs, oldest first by ``created_at`` (then run id)."""
        ...

    async def lookup_idempotent(
        self, tenant_id: str, actor_id: str, key: str
    ) -> tuple[str, str] | None:
        """The (run id, request digest) recorded for the key, or ``None``. Writes nothing."""
        ...

    async def create_run_in_conversation(
        self,
        run: RunRecord,
        events: EventBatch,
        state: Mapping[str, Any],
        actor_id: str,
        key: str,
        request_digest: str,
        conversation_revision: int,
    ) -> tuple[str, str]:
        """``create_run_idempotent`` for a run of ``run.conversation_id`` (``ValueError`` when
        unset; ``NotFound`` when the tenant has no such conversation).

        A recorded (tenant, actor, key) returns its (run id, digest) at once, with no
        conversation check and no bump; the caller compares the digest. Otherwise, in the
        transaction of the run insert, a conversation revision other than
        ``conversation_revision`` or a run of the conversation in a non-terminal state raises
        ``ConcurrencyConflict``; else the run is admitted and the conversation's revision and
        ``updated_at`` move. One active run per conversation is this check."""
        ...
