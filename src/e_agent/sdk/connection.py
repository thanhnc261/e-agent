"""Typed manifest ``connection`` section: auth methods and the sandbox probe (ADR 0012, 0026).

The host and every provider validate against this one definition. An unknown
placement, method type or key is refused, never defaulted. A plugin without a
``connection`` section needs none.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal

from e_agent.contracts.common import Record
from pydantic import Field, model_validator


class ApiKeyPlacement(Record):
    """Where the host puts an API key; only request headers are applied today."""

    placement: Literal["header"]
    header: str = Field(min_length=1)
    prefix: str
    """Written before the key, exactly as given (``"bearer "``, ``""``); no default."""


class AuthMethod(Record):
    id: str = Field(min_length=1)
    type: Literal["api_key", "none"]
    levels: tuple[Literal["tenant", "user"], ...] = ()
    api_key: ApiKeyPlacement | None = None
    input_schema: dict[str, object] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _placement_matches_type(self) -> AuthMethod:
        if self.type == "api_key" and self.api_key is None:
            raise ValueError(f"auth method {self.id!r}: api_key needs a placement")
        if self.type == "none" and self.api_key is not None:
            raise ValueError(f"auth method {self.id!r}: type none takes no placement")
        return self


class ConnectionSpec(Record):
    auth_methods: tuple[AuthMethod, ...] = ()
    test_connection: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]*$")
    """Name of the provider executor's read-only sandbox probe (a public method)."""

    @model_validator(mode="after")
    def _one_auth_method(self) -> ConnectionSpec:
        # Connections carry no auth-method id yet, so choosing among several
        # would be a default; one method per manifest until they do.
        if len(self.auth_methods) > 1:
            raise ValueError("more than one auth method; a connection cannot choose one yet")
        return self

    @classmethod
    def from_manifest(cls, section: Mapping[str, object]) -> ConnectionSpec | None:
        """Validate a manifest's ``connection`` section; ``None`` when it has none."""
        return cls.model_validate(dict(section)) if section else None

    def placement(self) -> dict[str, str] | None:
        """The credential placement the host applies, or ``None`` without an auth method."""
        if not self.auth_methods:
            return None
        method = self.auth_methods[0]
        if method.api_key is None:
            return {"method": method.type}
        return {
            "method": method.type,
            "header": method.api_key.header,
            "prefix": method.api_key.prefix,
        }
