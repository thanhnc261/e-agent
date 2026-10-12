"""Thin git wrappers. Every function takes the repository root and shells out once."""

from __future__ import annotations

import subprocess
from pathlib import Path


def git(root: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, check=True
    )
    return proc.stdout.strip()


def head_sha(root: Path) -> str:
    return git(root, "rev-parse", "HEAD")


def branch(root: Path) -> str:
    return git(root, "rev-parse", "--abbrev-ref", "HEAD")


def status_files(root: Path) -> list[str]:
    """Changed, staged and untracked paths (renames report the new path)."""
    files: list[str] = []
    for line in git(root, "status", "--porcelain", "--untracked-files=all").splitlines():
        path = line[3:]
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        files.append(path.strip('"'))
    return sorted(set(files))


def is_clean(root: Path) -> bool:
    return not status_files(root)


def diff_names(root: Path, base: str, head: str = "HEAD") -> list[str]:
    out = git(root, "diff", "--name-only", f"{base}..{head}")
    return sorted(line for line in out.splitlines() if line)


def is_ancestor(root: Path, ancestor: str, descendant: str) -> bool:
    proc = subprocess.run(
        ["git", "-C", str(root), "merge-base", "--is-ancestor", ancestor, descendant],
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode == 0
