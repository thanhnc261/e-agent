"""In-memory ConversationStore (ADR 0023 §3): the run store plus conversation rows.

Lock order: ``_conversation_lock``, then the parent's ``_lock``, never the reverse. No parent
method takes ``_conversation_lock``, and this class never takes ``_lock`` itself
(``asyncio.Lock`` is not reentrant). Reads of the parent's dicts between two ``await``s need
no lock: nothing else runs in between. The one-active-run check holds because only
``create_run_in_conversation`` creates linked runs and terminal states are final.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any

from e_agent.contracts.common import utc_now
from e_agent.contracts.conversation import Conversation, ConversationPage
from e_agent.contracts.run import TERMINAL_RUN_STATES, RunRecord
from e_agent.sdk.store import (
    MAX_CONVERSATION_PAGE,
    ConcurrencyConflict,
    EventBatch,
    NotFound,
)

from .memory_store import InMemoryRunStore


class InMemoryConversationStore(InMemoryRunStore):
    def __init__(self) -> None:
        super().__init__()
        self._conversation_lock = asyncio.Lock()
        self._conversations: dict[tuple[str, str], Conversation] = {}

    def _owned(self, tenant_id: str, owner_id: str, conversation_id: str) -> Conversation:
        found = self._conversations.get((tenant_id, conversation_id))
        if found is None or found.owner_id != owner_id:
            raise NotFound(conversation_id)
        return found

    async def create_conversation(self, conversation: Conversation) -> None:
        if conversation.revision < 1:
            raise ValueError("a new conversation starts at revision 1")
        async with self._conversation_lock:
            key = (conversation.tenant_id, conversation.conversation_id)
            if key in self._conversations:
                raise ConcurrencyConflict(f"conversation {conversation.conversation_id} exists")
            self._conversations[key] = conversation

    async def get_conversation(
        self, tenant_id: str, owner_id: str, conversation_id: str
    ) -> Conversation:
        return self._owned(tenant_id, owner_id, conversation_id)

    async def list_conversations(
        self, tenant_id: str, owner_id: str, *, after: str | None, limit: int
    ) -> ConversationPage:
        if not 1 <= limit <= MAX_CONVERSATION_PAGE:
            raise ValueError(f"limit must be 1 to {MAX_CONVERSATION_PAGE}, not {limit}")
        owned = sorted(
            (
                c
                for (t, _), c in self._conversations.items()
                if t == tenant_id and c.owner_id == owner_id
            ),
            key=_order,
            reverse=True,
        )
        if after is not None:
            cursor = self._owned(tenant_id, owner_id, after)
            owned = [c for c in owned if _order(c) < _order(cursor)]
        items = tuple(owned[:limit])
        more = len(owned) > limit
        return ConversationPage(items=items, next_after=items[-1].conversation_id if more else None)

    async def list_conversation_runs(
        self, tenant_id: str, owner_id: str, conversation_id: str
    ) -> tuple[RunRecord, ...]:
        self._owned(tenant_id, owner_id, conversation_id)
        return tuple(sorted(self._linked(tenant_id, conversation_id), key=_run_order))

    def _linked(self, tenant_id: str, conversation_id: str) -> list[RunRecord]:
        return [
            r
            for (t, _), r in self._runs.items()
            if t == tenant_id and r.conversation_id == conversation_id
        ]

    async def lookup_idempotent(
        self, tenant_id: str, actor_id: str, key: str
    ) -> tuple[str, str] | None:
        return self._idempotency.get((tenant_id, actor_id, key))

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
        if run.conversation_id is None:
            raise ValueError("a run created in a conversation names its conversation")
        async with self._conversation_lock:
            recorded = self._idempotency.get((run.tenant_id, actor_id, key))
            if recorded is not None:  # a replay: no conversation check, no bump
                return recorded
            ckey = (run.tenant_id, run.conversation_id)
            conversation = self._conversations.get(ckey)
            if conversation is None:
                raise NotFound(run.conversation_id)
            if conversation.revision != conversation_revision:
                raise ConcurrencyConflict(f"conversation {run.conversation_id} changed")
            linked = self._linked(run.tenant_id, run.conversation_id)
            if any(r.state not in TERMINAL_RUN_STATES for r in linked):
                raise ConcurrencyConflict(f"conversation {run.conversation_id} has an active run")
            admitted = await super().create_run_idempotent(
                run, events, state, actor_id, key, request_digest
            )
            if admitted == (run.run_id, request_digest):  # created here, not another's record
                self._conversations[ckey] = conversation.model_copy(
                    update={"revision": conversation.revision + 1, "updated_at": utc_now()}
                )
            return admitted


def _order(conversation: Conversation) -> tuple[Any, str]:
    return (conversation.created_at, conversation.conversation_id)


def _run_order(run: RunRecord) -> tuple[Any, str]:
    return (run.created_at, run.run_id)
