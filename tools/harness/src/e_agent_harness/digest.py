"""Digest rule: a task pins the hash of every authoritative file.

``context_digest`` is sha256 over ``path + NUL + sha256(file bytes)`` for each
authoritative file in manifest order, so a renamed, reordered or edited file
changes the digest and invalidates tasks materialised against the old one.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from e_agent_harness.manifest import Manifest


def context_digest(repo_root: Path, m: Manifest) -> str:
    outer = hashlib.sha256()
    for rel in m.authoritative.files:
        inner = hashlib.sha256((repo_root / rel).read_bytes()).hexdigest()
        outer.update(rel.encode("utf-8"))
        outer.update(b"\0")
        outer.update(inner.encode("ascii"))
        outer.update(b"\n")
    return outer.hexdigest()


def is_stale(pinned_digest: str, repo_root: Path, m: Manifest) -> bool:
    """True when the authoritative files no longer match the digest a task pinned."""
    return context_digest(repo_root, m) != pinned_digest
