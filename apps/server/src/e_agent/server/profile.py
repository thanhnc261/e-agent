"""Validated, non-secret runtime profile (MVP design §6)."""

from __future__ import annotations

import json
from importlib.resources import files
from pathlib import Path
from typing import Literal

from e_agent.contracts.common import Record
from e_agent.contracts.connection import ConnectionDescriptor
from e_agent.contracts.context import Budgets
from pydantic import Field


class OperatorConfig(Record):
    principal_id: str
    roles: frozenset[str]
    display_name: str | None = None


class EnabledPluginConfig(Record):
    version: str
    manifest_sha256: str | None = None
    settings: dict[str, object] = Field(default_factory=dict)


class FixtureConfig(Record):
    scenario: str = "valid"
    driver_mode: str = "valid"


class StoreConfig(Record):
    kind: Literal["memory", "postgres"] = "memory"
    dsn_env: str = "E_AGENT_PG_DSN"
    """Name of the environment variable holding the DSN; the DSN is never in the profile."""


class Profile(Record):
    profile_version: Literal["1"]
    environment: Literal["fixture", "live"]
    tenant_id: str
    operator: OperatorConfig
    enabled_plugins: dict[str, EnabledPluginConfig]
    connections: tuple[ConnectionDescriptor, ...]
    bindings: dict[str, tuple[str, ...]]
    budgets: Budgets = Budgets()
    store: StoreConfig = StoreConfig()
    fixture: FixtureConfig | None = None


def load_profile(path: str | Path | None = None) -> Profile:
    if path is None:
        text = files(__package__).joinpath("profiles/fixture.json").read_text("utf-8")
    else:
        text = Path(path).read_text("utf-8")
    profile = Profile.model_validate(json.loads(text))
    for conn in profile.connections:
        if conn.tenant_id != profile.tenant_id:
            raise ValueError("profile connections must belong to the profile tenant")
        if conn.secret_ref is not None and not conn.secret_ref.startswith("secretref:"):
            raise ValueError("connections carry secret references only, never secret values")
    return profile
