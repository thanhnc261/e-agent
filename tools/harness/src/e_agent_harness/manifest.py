"""Context manifest: the authoritative files, protected paths, boundaries and gates.

The manifest is ``harness/context.toml`` at the repository root. Everything here
is a pure function over that file and the repository tree.
"""

from __future__ import annotations

import fnmatch
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

HEADING = re.compile(r"^##\s+(.+?)\s*$", re.M)


@dataclass(frozen=True)
class Authoritative:
    files: tuple[str, ...]
    active_plan: str
    active_plan_required_sections: tuple[str, ...]


@dataclass(frozen=True)
class Protected:
    read_only: tuple[str, ...]
    bump_required: tuple[str, ...]
    bump_file: str
    secrets: tuple[str, ...]


@dataclass(frozen=True)
class Environment:
    allowed_containers: tuple[str, ...]
    denied_containers: tuple[str, ...]
    denied_paths: tuple[str, ...]


@dataclass(frozen=True)
class Status:
    token_budget: int
    language_order: tuple[str, ...]


@dataclass(frozen=True)
class Manifest:
    authoritative: Authoritative
    protected: Protected
    environment: Environment
    gates: dict[str, tuple[str, ...]] = field(default_factory=dict)
    roles: dict[str, str] = field(default_factory=dict)
    status: Status = Status(token_budget=1500, language_order=("en",))


def _strs(raw: Any, key: str) -> tuple[str, ...]:
    value = raw.get(key, [])
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ValueError(f"manifest: {key} must be a list of strings")
    return tuple(value)


def load_manifest(path: Path) -> Manifest:
    with path.open("rb") as fh:
        raw = tomllib.load(fh)
    auth = raw["authoritative"]
    prot = raw.get("protected", {})
    env = raw.get("environment", {})
    status = raw.get("status", {})
    return Manifest(
        authoritative=Authoritative(
            files=_strs(auth, "files"),
            active_plan=str(auth["active_plan"]),
            active_plan_required_sections=_strs(auth, "active_plan_required_sections"),
        ),
        protected=Protected(
            read_only=_strs(prot, "read_only"),
            bump_required=_strs(prot, "bump_required"),
            bump_file=str(prot.get("bump_file", "")),
            secrets=_strs(prot, "secrets"),
        ),
        environment=Environment(
            allowed_containers=_strs(env, "allowed_containers"),
            denied_containers=_strs(env, "denied_containers"),
            denied_paths=_strs(env, "denied_paths"),
        ),
        gates={name: _strs(raw.get("gates", {}), name) for name in raw.get("gates", {})},
        roles={k: str(v) for k, v in raw.get("roles", {}).items()},
        status=Status(
            token_budget=int(status.get("token_budget", 1500)),
            language_order=tuple(status.get("language_order", ["en"])),
        ),
    )


def validate_manifest(m: Manifest, repo_root: Path) -> list[str]:
    """Return the problems that make the manifest unusable on this checkout."""
    problems: list[str] = []
    for rel in m.authoritative.files:
        if not (repo_root / rel).is_file():
            problems.append(f"authoritative file missing: {rel}")
    plan = repo_root / m.authoritative.active_plan
    if not plan.is_file():
        problems.append(f"active plan missing: {m.authoritative.active_plan}")
    else:
        headings = set(HEADING.findall(plan.read_text(encoding="utf-8")))
        for section in m.authoritative.active_plan_required_sections:
            if section not in headings:
                problems.append(
                    f"active plan {m.authoritative.active_plan} lacks section: {section}"
                )
    for group, patterns in (
        ("protected.read_only", m.protected.read_only),
        ("protected.bump_required", m.protected.bump_required),
        ("protected.secrets", m.protected.secrets),
        ("environment.denied_paths", m.environment.denied_paths),
        ("environment.allowed_containers", m.environment.allowed_containers),
        ("environment.denied_containers", m.environment.denied_containers),
    ):
        for pattern in patterns:
            if not pattern or pattern != pattern.strip() or any(c.isspace() for c in pattern):
                problems.append(f"{group}: malformed pattern {pattern!r}")
    if m.protected.bump_required and not (repo_root / m.protected.bump_file).is_file():
        problems.append(f"protected.bump_file missing: {m.protected.bump_file}")
    for name, commands in m.gates.items():
        if not commands:
            problems.append(f"gates.{name}: empty command list")
    return problems


def _glob_match(path: str, pattern: str) -> bool:
    """``**`` matches across directories; ``*`` matches within one segment."""
    regex = _glob_regex(pattern)
    return re.fullmatch(regex, PurePosixPath(path).as_posix()) is not None


def _glob_regex(pattern: str) -> str:
    out = []
    i = 0
    while i < len(pattern):
        c = pattern[i]
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif c == "*":
            out.append("[^/]*")
            i += 1
        elif c == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(c))
            i += 1
    return "".join(out)


def is_protected(m: Manifest, path: str) -> bool:
    """True when the repository-relative path is read-only under the manifest."""
    return any(_glob_match(path, p) for p in m.protected.read_only)


def container_allowed(m: Manifest, name: str) -> bool:
    """Deny wins; otherwise the container must match an allowed pattern."""
    if any(fnmatch.fnmatchcase(name, p) for p in m.environment.denied_containers):
        return False
    return any(fnmatch.fnmatchcase(name, p) for p in m.environment.allowed_containers)
