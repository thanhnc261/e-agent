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
    """A plugin factory refuses its profile settings; admission fails closed.

    The message is shown to the operator at startup: it names the setting, never
    a credential or provider data.
    """
