"""Context policy and pack: what the model may see on a turn (ADR 0032 §1, ADR 0030).

The kernel assembles a ``ContextPack`` from the run's typed state; the driver renders it.
The pack holds rendered facts and ids, never model reasoning (PR-28). Numbers in a pack
digest travel as tagged strings, because the ``jcs-sha256-v1`` profile (ADR 0006) has no
JSON numbers.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from typing import Any, Self

from pydantic import Field, model_validator

from .common import Record
from .data_classes import DataClass
from .digest import digest as jcs_digest
from .evidence import Completeness, EvidenceRef


class ContextLayer(StrEnum):
    """The layers of a pack (target §7.2). The first four are the stable prefix."""

    INSTRUCTIONS = "instructions"
    TASK = "task"
    TOOLS = "tools"
    SKILLS = "skills"
    LEDGER = "ledger"
    FINDINGS = "findings"
    EVIDENCE = "evidence"
    KNOWLEDGE = "knowledge"
    RECENT_TURNS = "recent_turns"


STABLE_LAYERS = frozenset(
    {ContextLayer.INSTRUCTIONS, ContextLayer.TASK, ContextLayer.TOOLS, ContextLayer.SKILLS}
)
DYNAMIC_LAYERS = frozenset(ContextLayer) - STABLE_LAYERS


class ContextRoute(StrEnum):
    """The kinds of model route a class rule distinguishes (ADR 0032 §5)."""

    LOCAL = "local"
    HOSTED_DECLARED = "hosted_declared"
    """Hosted, with ``data_processing`` declared."""
    HOSTED_UNDECLARED = "hosted_undeclared"
    """Hosted without ``data_processing``, including ``hosted:unknown``."""


class ClassAction(StrEnum):
    KEEP = "keep"
    MASK = "mask"
    ABSENT = "absent"
    """Never present: the value is not sent in any form."""


def _row(personal: ClassAction, sensitive: ClassAction) -> dict[DataClass, ClassAction]:
    return {
        DataClass.PUBLIC: ClassAction.KEEP,
        DataClass.INTERNAL: ClassAction.KEEP,
        DataClass.PERSONAL: personal,
        DataClass.SENSITIVE_PERSONAL: sensitive,
        DataClass.SECRET: ClassAction.ABSENT,
    }


def _default_class_rules() -> dict[ContextRoute, dict[DataClass, ClassAction]]:
    keep, mask = ClassAction.KEEP, ClassAction.MASK
    return {
        ContextRoute.LOCAL: _row(keep, keep),
        ContextRoute.HOSTED_DECLARED: _row(keep, mask),
        ContextRoute.HOSTED_UNDECLARED: _row(mask, mask),
    }


def _default_layer_budgets() -> dict[ContextLayer, int]:
    return {
        ContextLayer.INSTRUCTIONS: 2000,
        ContextLayer.TASK: 2000,
        ContextLayer.TOOLS: 6000,
        ContextLayer.SKILLS: 0,
        ContextLayer.LEDGER: 2000,
        ContextLayer.FINDINGS: 3000,
        ContextLayer.EVIDENCE: 12000,
        ContextLayer.KNOWLEDGE: 0,
        ContextLayer.RECENT_TURNS: 4000,
    }


class ContextPolicy(Record):
    """Budgets and the class-per-route rule. In Phase 3 every run uses the defaults."""

    max_input_tokens: int = Field(default=32000, gt=0)
    layer_budgets: Mapping[ContextLayer, int] = Field(default_factory=_default_layer_budgets)
    tool_result_retention_turns: int = Field(default=3, ge=0)
    max_tool_output_tokens: int = Field(default=2000, gt=0)
    """The bound per observation (D3)."""
    class_rules: Mapping[ContextRoute, Mapping[DataClass, ClassAction]] = Field(
        default_factory=_default_class_rules
    )

    @model_validator(mode="after")
    def _complete(self) -> Self:
        if any(v < 0 for v in self.layer_budgets.values()):
            raise ValueError("a layer budget is not negative")
        for route in ContextRoute:
            rule = self.class_rules.get(route)
            if rule is None or set(rule) != set(DataClass):
                raise ValueError(f"class_rules must cover every data class for route {route}")
            if rule[DataClass.SECRET] is not ClassAction.ABSENT:
                raise ValueError("a secret value is never present on any route")
        return self


class RenderedObservation(Record):
    """An observation as the model may see it."""

    evidence: EvidenceRef
    data: Mapping[str, Any]
    partial: bool
    truncated: bool = False
    masked: bool = False

    @model_validator(mode="after")
    def _partial_says_why(self) -> Self:
        expected = (
            self.truncated or self.masked or self.evidence.completeness is not Completeness.COMPLETE
        )
        if self.partial is not expected:
            raise ValueError(
                "partial must be true exactly when the observation is truncated, masked "
                "or its evidence is not COMPLETE"
            )
        return self


class DroppedKind(StrEnum):
    OBSERVATION = "observation"
    ITEM = "item"
    VALUE = "value"
    TURN = "turn"


class DroppedReason(StrEnum):
    BUDGET = "budget"
    BOUND = "bound"
    CLEARED = "cleared"
    CLASS_ROUTE = "class_route"


class Dropped(Record):
    """Something left out of the pack. ``ref`` names it and never carries a value: an
    evidence id, an evidence id with an RFC 6901 pointer, or an event id."""

    kind: DroppedKind
    ref: str = Field(min_length=1)
    reason: DroppedReason


def _digestible(value: Any) -> Any:
    """JSON-mode data with numbers as tagged strings (the profile has no numbers)."""
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return value
    if isinstance(value, int | float):
        return {"$number": repr(value)}
    if isinstance(value, Mapping):
        return {k: _digestible(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_digestible(v) for v in value]
    return value


def _check_layers(stable: Mapping[Any, str], dynamic: Mapping[Any, str]) -> None:
    if not set(stable) <= STABLE_LAYERS:
        raise ValueError("stable_prefix holds only instructions, task, tools and skills")
    if not set(dynamic) <= DYNAMIC_LAYERS:
        raise ValueError(
            "dynamic_suffix holds only ledger, findings, evidence, knowledge and recent_turns"
        )


class ContextPack(Record):
    """What one driver turn may see. Built by the kernel, rendered by the driver."""

    stable_prefix: Mapping[ContextLayer, str]
    dynamic_suffix: Mapping[ContextLayer, str]
    observations: tuple[RenderedObservation, ...] = ()
    dropped: tuple[Dropped, ...] = ()
    digest: str

    @model_validator(mode="after")
    def _layers_and_digest(self) -> Self:
        if not set(self.stable_prefix) <= STABLE_LAYERS:
            raise ValueError("stable_prefix holds only instructions, task, tools and skills")
        if not set(self.dynamic_suffix) <= DYNAMIC_LAYERS:
            raise ValueError(
                "dynamic_suffix holds only ledger, findings, evidence, knowledge and recent_turns"
            )
        if self.digest != self.compute_digest():
            raise ValueError("digest does not match the pack content")
        return self

    def compute_digest(self) -> str:
        """The ``jcs-sha256-v1`` digest of the pack without its digest."""
        body = self.model_dump(mode="json", exclude={"digest"})
        return jcs_digest(_digestible(body))

    @classmethod
    def build(
        cls,
        *,
        stable_prefix: Mapping[ContextLayer, str],
        dynamic_suffix: Mapping[ContextLayer, str],
        observations: tuple[RenderedObservation, ...] = (),
        dropped: tuple[Dropped, ...] = (),
    ) -> Self:
        """A pack with its digest computed."""
        _check_layers(stable_prefix, dynamic_suffix)
        draft = cls.model_construct(
            stable_prefix=stable_prefix,
            dynamic_suffix=dynamic_suffix,
            observations=observations,
            dropped=dropped,
            digest="",
        )
        return cls(
            stable_prefix=stable_prefix,
            dynamic_suffix=dynamic_suffix,
            observations=observations,
            dropped=dropped,
            digest=draft.compute_digest(),
        )
