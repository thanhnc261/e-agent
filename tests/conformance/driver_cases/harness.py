"""What a case sees of a driver: the `Subject` and `DriverAdapter` protocols, and the
driver-neutral `ModelView` of one model request."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

from e_agent.sdk.ports import AgentDriver


class NoModel(AssertionError):
    """A case asked for the model view of a driver that has no model. Raised, never
    swallowed: such a case must be declared not applicable for that driver."""


class NoContinuation(AssertionError):
    """A case asked for the snapshot of a driver without ``snapshot`` and ``restore``."""


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
    connection_id: str

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
    not_applicable: Mapping[str, str]
    """Case id to the reason the case does not apply to this driver."""

    def subject(self, scenario: str) -> Subject:
        """A fresh subject for ``scenario``: its recorded model responses or its scripted
        mode. A scenario the adapter does not map raises `KeyError`, which fails the case."""
        ...
