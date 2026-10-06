"""Trusted identity and task context established by the host, never by the model."""

from __future__ import annotations

from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, field_validator

from .common import Record, UtcDatetime


class Principal(Record):
    principal_id: str
    tenant_id: str
    roles: frozenset[str]
    display_name: str | None = None


class Budgets(Record):
    max_driver_turns: int = 12
    max_read_calls: int = 20
    max_validation_repairs: int = 2
    max_admitted_writes: int = 1


class TaskContext(Record):
    run_id: str
    tenant_id: str
    principal: Principal
    resource_scope: frozenset[str]
    deadline: UtcDatetime | None = None
    budgets: Budgets = Budgets()


class ResourceHint(Record):
    """What a host page says the user is looking at. Untrusted; never grants access."""

    system_hint: str = Field(min_length=1, max_length=64)
    resource_type_hint: str = Field(min_length=1, max_length=128)
    external_id_hint: str = Field(min_length=1, max_length=256)


class HostContext(Record):
    """Provider-neutral, untrusted hints from an embedding host (UI architecture §4.7)."""

    host_kind: Literal["standalone", "embedded"]
    page_url_origin: str | None = Field(default=None, max_length=256)
    resource_hints: tuple[ResourceHint, ...] = Field(default=(), max_length=10)
    locale: str | None = Field(default=None, max_length=16)
    selection_text: str | None = Field(default=None, max_length=1000)

    @field_validator("page_url_origin")
    @classmethod
    def _origin_only(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parts = urlsplit(value)
        if parts.scheme not in {"http", "https"} or not parts.netloc:
            raise ValueError("page_url_origin must be an http(s) origin")
        if parts.path not in {"", "/"} or parts.query or parts.fragment or "@" in parts.netloc:
            raise ValueError("page_url_origin must be an origin only (no path, query or userinfo)")
        return f"{parts.scheme}://{parts.netloc}"


class ResolvedHint(Record):
    """A hint the host resolved to exactly one usable, in-scope connection."""

    connection_id: str
    resource_type: str
    external_id: str
