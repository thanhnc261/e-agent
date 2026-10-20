"""`e-agent explain <run_id>` (ADR 0033 §6, Task 3c.3): the run's explanation as JSON, read
from the profile's store as the operator."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest
from e_agent.plugins.erp.simulator import fixture_profile_path
from e_agent.server import cli
from e_agent.server.bootstrap import build_runtime
from e_agent.server.cli import demo_prompt, main
from e_agent.server.profile import load_profile

FIXTURE = ("--profile", str(fixture_profile_path()))


def test_explain_command_prints_the_runs_explanation(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The fixture store keeps no run across processes, so the command is given a runtime
    whose store already holds a fixture run waiting for approval."""
    profile = load_profile(str(fixture_profile_path()))

    async def seeded() -> tuple[Any, Any]:
        rt = await build_runtime(profile)
        preset = rt.registry.task_presets[profile.driver.task_kind]
        prompt = demo_prompt(preset, profile.driver)
        run = await rt.coordinator.start_run(rt.operator, prompt, rt.scope, task_kind=preset.kind)
        return rt, run

    rt, run = asyncio.run(seeded())
    seen: list[Any] = []

    async def same_runtime(*args: Any, **kwargs: Any) -> Any:
        seen.append(args)
        return rt

    monkeypatch.setattr(cli, "build_runtime", same_runtime)
    assert main([*FIXTURE, "explain", run.run_id]) == 0
    assert len(seen) == 1
    explained = json.loads(capsys.readouterr().out)
    assert explained["run"]["run_id"] == run.run_id
    assert explained["run"]["state"] == "WAITING_APPROVAL"
    assert explained["completeness"] in {"known", "partial"}
    (proposal,) = explained["proposals"]
    assert proposal["state"] == "AWAITING_APPROVAL" and proposal["digest"]
    assert "arguments" not in proposal
    assert explained["sources"] and explained["receipts"] == []


def test_explain_command_refuses_an_unknown_run(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([*FIXTURE, "explain", "run-missing"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "NOT_FOUND" in captured.err
