"""Task definitions: what a run may do and when it is done (ADR 0028, target §6.4.1)."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import timedelta
from typing import Any, Self

from pydantic import (
    Field,
    SerializerFunctionWrapHandler,
    field_validator,
    model_serializer,
    model_validator,
)

from .common import Record
from .context import Budgets
from .outcome import OutcomeReport, OutcomeStatus

GROUNDED_ANSWER = "grounded.answer.v1"
"""The core generic grounded answer (ADR 0033 §3): owned by the kernel, never a registry
capability. Its arguments are ``{summary}``, with at least one citation in the kernel
envelope; a run it ends is ``GROUNDED``, never verified (PR-19)."""


class RequiredEffect(Record):
    """A capability whose effect must be verified at least ``min_verified`` times."""

    contract_id: str
    min_verified: int = Field(default=1, ge=1)


class AnswerCondition(Record):
    """A value the required answer's verifier must have computed (ADR 0028 amendment).

    It names one of the verifier's `OutcomeCheck` entries by ``check``, and ``expected`` is
    compared with that check's own ``expected``: the value the verifier computed from fresh
    reads, never the model's arguments or the check's ``observed``."""

    check: str
    expected: str
    """Compared as an exact string; a decimal is in its canonical form (`format_decimal`)."""


class AcceptanceSpec(Record):
    """What the kernel checks at run end; model output cannot satisfy it (ENG-TRUST-1).

    Disjunctive (ADR 0028: "required verified effects, or a required verified answer"):
    with both fields set, the spec is met when every ``required_effects`` entry is
    verified, or when the answer alternative is met (`answer_condition_met`), such as a
    verified no-op (target §1.3: "a verified draft PO or a verified no-op"). With only one
    field set, only that one counts. With neither set, nothing is required.

    The answer alternative is the ``required_answer`` outcome VERIFIED and, when
    ``answer_condition`` is set, the verifier's check of that name computing that value:
    draft-po's no-op is a verified shortage answer whose verifier computed a shortage of
    ``"0"``, so an accurate answer reporting a positive shortage does not meet it (ADR 0028
    amendment, proposed; Codex review C-2). A condition needs a ``required_answer``.
    """

    required_effects: tuple[RequiredEffect, ...] = ()
    required_answer: str | None = None
    """An answer contract that must verify."""
    answer_condition: AnswerCondition | None = None
    """Narrows the answer alternative to a verified answer whose verifier computed this."""
    grounded_answer: bool = False
    """Admits `GROUNDED_ANSWER` for the definition's runs, and makes the run's ``GROUNDED``
    end, and only that, meet the spec (ADR 0033 §3, refining ADR 0028). Valid only when
    ``required_effects`` and ``required_answer`` are both empty, so a definition naming a
    typed answer or an effect is never met by a grounded one."""

    @model_validator(mode="after")
    def _check_condition(self) -> Self:
        check_answer_condition(self)
        return self

    @model_serializer(mode="wrap")
    def _omit_false_grounded(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        """Leave ``grounded_answer`` out when false, so every definition without it, its
        snapshot in a continuation and the context pack's task layer, serializes exactly as
        before ADR 0033 (review R1-5)."""
        data: dict[str, Any] = handler(self)
        if not self.grounded_answer:
            data.pop("grounded_answer", None)
        return data


def check_answer_condition(spec: AcceptanceSpec) -> None:
    """The record's rules, also re-applied at registry admission to a built record: an
    answer condition needs a ``required_answer``, and ``grounded_answer`` needs neither a
    required effect nor a required answer."""
    if spec.answer_condition is not None and spec.required_answer is None:
        raise ValueError("answer_condition needs a required_answer")
    if spec.grounded_answer and (spec.required_effects or spec.required_answer is not None):
        raise ValueError("grounded_answer needs no required_effects and no required_answer")


def answer_condition_met(spec: AcceptanceSpec, outcome: OutcomeReport) -> bool:
    """Whether ``outcome`` meets the spec's answer alternative.

    The caller passes the verifier's report for the spec's ``required_answer`` action (a
    report names no contract). False without a ``required_answer`` or unless the report is
    VERIFIED. With an ``answer_condition``, at least one check of its name must exist, and
    every check of that name must have passed with the verifier's own ``expected`` equal to
    the condition's: ``observed``, the model's claim, is never read. Pure; 2c.6's run-end
    acceptance check calls it."""
    if spec.required_answer is None or outcome.status is not OutcomeStatus.VERIFIED:
        return False
    condition = spec.answer_condition
    if condition is None:
        return True
    named = [check for check in outcome.checks if check.name == condition.check]
    return bool(named) and all(c.passed and c.expected == condition.expected for c in named)


def acceptance_met(
    spec: AcceptanceSpec,
    verified: Mapping[str, int],
    answers: Iterable[OutcomeReport],
    *,
    grounded: bool = False,
) -> bool:
    """Whether a run met ``spec`` at its end (ADR 0028, target §6.4.1).

    ``verified`` counts the run's VERIFIED actions by contract id, and ``answers`` are the
    verifier reports of its VERIFIED ``required_answer`` actions; the kernel reads both from
    its own records, so model output cannot meet the spec (ENG-TRUST-1). Disjunctive, as the
    spec states: every required effect verified at least ``min_verified`` times, or the
    answer alternative met (`answer_condition_met`). With neither field set nothing is
    required. ``grounded`` is whether the run ended ``GROUNDED``, read from the kernel's own
    ``message.final`` (ADR 0033 §3): a spec with ``grounded_answer`` is met by that end alone,
    and a grounded end meets no other spec. Pure."""
    if spec.grounded_answer or grounded:
        return spec.grounded_answer and grounded
    if not spec.required_effects and spec.required_answer is None:
        return True
    effects = bool(spec.required_effects) and all(
        verified.get(effect.contract_id, 0) >= effect.min_verified
        for effect in spec.required_effects
    )
    return effects or any(answer_condition_met(spec, report) for report in answers)


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
