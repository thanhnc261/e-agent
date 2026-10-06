"""Errors plugins raise to tell the kernel what is known about an effect."""

from __future__ import annotations


class KnownNoEffectError(Exception):
    """The provider authoritatively rejected the call; nothing was committed.

    Any other exception raised during ``execute`` is treated as an ambiguous
    outcome (``UNKNOWN``) and is never blindly retried.
    """

    def __init__(self, code: str, safe_message: str) -> None:
        super().__init__(f"{code}: {safe_message}")
        self.code = code
        self.safe_message = safe_message
