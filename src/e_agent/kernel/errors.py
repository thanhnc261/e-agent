"""Structured kernel errors (MVP design §12)."""

from __future__ import annotations

from enum import StrEnum


class ErrorCode(StrEnum):
    INVALID_REQUEST = "INVALID_REQUEST"
    NOT_FOUND = "NOT_FOUND"
    CONFLICT = "CONFLICT"
    FORBIDDEN = "FORBIDDEN"
    APPROVAL_STALE = "APPROVAL_STALE"
    VALIDATION_BLOCKED = "VALIDATION_BLOCKED"
    DEPENDENCY_UNAVAILABLE = "DEPENDENCY_UNAVAILABLE"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
    ACTION_UNRESOLVED = "ACTION_UNRESOLVED"
    STARTUP_REJECTED = "STARTUP_REJECTED"


class KernelError(Exception):
    def __init__(self, code: ErrorCode, safe_message: str) -> None:
        super().__init__(f"{code}: {safe_message}")
        self.code = code
        self.safe_message = safe_message
