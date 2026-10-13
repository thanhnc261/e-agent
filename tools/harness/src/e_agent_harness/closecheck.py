"""Close ritual checks (harness plan H2, close-check and handoff)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from e_agent_harness import contracts, gitinfo, progress, state, tasks
from e_agent_harness.manifest import Manifest, path_matches

BOOKKEEPING: tuple[str, ...] = state.BOOKKEEPING


def _is_bookkeeping(path: str) -> bool:
    return any(path_matches(path, pattern) for pattern in BOOKKEEPING)


def evidence_ties_to_head(
    repo_root: Path, evidence: dict[str, Any], task_id: str | None = None
) -> str | None:
    if task_id is not None and evidence.get("task") != task_id:
        return f"evidence recorded for task {evidence.get('task')}, not {task_id}"
    if not evidence.get("ok"):
        return "evidence is from a failed gate; fix the failure and run the gate again"
    if not evidence.get("clean_tree"):
        return "evidence was recorded on a dirty tree; commit first, then run the gate again"
    commit = str(evidence.get("commit", ""))
    head = gitinfo.head_sha(repo_root)
    if commit == head:
        return None
    if not gitinfo.is_ancestor(repo_root, commit, head):
        return f"evidence commit {commit[:7]} is not an ancestor of HEAD {head[:7]}"
    code_changes = [
        p for p in gitinfo.diff_names(repo_root, commit, head) if not _is_bookkeeping(p)
    ]
    if code_changes:
        return f"code changed after evidence {commit[:7]}: {', '.join(code_changes)}"
    return None


def handoff_problems(paths: state.Paths, repo_root: Path, phase: str, task_id: str) -> list[str]:
    path = paths.handoff(phase, task_id)
    if not path.is_file():
        return [f"handoff missing: {path.relative_to(repo_root)}"]
    doc = state.read_json(path)
    problems = [f"handoff {p}" for p in contracts.validate("handoff", doc)]
    if not problems:
        for ref in doc.get("evidence_refs", []):
            if not (repo_root / ref).is_file():
                problems.append(f"handoff evidence ref missing: {ref}")
    return problems


def problems(
    paths: state.Paths, m: Manifest, repo_root: Path, *, session: str | None = None
) -> list[str]:
    loaded = state.load_task(paths)
    if loaded is None:
        return ["no active task"]
    contract, _ = loaded
    task_id, phase = str(contract["id"]), str(contract["phase"])
    found: list[str] = []
    if not gitinfo.is_clean(repo_root):
        found.append("working tree is not clean")
    if tasks.acceptance_drift(paths, contract):
        found.append(
            "acceptance changed since the task was materialised; "
            "run e-agent-harness refresh-task --from-features"
        )
    entries = (
        progress.parse_progress(paths.progress.read_text(encoding="utf-8"))
        if paths.progress.is_file()
        else []
    )
    last = entries[-1] if entries else None
    if last is None or last.task != task_id:
        found.append(f"progress log has no entry for task {task_id}")
    elif session and last.session != session:
        found.append(f"last progress entry is not from session {session}")
    features_path = paths.features(phase)
    entries_by_id: dict[str, Any] = (
        {e["id"]: e for e in state.read_json(features_path)["entries"]}
        if features_path.is_file()
        else {}
    )
    for fid in contract["feature_ids"]:
        feature = entries_by_id.get(fid)
        if not feature or not feature.get("passes"):
            continue
        ref = feature.get("evidence")
        if not ref:
            found.append(f"feature {fid} passes without an evidence reference")
            continue
        evidence_file = repo_root / ref
        if not evidence_file.is_file():
            found.append(f"feature {fid}: evidence missing: {ref}")
            continue
        reason = evidence_ties_to_head(repo_root, state.read_json(evidence_file), task_id)
        if reason:
            found.append(f"feature {fid}: {reason}")
    found.extend(handoff_problems(paths, repo_root, phase, task_id))
    return found
