"""Digest rule: a task pins the hash of every authoritative file.

``context_digest`` is sha256 over ``path + NUL + sha256(file bytes)`` for each
digest input in order: the authoritative files, then the active plan, then the
manifest itself. A renamed, reordered, edited or missing file changes the
digest and invalidates tasks materialised against the old one.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from e_agent_harness.manifest import MANIFEST_RELPATH, Manifest

MISSING = "missing"


def digest_inputs(m: Manifest) -> tuple[str, ...]:
    """Every file whose change invalidates a task, in digest order."""
    return (*m.authoritative.files, m.authoritative.active_plan, MANIFEST_RELPATH)


def context_digest(repo_root: Path, m: Manifest) -> str:
    outer = hashlib.sha256()
    for rel in digest_inputs(m):
        file = repo_root / rel
        inner = hashlib.sha256(file.read_bytes()).hexdigest() if file.is_file() else MISSING
        outer.update(rel.encode("utf-8"))
        outer.update(b"\0")
        outer.update(inner.encode("ascii"))
        outer.update(b"\n")
    return outer.hexdigest()


def is_stale(pinned_digest: str, repo_root: Path, m: Manifest) -> bool:
    """True when the authoritative files no longer match the digest a task pinned."""
    return context_digest(repo_root, m) != pinned_digest
