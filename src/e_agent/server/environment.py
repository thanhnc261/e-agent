"""The one place product code reads the process environment (PR-37).

Profiles name environment variables (``dsn_env``, ``api_key_env``) instead of holding secrets.
Ruff bans ``os.environ`` and ``os.getenv`` in ``src/``; the two reads here carry pinned line-level
exemptions. An error names the variable and never echoes its value, because the value can be a
credential.
"""

from __future__ import annotations

import os
from typing import overload

from e_agent.kernel.errors import ErrorCode, KernelError


def require_env(name: str, *, purpose: str = "") -> str:
    """Return the variable's value; a missing or empty one is a startup error naming it."""
    value = os.environ.get(name)  # noqa: TID251 - the one environment reader (PR-37)
    if not value:
        suffix = f" {purpose}" if purpose else ""
        raise KernelError(ErrorCode.STARTUP_REJECTED, f"{name} is not set{suffix}")
    return value


@overload
def optional_env(name: str) -> str | None: ...
@overload
def optional_env(name: str, default: str) -> str: ...
def optional_env(name: str, default: str | None = None) -> str | None:
    """Return the variable's value, else ``default``; an empty value is returned as is."""
    return os.environ.get(name, default)  # noqa: TID251 - the one environment reader (PR-37)
