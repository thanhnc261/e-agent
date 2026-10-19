"""Errors plugins raise to tell the kernel what is known about an effect."""

from __future__ import annotations

AUTH_REQUIRED = "AUTH_REQUIRED"
"""Rejection code: credentials are unavailable; the model cannot fix this."""


class KnownNoEffectError(Exception):
    """The provider authoritatively rejected the call; nothing was committed.

    Any other exception raised during ``execute`` is treated as an ambiguous
    outcome (``UNKNOWN``) and is never blindly retried.
    """

    def __init__(self, code: str, safe_message: str) -> None:
        super().__init__(f"{code}: {safe_message}")
        self.code = code
        self.safe_message = safe_message


class DriverBudgetExceeded(Exception):
    """The driver exhausted a host-supplied usage bound; no tool was dispatched."""


class InvalidPluginSettings(ValueError):
    """A plugin factory refuses one of its profile settings; admission fails closed.

    The host composes the operator's startup message from ``setting`` (the name)
    and ``reason`` (fixed text from the plugin). A setting's value is never part of
    either: a profile value may hold anything, including private data.
    """

    def __init__(self, setting: str, reason: str) -> None:
        super().__init__(f"{setting}: {reason}")
        self.setting = setting
        self.reason = reason


class DriverStateMismatch(Exception):
    """A driver continuation does not match the run's pinned modes (ADR 0032 §8): the
    kernel's restore check (its ``rendering`` marker against the pin), or a driver's own
    ``restore``, refuses it. The kernel restores nothing and fails the run closed with
    ``DRIVER_STATE_MISMATCH``, or sends it to reconciliation while a write is unresolved.
    A driver schema or version change is a plain ``ValueError`` and is not this refusal."""


class ContextNotRendered(Exception):
    """A driver cannot render the turn from the context pack it was given (ADR 0032 §6,
    review D3-42), for example a pending read whose observation the pack does not hold. It
    never falls back to ``Observation.data``; the kernel fails closed with
    ``CONTEXT_UNAVAILABLE``."""
