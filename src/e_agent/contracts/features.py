"""Feature toggles carried by the run profile (ADR 0027, target architecture §6.4.8).

Each new runtime feature is one field of ``Features``, a ``FeatureMode``. Every
field defaults to ``off``, which is exactly the behaviour before the feature; an
unknown feature name is a validation error. Toggles come only from the typed
profile, never from an environment variable.
"""

from __future__ import annotations

from enum import StrEnum

from .common import Record


class FeatureMode(StrEnum):
    OFF = "off"
    SHADOW = "shadow"
    """Computes the new path and records a comparison with the live path; acts on nothing."""
    ON = "on"
    """Uses the new path; falls back only before the first write reservation."""


class Features(Record):
    execution_ir: FeatureMode = FeatureMode.OFF
    """Execution IR: compiled plans and steps (ADR 0025)."""
