"""Capability contracts and implementation bindings (HLD §5, ADR 0002)."""

from __future__ import annotations

import re
from collections.abc import Mapping
from enum import StrEnum
from typing import Any, Self

from pydantic import Field, field_validator, model_validator

from .common import Record
from .data_classes import DataClass, check_class_key

_CONTRACT_ID = re.compile(r"^[a-z][a-z0-9-]*(\.[a-z][a-z0-9-]*)+\.v[0-9]+$")


class EffectKind(StrEnum):
    READ = "read"
    WRITE = "write"
    ANSWER = "answer"
    """A structured answer: no provider effect, no approval; independently verified."""


class Risk(StrEnum):
    """How severe a capability's effect is (ADR 0029, target §6.4.2)."""

    READ = "read"
    WRITE_LOW = "write_low"
    WRITE_HIGH = "write_high"
    DESTRUCTIVE = "destructive"


class Reversibility(StrEnum):
    """Whether a capability's effect can be undone (ADR 0029)."""

    IRREVERSIBLE = "irreversible"
    COMPENSABLE = "compensable"
    """Undone by the contract named in ``compensating_contract_id``."""


class Idempotency(StrEnum):
    """Whether a binding's provider deduplicates a repeated call (ADR 0029)."""

    NONE = "none"
    PROVIDER_KEY = "provider_key"
    """The provider deduplicates on a key derived from ``logical_operation_id``."""


def _default_risk(data: dict[str, Any]) -> Risk:
    # ADR 0029: `read` for read and answer contracts, `write_high` for writes. A default
    # factory keeps the field out of `model_fields_set`, so a defaulted risk stays visible.
    effect = data.get("effect")
    return Risk.READ if effect in (EffectKind.READ, EffectKind.ANSWER) else Risk.WRITE_HIGH


def _check_contract_id_format(value: str) -> str:
    if not _CONTRACT_ID.match(value):
        raise ValueError(f"contract id must be <context>.<entity>.<op>.vN: {value!r}")
    return value


class CapabilityDescriptor(Record):
    """A business capability contract, named by bounded context (ADR 0002)."""

    contract_id: str
    effect: EffectKind
    input_schema_id: str
    output_schema_id: str
    description: str = ""
    required_features: frozenset[str] = frozenset()
    agent_visible: bool = True
    """False for capabilities only the host uses (e.g. verification read-back)."""
    risk: Risk = Field(default_factory=_default_risk)
    """Defaults to `read` for read/answer effects, `write_high` for writes (ADR 0029). A
    defaulted value is absent from ``model_fields_set``."""
    reversibility: Reversibility = Reversibility.IRREVERSIBLE
    compensating_contract_id: str | None = None
    """The contract that undoes this one; required exactly when ``compensable``."""
    data_classes: Mapping[str, DataClass] = Field(default_factory=dict)
    """Field classes beside the schemas (ADR 0030, sdk_api 1.2), keyed by instance path:
    an RFC 6901 pointer under ``/input`` or ``/output`` into the data, with ``items`` for
    every array index (``/output/orders/items/partner_name``). A value's class is the most
    restrictive one declared on its path or an ancestor; an undeclared value is
    ``personal``. The schemas are unchanged, so the model-facing tool schemas are too;
    admission refuses a path that resolves to no property of the schema."""

    def __hash__(self) -> int:
        # The mapping field is not hashable; equal descriptors share a contract id.
        return hash((type(self), self.contract_id))

    @field_validator("contract_id")
    @classmethod
    def _check_contract_id(cls, value: str) -> str:
        return _check_contract_id_format(value)

    @field_validator("data_classes")
    @classmethod
    def _check_data_class_keys(cls, value: Mapping[str, DataClass]) -> Mapping[str, DataClass]:
        for key in value:
            check_class_key(key)
        return value

    @field_validator("compensating_contract_id")
    @classmethod
    def _check_compensating_id(cls, value: str | None) -> str | None:
        return None if value is None else _check_contract_id_format(value)

    @model_validator(mode="after")
    def _check_effect_declarations(self) -> Self:
        if self.risk is Risk.READ and self.effect is EffectKind.WRITE:
            raise ValueError("a write capability may not declare risk 'read'")
        compensable = self.reversibility is Reversibility.COMPENSABLE
        if compensable != (self.compensating_contract_id is not None):
            raise ValueError(
                "compensating_contract_id is required for, and only for, "
                "reversibility 'compensable'"
            )
        return self

    @property
    def bounded_context(self) -> str:
        return self.contract_id.split(".", 1)[0]


class CapabilityBinding(Record):
    """One implementation of a capability contract, served through one connection."""

    binding_id: str
    contract_id: str
    plugin_id: str
    plugin_version: str
    connection_id: str
    supported_features: frozenset[str] = frozenset()
    idempotency: Idempotency = Idempotency.NONE
    """Defaults to `none` (ADR 0029); a defaulted value is absent from ``model_fields_set``."""
