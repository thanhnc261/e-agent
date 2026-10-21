"""Conversation message routing (ADR 0023 §4, §9, D2).

`route_message` is pure: it looks only at the conversation's latest run and the
``reply_to`` the user sent, never at the text, a clock or a store. The decision is a value,
separate from the act, so a shadow comparison can read it without acting (Task 4d.3).

`ConversationFlow` is the act, which the coordinator delegates to. Its check order is fixed:
(0) the message's idempotency record, (1) the caller owns the conversation, (2) ``reply_to``
names a run of this conversation, (3) the answer replay check; only then the route. An
answer is bound to the question the user saw (``reply_to.run_revision``), never to the
conversation revision. No route reaches the approval flow: message text is never a decision
(PR-13, PR-15).

In ``shadow`` (the profile's toggle: no run exists yet when a message is routed) the flow
refuses nothing today's path accepts (ADR 0023 §9, ADR 0027). A message the router would
refuse without a ``reply_to`` starts an unlinked run, as ``POST /v1/runs`` would, recording
``conversation.compared`` with ``route: refuse``; a stale ``reply_to`` is still ``CONFLICT``,
as ``/inputs`` gives today. A linked start or answer that fails in the conversation step
falls back, in the same request and under the message's own idempotency record, to today's
unlinked run or plain input, recording ``conversation.shadow_failed``. Every other mode
routes as ``on`` (``off`` is Task 4d.4's).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType

from e_agent.contracts.common import new_id
from e_agent.contracts.context import HostContext, Principal
from e_agent.contracts.conversation import Conversation, MessageRoute, ReplyTo, RouteKind
from e_agent.contracts.events import RunEventType
from e_agent.contracts.features import FeatureMode
from e_agent.contracts.run import TERMINAL_RUN_STATES, RunRecord, RunState
from e_agent.sdk.store import ConcurrencyConflict, ConversationStore, EventSpec, NotFound

from .carried import compared_payload
from .errors import ErrorCode, KernelError

QUESTION_CHANGED = "the question changed; read it again"
WAIT_FOR_RUN = "wait, decide the approval, or stop the run"
NOT_FOUND_MESSAGE = "conversation not found"
"""One message for an absent, foreign or other-tenant conversation and for a ``reply_to`` run
outside it, so a refusal never tells which (PR-24)."""
KEY_REUSED = "idempotency key reused with another request"

SHADOW_FAILED_MESSAGES = MappingProxyType(
    {
        "start": "The conversation step of the start failed; the run started unlinked.",
        "answer": "The conversation step of the answer failed; it was taken as plain input.",
        "reply_to": "The reply names an unlinked run; it was taken as plain input.",
        "carry": "The carried conversation context could not be compared.",
    }
)
"""The kernel's fixed message per ``conversation.shadow_failed`` stage (ADR 0023 §11)."""

Admit = Callable[..., Awaitable[tuple[str, bool]]]
Accept = Callable[..., Awaitable[RunRecord]]
Replayed = Callable[[Principal, str, str, int, str], Awaitable[bool]]
RunOf = Callable[[str, str], Awaitable[RunRecord]]


class ConversationStepFailed(KernelError):
    """A linked start the store refused in the conversation step: the revision or active-run
    check (``CONFLICT``) or a missing conversation (``NOT_FOUND``). ``on`` raises it as
    today's `KernelError`; ``shadow`` falls back on it. A reused key is never this."""


def failure_code(error: BaseException) -> ErrorCode:
    """The kernel error code of a conversation-step failure; a store error with no kernel
    meaning is ``DEPENDENCY_UNAVAILABLE``."""
    if isinstance(error, KernelError):
        return error.code
    if isinstance(error, ConcurrencyConflict):
        return ErrorCode.CONFLICT
    if isinstance(error, NotFound):
        return ErrorCode.NOT_FOUND
    return ErrorCode.DEPENDENCY_UNAVAILABLE


def shadow_failed_event(stage: str, code: ErrorCode) -> EventSpec:
    """``conversation.shadow_failed {stage, code}`` with the stage's fixed message: never an
    exception's text (PR-25, PR-28)."""
    payload = {"stage": stage, "code": code.value, "message": SHADOW_FAILED_MESSAGES[stage]}
    return (RunEventType.CONVERSATION_SHADOW_FAILED, payload, None)


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


@dataclass(frozen=True)
class _Message:
    """One posted message, as the start paths need it."""

    principal: Principal
    conversation_id: str
    text: str
    host_context: HostContext | None
    idempotency_key: str
    request_digest: str
    resource_scope: frozenset[str]


class ConversationFlow:
    """One message's checks and act. ``admit`` is the coordinator's conversation variant of
    ``admit_run`` (private: only this flow calls it, after its ownership check), and
    ``admit_unlinked`` its ``admit_run``, today's ``POST /v1/runs`` path, with the events a
    shadow fallback records; ``accept`` and ``replayed`` are its ``accept_input`` (which
    records a shadow fallback's events in the input's own write) and ``input_replayed``.
    Admission only creates the run and its start work in one store
    transaction; the worker starts it, so no driver call happens here (PR-17)."""

    def __init__(
        self,
        store: ConversationStore,
        clock: Callable[[], datetime],
        *,
        mode: FeatureMode,
        admit: Admit,
        admit_unlinked: Admit,
        accept: Accept,
        replayed: Replayed,
        run_of: RunOf,
    ) -> None:
        self._store = store
        self._clock = clock
        self._shadow = mode is FeatureMode.SHADOW
        self._admit = admit
        self._admit_unlinked = admit_unlinked
        self._accept = accept
        self._replayed = replayed
        self._run_of = run_of

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
        message = _Message(
            principal,
            conversation_id,
            text,
            host_context,
            idempotency_key,
            request_digest,
            resource_scope,
        )
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
        except Exception as error:  # a store error on the conversation row
            if not self._shadow:
                raise
            code = failure_code(error)
            if reply_to is not None:
                return await self._plain_input(principal, reply_to, text, "answer", code)
            return await self._unlinked(message, shadow_failed_event("start", code))
        if reply_to is not None:
            if reply_to.run_id not in {r.run_id for r in runs}:
                if self._shadow and await self._own_unlinked(principal, reply_to.run_id):
                    stage, code = "reply_to", ErrorCode.NOT_FOUND
                    return await self._plain_input(principal, reply_to, text, stage, code)
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
            if not self._shadow or reply_to is not None:  # a stale reply_to, as /inputs
                raise KernelError(ErrorCode.CONFLICT, route.hint or WAIT_FOR_RUN)
            refused = compared_payload(conversation_id, RouteKind.REFUSE)
            return await self._unlinked(
                message, (RunEventType.CONVERSATION_COMPARED, refused, None)
            )
        if route.kind is RouteKind.ANSWER:
            if reply_to is None:  # route_message answers only a reply_to
                raise KernelError(ErrorCode.CONFLICT, QUESTION_CHANGED)
            await self._accept(
                principal, reply_to.run_id, text, reply_to.run_revision, enqueue=True
            )
            return self._answered(reply_to)
        return await self._start(message, conversation.revision)

    async def _start(self, message: _Message, revision: int) -> tuple[MessageRoute, str]:
        """A linked start; in ``shadow``, today's unlinked run when the conversation step
        fails. Any other error (a reused key, task admission) is today's error in every
        mode: the unlinked path would refuse it the same way."""
        try:
            claimed, _ = await self._admit(
                message.principal,
                message.text,
                message.resource_scope,
                run_id=new_id("run"),
                conversation_id=message.conversation_id,
                conversation_revision=revision,
                idempotency_key=message.idempotency_key,
                request_digest=message.request_digest,
                host_context=message.host_context,
            )
        except ConversationStepFailed as failed:
            if not self._shadow:
                raise
            code = failed.code
        except KernelError:
            raise
        except Exception as error:  # a store error on the conversation row
            if not self._shadow:
                raise
            code = failure_code(error)
        else:
            return MessageRoute(kind=RouteKind.START, run_id=claimed), claimed
        return await self._unlinked(message, shadow_failed_event("start", code))

    async def _unlinked(self, message: _Message, event: EventSpec) -> tuple[MessageRoute, str]:
        """Today's unlinked run (``POST /v1/runs``), under the message's own key and digest,
        so a retry replays it at step (0); ``event`` is recorded in its admission."""
        claimed, _ = await self._admit_unlinked(
            message.principal,
            message.text,
            message.resource_scope,
            run_id=new_id("run"),
            idempotency_key=message.idempotency_key,
            request_digest=message.request_digest,
            host_context=message.host_context,
            recorded=(event,),
        )
        return MessageRoute(kind=RouteKind.START, run_id=claimed), claimed

    async def _own_unlinked(self, principal: Principal, run_id: str) -> bool:
        """Whether ``run_id`` is the caller's own run outside any conversation (made by a
        shadow fallback). Anything else, absent included, stays ``NOT_FOUND``."""
        try:
            run = await self._run_of(principal.tenant_id, run_id)
        except NotFound:
            return False
        return run.conversation_id is None and run.requester_id == principal.principal_id

    async def _plain_input(
        self, principal: Principal, reply_to: ReplyTo, text: str, stage: str, code: ErrorCode
    ) -> tuple[MessageRoute, str]:
        """The answer as ``/v1/runs/{id}/inputs`` takes it: the replay check, then a plain
        ``accept_input`` that records ``conversation.shadow_failed`` in the same write as the
        input and its work (PR-17)."""
        run_id, revision = reply_to.run_id, reply_to.run_revision
        if not await self._replayed(principal, principal.tenant_id, run_id, revision, text):
            events: Sequence[EventSpec] = (shadow_failed_event(stage, code),)
            await self._accept(principal, run_id, text, revision, enqueue=True, events=events)
        return self._answered(reply_to)

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
