"""Task definitions: what a run may do and when it is done (ADR 0028, target §6.4.1)."""

from __future__ import annotations

from datetime import timedelta
from typing import Self

from pydantic import Field, field_validator, model_validator

from .common import Record
from .context import Budgets


class RequiredEffect(Record):
    """A capability whose effect must be verified at least ``min_verified`` times."""

    contract_id: str
    min_verified: int = Field(default=1, ge=1)


class AcceptanceSpec(Record):
    """What the kernel checks at run end; model output cannot satisfy it (ENG-TRUST-1).

    Disjunctive (ADR 0028: "required verified effects, or a required verified answer"):
    with both fields set, the spec is met when every ``required_effects`` entry is
    verified, or when ``required_answer`` verified, such as a verified no-op (target
    §1.3: "a verified draft PO or a verified no-op"). With only one field set, only that
    one counts. With neither set, nothing is required.
    """

    required_effects: tuple[RequiredEffect, ...] = ()
    required_answer: str | None = None
    """An answer contract that must verify."""


class TaskDefinition(Record):
    """A versioned domain-pack resource. Policy checks (admitted bindings, budget narrowing,
    duplicate ``task_id``) belong to the registry; this record checks its own structure."""

    task_id: str
    version: str
    title: str
    goal_template: str
    capabilities: tuple[str, ...]
    """Contract ids: the run's fixed tool set."""
    acceptance: AcceptanceSpec
    budgets: Budgets | None = None
    """Narrows the profile budgets, never widens them; only fields set here count."""
    approval_ttl: timedelta | None = None
    """Replaces the global approval TTL for this definition's runs (D7)."""

    @field_validator("capabilities")
    @classmethod
    def _check_capabilities(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value:
            raise ValueError("a task definition needs at least one capability")
        seen: set[str] = set()
        for contract_id in value:
            if contract_id in seen:
                raise ValueError(f"duplicate capability {contract_id!r}")
            seen.add(contract_id)
        return value

    @field_validator("approval_ttl")
    @classmethod
    def _check_ttl(cls, value: timedelta | None) -> timedelta | None:
        if value is not None and value <= timedelta(0):
            raise ValueError("approval_ttl must be positive")
        return value

    @model_validator(mode="after")
    def _check_acceptance_inside_capabilities(self) -> Self:
        named = [effect.contract_id for effect in self.acceptance.required_effects]
        if self.acceptance.required_answer is not None:
            named.append(self.acceptance.required_answer)
        outside = sorted(set(named) - set(self.capabilities))
        if outside:
            raise ValueError(f"acceptance names {outside}, not among the definition's capabilities")
        return self
