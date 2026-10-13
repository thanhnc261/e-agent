"""Static plugin manifests, packaged as resources and read without importing code."""

from __future__ import annotations

import re

from e_agent.contracts.capability import CapabilityDescriptor
from e_agent.contracts.common import Record
from pydantic import Field, field_validator

_RANGE = re.compile(r"^(>=)(\d+)\.(\d+),<(\d+)\.(\d+)$")


class BindingTemplate(Record):
    """A binding the plugin can provide once a connection is assigned by the host."""

    binding_id: str
    contract_id: str
    supported_features: frozenset[str] = frozenset()


class PluginManifest(Record):
    plugin_id: str
    version: str
    sdk_api: str
    factory: str
    kind: str
    provides_capabilities: tuple[CapabilityDescriptor, ...] = ()
    provides_bindings: tuple[BindingTemplate, ...] = ()
    requires_capabilities: tuple[str, ...] = ()
    settings_schema: dict[str, object] = Field(default_factory=dict)
    connection: dict[str, object] = Field(default_factory=dict)
    """Provider-neutral connection/auth declaration (ADR 0012/0013)."""

    @field_validator("sdk_api")
    @classmethod
    def _check_range(cls, value: str) -> str:
        if not _RANGE.match(value):
            raise ValueError("sdk_api must look like '>=1.0,<2.0'")
        return value

    @field_validator("factory")
    @classmethod
    def _check_factory(cls, value: str) -> str:
        module, sep, attr = value.partition(":")
        if not sep or not module or not attr:
            raise ValueError("factory must be 'module:attribute'")
        return value

    def supports_sdk(self, sdk_version: str) -> bool:
        match = _RANGE.match(self.sdk_api)
        if match is None:  # pragma: no cover - validated above
            return False
        lo = (int(match.group(2)), int(match.group(3)))
        hi = (int(match.group(4)), int(match.group(5)))
        major, minor = (int(p) for p in sdk_version.split(".")[:2])
        return lo <= (major, minor) < hi
