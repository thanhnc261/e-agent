"""What a case sees of a driver: the `Subject` and `DriverAdapter` protocols, and the
driver-neutral `ModelView` of one model request."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol

from e_agent.sdk.ports import AgentDriver


class NoModel(AssertionError):
    """A case asked for the model view of a driver that has no model. Never caught by a
    case: it fails the case, unless the adapter declared that case not applicable with
    `NotApplicable.NO_MODEL`, which the suite checks and which skips the whole case."""


class NoContinuation(AssertionError):
    """A case asked for the snapshot of a driver without ``snapshot`` and ``restore``."""


class NotApplicable(StrEnum):
    """The closed set of reasons a case may not apply to a driver. Each is a structural
    claim the suite checks against the adapter's subject (`runner.check_claim`) before it
    accepts the declaration, and a case accepts only the reasons it names (`Case.needs`)."""

    NO_MODEL = "NO_MODEL"
    """The subject's ``views()`` raises `NoModel`."""
    NO_CONTINUATION = "NO_CONTINUATION"
    """The driver has neither ``snapshot`` nor ``restore``, and ``snapshot()`` of the
    subject raises `NoContinuation`."""
    NO_TOKEN_SPEND = "NO_TOKEN_SPEND"
    """The driver has no model (``views()`` raises `NoModel`) and reports no token usage:
    no ``tokens_used``, or zero after a full run."""


REASON_TEXT: Mapping[NotApplicable, str] = {
    NotApplicable.NO_MODEL: "no model: it offers no tools and sends no model request",
    NotApplicable.NO_CONTINUATION: (
        "declares neither snapshot nor restore: the kernel starts it fresh at its next turn "
        "(continuation._restore_for_turn)"
    ),
    NotApplicable.NO_TOKEN_SPEND: "makes no model call, so it spends no model tokens",
}
"""The human text of each reason, printed with the declaration."""


@dataclass(frozen=True)
class ModelView:
    """One request a model received, in driver-neutral terms."""

    instructions: str
    offered: frozenset[str]
    """The contract ids of the business tools offered on this request."""
    protocol_tools: frozenset[str]
    """Every other tool offered (clarification, plan, generic grounded answer)."""
    schemas: Mapping[str, Mapping[str, Any]]
    """Each offered tool's parameter schema, by contract id or protocol tool name."""
    call_ids: tuple[str, ...]
    """The tool call ids in the request's history, in order."""
    return_ids: tuple[str, ...]
    """The tool return ids in the request's history, in order."""
    returns: Mapping[str, Any] = field(default_factory=dict)
    """Each tool return's content, by call id."""
    prompts: tuple[str, ...] = ()
    """Every user prompt part, in order; the last is the turn's request-only suffix when a
    pack has one."""
    sent: str = ""
    """Everything the request sent (instructions, tools and messages) as one JSON text."""


class Subject(Protocol):
    """One driver instance under test, with what the case may inspect."""

    driver: AgentDriver

    @property
    def connection_id(self) -> str:
        """The host connection every read and proposal must name."""
        ...

    def views(self) -> list[ModelView]:
        """Every model request so far, oldest first; `NoModel` for a driver without one."""
        ...

    def restart(self, *run_ids: str) -> None:
        """Replace ``driver`` with a new instance resumed as the kernel resumes it: each of
        ``run_ids`` from a JSON round trip of its snapshot when the driver has ``snapshot``
        and ``restore``, else fresh."""
        ...

    def snapshot(self, run_id: str) -> dict[str, Any] | None:
        """The driver's snapshot of ``run_id``; `NoContinuation` for a driver without one."""
        ...


class DriverAdapter(Protocol):
    """How a driver joins the suite."""

    name: str
    not_applicable: Mapping[str, NotApplicable]
    """Case id to the typed reason the case does not apply to this driver."""

    def subject(self, scenario: str) -> Subject:
        """A fresh subject for ``scenario``: its recorded model responses or its scripted
        mode. A scenario the adapter does not map raises `KeyError`, which fails the case."""
        ...
