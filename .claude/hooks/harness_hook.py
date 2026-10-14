#!/usr/bin/env python3
"""Claude Code hook entry for the e-agent development harness (stdlib only).

Called from .claude/settings.json as
``python3 "$CLAUDE_PROJECT_DIR"/.claude/hooks/harness_hook.py <args>``.

The hook payload arrives on stdin. The repository is the nearest ancestor of the
payload's ``cwd`` that holds ``harness/context.toml`` (a worktree is its own
repository), and the harness runs from there:
``uv run --directory <repo> e-agent-harness <args>``, or the current interpreter's
``e_agent_harness`` when the repository is not a uv project.

Failure policy: ``check-scope`` fails closed (exit 2), because an unchecked edit is
worse than a refused one; ``close-check`` fails closed only when
E_AGENT_HARNESS_UNATTENDED=1; ``status`` and ``checkpoint`` never block.
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
import shlex
import subprocess
import sys
import tomllib
from pathlib import Path

MANIFEST = Path("harness") / "context.toml"
TIMEOUT = 110


def _fails_closed(command: str) -> bool:
    if command == "check-scope":
        return True
    return command == "close-check" and os.environ.get("E_AGENT_HARNESS_UNATTENDED") == "1"


def _repo_root(start: Path) -> Path | None:
    for candidate in (start, *start.parents):
        if (candidate / MANIFEST).is_file():
            return candidate
    return None


def _runner(root: Path) -> list[str]:
    if (root / "pyproject.toml").is_file():
        return ["uv", "run", "--quiet", "--directory", str(root), "e-agent-harness"]
    return [sys.executable, "-m", "e_agent_harness.cli"]


# --- bash-guard: command shapes that permission rules cannot see -----------------------

_SEPARATORS = re.compile(r"&&|\|\||;|\||\n|\$\(|`|\(|\)")
_WRAPPERS = {"sudo", "env", "command", "exec", "nohup", "time", "nice", "xargs"}
_CONTAINER_TOOLS = {"docker", "docker-compose", "podman"}
_GIT_OPTIONS_WITH_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path"}
_ASK = {"push", "merge", "rebase"}


def _words(segment: str) -> list[str]:
    try:
        words = shlex.split(segment)
    except ValueError:
        words = segment.split()
    while words and (re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", words[0]) or words[0] in _WRAPPERS):
        words = words[1:]
    return words


def _git_subcommand(words: list[str]) -> tuple[str, list[str]]:
    i = 1
    while i < len(words) and words[i].startswith("-"):
        i += 2 if words[i] in _GIT_OPTIONS_WITH_VALUE else 1
    return (words[i], words[i + 1 :]) if i < len(words) else ("", [])


def _denied_containers(root: Path) -> list[str]:
    with (root / MANIFEST).open("rb") as fh:
        env = tomllib.load(fh).get("environment", {})
    return [str(p) for p in env.get("denied_containers", [])]


def bash_guard(root: Path, command: str) -> tuple[int, str]:
    """(exit code, stdout). Exit 2 denies; stdout may carry an "ask" decision."""
    denied = _denied_containers(root)
    for segment in _SEPARATORS.split(command):
        words = _words(segment)
        if not words:
            continue
        tools = {Path(w).name for w in words}
        if tools & _CONTAINER_TOOLS:
            for word in words:
                for part in word.split("="):
                    if any(fnmatch.fnmatchcase(part, pattern) for pattern in denied):
                        print(
                            f"bash-guard: {part} is a denied container ({MANIFEST})",
                            file=sys.stderr,
                        )
                        return 2, ""
        if Path(words[0]).name == "git":
            sub, rest = _git_subcommand(words)
            if sub in _ASK or (sub == "reset" and "--hard" in rest):
                decision = {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "ask",
                        "permissionDecisionReason": (
                            f"git {sub} changes shared history: the owner decides"
                        ),
                    }
                }
                return 0, json.dumps(decision)
    return 0, ""


def main(argv: list[str]) -> int:
    command = argv[0] if argv else ""
    if command == "close-check" and os.environ.get("E_AGENT_HARNESS_UNATTENDED") != "1":
        return 0  # an attended Stop never runs the gate: return before spawning anything
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        payload = {}
    cwd = Path(payload.get("cwd") or os.getcwd())
    root = _repo_root(cwd.resolve() if cwd.exists() else cwd)
    if command == "bash-guard":
        if root is None or not (root / MANIFEST).is_file():
            return 0
        try:
            code, out = bash_guard(root, str((payload.get("tool_input") or {}).get("command", "")))
        except Exception as exc:  # a broken guard must not let a denied command through
            print(f"bash-guard error: {exc}", file=sys.stderr)
            return 2
        sys.stdout.write(out)
        return code
    if root is None:
        if _fails_closed(command):
            print(f"harness hook: no repository with {MANIFEST} above {cwd}", file=sys.stderr)
            return 2
        return 0
    try:
        proc = subprocess.run(
            [*_runner(root), *argv],
            input=raw,
            cwd=root,
            capture_output=True,
            text=True,
            timeout=TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        if _fails_closed(command):
            print(f"harness hook: could not run e-agent-harness: {exc}", file=sys.stderr)
            return 2
        return 0
    sys.stdout.write(proc.stdout)
    sys.stderr.write(proc.stderr)
    if proc.returncode not in (0, 2) and _fails_closed(command):
        return 2  # an unexpected failure of a guarding command still blocks
    return proc.returncode if proc.returncode in (0, 2) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
