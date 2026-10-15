"""Task presets come from the domain pack; task_kind is a string checked at startup (R-3).

The server holds no table of task kinds or demo prompts: the CLI renders the
prompt from the admitted preset, and bootstrap refuses a kind no admitted
plugin contributes.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from e_agent.erp.plugin import TASK_PRESETS
from e_agent.kernel.errors import ErrorCode, KernelError
from e_agent.server import cli
from e_agent.server.bootstrap import build_runtime
from e_agent.server.profile import Profile, load_profile

from .record_demo_prompts import GOLDEN, TASKS, capture_prompts


def _profile(**driver: Any) -> Profile:
    data = load_profile().model_dump(mode="json")
    data["driver"] |= driver
    return Profile.model_validate(data)


def test_cli_demo_prompts_unchanged() -> None:
    assert capture_prompts() == json.loads(GOLDEN.read_text("utf-8"))


async def test_unknown_task_kind_refused_at_startup() -> None:
    with pytest.raises(KernelError) as exc:
        await build_runtime(_profile(task_kind="no-such-task"))
    assert exc.value.code is ErrorCode.STARTUP_REJECTED
    assert "no-such-task" in exc.value.safe_message
    with pytest.raises(KernelError) as exc:
        await build_runtime(load_profile(), task_kind="no-such-task")
    assert exc.value.code is ErrorCode.STARTUP_REJECTED


def test_profile_accepts_non_erp_task_kind_string() -> None:
    assert _profile(task_kind="notes-summary").driver.task_kind == "notes-summary"
    assert load_profile().driver.task_kind == "draft-po"


async def test_task_kind_choices_come_from_presets() -> None:
    contributed = {preset.kind for preset in TASK_PRESETS}
    assert contributed == set(TASKS)
    rt = await build_runtime(load_profile())
    assert set(rt.registry.task_presets) == contributed
    # The parser holds no list of kinds; the admitted presets decide at startup.
    args = cli.build_parser().parse_args(["demo", "--task", "notes-summary"])
    assert args.task == "notes-summary"
    with pytest.raises(KernelError) as exc:
        await build_runtime(load_profile(), task_kind="notes-summary")
    assert all(kind in exc.value.safe_message for kind in contributed)
