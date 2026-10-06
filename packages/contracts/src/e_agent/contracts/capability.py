"""Capability contracts and implementation bindings (HLD §5, ADR 0002)."""

from __future__ import annotations

import re
from enum import StrEnum

from pydantic import field_validator

from .common import Record

_CONTRACT_ID = re.compile(r"^[a-z][a-z0-9-]*(\.[a-z][a-z0-9-]*)+\.v[0-9]+$")


class EffectKind(StrEnum):
    READ = "read"
    WRITE = "write"
    ANSWER = "answer"
    """A structured answer: no provider effect, no approval; independently verified."""


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

    @field_validator("contract_id")
    @classmethod
    def _check_contract_id(cls, value: str) -> str:
        if not _CONTRACT_ID.match(value):
            raise ValueError(f"contract id must be <context>.<entity>.<op>.vN: {value!r}")
        return value

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
