"""Validated, non-secret runtime profile (MVP design §6)."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

from e_agent.contracts.common import Record
from e_agent.contracts.connection import ConnectionDescriptor
from e_agent.contracts.context import Budgets
from e_agent.kernel.errors import ErrorCode, KernelError
from pydantic import Field, model_validator


class OperatorConfig(Record):
    principal_id: str
    roles: frozenset[str]
    display_name: str | None = None
    allow_self_approval: bool = False
    """Local demo only: one operator holds requester and approver (HLD §3, ADR 0019)."""


class EnabledPluginConfig(Record):
    version: str
    manifest_sha256: str | None = None
    artifact_sha256: str | None = None
    settings: dict[str, object] = Field(default_factory=dict)


class FixtureConfig(Record):
    scenario: str | None = None
    """Kept for profiles written before ADR 0026: the scenario is now a setting of the
    simulator plugin. When set, it must equal that setting (``fixture_scenario_check``)."""
    driver_mode: str = "valid"


class StoreConfig(Record):
    kind: Literal["memory", "postgres"] = "memory"
    dsn_env: str = "E_AGENT_PG_DSN"
    """Name of the environment variable holding the DSN; the DSN is never in the profile."""


OLD_REF_KEYS = frozenset({"demand_ref", "product_ref"})
"""Top-level driver keys that profiles written before ADR 0026 carry."""


class DriverConfig(Record):
    kind: Literal["scripted", "pydantic-ai"] = "scripted"
    provider: Literal["ollama", "litellm"] = "ollama"
    """Ollama is the default; LiteLLM is explicit opt-in (ADR 0021). Never a fallback."""
    model: str | None = None
    base_url_env: str | None = None
    """Env var holding the endpoint; defaults to E_AGENT_OLLAMA_URL or E_AGENT_LITELLM_URL."""
    api_key_env: str | None = None
    """LiteLLM only: env var holding the proxy key. The key itself is never in the profile."""
    requests_per_step: int = 4
    temperature: str | None = None
    task_kind: str = "draft-po"
    """A task preset kind contributed by an admitted plugin; startup refuses any other."""
    refs: dict[str, str] = Field(default_factory=dict)
    """Refs that replace the task preset's defaults in the demo prompt and scripted driver."""

    @model_validator(mode="before")
    @classmethod
    def _fold_old_ref_keys(cls, data: Any) -> Any:
        """Move the old top-level ``demand_ref`` and ``product_ref`` into ``refs`` (ADR 0026).

        An old key that differs from its ``refs`` entry is refused, never resolved.
        """
        if not isinstance(data, Mapping) or not OLD_REF_KEYS & data.keys():
            return data
        folded = {k: v for k, v in data.items() if k not in OLD_REF_KEYS}
        refs = folded.get("refs", {})
        if not isinstance(refs, Mapping):
            return folded  # field validation reports the bad refs
        refs = dict(refs)
        for name in sorted(OLD_REF_KEYS & data.keys()):
            value = data[name]
            if value is None:
                continue
            if name in refs and refs[name] != value:
                raise ValueError(f"driver.{name} and driver.refs.{name} differ; keep only refs")
            refs[name] = value
        folded["refs"] = refs
        return folded


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
    driver: DriverConfig = DriverConfig()
    fixture: FixtureConfig | None = None


def load_profile(path: str | Path | None = None) -> Profile:
    """Load the given profile, else the one ``E_AGENT_PROFILE`` names; the server ships none."""
    path = path or os.environ.get("E_AGENT_PROFILE")
    if not path:
        raise KernelError(
            ErrorCode.STARTUP_REJECTED, "no profile given: pass --profile or set E_AGENT_PROFILE"
        )
    text = Path(path).read_text("utf-8")
    profile = Profile.model_validate(json.loads(text))
    for conn in profile.connections:
        if conn.tenant_id != profile.tenant_id:
            raise ValueError("profile connections must belong to the profile tenant")
        if conn.secret_ref is not None and not conn.secret_ref.startswith("secretref:"):
            raise ValueError("connections carry secret references only, never secret values")
    return profile
