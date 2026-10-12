"""Scope decisions: which paths a task may change, as a tree check and as a hook."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from e_agent_harness import gitinfo, state
from e_agent_harness.manifest import Manifest, is_protected, normalize_relpath, path_matches

EDIT_TOOLS = ("Edit", "Write", "NotebookEdit")


def deny_reason(contract: dict[str, Any] | None, m: Manifest, relpath: str) -> str | None:
    norm = normalize_relpath(relpath)
    if is_protected(m, norm):
        return f"{norm}: protected path (read-only)"
    if contract is None:
        return None
    if not any(path_matches(norm, p) for p in contract["allowed_paths"]):
        return f"{norm}: outside the task's allowed paths"
    return None


def check_tree(contract: dict[str, Any] | None, m: Manifest, repo_root: Path) -> list[str]:
    changed = set(gitinfo.status_files(repo_root))
    if contract is not None:
        changed.update(gitinfo.diff_names(repo_root, contract["base_commit"]))
    problems = [r for r in (deny_reason(contract, m, p) for p in sorted(changed)) if r]
    normalized = {normalize_relpath(p) for p in changed}
    needs_bump = any(path_matches(p, pat) for p in normalized for pat in m.protected.bump_required)
    if needs_bump and normalize_relpath(m.protected.bump_file) not in normalized:
        problems.append(
            f"{m.protected.bump_file}: must change when files under "
            f"{', '.join(m.protected.bump_required)} change"
        )
    return problems


Resolver = Callable[[Path], tuple[Manifest, dict[str, Any] | None]]


def hook_decision(payload: dict[str, Any], resolve: Resolver) -> tuple[int, str]:
    """(exit code, reason). 2 denies. Only edit tools are judged."""
    if payload.get("tool_name") not in EDIT_TOOLS:
        return 0, ""
    tool_input = payload.get("tool_input") or {}
    raw = tool_input.get("file_path") or tool_input.get("notebook_path")
    if not raw:
        return 0, ""
    cwd = Path(payload.get("cwd") or Path.cwd())
    try:
        repo_root = state.find_repo_root(cwd).resolve()
    except ValueError as exc:
        return 2, str(exc)
    target = (Path(raw) if Path(raw).is_absolute() else cwd / raw).resolve()
    try:
        rel = target.relative_to(repo_root).as_posix()
    except ValueError:
        return 2, f"{target}: outside the repository {repo_root}"
    m, contract = resolve(repo_root)
    reason = deny_reason(contract, m, rel)
    return (2, reason) if reason else (0, "")
