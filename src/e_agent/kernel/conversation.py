"""Conversation message routing (ADR 0023 §4, D2).

`route_message` is pure: it looks only at the conversation's latest run and the
``reply_to`` the user sent, never at the text, a clock or a store. The decision is a value,
separate from the act, so a shadow comparison can read it without acting (Task 4d.3).

`ConversationFlow` is the act, which the coordinator delegates to. Its check order is fixed:
(0) the message's idempotency record, (1) the caller owns the conversation, (2) ``reply_to``
names a run of this conversation, (3) the answer replay check; only then the route. An
answer is bound to the question the user saw (``reply_to.run_revision``), never to the
conversation revision. No route reaches the approval flow: message text is never a decision
(PR-13, PR-15).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime

from e_agent.contracts.common import new_id
from e_agent.contracts.context import HostContext, Principal
from e_agent.contracts.conversation import Conversation, MessageRoute, ReplyTo, RouteKind
from e_agent.contracts.run import TERMINAL_RUN_STATES, RunRecord, RunState
from e_agent.sdk.store import ConversationStore, NotFound

from .errors import ErrorCode, KernelError

QUESTION_CHANGED = "the question changed; read it again"
WAIT_FOR_RUN = "wait, decide the approval, or stop the run"
NOT_FOUND_MESSAGE = "conversation not found"
"""One message for an absent, foreign or other-tenant conversation and for a ``reply_to`` run
outside it, so a refusal never tells which (PR-24)."""
KEY_REUSED = "idempotency key reused with another request"

Admit = Callable[..., Awaitable[tuple[str, bool]]]
Accept = Callable[..., Awaitable[RunRecord]]
Replayed = Callable[[Principal, str, str, int, str], Awaitable[bool]]


def route_message(latest: RunRecord | None, reply_to: ReplyTo | None) -> MessageRoute:
    """The route for a message to a conversation whose latest run is ``latest`` (D2)."""
    if latest is None or latest.state in TERMINAL_RUN_STATES:
        return MessageRoute(kind=RouteKind.START)
    if latest.state is RunState.WAITING_INPUT:
        if (
            reply_to is not None
            and reply_to.run_id == latest.run_id
            and reply_to.run_revision == latest.revision
        ):
            return MessageRoute(
                kind=RouteKind.ANSWER, run_id=latest.run_id, run_revision=latest.revision
            )
        return MessageRoute(kind=RouteKind.REFUSE, run_id=latest.run_id, hint=QUESTION_CHANGED)
    # CREATED, RUNNING, VERIFYING, WAITING_APPROVAL, NEEDS_RECONCILIATION: no queue, no cancel.
    return MessageRoute(kind=RouteKind.REFUSE, run_id=latest.run_id, hint=WAIT_FOR_RUN)


def latest_run(runs: tuple[RunRecord, ...]) -> RunRecord | None:
    """The latest run of ``runs`` (oldest first): the active one when there is one, which is
    always the newest (only ``create_run_in_conversation`` links a run, never beside an
    active one), else the last listed. It does not depend on two runs' ``created_at``
    differing (ruling R2). Every caller that routes, the shadow comparison included, uses
    this, so ``on`` and ``shadow`` see the same latest run."""
    active = [r for r in runs if r.state not in TERMINAL_RUN_STATES]
    return active[-1] if active else (runs[-1] if runs else None)


class ConversationFlow:
    """One message's checks and act. ``admit`` is the coordinator's conversation variant of
    ``admit_run`` (private: only this flow calls it, after its ownership check); ``accept``
    and ``replayed`` are its ``accept_input`` and ``input_replayed``. Admission only creates
    the run and its start work in one store transaction; the worker starts it, so no driver
    call happens here (PR-17)."""

    def __init__(
        self,
        store: ConversationStore,
        clock: Callable[[], datetime],
        *,
        admit: Admit,
        accept: Accept,
        replayed: Replayed,
    ) -> None:
        self._store = store
        self._clock = clock
        self._admit = admit
        self._accept = accept
        self._replayed = replayed

    async def create_conversation(self, principal: Principal) -> Conversation:
        now = self._clock()
        conversation = Conversation(
            tenant_id=principal.tenant_id,
            conversation_id=new_id("conv"),
            owner_id=principal.principal_id,  # from the principal, never from a body
            revision=1,
            created_at=now,
            updated_at=now,
        )
        await self._store.create_conversation(conversation)
        return conversation

    async def post_message(
        self,
        principal: Principal,
        conversation_id: str,
        text: str,
        *,
        reply_to: ReplyTo | None,
        host_context: HostContext | None,
        idempotency_key: str,
        request_digest: str,
        resource_scope: frozenset[str],
    ) -> tuple[MessageRoute, str]:
        tenant, owner = principal.tenant_id, principal.principal_id
        # (0) A recorded key replays its start whatever state that run is in now (PR-17).
        replayed = await self._replayed_start(principal, idempotency_key, request_digest)
        if replayed is not None:
            return replayed
        # (1) The caller owns the conversation; (2) reply_to names one of its runs.
        try:
            conversation = await self._store.get_conversation(tenant, owner, conversation_id)
            runs = await self._store.list_conversation_runs(tenant, owner, conversation_id)
        except NotFound:
            raise KernelError(ErrorCode.NOT_FOUND, NOT_FOUND_MESSAGE) from None
        if reply_to is not None:
            if reply_to.run_id not in {r.run_id for r in runs}:
                raise KernelError(ErrorCode.NOT_FOUND, NOT_FOUND_MESSAGE)
            # (3) A retried answer returns the first result, even after the run moved on.
            if await self._replayed(
                principal, tenant, reply_to.run_id, reply_to.run_revision, text
            ):
                return self._answered(reply_to)
        route = route_message(latest_run(runs), reply_to)
        if route.kind is RouteKind.REFUSE:
            # The active run may be this key's own start, committed after step (0) missed
            # (review A1-1): read the record again, so a retried start still replays.
            replayed = await self._replayed_start(principal, idempotency_key, request_digest)
            if replayed is not None:
                return replayed
            raise KernelError(ErrorCode.CONFLICT, route.hint or WAIT_FOR_RUN)
        if route.kind is RouteKind.ANSWER:
            if reply_to is None:  # route_message answers only a reply_to
                raise KernelError(ErrorCode.CONFLICT, QUESTION_CHANGED)
            await self._accept(
                principal, reply_to.run_id, text, reply_to.run_revision, enqueue=True
            )
            return self._answered(reply_to)
        claimed, _ = await self._admit(
            principal,
            text,
            resource_scope,
            run_id=new_id("run"),
            conversation_id=conversation_id,
            conversation_revision=conversation.revision,
            idempotency_key=idempotency_key,
            request_digest=request_digest,
            host_context=host_context,
        )
        return MessageRoute(kind=RouteKind.START, run_id=claimed), claimed

    async def _replayed_start(
        self, principal: Principal, idempotency_key: str, request_digest: str
    ) -> tuple[MessageRoute, str] | None:
        """Step (0): a recorded key with this digest replays its start whatever state that run
        is in now; another digest is ``CONFLICT`` (PR-17). ``None`` when nothing is recorded."""
        recorded = await self._store.lookup_idempotent(
            principal.tenant_id, principal.principal_id, idempotency_key
        )
        if recorded is None:
            return None
        if recorded[1] != request_digest:
            raise KernelError(ErrorCode.CONFLICT, KEY_REUSED)
        return MessageRoute(kind=RouteKind.START, run_id=recorded[0]), recorded[0]

    @staticmethod
    def _answered(reply_to: ReplyTo) -> tuple[MessageRoute, str]:
        route = MessageRoute(
            kind=RouteKind.ANSWER, run_id=reply_to.run_id, run_revision=reply_to.run_revision
        )
        return route, reply_to.run_id
