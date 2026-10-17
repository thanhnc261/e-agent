"""The supervised-task helper logs a failure and still surfaces it (PR-38, ENG-ARCH-7)."""

from __future__ import annotations

import asyncio
import logging

import pytest
from e_agent.sdk import tasks
from e_agent.sdk.tasks import supervised_task

LOGGER = "e_agent.sdk.tasks"
CANARY = "canary-secret-value"


class _Boom(RuntimeError):
    pass


async def test_supervised_task_failure_is_logged_and_reraised_on_await(
    caplog: pytest.LogCaptureFixture,
) -> None:
    sentinel = _Boom(CANARY)

    async def fail() -> None:
        raise sentinel

    caplog.set_level(logging.DEBUG, logger=LOGGER)
    task = supervised_task(fail(), name="probe.failing")
    with pytest.raises(_Boom) as excinfo:
        await task
    await asyncio.sleep(0)
    assert excinfo.value is sentinel
    records = [r for r in caplog.records if r.name == LOGGER]
    assert len(records) == 1
    [record] = records
    assert record.levelno >= logging.WARNING
    assert "probe.failing" in record.getMessage()
    assert "_Boom" in record.getMessage()
    # PR-28: the exception's message and traceback never reach the log.
    assert record.exc_info is None
    assert CANARY not in caplog.text


async def test_supervised_task_cancel_is_not_logged_as_failure(
    caplog: pytest.LogCaptureFixture,
) -> None:
    started = asyncio.Event()

    async def wait_forever() -> None:
        started.set()
        await asyncio.Event().wait()

    caplog.set_level(logging.DEBUG, logger=LOGGER)
    task = supervised_task(wait_forever(), name="probe.cancelled")
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await asyncio.sleep(0)
    assert task.cancelled()
    assert not [r for r in caplog.records if r.name == LOGGER]


async def test_supervised_task_holds_a_reference_until_done() -> None:
    release = asyncio.Event()

    async def wait() -> int:
        await release.wait()
        return 7

    task = supervised_task(wait(), name="probe.reference")
    assert task.get_name() == "probe.reference"
    assert task in tasks._RUNNING
    release.set()
    assert await task == 7
    await asyncio.sleep(0)
    assert task not in tasks._RUNNING


async def test_supervised_task_without_failure_logging_still_reraises(
    caplog: pytest.LogCaptureFixture,
) -> None:
    sentinel = _Boom(CANARY)

    async def fail() -> None:
        raise sentinel

    caplog.set_level(logging.DEBUG, logger=LOGGER)
    task = supervised_task(fail(), name="probe.awaited", log_failure=False)
    with pytest.raises(_Boom) as excinfo:
        await task
    await asyncio.sleep(0)
    assert excinfo.value is sentinel
    assert not [r for r in caplog.records if r.name == LOGGER]
    assert task not in tasks._RUNNING
