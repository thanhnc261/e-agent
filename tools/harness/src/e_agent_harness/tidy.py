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


def tidy(contract: dict[str, Any] | None, repo_root: Path) -> tuple[int, list[str]]:
    """(exit code, report lines). Exit 1 when lint errors remain that ruff cannot fix."""
    changed = scope.changed_paths(contract, repo_root)
    python = sorted(p for p in changed if p.endswith(".py") and (repo_root / p).is_file())
    ui = any(p.startswith("ui/") for p in changed) and (repo_root / "ui/package.json").is_file()
    if not python and not ui:
        return 0, ["nothing to tidy"]
    report: list[str] = []
    code = 0
    if python:
        # --force-exclude keeps the configured exclusions for explicitly named files.
        _run([*RUFF, "check", "--fix", "--force-exclude", "--quiet", *python], repo_root)
        _run([*RUFF, "format", "--force-exclude", "--quiet", *python], repo_root)
        left = _run(
            [*RUFF, "check", "--force-exclude", "--output-format", "concise", *python], repo_root
        )
        noun = "file" if len(python) == 1 else "files"
        report.append(f"tidied {len(python)} Python {noun}")
        if left.returncode:
            code = 1
            report += [line for line in left.stdout.splitlines() if ": " in line]
    if ui:
        result = _run(["pnpm", "--dir", "ui", "format"], repo_root)
        report.append("formatted the UI scope" if result.returncode == 0 else "UI format failed")
        code = code or (0 if result.returncode == 0 else 1)
    return code, report
