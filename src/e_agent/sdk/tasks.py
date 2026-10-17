"""Supervised background tasks (PR-38, ENG-ARCH-7).

Product code starts a background task only through ``supervised_task``; Ruff TID251 bans a
bare ``asyncio.create_task`` under ``src/e_agent``, and the one call below carries a pinned
line-level exemption. The helper keeps a strong reference until the task is done and logs a
failure with the task's name, unless the caller awaits the task and handles the failure itself
(``log_failure=False``). It never swallows the failure: awaiting the task raises the original
exception. The log line carries the task name and the exception type only, never its message
or traceback (PR-28). Cancellation is not a failure and is not logged.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine
from typing import Any

LOG = logging.getLogger("e_agent.sdk.tasks")

_RUNNING: set[asyncio.Task[Any]] = set()


def supervised_task[T](
    coro: Coroutine[Any, Any, T], *, name: str, log_failure: bool = True
) -> asyncio.Task[T]:
    """Start ``coro`` as a named task that is referenced until done and logged on failure.

    ``log_failure=False`` is for a task whose caller awaits it and handles the failure itself,
    so the failure is surfaced once, by that caller.
    """
    task = asyncio.create_task(coro, name=name)  # noqa: TID251 - the one supervised caller (PR-38)
    _RUNNING.add(task)
    task.add_done_callback(_log_failure if log_failure else _RUNNING.discard)
    return task


def _log_failure(task: asyncio.Task[Any]) -> None:
    _RUNNING.discard(task)
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        LOG.warning("background task %s failed (%s)", task.get_name(), type(exc).__name__)
