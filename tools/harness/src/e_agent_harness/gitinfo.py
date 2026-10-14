"""Thin git wrappers. Every function takes the repository root and shells out once."""

from __future__ import annotations

import subprocess
from pathlib import Path


def git(root: Path, *args: str, strip: bool = True) -> str:
    proc = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, check=True
    )
    return proc.stdout.strip() if strip else proc.stdout


def head_sha(root: Path) -> str:
    return git(root, "rev-parse", "HEAD")


def branch(root: Path) -> str:
    return git(root, "rev-parse", "--abbrev-ref", "HEAD")


def status_files(root: Path) -> list[str]:
    """Changed, staged and untracked paths, exactly as named (NUL-separated, no renames)."""
    out = git(
        root,
        "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=all",
        "--no-renames",
        strip=False,
    )
    return sorted({entry[3:] for entry in out.split("\0") if len(entry) > 3})


def is_clean(root: Path) -> bool:
    return not status_files(root)


def diff_names(root: Path, base: str, head: str = "HEAD") -> list[str]:
    """Paths changed on ``head`` since its merge base with ``base`` (three-dot diff),
    so upstream commits merged into a task branch are not attributed to the task."""
    out = git(root, "diff", "--name-only", "-z", "--no-renames", f"{base}...{head}", strip=False)
    return sorted(name for name in out.split("\0") if name)


def commit_exists(root: Path, rev: str) -> bool:
    proc = subprocess.run(
        ["git", "-C", str(root), "cat-file", "-e", f"{rev}^{{commit}}"],
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode == 0


class GitLookupError(RuntimeError):
    """git could not answer: missing objects, a bad revision, a broken repository."""


def exists_at(root: Path, rev: str, path: str) -> bool:
    """True when ``path`` is tracked in commit ``rev``; GitLookupError when git cannot tell."""
    proc = subprocess.run(
        ["git", "-C", str(root), "ls-tree", "-z", "--name-only", rev, "--", path],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise GitLookupError(proc.stderr.strip() or f"git ls-tree {rev} failed")
    return bool(proc.stdout.strip("\0"))


def is_ancestor(root: Path, ancestor: str, descendant: str) -> bool:
    proc = subprocess.run(
        ["git", "-C", str(root), "merge-base", "--is-ancestor", ancestor, descendant],
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode == 0
