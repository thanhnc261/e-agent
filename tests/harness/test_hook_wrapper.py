"""The Claude Code hook entry script (.claude/hooks/harness_hook.py), run as Claude Code runs it."""

import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / ".claude" / "hooks" / "harness_hook.py"


def hook(args: list[str], payload: dict, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env={**os.environ, **(env or {})},
        timeout=120,
    )


def _activate(repo) -> None:
    assert (
        repo.invoke("new-task", "1", "1c.1", "--feature", "F-1", "--paths", "src/pkg/**").code == 0
    )


def _write(repo, path: str, cwd: Path | None = None) -> dict:
    return {
        "hook_event_name": "PreToolUse",
        "tool_name": "Write",
        "tool_input": {"file_path": path},
        "cwd": str(cwd or repo.root),
    }


def test_wrapper_denies_out_of_scope_write(repo) -> None:
    _activate(repo)
    result = hook(["check-scope", "--hook"], _write(repo, str(repo.root / "docs/other.md")))
    assert result.returncode == 2, result
    assert "outside the task's allowed paths" in result.stderr


def test_wrapper_allows_in_scope_write(repo) -> None:
    _activate(repo)
    result = hook(["check-scope", "--hook"], _write(repo, "src/pkg/mod.py"))
    assert result.returncode == 0, result


def test_wrapper_uses_the_payload_cwd_repository(repo, tmp_path) -> None:
    _activate(repo)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    # The hook process starts somewhere else; the payload cwd is a subdirectory of the repo.
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "check-scope", "--hook"],
        input=json.dumps(_write(repo, str(repo.root / "archive/old.md"), cwd=repo.root / "src")),
        capture_output=True,
        text=True,
        cwd=elsewhere,
        timeout=120,
    )
    assert result.returncode == 2
    assert "protected path" in result.stderr


def test_wrapper_status_prints_sessionstart_json(repo) -> None:
    payload = {"hook_event_name": "SessionStart", "source": "startup", "cwd": str(repo.root)}
    result = hook(["status", "--format", "hook"], payload)
    assert result.returncode == 0, result
    out = json.loads(result.stdout)["hookSpecificOutput"]
    assert out["hookEventName"] == "SessionStart"
    assert "new-task" in out["additionalContext"]


def test_wrapper_checkpoint_appends_an_entry(repo) -> None:
    payload = {"hook_event_name": "PreCompact", "session_id": "s-hook", "cwd": str(repo.root)}
    result = hook(["checkpoint", "--hook"], payload)
    assert result.returncode == 0, result
    assert "s-hook" in (repo.root / "harness/state/progress.md").read_text()


def test_wrapper_failure_modes(repo, tmp_path) -> None:
    outside = tmp_path / "no-repo"
    outside.mkdir()
    payload = _write(repo, "x.py", cwd=outside)
    denied = hook(["check-scope", "--hook"], payload)
    assert denied.returncode == 2
    assert "no repository" in denied.stderr
    for args in (
        ["status", "--format", "hook"],
        ["checkpoint", "--hook"],
        ["close-check", "--hook"],
    ):
        assert hook(args, payload).returncode == 0, args
    # uv missing in a uv project: check-scope still fails closed, the others stay silent.
    (repo.root / "pyproject.toml").write_text("[project]\nname = 'x'\nversion = '0'\n")
    no_uv = {"PATH": "/nonexistent"}
    assert hook(["check-scope", "--hook"], _write(repo, "src/pkg/mod.py"), no_uv).returncode == 2
    status_payload = {"hook_event_name": "SessionStart", "cwd": str(repo.root)}
    assert hook(["status", "--format", "hook"], status_payload, no_uv).returncode == 0
    unattended = {**no_uv, "E_AGENT_HARNESS_UNATTENDED": "1"}
    stop = {"hook_event_name": "Stop", "stop_hook_active": False, "cwd": str(repo.root)}
    assert hook(["close-check", "--hook"], stop, unattended).returncode == 2


def test_wrapper_has_no_format_mode(repo) -> None:
    script = SCRIPT.read_text()
    assert '"format"' not in script and "ruff" not in script


def test_stop_hook_spawns_nothing_when_attended(repo, tmp_path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    marker = tmp_path / "uv-was-called"
    fake_uv = bin_dir / "uv"
    fake_uv.write_text(f"#!/bin/sh\ntouch {marker}\nexit 0\n")
    fake_uv.chmod(0o755)
    (repo.root / "pyproject.toml").write_text("[project]\nname = 'x'\nversion = '0'\n")
    env = {k: v for k, v in os.environ.items() if k != "E_AGENT_HARNESS_UNATTENDED"}
    env["PATH"] = f"{bin_dir}:/usr/bin:/bin"
    stop = {"hook_event_name": "Stop", "stop_hook_active": False, "cwd": str(repo.root)}
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "close-check", "--hook"],
        input=json.dumps(stop),
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )
    assert result.returncode == 0
    assert not marker.exists(), "an attended Stop must not start the harness"


def _bash(repo, command: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": command},
        "cwd": str(cwd or repo.root),
    }
    return hook(["bash-guard"], payload)


def test_bash_guard_denies_docker_on_a_denied_container(repo) -> None:
    for command in (
        "/usr/local/bin/docker stop odoo-bench-db-1",
        "docker compose --project-name=odoo-bench down",
        "docker compose -p odoo-bench down",
        "sudo docker exec -it odoo-bench-odoo-1 bash",
        "ls && docker kill odoo-bench-db-1",
        "DOCKER_HOST=unix:///x docker rm odoo-bench-db-1",
        "echo $(docker restart odoo-bench-odoo-1)",
    ):
        result = _bash(repo, command)
        assert result.returncode == 2, command
        assert "odoo-bench" in result.stderr


def test_bash_guard_lets_other_commands_through(repo) -> None:
    for command in (
        "docker exec odoo19-learning-odoo-1 odoo --version",
        "grep -rn odoo-bench docs",
        "git status",
        "git reset --soft HEAD~1",
        "git log --grep push",
    ):
        result = _bash(repo, command)
        assert result.returncode == 0, command
        assert result.stdout == "", command


def test_bash_guard_asks_before_integration_commands(repo) -> None:
    for command in (
        "git push",
        "git -C . push origin main",
        "git -c core.pager=cat push",
        "git --no-pager merge feature",
        "cd sub && git rebase main",
        "git reset HEAD~1 --hard",
        "git --git-dir=.git reset --hard",
    ):
        result = _bash(repo, command)
        assert result.returncode == 0, command
        decision = json.loads(result.stdout)["hookSpecificOutput"]
        assert decision["hookEventName"] == "PreToolUse"
        assert decision["permissionDecision"] == "ask", command
