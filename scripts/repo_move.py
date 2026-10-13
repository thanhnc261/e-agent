"""Move code and documents to the Phase 1 layout and keep relative links working.

Subcommands:
  layout   git mv each distribution's code to src/e_agent/<part>, its tests to
           tests/unit/<part> and its pyproject.toml to dists/<name>/, where the
           uv_build sections are replaced by hatchling force-include ones.
  links    rewrite relative Markdown links after `layout` (--layout), or git mv
           documents into a folder and rewrite links to and from them (--move).
  check    report broken relative links and references to old paths.

archive/ and research/ are history and are never rewritten.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parent.parent
HATCHLING = "hatchling>=1.32,<2"
READ_ONLY = ("archive/", "research/")
# History or fixtures that name old paths on purpose; never reported as stale.
STALE_EXEMPT = (
    "archive/",
    "research/",
    "harness/state/",
    "scripts/repo_move.py",
    "tests/conformance/test_repo_move.py",
)
CACHE_PARTS = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
DROPPED_SECTIONS = {"build-system", "tool.uv.build-backend"}
_HEADER = re.compile(r"^\[([^\[\]]+)\]\s*$")
_INLINE_LINK = re.compile(r"(\]\()([^)\s]+)((?:\s+\"[^\"]*\")?\))")
_REFERENCE_LINK = re.compile(r"^(\s*\[[^\]]+\]:\s*)(\S+)(.*)$")
_SCHEME = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")
_FENCE = re.compile(r"^\s*(```|~~~)")


class MoveError(RuntimeError):
    pass


@dataclass(frozen=True)
class Move:
    old_root: str
    part: str

    @property
    def name(self) -> str:
        return Path(self.old_root).name

    @property
    def old_code(self) -> str:
        return f"{self.old_root}/src/e_agent/{self.part}"

    @property
    def new_code(self) -> str:
        return f"src/e_agent/{self.part}"

    @property
    def old_tests(self) -> str:
        return f"{self.old_root}/tests"

    @property
    def new_tests(self) -> str:
        return f"tests/unit/{self.part}"

    @property
    def old_config(self) -> str:
        return f"{self.old_root}/pyproject.toml"

    @property
    def new_config(self) -> str:
        return f"dists/{self.name}/pyproject.toml"


MOVES: tuple[Move, ...] = (
    Move("packages/contracts", "contracts"),
    Move("packages/plugin-sdk", "sdk"),
    Move("packages/kernel", "kernel"),
    Move("packages/domain-erp", "erp"),
    Move("packages/adapter-agent-pydantic", "adapters/pydantic_ai"),
    Move("packages/adapter-postgres", "adapters/postgres"),
    Move("packages/adapter-odoo", "adapters/odoo"),
    Move("packages/adapter-shacl", "adapters/shacl"),
    Move("packages/adapter-secretstore-local", "adapters/secretstore_local"),
    Move("apps/server", "server"),
)


@dataclass
class Report:
    broken_links: list[tuple[str, str]] = field(default_factory=list)
    stale_references: list[tuple[str, int, str]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.broken_links and not self.stale_references


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise MoveError(f"git {' '.join(args)}: {result.stderr.strip()}")
    return result.stdout


def _git_mv(root: Path, source: str, target: str) -> None:
    (root / target).parent.mkdir(parents=True, exist_ok=True)
    _git(root, "mv", source, target)


def _is_cache(rel: Path) -> bool:
    return bool(CACHE_PARTS.intersection(rel.parts)) or rel.suffix == ".pyc"


def _leftovers(root: Path, move: Move) -> list[str]:
    kept = (move.old_code + "/", move.old_tests + "/")
    found = []
    for path in sorted((root / move.old_root).rglob("*")):
        rel = path.relative_to(root)
        name = rel.as_posix()
        if path.is_dir() or name == move.old_config or name.startswith(kept) or _is_cache(rel):
            continue
        found.append(name)
    return found


def _remove_cache_tree(path: Path) -> None:
    """Remove a directory that holds only caches; anything else is an error."""
    if not path.exists():
        return
    for item in sorted(path.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        if item.is_dir():
            item.rmdir()  # deepest first, so only empty directories are left here
        elif _is_cache(item.relative_to(path)):
            item.unlink()
        else:
            raise MoveError(f"unexpected file left behind: {item}")
    path.rmdir()


def dist_pyproject(old_text: str, part: str) -> str:
    """Keep every table except the uv_build ones; add hatchling force-include."""
    kept: list[str] = []
    section = ""
    for line in old_text.splitlines():
        header = _HEADER.match(line)
        if header:
            section = header.group(1).strip()
        if section not in DROPPED_SECTIONS:
            kept.append(line)
    body = re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).rstrip()
    return (
        f"{body}\n\n"
        "[build-system]\n"
        f'requires = ["{HATCHLING}"]\n'
        'build-backend = "hatchling.build"\n\n'
        "[tool.hatch.build.targets.wheel]\n"
        'dev-mode-dirs = ["../../src"]\n\n'
        "[tool.hatch.build.targets.wheel.force-include]\n"
        f'"../../src/e_agent/{part}" = "e_agent/{part}"\n'
    )


def layout(root: Path, moves: Sequence[Move] = MOVES) -> None:
    for move in moves:
        if not (root / move.old_config).is_file():
            raise MoveError(f"missing {move.old_config}")
        for target in (move.new_code, move.new_tests, move.new_config):
            if (root / target).exists():
                raise MoveError(f"target exists: {target}")
    leftovers = [name for move in moves for name in _leftovers(root, move)]
    if leftovers:
        raise MoveError("files outside code, tests and config: " + ", ".join(leftovers))

    for move in moves:
        _git_mv(root, move.old_code, move.new_code)
        if (root / move.old_tests).is_dir():
            _git_mv(root, move.old_tests, move.new_tests)
        _git_mv(root, move.old_config, move.new_config)
        config = root / move.new_config
        config.write_text(
            dist_pyproject(config.read_text(encoding="utf-8"), move.part), encoding="utf-8"
        )
        _remove_cache_tree(root / move.old_root)

    for package in sorted({str(Path(m.new_tests).parent) for m in moves}):
        while package != "tests":
            init = root / package / "__init__.py"
            if not init.exists():
                init.write_text("", encoding="utf-8")
            package = str(Path(package).parent)
    _git(root, "add", "--", *(m.new_config for m in moves), "tests/unit")
    for old in sorted({Path(m.old_root).parts[0] for m in moves}):
        _remove_cache_tree(root / old)


def layout_mapping(moves: Sequence[Move] = MOVES) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for move in moves:
        mapping[move.old_code] = move.new_code
        mapping[move.old_tests] = move.new_tests
        mapping[move.old_config] = move.new_config
        mapping[move.old_root] = move.new_code
    return mapping


def _map(path: str, mapping: dict[str, str]) -> str:
    for old in sorted(mapping, key=len, reverse=True):
        if path == old or path.startswith(old + "/"):
            return mapping[old] + path[len(old) :]
    return path


def _tracked(root: Path, *patterns: str) -> list[str]:
    return sorted(_git(root, "ls-files", "-z", "--", *patterns).split("\0")[:-1])


def _unfenced_segments(text: str) -> Iterable[tuple[int, int, str]]:
    """Yield (line number, segment index, segment) outside code fences and code spans."""
    fenced = False
    for number, line in enumerate(text.split("\n"), start=1):
        if _FENCE.match(line):
            fenced = not fenced
            continue
        if fenced:
            continue
        for index, segment in enumerate(line.split("`")):
            if index % 2 == 0:
                yield number, index, segment


def _targets(segment: str) -> list[str]:
    targets = [m.group(2) for m in _INLINE_LINK.finditer(segment)]
    reference = _REFERENCE_LINK.match(segment)
    if reference:
        targets.append(reference.group(2))
    return targets


def _relative_path(target: str) -> str | None:
    if not target or target.startswith(("#", "/")) or _SCHEME.match(target):
        return None
    path = re.split(r"[#?]", target, maxsplit=1)[0]
    return path or None


def rewrite_links(root: Path, mapping: dict[str, str]) -> list[str]:
    """Rewrite relative links in tracked Markdown so they resolve after `mapping` moves."""
    inverse = {new: old for old, new in mapping.items()}
    changed = []
    for name in _tracked(root, "*.md"):
        if name.startswith(READ_ONLY):
            continue
        new_dir = os.path.dirname(name)
        old_dir = os.path.dirname(_map(name, inverse))

        def fix(target: str, new_dir: str = new_dir, old_dir: str = old_dir) -> str:
            path = _relative_path(target)
            if path is None:
                return target
            old_target = os.path.normpath(os.path.join(old_dir, unquote(path)))
            if old_target.startswith(".."):
                return target
            new_rel = os.path.relpath(_map(old_target, mapping), new_dir or ".")
            if path.endswith("/") and not new_rel.endswith("/"):
                new_rel += "/"
            current = os.path.normpath(os.path.join(new_dir, unquote(path)))
            if os.path.normpath(os.path.join(new_dir, new_rel)) == current:
                return target
            return new_rel + target[len(path) :]

        file = root / name
        text = file.read_text(encoding="utf-8")
        lines = text.split("\n")
        edits: dict[int, dict[int, str]] = {}
        for number, index, segment in _unfenced_segments(text):
            new = _INLINE_LINK.sub(lambda m: m.group(1) + fix(m.group(2)) + m.group(3), segment)
            new = _REFERENCE_LINK.sub(lambda m: m.group(1) + fix(m.group(2)) + m.group(3), new)
            if new != segment:
                edits.setdefault(number, {})[index] = new
        if not edits:
            continue
        for number, segments in edits.items():
            parts = lines[number - 1].split("`")
            for index, new in segments.items():
                parts[index] = new
            lines[number - 1] = "`".join(parts)
        file.write_text("\n".join(lines), encoding="utf-8")
        changed.append(name)
    return changed


def move_documents(root: Path, files: Sequence[str], folder: str) -> list[str]:
    mapping = {name: f"{folder}/{Path(name).name}" for name in files}
    for old, new in mapping.items():
        _git_mv(root, old, new)
    return rewrite_links(root, mapping)


def check(root: Path, moves: Sequence[Move] = MOVES, extra_old: Sequence[str] = ()) -> Report:
    report = Report()
    for name in _tracked(root, "*.md"):
        if name.startswith("archive/"):
            continue
        base = os.path.dirname(name)
        text = (root / name).read_text(encoding="utf-8")
        for _, _, segment in _unfenced_segments(text):
            for target in _targets(segment):
                path = _relative_path(target)
                if path and not (root / base / unquote(path)).exists():
                    report.broken_links.append((name, path))
    old = [m.old_root for m in moves] + list(extra_old)
    # A path starts the token or follows ./ or ../; ui/packages/... is a different tree.
    pattern = re.compile(
        r"(?:(?<![\w./-])|(?<=\./))(" + "|".join(re.escape(o) for o in old) + r")(?![\w-])"
    )
    for name in _tracked(root):
        if name.startswith(STALE_EXEMPT) or name.endswith(".md"):
            continue
        try:
            text = (root / name).read_text(encoding="utf-8")
        except (UnicodeDecodeError, FileNotFoundError, IsADirectoryError):
            continue
        for number, line in enumerate(text.splitlines(), start=1):
            for match in pattern.finditer(line):
                report.stale_references.append((name, number, match.group(1)))
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--root", type=Path, default=ROOT)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("layout")
    links = sub.add_parser("links")
    links.add_argument("--layout", action="store_true", help="rewrite after `layout`")
    links.add_argument("--move", nargs="+", default=[], help="documents to git mv")
    links.add_argument("--to", help="target folder for --move")
    checker = sub.add_parser("check")
    checker.add_argument("--old", nargs="*", default=[], help="more old paths to report")
    args = parser.parse_args(argv)
    root: Path = args.root.resolve()

    if args.command == "layout":
        layout(root)
        print(f"moved {len(MOVES)} distributions; run `links --layout` next")
        return 0
    if args.command == "links":
        if args.move:
            if not args.to:
                parser.error("--move needs --to")
            changed = move_documents(root, args.move, args.to.rstrip("/"))
        elif args.layout:
            changed = rewrite_links(root, layout_mapping())
        else:
            parser.error("links needs --layout or --move")
        print(f"rewrote links in {len(changed)} files")
        for name in changed:
            print(f"  {name}")
        return 0
    report = check(root, MOVES, args.old)
    for name, target in report.broken_links:
        print(f"broken link: {name}: {target}")
    for name, number, old in report.stale_references:
        print(f"old path: {name}:{number}: {old}")
    print(
        f"{len(report.broken_links)} broken links, "
        f"{len(report.stale_references)} old-path references"
    )
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
