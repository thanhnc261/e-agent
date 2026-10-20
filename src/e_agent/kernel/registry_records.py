"""Records the plugin registry takes and reports (MVP design §6).

Kept apart from ``registry.py`` so that module stays under the kernel size limit; the
registry re-exports them, so ``from e_agent.kernel.registry import EnabledPlugin`` holds.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(frozen=True)
class EnabledPlugin:
    version: str
    manifest_sha256: str | None = None
    settings: Mapping[str, Any] = field(default_factory=dict)
    artifact_sha256: str | None = None
    allow_unverified_fixture: bool = False


@dataclass(frozen=True)
class DefaultedDeclaration:
    """A write capability or connected write binding that relies on a default effect
    field (ADR 0029). A fixture profile admits it and lists it here; a live profile
    refuses it."""

    plugin_id: str
    subject: Literal["capability", "binding"]
    subject_id: str
    """The contract id of a capability, or the binding id of a binding."""
    fields: tuple[str, ...]


@dataclass
class AdmissionReport:
    admitted: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    defaulted_declarations: list[DefaultedDeclaration] = field(default_factory=list)
    """Effect declarations admitted on their defaults (fixture profiles only)."""
