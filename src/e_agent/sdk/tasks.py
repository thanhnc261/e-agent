"""Supervised background tasks (PR-38, ENG-ARCH-7).

Product code starts a background task only through ``supervised_task``; Ruff TID251 bans a
bare ``asyncio.create_task`` elsewhere under ``src/e_agent``. The helper keeps a strong
reference until the task is done and logs a failure with the task's name. It never swallows
the failure: awaiting the task raises the original exception. The log line carries the task
name and the exception type only, never its message or traceback (PR-28). Cancellation is
not a failure and is not logged.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine
from typing import Any

LOG = logging.getLogger("e_agent.sdk.tasks")

_RUNNING: set[asyncio.Task[Any]] = set()


def supervised_task[T](coro: Coroutine[Any, Any, T], *, name: str) -> asyncio.Task[T]:
    """Start ``coro`` as a named task that is referenced until done and logged on failure."""
    task = asyncio.create_task(coro, name=name)
    _RUNNING.add(task)
    task.add_done_callback(_finished)
    return task


def _finished(task: asyncio.Task[Any]) -> None:
    _RUNNING.discard(task)
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        LOG.warning("background task %s failed (%s)", task.get_name(), type(exc).__name__)
