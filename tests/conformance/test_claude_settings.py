"""The committed Claude Code settings: permissions, hooks, compaction and worktrees (harness H4)."""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SETTINGS = json.loads((ROOT / ".claude" / "settings.json").read_text())
HOOK = '"$CLAUDE_PROJECT_DIR"/.claude/hooks/harness_hook.py'


def _bash_rule_matches(rule: str, command: str) -> bool:
    """Claude Code Bash rules: `*` matches any run of characters; `:*` is a trailing `*`.

    A bare `Bash` rule matches every shell command.
    """
    if rule == "Bash":
        return True
    m = re.fullmatch(r"Bash\((.*)\)", rule)
    if not m:
        return False
    pattern = m.group(1).removesuffix(":*") + ("*" if m.group(1).endswith(":*") else "")
    regex = "".join(".*" if c == "*" else re.escape(c) for c in pattern)
    # "git push *" also matches a bare "git push" (the trailing " *" is optional).
    regex = regex.removesuffix(r"\ .*") + r"(?:\ .*)?" if pattern.endswith(" *") else regex
    return re.fullmatch(regex, command) is not None


def _decision(command: str) -> str:
    """Which literal rule a single, plain command matches (deny, then ask, then allow).

    This checks the rule text only. It is not Claude Code's command evaluator: compound
    commands, wrappers and dynamic execution are bash-guard's job, tested in
    tests/harness/test_hook_wrapper.py and live in the H4 handoffs.
    """
    perms = SETTINGS["permissions"]
    for kind in ("deny", "ask", "allow"):
        if any(_bash_rule_matches(r, command) for r in perms.get(kind, [])):
            return kind
    return "default"


def test_context_settings() -> None:
    assert SETTINGS["autoCompactWindow"] == 400000
    assert SETTINGS["worktree"]["baseRef"] == "head"


def test_deny_rules_cover_odoo_bench_shapes() -> None:
    for command in (
        "docker compose -p odoo-bench down",
        "docker exec odoo-bench-db-1 psql -U odoo",
        "docker exec -it odoo-bench-odoo-1 bash",
        "docker stop odoo-bench-db-1",
        "docker restart odoo-bench-odoo-1",
        "docker rm -f odoo-bench-db-1",
        "docker kill odoo-bench-odoo-1",
        "docker logs odoo-bench-odoo-1",
    ):
        assert _decision(command) == "deny", command


def test_deny_rules_cover_commands_that_reach_every_container() -> None:
    # They never name odoo-bench but would still stop or delete the running bench.
    for command in (
        "docker stop $(docker ps -q)",
        "docker kill $(docker ps -q)",
        "docker restart $(docker ps -q)",
        "docker rm -f $(docker ps -aq)",
        "docker system prune -af",
        "docker container prune -f",
        "docker volume prune -f",
        "docker network prune -f",
    ):
        assert _decision(command) == "deny", command
    assert _decision("docker stop e-agent-test-pg") == "allow"


def test_sandbox_commands_are_allowed() -> None:
    for command in (
        "docker compose -p odoo19-learning ps",
        "docker exec odoo19-learning-odoo-1 odoo --version",
        "docker exec odoo19-learning-db-1 psql -l",
        "docker logs odoo19-learning-odoo-1 --tail 50",
        "uv run e-agent-harness status",
    ):
        assert _decision(command) == "allow", command


def test_shell_is_pre_approved_and_deny_still_wins() -> None:
    """The owner's 2026-10-15 instruction: no manual shell approval; deny rules stay."""
    perms = SETTINGS["permissions"]
    assert perms["allow"] == ["Bash"]
    assert "ask" not in perms
    for command in ("git status", "git push origin main", "git reset --hard HEAD~1"):
        assert _decision(command) == "allow", command
    assert _decision("docker exec odoo-bench-db-1 psql -U odoo") == "deny"


def test_protected_and_external_paths_are_denied() -> None:
    deny = SETTINGS["permissions"]["deny"]
    assert "Edit(archive/**)" in deny
    assert "Read(//**/ERP-Bench/**/solution/**)" in deny
    assert "Read(//**/ERP-Bench/**/tests/**)" in deny
    assert "Edit(~/dev/lab/enterprise-agent/experiment/**)" in deny


def test_no_user_specific_absolute_paths_are_committed() -> None:
    assert "/Users/" not in json.dumps(SETTINGS)


def _commands(event: str, matcher: str | None = None) -> list[dict]:
    groups = SETTINGS["hooks"][event]
    return [h for g in groups if matcher is None or g.get("matcher") == matcher for h in g["hooks"]]


def test_hooks_call_the_entry_script() -> None:
    expected = {
        ("SessionStart", "startup|resume|clear|compact"): "status --format hook",
        ("PreCompact", None): "checkpoint --hook",
        ("PreToolUse", "Edit|Write|NotebookEdit"): "check-scope --hook",
        ("Stop", None): "close-check --hook",
    }
    # A guarding hook maps any startup failure (an old python3, a missing script) to exit 2.
    suffix = {
        "check-scope --hook": " || exit 2",
        "close-check --hook": ' || { test "$E_AGENT_HARNESS_UNATTENDED" = 1 && exit 2; exit 0; }',
    }
    for (event, matcher), args in expected.items():
        (hook,) = _commands(event, matcher)
        assert hook["type"] == "command"
        expected_command = f"python3 {HOOK} {args}{suffix.get(args, '')}"
        assert hook["command"] == expected_command, (event, hook["command"])
        assert 5 <= hook["timeout"] <= 180


def test_scope_hook_fails_closed_on_timeout() -> None:
    (hook,) = _commands("PreToolUse", "Edit|Write|NotebookEdit")
    assert hook["onFailure"] == "block"


def test_no_per_edit_formatting_hook() -> None:
    # Formatting and lint run once over the whole change with `e-agent-harness tidy`.
    assert "PostToolUse" not in SETTINGS["hooks"]
    assert sorted(SETTINGS["hooks"]) == ["PreCompact", "PreToolUse", "SessionStart", "Stop"]


def test_bash_guard_is_not_wired() -> None:
    # Unwired at the owner's 2026-10-15 instruction so it cannot ask for shell approval;
    # the helper stays tested in tests/harness.
    assert _commands("PreToolUse", "Bash") == []


def test_wrapper_timeout_is_below_every_host_timeout() -> None:
    """The wrapper, not the host, must end a stalled check: onFailure needs a newer Claude Code."""
    script = (ROOT / ".claude" / "hooks" / "harness_hook.py").read_text()
    wrapper = int(re.search(r"^TIMEOUT = (\d+)$", script, re.M).group(1))
    for groups in SETTINGS["hooks"].values():
        for group in groups:
            for entry in group["hooks"]:
                if "harness_hook.py" in entry["command"] and "bash-guard" not in entry["command"]:
                    assert entry["timeout"] > wrapper + 10, entry["command"]


def _run_hook_command(command: str, tmp_path: Path, env: dict[str, str]) -> int:
    import os
    import subprocess

    return subprocess.run(
        ["sh", "-c", command],
        input="{}",
        capture_output=True,
        text=True,
        env={**os.environ, "CLAUDE_PROJECT_DIR": str(tmp_path), **env},
        timeout=30,
        check=False,
    ).returncode


def test_guarding_hooks_block_when_python_fails_to_start(tmp_path) -> None:
    """R6-1: the installed Claude Code ignores onFailure, so the command line maps failures."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    broken = bin_dir / "python3"
    broken.write_text("#!/bin/sh\necho 'ModuleNotFoundError: tomllib' >&2\nexit 1\n")
    broken.chmod(0o755)
    path = {"PATH": f"{bin_dir}:/usr/bin:/bin"}
    scope = _commands("PreToolUse", "Edit|Write|NotebookEdit")[0]["command"]
    stop = _commands("Stop", None)[0]["command"]
    status = _commands("SessionStart", "startup|resume|clear|compact")[0]["command"]
    assert _run_hook_command(scope, tmp_path, path) == 2
    assert _run_hook_command(stop, tmp_path, {**path, "E_AGENT_HARNESS_UNATTENDED": "1"}) == 2
    assert _run_hook_command(stop, tmp_path, {**path, "E_AGENT_HARNESS_UNATTENDED": ""}) == 0
    assert _run_hook_command(status, tmp_path, path) == 1  # never blocks: not exit 2
