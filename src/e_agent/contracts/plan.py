"""Model proposals and action plans. A proposal is never an approval or an executed action.

An action plan (ADR 0025, target §6.4.3) is a proposal too. These records check structure
only: unique step ids, known and earlier dependencies (so step-index order is topological),
and lineage placeholders that name a dependency. Policy (capabilities inside the task
definition, the write budget, domain validation) is the kernel's.
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping
from graphlib import CycleError, TopologicalSorter
from typing import Any, Self

from pydantic import field_validator, model_validator

from .common import Record

LINEAGE_KEY = "$lineage"
"""The digest encoding of a placeholder (target §6.4.4); refused as a literal argument key."""

_JSON_POINTER = re.compile(r"^(/([^~/]|~[01])*)*$")


class ActionProposal(Record):
    """One proposed capability invocation, payload validated by the capability schema."""

    contract_id: str
    connection_id: str
    arguments: dict[str, Any]
    expected_effects: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()


class LineageRef(Record):
    """A placeholder for a value copied from an earlier step's verified outcome.

    It has one rule (copy from the verified outcome, never a receipt or model output); a
    new rule kind needs an ADR (ADR 0025).
    """

    step_id: str
    """An earlier plan step this step depends on."""
    path: str
    """RFC 6901 JSON pointer into that step's verified outcome."""

    @field_validator("path")
    @classmethod
    def _check_pointer(cls, value: str) -> str:
        if not _JSON_POINTER.match(value):
            raise ValueError(f"path must be an RFC 6901 JSON pointer: {value!r}")
        return value


def lineage_refs(value: Any) -> Iterator[LineageRef]:
    """Yield every placeholder in ``value``; refuse a literal ``$lineage`` key anywhere."""
    if isinstance(value, LineageRef):
        yield value
    elif isinstance(value, Mapping):
        if LINEAGE_KEY in value:
            raise ValueError(f"argument key {LINEAGE_KEY!r} is reserved for lineage placeholders")
        for item in value.values():
            yield from lineage_refs(item)
    elif isinstance(value, list | tuple):
        for item in value:
            yield from lineage_refs(item)


class PlannedStep(Record):
    """One proposed capability invocation inside a plan; yields exactly one action."""

    step_id: str
    proposal: ActionProposal
    """Its arguments may hold `LineageRef` placeholders."""
    depends_on: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _check_dependencies(self) -> Self:
        if self.step_id in self.depends_on:
            raise ValueError(f"step {self.step_id!r} depends on itself")
        if len(set(self.depends_on)) != len(self.depends_on):
            raise ValueError(f"step {self.step_id!r} lists a dependency twice")
        for ref in lineage_refs(self.proposal.arguments):
            if ref.step_id not in self.depends_on:
                raise ValueError(
                    f"step {self.step_id!r}: lineage step {ref.step_id!r} is not in depends_on"
                )
        return self


class ActionPlan(Record):
    plan_id: str
    task_id: str
    task_version: str
    steps: tuple[PlannedStep, ...]
    """Step index = position; dispatch runs in this order."""

    @model_validator(mode="after")
    def _check_structure(self) -> Self:
        if not self.steps:
            raise ValueError("a plan needs at least one step")
        index: dict[str, int] = {}
        for position, step in enumerate(self.steps):
            if step.step_id in index:
                raise ValueError(f"duplicate step id {step.step_id!r}")
            index[step.step_id] = position
        for step in self.steps:
            for dependency in step.depends_on:
                if dependency not in index:
                    raise ValueError(
                        f"step {step.step_id!r} depends on unknown step {dependency!r}"
                    )
        self._check_acyclic()
        for position, step in enumerate(self.steps):
            for dependency in step.depends_on:
                if index[dependency] > position:
                    raise ValueError(
                        f"step {step.step_id!r} depends on later step {dependency!r}; "
                        "step order must be a topological order"
                    )
        return self

    def _check_acyclic(self) -> None:
        graph = {step.step_id: step.depends_on for step in self.steps}
        try:
            TopologicalSorter(graph).prepare()
        except CycleError as exc:
            cycle = exc.args[1]
            raise ValueError(f"dependency cycle: {' -> '.join(cycle)}") from None
