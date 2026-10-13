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
E_AGENT_HARNESS_UNATTENDED=1; ``status``, ``checkpoint`` and ``format`` never block.
"""

from __future__ import annotations

import contextlib
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


def _runner(root: Path, tool: str) -> list[str]:
    if (root / "pyproject.toml").is_file():
        return ["uv", "run", "--quiet", "--directory", str(root), tool]
    module = "e_agent_harness.cli" if tool == "e-agent-harness" else tool
    return [sys.executable, "-m", module]


def _format(root: Path, payload: dict) -> int:
    path = (payload.get("tool_input") or {}).get("file_path") or ""
    target = Path(path) if Path(path).is_absolute() else root / path
    if target.suffix != ".py" or not target.is_file():
        return 0
    # Formatting is a convenience; the gate catches what it misses.
    with contextlib.suppress(OSError, subprocess.SubprocessError):
        subprocess.run(
            [*_runner(root, "ruff"), "format", "--quiet", str(target)],
            cwd=root,
            capture_output=True,
            timeout=TIMEOUT,
            check=False,
        )
    return 0


def main(argv: list[str]) -> int:
    command = argv[0] if argv else ""
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
    if command == "format":
        return _format(root, payload)
    try:
        proc = subprocess.run(
            [*_runner(root, "e-agent-harness"), *argv],
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
