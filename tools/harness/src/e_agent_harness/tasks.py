"""Materialise a task contract from the phase feature list (harness plan H2, new-task)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from e_agent_harness import contracts, gitinfo, state
from e_agent_harness.digest import context_digest
from e_agent_harness.manifest import Manifest

IMPLICIT_PATHS: tuple[str, ...] = ("harness/state/**", "docs/handoffs/**")


def materialise(
    paths: state.Paths,
    m: Manifest,
    repo_root: Path,
    *,
    phase: str,
    task_id: str,
    feature_ids: Sequence[str],
    allowed_paths: Sequence[str],
    acceptance: Sequence[str],
    gate_set: str,
    now: datetime,
) -> dict[str, Any]:
    features_path = paths.features(phase)
    if not features_path.is_file():
        raise ValueError(f"feature list missing: {features_path.relative_to(repo_root)}")
    entries = {e["id"]: e for e in state.read_json(features_path)["entries"]}
    unknown = [f for f in feature_ids if f not in entries]
    if unknown:
        raise ValueError(f"unknown feature id(s): {', '.join(unknown)}")
    steps = list(acceptance) or [step for f in feature_ids for step in entries[f]["steps"]]
    task_path = paths.task(phase, task_id)
    previous: dict[str, Any] = state.read_json(task_path) if task_path.is_file() else {}
    contract: dict[str, Any] = {
        "id": task_id,
        "phase": phase,
        "plan_ref": m.authoritative.active_plan,
        "feature_ids": list(feature_ids),
        "context_digest": context_digest(repo_root, m),
        "allowed_paths": [*allowed_paths, *IMPLICIT_PATHS, m.authoritative.active_plan],
        "acceptance": steps,
        "gate_set": gate_set,
        # Re-materialising the same task keeps its base and birth: the scope check
        # must still see every commit made since the task started.
        "base_commit": previous.get("base_commit") or gitinfo.head_sha(repo_root),
        "created_at": previous.get("created_at") or now.isoformat(timespec="seconds"),
    }
    problems = contracts.validate("task", contract)
    if problems:
        raise ValueError("task contract invalid: " + "; ".join(problems))
    state.write_json(task_path, contract)
    state.save_active(paths, phase, task_id)
    return contract
