"""Context policy and pack: what the model may see on a turn (ADR 0032 §1, ADR 0030).

The kernel assembles a ``ContextPack`` from the run's typed state; the driver renders it.
The pack holds rendered facts and ids, never model reasoning (PR-28). Its digest is the
plain ``jcs-sha256-v1`` digest (ADR 0006), which has no JSON numbers, so a rendered
observation carries none: the kernel renders numbers as strings.
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
    """Budgets and the class-per-route rule. In Phase 3 every run uses the defaults.

    The default budgets are starting values (ADR 0032 consequences): the ablation and the
    release report's context columns are the evidence for changing them."""

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
        if set(self.layer_budgets) != set(ContextLayer):
            raise ValueError("layer_budgets must cover every context layer")
        if any(v < 0 for v in self.layer_budgets.values()):
            raise ValueError("a layer budget must not be negative")
        for route in ContextRoute:
            rule = self.class_rules.get(route)
            if rule is None or set(rule) != set(DataClass):
                raise ValueError(f"class_rules must cover every data class for route {route}")
            if rule[DataClass.SECRET] is not ClassAction.ABSENT:
                raise ValueError("a secret value is never present on any route")
        return self


def _first_number(value: Any, pointer: str) -> str | None:
    """The RFC 6901 pointer of the first JSON number in ``value``, or None. A bool is a
    JSON boolean, not a number."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return pointer
    if isinstance(value, Mapping):
        for key, item in value.items():
            token = str(key).replace("~", "~0").replace("/", "~1")
            if (found := _first_number(item, f"{pointer}/{token}")) is not None:
                return found
    elif isinstance(value, list | tuple):
        for index, item in enumerate(value):
            if (found := _first_number(item, f"{pointer}/{index}")) is not None:
                return found
    return None


class RenderedObservation(Record):
    """An observation as the model may see it."""

    evidence: EvidenceRef
    data: Mapping[str, Any]
    partial: bool
    truncated: bool = False
    masked: bool = False

    @model_validator(mode="after")
    def _no_numbers(self) -> Self:
        if (where := _first_number(self.data, "")) is not None:
            raise ValueError(
                f"data must not hold a JSON number (found at {where or '/'}); "
                "render numbers as strings"
            )
        return self

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
    evidence id, an evidence id with an RFC 6901 pointer, an event id, or (ADR 0032 §5)
    ``finding:<index>#/expected``, ``finding:<index>#/observed`` or
    ``read_error:<request_id>``."""

    kind: DroppedKind
    ref: str = Field(min_length=1)
    reason: DroppedReason


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
        if self.digest != pack_digest(self):
            raise ValueError("digest does not match the pack content")
        return self

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
        body = {
            "stable_prefix": {ContextLayer(k).value: v for k, v in stable_prefix.items()},
            "dynamic_suffix": {ContextLayer(k).value: v for k, v in dynamic_suffix.items()},
            "observations": [o.model_dump(mode="json") for o in observations],
            "dropped": [d.model_dump(mode="json") for d in dropped],
        }
        return cls(
            stable_prefix=stable_prefix,
            dynamic_suffix=dynamic_suffix,
            observations=observations,
            dropped=dropped,
            digest=jcs_digest(body),
        )


def pack_digest(pack: ContextPack) -> str:
    """The ``jcs-sha256-v1`` digest of the pack without its digest field."""
    return jcs_digest(pack.model_dump(mode="json", exclude={"digest"}))
