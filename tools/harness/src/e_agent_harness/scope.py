"""Scope decisions: which paths a task may change, as a tree check and as a hook."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from e_agent_harness import gitinfo, state
from e_agent_harness.manifest import (
    Manifest,
    is_create_only,
    is_protected,
    normalize_relpath,
    path_matches,
)

EDIT_TOOLS = ("Edit", "Write", "NotebookEdit")


def deny_reason(
    contract: dict[str, Any] | None, m: Manifest, relpath: str, *, new_file: bool = False
) -> str | None:
    if "\\" in relpath:
        return f"{relpath}: path contains a backslash; refusing an ambiguous path"
    norm = normalize_relpath(relpath)
    if _protected(m, norm) and not (new_file and _create_only(m, norm)):
        return f"{norm}: protected path (read-only)"
    if contract is None:
        return None
    if not any(path_matches(norm, p) for p in contract["allowed_paths"]):
        return f"{norm}: outside the task's allowed paths"
    return None


def _protected(m: Manifest, norm: str) -> bool:
    # Case-folded as well: on a case-insensitive file system Archive/x is archive/x.
    return is_protected(m, norm) or any(
        path_matches(norm.casefold(), p.casefold()) for p in m.protected.read_only
    )


def _create_only(m: Manifest, norm: str) -> bool:
    return is_create_only(m, norm) or any(
        path_matches(norm.casefold(), p.casefold()) for p in m.protected.create_only
    )


def changed_paths(contract: dict[str, Any] | None, repo_root: Path) -> set[str]:
    """Working-tree changes, plus everything committed since the task's base commit."""
    changed = set(gitinfo.status_files(repo_root))
    if contract is not None:
        changed.update(gitinfo.diff_names(repo_root, contract["base_commit"]))
    return changed


def check_tree(contract: dict[str, Any] | None, m: Manifest, repo_root: Path) -> list[str]:
    changed = changed_paths(contract, repo_root)
    base = str(contract["base_commit"]) if contract else "HEAD"
    problems = [
        r
        for r in (
            deny_reason(
                contract,
                m,
                p,
                new_file=_protected(m, normalize_relpath(p)) and _is_new(repo_root, base, p),
            )
            for p in sorted(changed)
        )
        if r
    ]
    normalized = {normalize_relpath(p) for p in changed}
    needs_bump = any(path_matches(p, pat) for p in normalized for pat in m.protected.bump_required)
    if needs_bump and normalize_relpath(m.protected.bump_file) not in normalized:
        problems.append(
            f"{m.protected.bump_file}: must change when files under "
            f"{', '.join(m.protected.bump_required)} change"
        )
    return problems


def _is_new(repo_root: Path, base: str, relpath: str) -> bool:
    """Not tracked at the task's base (or at HEAD without a task): created by this work.

    Only a confirmed absence counts: an unknown base (a shallow clone, a rewritten
    history) never makes a protected path writable.
    """
    if not gitinfo.commit_exists(repo_root, base):
        return False
    norm = normalize_relpath(relpath)
    try:
        if gitinfo.exists_at(repo_root, base, norm):
            return False
        # A case variant of a tracked file is that file on a case-insensitive file system.
        return norm.casefold() not in gitinfo.tracked_casefold(repo_root, base)
    except gitinfo.GitLookupError:
        return False


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
    base = str(contract["base_commit"]) if contract else "HEAD"
    new_file = _protected(m, normalize_relpath(rel)) and _is_new(repo_root, base, rel)
    reason = deny_reason(contract, m, rel, new_file=new_file)
    return (2, reason) if reason else (0, "")
