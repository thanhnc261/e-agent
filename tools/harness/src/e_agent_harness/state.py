"""Harness state on disk: paths, JSON helpers, the active task pointer, repository root."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from e_agent_harness.manifest import MANIFEST_RELPATH

STATE_DIR = "harness/state"
# Paths a task may change besides its own scope: harness bookkeeping and handoffs.
BOOKKEEPING_COMMITTED: tuple[str, ...] = ("harness/state/**", "docs/handoffs/**")
# Also bookkeeping for the evidence-to-HEAD rule: the legacy local evidence folder.
BOOKKEEPING: tuple[str, ...] = (*BOOKKEEPING_COMMITTED, "evidence/**")


def find_repo_root(start: Path) -> Path:
    """The nearest ancestor holding the manifest, else the git top level."""
    for candidate in (start, *start.parents):
        if (candidate / MANIFEST_RELPATH).is_file():
            return candidate
    proc = subprocess.run(
        ["git", "-C", str(start), "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode == 0 and proc.stdout.strip():
        return Path(proc.stdout.strip())
    raise ValueError(f"no repository with {MANIFEST_RELPATH} above {start}")


@dataclass(frozen=True)
class Paths:
    repo_root: Path

    @property
    def manifest(self) -> Path:
        return self.repo_root / MANIFEST_RELPATH

    @property
    def state(self) -> Path:
        return self.repo_root / STATE_DIR

    @property
    def active(self) -> Path:
        return self.state / "active.json"

    @property
    def progress(self) -> Path:
        return self.state / "progress.md"

    def features(self, phase: str) -> Path:
        return self.state / phase / "features.json"

    def task(self, phase: str, task_id: str) -> Path:
        return self.state / phase / "tasks" / f"{task_id}.json"

    def handoff(self, phase: str, task_id: str) -> Path:
        return self.state / phase / "handoffs" / f"{task_id}.json"

    def evidence(self, task_id: str) -> Path:
        # Committed with the bookkeeping, so a fresh clone can close the task (HP-4).
        return self.state / "evidence" / "gates" / task_id

    @property
    def live_evidence(self) -> Path:
        return self.state / "evidence" / "live"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, doc: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_active(paths: Paths) -> dict[str, Any] | None:
    if not paths.active.is_file():
        return None
    doc = read_json(paths.active)
    return doc if isinstance(doc, dict) else None


def save_active(paths: Paths, phase: str, task_id: str | None) -> None:
    write_json(paths.active, {"phase": phase, "task": task_id})


def load_task(paths: Paths) -> tuple[dict[str, Any], Path] | None:
    """The active task contract and its path, or None when no task is active."""
    active = load_active(paths)
    if not active or not active.get("task"):
        return None
    path = paths.task(str(active["phase"]), str(active["task"]))
    if not path.is_file():
        return None
    doc = read_json(path)
    return (doc, path) if isinstance(doc, dict) else None
