"""The committed Claude Code settings: permissions, hooks, compaction and worktrees (harness H4)."""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SETTINGS = json.loads((ROOT / ".claude" / "settings.json").read_text())
HOOK = '"$CLAUDE_PROJECT_DIR"/.claude/hooks/harness_hook.py'


def _bash_rule_matches(rule: str, command: str) -> bool:
    """Claude Code Bash rules: `*` matches any run of characters; `:*` is a trailing `*`."""
    m = re.fullmatch(r"Bash\((.*)\)", rule)
    if not m:
        return False
    pattern = m.group(1).removesuffix(":*") + ("*" if m.group(1).endswith(":*") else "")
    regex = "".join(".*" if c == "*" else re.escape(c) for c in pattern)
    # "git push *" also matches a bare "git push" (the trailing " *" is optional).
    regex = regex.removesuffix(r"\ .*") + r"(?:\ .*)?" if pattern.endswith(" *") else regex
    return re.fullmatch(regex, command) is not None


def _segment_decision(command: str) -> str:
    perms = SETTINGS["permissions"]
    for kind in ("deny", "ask", "allow"):
        if any(_bash_rule_matches(r, command) for r in perms.get(kind, [])):
            return kind
    return "default"


def _decision(command: str) -> str:
    """Claude Code checks each subcommand of a compound command; the strictest wins.

    This models the rule syntax only. Command shapes the rules cannot see (an absolute
    docker path, git global options) are handled by the bash-guard hook, tested in
    tests/harness/test_hook_wrapper.py.
    """
    order = ("deny", "ask", "default", "allow")
    segments = [s.strip() for s in re.split(r"&&|\|\||;|\|", command) if s.strip()]
    return min((_segment_decision(s) for s in segments), key=order.index)


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


def test_sandbox_commands_are_allowed() -> None:
    for command in (
        "docker compose -p odoo19-learning ps",
        "docker exec odoo19-learning-odoo-1 odoo --version",
        "docker exec odoo19-learning-db-1 psql -l",
        "docker logs odoo19-learning-odoo-1 --tail 50",
        "uv run e-agent-harness status",
    ):
        assert _decision(command) == "allow", command


def test_integration_commands_ask_the_owner() -> None:
    for command in (
        "git push",
        "git push origin main",
        "git merge --ff-only harness/h4-adapters",
        "git rebase main",
        "git reset --hard HEAD~1",
    ):
        assert _decision(command) == "ask", command
    assert _decision("git status") == "default"


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
        ("PreToolUse", "Bash"): "bash-guard",
        ("Stop", None): "close-check --hook",
    }
    for (event, matcher), args in expected.items():
        (hook,) = _commands(event, matcher)
        assert hook["type"] == "command"
        assert hook["command"] == f"python3 {HOOK} {args}", (event, hook["command"])
        assert 5 <= hook["timeout"] <= 180


def test_scope_hook_fails_closed_on_timeout() -> None:
    (hook,) = _commands("PreToolUse", "Edit|Write|NotebookEdit")
    assert hook["onFailure"] == "block"


def test_no_per_edit_formatting_hook() -> None:
    # Formatting and lint run once over the whole change with `e-agent-harness tidy`.
    assert "PostToolUse" not in SETTINGS["hooks"]
    assert sorted(SETTINGS["hooks"]) == ["PreCompact", "PreToolUse", "SessionStart", "Stop"]


def test_compound_commands_take_the_strictest_rule() -> None:
    assert _decision("docker compose -p odoo19-learning ps && git push origin main") == "ask"
    assert _decision("uv run e-agent-harness status; docker kill odoo-bench-db-1") == "deny"


def test_bash_guard_fails_closed_on_timeout() -> None:
    (hook,) = _commands("PreToolUse", "Bash")
    assert hook["onFailure"] == "block"
