"""Materialise a task contract from the phase feature list (harness plan H2, new-task)."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from e_agent_harness import contracts, gitinfo, state
from e_agent_harness.digest import context_digest
from e_agent_harness.manifest import Manifest

IMPLICIT_PATHS: tuple[str, ...] = state.BOOKKEEPING_COMMITTED


def features_digest(entries: Mapping[str, Any], feature_ids: Sequence[str]) -> str:
    """Hash of what the contract's acceptance was derived from: each feature's text and steps."""
    pinned = [
        {"id": f, "description": entries[f]["description"], "steps": entries[f]["steps"]}
        for f in feature_ids
        if f in entries
    ]
    return hashlib.sha256(json.dumps(pinned, sort_keys=True).encode()).hexdigest()


def _entries(paths: state.Paths, phase: str) -> dict[str, Any]:
    path = paths.features(phase)
    return {e["id"]: e for e in state.read_json(path)["entries"]} if path.is_file() else {}


def acceptance_drift(paths: state.Paths, contract: Mapping[str, Any]) -> bool:
    """True when the feature entries changed after the contract was materialised (HP-8)."""
    pinned = contract.get("features_digest")
    if not pinned:
        return False
    current = features_digest(_entries(paths, str(contract["phase"])), contract["feature_ids"])
    return bool(current != pinned)


def _write(paths: state.Paths, contract: dict[str, Any]) -> dict[str, Any]:
    problems = contracts.validate("task", contract)
    if problems:
        raise ValueError("task contract invalid: " + "; ".join(problems))
    state.write_json(paths.task(str(contract["phase"]), str(contract["id"])), contract)
    return contract


def _active(paths: state.Paths) -> dict[str, Any]:
    loaded = state.load_task(paths)
    if loaded is None:
        raise ValueError("no active task")
    return loaded[0]


def refresh(
    paths: state.Paths, m: Manifest, repo_root: Path, *, from_features: bool
) -> dict[str, Any]:
    """New context and feature digests for the active task; base, birth and scope are kept."""
    contract = _active(paths)
    entries = _entries(paths, str(contract["phase"]))
    contract["context_digest"] = context_digest(repo_root, m)
    contract["features_digest"] = features_digest(entries, contract["feature_ids"])
    if from_features:
        contract["acceptance"] = [
            step for f in contract["feature_ids"] for step in entries.get(f, {}).get("steps", [])
        ]
    return _write(paths, contract)


def amend_scope(paths: state.Paths, glob: str, reason: str, now: datetime) -> dict[str, Any]:
    """Add one allowed path to the active task, recording why (HP-11)."""
    contract = _active(paths)
    if glob not in contract["allowed_paths"]:
        contract["allowed_paths"].append(glob)
    contract.setdefault("scope_changes", []).append(
        {"glob": glob, "reason": reason, "at": now.isoformat(timespec="seconds")}
    )
    return _write(paths, contract)


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
    if gate_set not in m.gates:
        raise ValueError(f"unknown gate set: {gate_set} (have {', '.join(sorted(m.gates))})")
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
        "allowed_paths": list(
            dict.fromkeys(
                [
                    *allowed_paths,
                    *(c["glob"] for c in previous.get("scope_changes", [])),
                    *IMPLICIT_PATHS,
                    m.authoritative.active_plan,
                ]
            )
        ),
        "acceptance": steps,
        "gate_set": gate_set,
        # Re-materialising the same task keeps its base and birth: the scope check
        # must still see every commit made since the task started.
        "base_commit": previous.get("base_commit") or gitinfo.head_sha(repo_root),
        "created_at": previous.get("created_at") or now.isoformat(timespec="seconds"),
        "features_digest": features_digest(entries, feature_ids),
    }
    if previous.get("scope_changes"):
        contract["scope_changes"] = previous["scope_changes"]
    _write(paths, contract)
    state.save_active(paths, phase, task_id)
    return contract
