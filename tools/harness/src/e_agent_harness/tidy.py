"""tidy: format and lint the whole change once, before the commit (harness H4.6).

The change is the working tree plus everything committed since the open task's base
commit. Python files in it get ``ruff check --fix`` and ``ruff format``; a change
under ``ui/`` runs the UI's scoped formatter. The gate stays the check; tidy only
saves a round trip.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

from e_agent_harness import scope

RUFF = (sys.executable, "-m", "ruff")


def _run(args: list[str], root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=root, capture_output=True, text=True, check=False)


def _ui_scope(repo_root: Path) -> list[str]:
    scope_file = repo_root / "ui" / ".prettierscope"
    if not scope_file.is_file():
        return []
    lines = (line.strip() for line in scope_file.read_text().splitlines())
    return [line.rstrip("/") for line in lines if line and not line.startswith("#")]


def _in_scope(path: str, entries: list[str]) -> bool:
    return any(path == e or path.startswith(e + "/") for e in entries)


def _tail(result: subprocess.CompletedProcess[str]) -> str:
    text = (result.stderr or result.stdout or "").strip().splitlines()
    return " | ".join(text[-3:])


def tidy(contract: dict[str, Any] | None, repo_root: Path) -> tuple[int, list[str]]:
    """(exit code, report lines). Exit 1 when a tool failed or lint errors remain."""
    changed = scope.changed_paths(contract, repo_root)
    python = sorted(p for p in changed if p.endswith(".py") and (repo_root / p).is_file())
    ui_files: list[str] = []
    if (repo_root / "ui" / "package.json").is_file():
        entries = _ui_scope(repo_root)
        ui_files = sorted(
            p.removeprefix("ui/")
            for p in changed
            if p.startswith("ui/")
            and (repo_root / p).is_file()
            and _in_scope(p.removeprefix("ui/"), entries)
        )
    if not python and not ui_files:
        return 0, ["nothing to tidy"]
    report: list[str] = []
    code = 0
    if python:
        # --force-exclude keeps the configured exclusions for explicitly named files.
        fixed = _run([*RUFF, "check", "--fix", "--force-exclude", "--quiet", *python], repo_root)
        if fixed.returncode not in (0, 1):  # 1 = violations remain, reported below
            code = 1
            report.append(f"ruff check --fix failed: {_tail(fixed)}")
        formatted = _run([*RUFF, "format", "--force-exclude", "--quiet", *python], repo_root)
        if formatted.returncode != 0:
            code = 1
            report.append(f"ruff format failed: {_tail(formatted)}")
        left = _run(
            [*RUFF, "check", "--force-exclude", "--output-format", "concise", *python], repo_root
        )
        noun = "file" if len(python) == 1 else "files"
        report.append(f"tidied {len(python)} Python {noun}")
        if left.returncode:
            code = 1
            report += [line for line in left.stdout.splitlines() if ": " in line]
    if ui_files:
        # Only changed files inside the migrated Prettier scope: nothing unrelated moves.
        result = _run(["pnpm", "--dir", "ui", "format", *ui_files], repo_root)
        if result.returncode == 0:
            report.append(f"formatted {len(ui_files)} UI file(s)")
        else:
            code = 1
            report.append(f"UI format failed: {_tail(result)}")
    return code, report
