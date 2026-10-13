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

import json
import os
import subprocess
import sys
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
