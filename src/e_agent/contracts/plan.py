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

from pydantic import model_validator

from .common import Record

LINEAGE_KEY = "$lineage"
"""The digest encoding of a placeholder (target §6.4.4); refused as a literal argument key."""

_JSON_POINTER = re.compile(r"(/([^~/]|~[01])*)*")
"""RFC 6901: zero or more `/`-prefixed segments; `~` only as `~0` or `~1`. Use fullmatch."""


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

    @model_validator(mode="after")
    def _check_path(self) -> Self:
        # An after model validator also runs when an existing (e.g. `model_construct`-built)
        # instance is validated; a field validator would not.
        _check_pointer(self.path)
        return self


def _check_pointer(path: object) -> None:
    """The one RFC 6901 check, applied to every `LineageRef` however it was built."""
    if not isinstance(path, str) or _JSON_POINTER.fullmatch(path) is None:
        raise ValueError(f"path must be an RFC 6901 JSON pointer: {path!r}")


def lineage_refs(value: Any) -> Iterator[LineageRef]:
    """Yield every placeholder in ``value``, checking its pointer; refuse a literal
    ``$lineage`` key anywhere. Arguments are typed `Any`, so pydantic never validates a
    nested `LineageRef`: this walk is where its pointer is checked."""
    if isinstance(value, LineageRef):
        _check_pointer(value.path)
        yield value
    elif isinstance(value, Mapping):
        if LINEAGE_KEY in value:
            raise ValueError(f"argument key {LINEAGE_KEY!r} is reserved for lineage placeholders")
        for item in value.values():
            yield from lineage_refs(item)
    elif isinstance(value, list | tuple | set | frozenset):
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
        _check_step_rules(self)
        return self


def _check_step_rules(step: PlannedStep) -> None:
    """Step-local structure: no self or repeated dependency, no literal `$lineage` key, and
    every placeholder names a dependency. `ActionPlan` re-applies it to every step, so a
    revalidated or `model_construct`-built plan cannot skip it."""
    if step.step_id in step.depends_on:
        raise ValueError(f"step {step.step_id!r} depends on itself")
    if len(set(step.depends_on)) != len(step.depends_on):
        raise ValueError(f"step {step.step_id!r} lists a dependency twice")
    for ref in lineage_refs(step.proposal.arguments):
        if ref.step_id not in step.depends_on:
            raise ValueError(
                f"step {step.step_id!r}: lineage step {ref.step_id!r} is not in depends_on"
            )


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
        for step in self.steps:
            # Pydantic does not revalidate nested instances, so re-apply the step rules here.
            _check_step_rules(step)
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
