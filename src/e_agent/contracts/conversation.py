"""Conversations: a thread of runs with carried context (ADR 0023 §2, §6).

A ``Conversation`` holds ids, an owner, a revision and timestamps, never text: the user's
words stay in ``runs.task`` and ``input.received``. Carried records hold references and
checked typed values only, never model text (PR-13, PR-26).
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from typing import Any, Self

from pydantic import model_validator

from .common import Record, UtcDatetime
from .run import ReasonCode, RunState


class Conversation(Record):
    tenant_id: str
    conversation_id: str
    owner_id: str
    revision: int
    created_at: UtcDatetime
    updated_at: UtcDatetime


class CarriedRef(Record):
    """A record ref an earlier run read. ``source_ref`` holds ``EvidenceRef.locator``."""

    contract_id: str
    source_ref: str
    revision: str | None
    observed_at: UtcDatetime


class CarriedAnswer(Record):
    """The class-walked arguments of one ``VERIFIED`` answer action: only paths that carry a
    declared value format and pass it (ADR 0023 §6, §7)."""

    contract_id: str
    arguments: Mapping[str, Any]


class CarriedRun(Record):
    run_id: str
    task_id: str | None = None
    task_version: str | None = None
    state: RunState
    reason_code: ReasonCode | None = None
    user_messages: tuple[str, ...] = ()
    answers: tuple[CarriedAnswer, ...] = ()
    refs: tuple[CarriedRef, ...] = ()


class ReplyTo(Record):
    """The waiting run and the revision the user saw with its question (D2)."""

    run_id: str
    run_revision: int


class RouteKind(StrEnum):
    ANSWER = "answer"
    START = "start"
    REFUSE = "refuse"


class MessageRoute(Record):
    kind: RouteKind
    run_id: str | None = None
    run_revision: int | None = None
    hint: str | None = None

    @model_validator(mode="after")
    def _check_kind(self) -> Self:
        if self.kind is RouteKind.ANSWER and (self.run_id is None or self.run_revision is None):
            raise ValueError("an answer route names the run and the revision")
        if self.kind is RouteKind.REFUSE and not self.hint:
            raise ValueError("a refuse route carries its hint")
        return self


class ConversationPage(Record):
    items: tuple[Conversation, ...]
    next_after: str | None = None


class ConversationSummary(Record):
    conversation_id: str
    title: str
    updated_at: UtcDatetime
    latest_state: RunState | None = None
    reply_pending: bool = False


class ConversationList(Record):
    items: tuple[ConversationSummary, ...]
    next_after: str | None = None


class ThreadRun(Record):
    run_id: str
    task: str
    state: RunState
    reason_code: ReasonCode | None = None
    revision: int
    created_at: UtcDatetime


class ConversationSnapshot(Record):
    conversation: Conversation
    runs: tuple[ThreadRun, ...]
