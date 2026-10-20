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
    context_assembler: FeatureMode = FeatureMode.OFF
    """The kernel-built, bounded and masked context pack for each driver turn (ADR 0032)."""
    kernel_repeat: FeatureMode = FeatureMode.OFF
    """The kernel's repeated-call check (ADR 0031)."""
    grounded_answers: FeatureMode = FeatureMode.OFF
    """Answers grounded in cited evidence (ADR 0033)."""


class RunModes(Record):
    """The Phase 3 modes a run pins when it is prepared (ADR 0032 §8).

    A run keeps these modes for its whole life, whatever the profile later says; a profile
    flip affects new runs only. ``execution_ir`` is not pinned: it keeps reading the profile
    per call, as Phase 2 shipped. The kernel stores the pin only when a mode is not ``off``,
    and an absent pin means every mode is ``off``.
    """

    context_assembler: FeatureMode = FeatureMode.OFF
    kernel_repeat: FeatureMode = FeatureMode.OFF
    grounded_answers: FeatureMode = FeatureMode.OFF

    @classmethod
    def from_features(cls, features: Features) -> RunModes:
        return cls(**{name: getattr(features, name) for name in cls.model_fields})

    @property
    def all_off(self) -> bool:
        return all(getattr(self, name) is FeatureMode.OFF for name in type(self).model_fields)
