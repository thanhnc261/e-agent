"""Conversation routes (ADR 0023 §10, Task 4d.4).

Each route has the session dependency (PR-27), and each handler only delegates to the
kernel facade: the routing, the ``off`` refusal and the request digest are the kernel's
(PR-03). Errors use the API's envelope ``{code, message, correlation_id}``. The owner is
the session's principal and the conversation id comes from the path, never from a body.
``create_app`` (``server/api.py``) adds the routes to the app itself, not through an
included router, so each is an ``APIRoute`` of ``app.routes`` that the route authorization
test walks (PR-27).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Literal

from e_agent.contracts.context import HostContext
from e_agent.contracts.conversation import (
    ConversationList,
    ConversationSnapshot,
    ReplyTo,
    RouteKind,
)
from e_agent.sdk.store import MAX_CONVERSATION_PAGE
from fastapi import Depends, FastAPI, Header, Query
from pydantic import BaseModel, ConfigDict, Field

from .api import ApiState, Session

DEFAULT_PAGE = 50


class PostMessage(BaseModel):
    """``text`` has ``CreateRun.task``'s bounds and ``host_context`` its type and validation
    (``server/api.py`` ``CreateRun``; 4d.1 B1-3)."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=4000)
    reply_to: ReplyTo | None = None
    host_context: HostContext | None = None  # untrusted hints, resolved or dropped (ADR 0011)


class CreatedConversation(BaseModel):
    conversation_id: str


class PostedMessage(BaseModel):
    """A refusal is never a 202: it is ``CONFLICT`` with the fixed hint (ADR 0023 §4)."""

    route: Literal[RouteKind.START, RouteKind.ANSWER]
    run_id: str


PREFIX = "/v1/conversations"


def add_conversation_routes(
    app: FastAPI, state: Callable[[], ApiState], session: Callable[..., Awaitable[Session]]
) -> None:
    """Add the routes to ``app``, bound to its state and its session dependency."""

    @app.post(PREFIX, status_code=201)
    async def create_conversation(s: Session = Depends(session)) -> CreatedConversation:
        conversation = await state().runtime.coordinator.create_conversation(s.principal)
        return CreatedConversation(conversation_id=conversation.conversation_id)

    @app.get(PREFIX)
    async def list_conversations(
        after: str | None = None,
        limit: int = Query(default=DEFAULT_PAGE, ge=1, le=MAX_CONVERSATION_PAGE),
        s: Session = Depends(session),
    ) -> ConversationList:
        return await state().runtime.coordinator.list_conversations(
            s.principal, after=after, limit=limit
        )

    @app.get(PREFIX + "/{conversation_id}")
    async def get_conversation(
        conversation_id: str, s: Session = Depends(session)
    ) -> ConversationSnapshot:
        return await state().runtime.coordinator.get_conversation(s.principal, conversation_id)

    @app.post(PREFIX + "/{conversation_id}/messages", status_code=202)
    async def post_message(
        conversation_id: str,
        body: PostMessage,
        s: Session = Depends(session),
        idempotency_key: str = Header(min_length=8, max_length=200),
    ) -> PostedMessage:
        rt = state().runtime
        route, run_id = await rt.coordinator.post_message(
            s.principal,
            conversation_id,
            body.text,
            reply_to=body.reply_to,
            host_context=body.host_context,
            idempotency_key=idempotency_key,
            resource_scope=rt.scope,
        )
        return PostedMessage(route=route.kind, run_id=run_id)
