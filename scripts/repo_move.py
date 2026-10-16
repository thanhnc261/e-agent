"""Move code and documents to the Phase 1 layout and keep relative links working.

Subcommands:
  layout   git mv each distribution's code to src/e_agent/<part>, its tests to
           tests/unit/<part> and its pyproject.toml to dists/<name>/, where the
           uv_build sections are replaced by a hatchling build that takes the
           package sub-tree from src/ through the shared dists/_hooks hook.
           `layout --set plugins` instead moves the ERP domain pack and the Odoo
           adapter under src/e_agent/plugins/erp (ADR 0026, Task 1d.9) and
           rewrites their module paths in tracked code and config.
  links    rewrite relative Markdown links after `layout` (--layout), or git mv
           documents into a folder and rewrite links to and from them (--move).
  check    report broken relative links and references to old paths; --docs also
           fails on old paths named in current (non-history) Markdown.
           `check --set plugins` reports the old plugin module paths instead.

archive/ and research/ are history and are never rewritten.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parent.parent
HATCHLING = "hatchling>=1.32,<2"
HOOK_PATH = "dists/_hooks/src_tree.py"
HOOK = '''"""Hatch build hook shared by every e-agent distribution (Phase 1 layout).

A standard wheel gets its package sub-tree from the shared src/ tree. An
editable install gets only the .pth that dev-mode-dirs writes: a static
force-include would also be copied into site-packages and shadow src/.
The distributions are released as wheels; an sdist could not carry the
shared tree, so building one fails instead of producing an empty archive.
"""

from pathlib import Path
from typing import Any

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class SrcTreeHook(BuildHookInterface):
    PLUGIN_NAME = "custom"

    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        if self.target_name == "sdist":
            raise RuntimeError(
                "e-agent distributions build as wheels from the shared src/ tree; "
                "use `uv build --package <name> --wheel`"
            )
        if version != "standard":
            return
        package = self.config["package"]
        source = Path(self.root, "../../src", package).resolve()
        if not source.is_dir():
            raise ValueError(f"missing package source: {source}")
        build_data["force_include"][str(source)] = package
'''
READ_ONLY = ("archive/", "research/")
# Files that name old paths on purpose (history, fixtures); never reported.
STALE_EXEMPT = (
    "archive/",
    "research/",
    "harness/state/",
    "scripts/repo_move.py",
    "tests/conformance/test_repo_layout.py",
    "tests/conformance/test_repo_move.py",
)
# Dated records keep the paths of their day; current docs are reported.
DOC_HISTORY = (
    "docs/adr/",
    "docs/handoffs/",
    "docs/plans/",
    "docs/reviews/",
    "docs/specs/",
)
CACHE_PARTS = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
DROPPED_SECTIONS = {"build-system", "tool.uv.build-backend"}
_HEADER = re.compile(r"^\[([^\[\]]+)\]\s*$")
_TITLE = r"(?:\"[^\"]*\"|'[^']*'|\([^)]*\))"
_INLINE_LINK = re.compile(r"(\]\()([^)\s]+)((?:\s+" + _TITLE + r")?\s*\))")
_REFERENCE_LINK = re.compile(r"^(\s{0,3}\[(?!\^)[^\]]+\]:\s*)(\S+)(\s*(?:" + _TITLE + r")?\s*)$")
_SCHEME = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")
_FENCE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")
_CODE_SPAN = re.compile(r"(?<!`)(`+)(?!`).*?(?<!`)\1(?!`)")


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


@dataclass(frozen=True)
class PluginMove:
    """One package moved inside src/, with its tests; no build config moves."""

    old_code: str
    new_code: str
    old_tests: str
    new_tests: str

    @property
    def old_module(self) -> str:
        return self.old_code.removeprefix("src/").replace("/", ".")

    @property
    def new_module(self) -> str:
        return self.new_code.removeprefix("src/").replace("/", ".")


PLUGIN_MOVES: tuple[PluginMove, ...] = (
    PluginMove(
        "src/e_agent/erp",
        "src/e_agent/plugins/erp/domain",
        "tests/unit/erp",
        "tests/unit/plugins/erp/domain",
    ),
    PluginMove(
        "src/e_agent/adapters/odoo",
        "src/e_agent/plugins/erp/odoo",
        "tests/unit/adapters/odoo",
        "tests/unit/plugins/erp/odoo",
    ),
)
DEFAULT_SET = "packages"
MOVE_SETS = (DEFAULT_SET, "plugins")
PLUGIN_REWRITE_SUFFIXES = (".py", ".toml", ".json")
# History, harness records and the mover's own fixtures keep the old plugin paths.
PLUGIN_EXEMPT = (
    "archive/",
    "research/",
    "harness/state/",
    "docs/handoffs/",
    "scripts/repo_move.py",
    "tests/conformance/test_repo_move.py",
)


def plugin_mapping(moves: Sequence[PluginMove] = PLUGIN_MOVES) -> dict[str, str]:
    """Old to new paths for code and tests (Markdown links)."""
    mapping: dict[str, str] = {}
    for move in moves:
        mapping[move.old_code] = move.new_code
        mapping[move.old_tests] = move.new_tests
    return mapping


def _plugin_keys(moves: Sequence[PluginMove]) -> tuple[dict[str, str], dict[str, str]]:
    dotted = {m.old_module: m.new_module for m in moves}
    slashed: dict[str, str] = {}
    for move in moves:
        slashed[move.old_code.removeprefix("src/")] = move.new_code.removeprefix("src/")
        slashed[move.old_tests] = move.new_tests
    return dotted, slashed


def _plugin_pattern(moves: Sequence[PluginMove]) -> tuple[re.Pattern[str], dict[str, str]]:
    """Dotted module keys and slash path keys, longest first, on token boundaries."""
    dotted, slashed = _plugin_keys(moves)

    def alternation(keys: dict[str, str]) -> str:
        return "|".join(re.escape(k) for k in sorted(keys, key=len, reverse=True))

    pattern = re.compile(
        r"(?<![\w.])(" + alternation(dotted) + r")(?!\w)"
        r"|(?<!\w)(" + alternation(slashed) + r")(?!\w)"
    )
    return pattern, {**dotted, **slashed}


@dataclass
class Report:
    broken_links: list[tuple[str, str]] = field(default_factory=list)
    read_only_broken_links: list[tuple[str, str]] = field(default_factory=list)
    stale_references: list[tuple[str, int, str]] = field(default_factory=list)
    doc_references: list[tuple[str, int, str]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.broken_links and not self.stale_references

    @property
    def ok_with_docs(self) -> bool:
        return self.ok and not self.doc_references


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
    """Files layout would leave behind or carry along unstaged: refuse them all."""
    kept = (move.old_code + "/", move.old_tests + "/")
    found = []
    for path in sorted((root / move.old_root).rglob("*")):
        rel = path.relative_to(root)
        name = rel.as_posix()
        if path.is_dir() or name == move.old_config or name.startswith(kept) or _is_cache(rel):
            continue
        found.append(name)
    untracked = _git(root, "ls-files", "-z", "--others", "--exclude-standard", "--", *kept)
    found.extend(name for name in untracked.split("\0")[:-1] if name not in found)
    return found


def _drop_caches(path: Path) -> None:
    """git mv carries ignored caches along; their compiled paths name the old tree."""
    for cache in sorted(path.rglob("__pycache__"), reverse=True):
        shutil.rmtree(cache)


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
    """Keep every table except the uv_build ones; build from src/ through the hook."""
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
        "[tool.hatch.build.hooks.custom]\n"
        'path = "../_hooks/src_tree.py"\n'
        f'package = "e_agent/{part}"\n'
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
        raise MoveError("files outside tracked code, tests and config: " + ", ".join(leftovers))

    for move in moves:
        _git_mv(root, move.old_code, move.new_code)
        _drop_caches(root / move.new_code)
        if (root / move.old_tests).is_dir():
            _git_mv(root, move.old_tests, move.new_tests)
            _drop_caches(root / move.new_tests)
        _git_mv(root, move.old_config, move.new_config)
        config = root / move.new_config
        config.write_text(
            dist_pyproject(config.read_text(encoding="utf-8"), move.part), encoding="utf-8"
        )
        _remove_cache_tree(root / move.old_root)

    hook = root / HOOK_PATH
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_text(HOOK, encoding="utf-8")
    created = [HOOK_PATH]
    for package in sorted({str(Path(m.new_tests).parent) for m in moves}):
        while package != "tests":
            init = root / package / "__init__.py"
            if not init.exists():
                init.write_text("", encoding="utf-8")
                created.append(init.relative_to(root).as_posix())
            package = str(Path(package).parent)
    _git(root, "add", "--", *(m.new_config for m in moves), *created)
    for old in sorted({Path(m.old_root).parts[0] for m in moves}):
        _remove_cache_tree(root / old)


def _plugin_leftovers(root: Path, moves: Sequence[PluginMove]) -> list[str]:
    """Untracked, non-cache files git mv would carry along unstaged: refuse them."""
    kept = [d + "/" for m in moves for d in (m.old_code, m.old_tests) if (root / d).is_dir()]
    untracked = _git(root, "ls-files", "-z", "--others", "--exclude-standard", "--", *kept)
    return [name for name in untracked.split("\0")[:-1] if not _is_cache(Path(name))]


def rewrite_plugin_paths(root: Path, moves: Sequence[PluginMove] = PLUGIN_MOVES) -> list[str]:
    """Rewrite old plugin module paths in tracked code and config; Markdown is left alone."""
    pattern, mapping = _plugin_pattern(moves)
    changed = []
    for name in _tracked(root):
        if not name.endswith(PLUGIN_REWRITE_SUFFIXES) or name.startswith(PLUGIN_EXEMPT):
            continue
        file = root / name
        text = file.read_text(encoding="utf-8")
        new = pattern.sub(lambda m: mapping[m.group(0)], text)
        if new != text:
            file.write_text(new, encoding="utf-8")
            changed.append(name)
    return changed


def layout_plugins(root: Path, moves: Sequence[PluginMove] = PLUGIN_MOVES) -> list[str]:
    """git mv the plugin packages and their tests, then rewrite paths and links."""
    for move in moves:
        if not (root / move.old_code).is_dir():
            raise MoveError(f"missing {move.old_code}")
        for target in (move.new_code, move.new_tests):
            if (root / target).exists():
                raise MoveError(f"target exists: {target}")
    leftovers = _plugin_leftovers(root, moves)
    if leftovers:
        raise MoveError("untracked files in moved trees: " + ", ".join(leftovers))

    for move in moves:
        _git_mv(root, move.old_code, move.new_code)
        _drop_caches(root / move.new_code)
        if (root / move.old_tests).is_dir():
            _git_mv(root, move.old_tests, move.new_tests)
            _drop_caches(root / move.new_tests)
    changed = rewrite_plugin_paths(root, moves)
    changed += rewrite_links(root, plugin_mapping(moves))

    # src/e_agent/plugins and plugins/erp stay namespace packages; tests are packages.
    created = []
    for package in sorted({str(Path(m.new_tests).parent) for m in moves}):
        while package != "tests":
            init = root / package / "__init__.py"
            if not init.exists():
                init.write_text("", encoding="utf-8")
                created.append(init.relative_to(root).as_posix())
            package = str(Path(package).parent)
    if created:
        _git(root, "add", "--", *created)
    return sorted(set(changed))


def layout_mapping(moves: Sequence[Move] = MOVES) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for move in moves:
        mapping[move.old_code] = move.new_code
        mapping[move.old_tests] = move.new_tests
        mapping[move.old_config] = move.new_config
        mapping[move.old_root] = move.new_code  # a link to the distribution means its code
    return mapping


def _map(path: str, mapping: dict[str, str]) -> str:
    for old in sorted(mapping, key=len, reverse=True):
        if path == old or path.startswith(old + "/"):
            return mapping[old] + path[len(old) :]
    return path


def _inverse(mapping: dict[str, str]) -> dict[str, str]:
    """New path to its most specific old path (old_root and old_code share a target)."""
    inverse: dict[str, str] = {}
    for old in sorted(mapping, key=len):
        inverse[mapping[old]] = old
    return inverse


def _tracked(root: Path, *patterns: str) -> list[str]:
    return sorted(_git(root, "ls-files", "-z", "--", *patterns).split("\0")[:-1])


def _edit_prose(text: str, edit: Callable[[str], str]) -> str:
    """Apply `edit` to the text outside code fences and code spans."""
    lines = text.split("\n")
    fence = ""
    for number, line in enumerate(lines):
        opening = _FENCE.match(line)
        if fence:
            closing = line.strip()
            if len(closing) >= len(fence) and not closing.strip(fence[0]):
                fence = ""
            continue
        if opening:
            fence = opening.group(1)
            continue
        spans = list(_CODE_SPAN.finditer(line))
        if not spans:
            lines[number] = edit(line)
            continue
        parts, start = [], 0
        for span in spans:
            parts.append(edit(line[start : span.start()]))
            parts.append(span.group(0))
            start = span.end()
        parts.append(edit(line[start:]))
        lines[number] = "".join(parts)
    return "\n".join(lines)


def _relative_path(target: str) -> str | None:
    if not target or target.startswith(("#", "/")) or _SCHEME.match(target):
        return None
    path = re.split(r"[#?]", target, maxsplit=1)[0]
    return path or None


def _rewrite_targets(segment: str, fix: Callable[[str], str]) -> str:
    segment = _INLINE_LINK.sub(lambda m: m.group(1) + fix(m.group(2)) + m.group(3), segment)
    return _REFERENCE_LINK.sub(lambda m: m.group(1) + fix(m.group(2)) + m.group(3), segment)


def rewrite_links(root: Path, mapping: dict[str, str]) -> list[str]:
    """Rewrite relative links in tracked Markdown so they resolve after `mapping` moves."""
    inverse = _inverse(mapping)
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
        new = _edit_prose(text, partial(_rewrite_targets, fix=fix))
        if new != text:
            file.write_text(new, encoding="utf-8")
            changed.append(name)
    return changed


def move_documents(root: Path, files: Sequence[str], folder: str) -> list[str]:
    mapping = {name: f"{folder}/{Path(name).name}" for name in files}
    for old, new in mapping.items():
        _git_mv(root, old, new)
    return rewrite_links(root, mapping)


def _link_targets(text: str) -> list[str]:
    found: list[str] = []

    def record(target: str) -> str:
        found.append(target)
        return target

    def collect(segment: str) -> str:
        return _rewrite_targets(segment, record)

    _edit_prose(text, collect)
    return found


def _check_links(root: Path, report: Report) -> None:
    for name in _tracked(root, "*.md"):
        if name.startswith("archive/"):
            continue
        base = os.path.dirname(name)
        broken = (
            report.read_only_broken_links if name.startswith(READ_ONLY) else report.broken_links
        )
        for target in _link_targets((root / name).read_text(encoding="utf-8")):
            path = _relative_path(target)
            if path and not (root / base / unquote(path)).exists():
                broken.append((name, path))


def check(root: Path, moves: Sequence[Move] = MOVES, extra_old: Sequence[str] = ()) -> Report:
    report = Report()
    _check_links(root, report)
    old = [m.old_root for m in moves] + list(extra_old)
    # A path starts the token or follows ./ or ../; ui/packages/... is a different tree.
    full = re.compile(
        r"(?:(?<![\w./-])|(?<=\./))(" + "|".join(re.escape(o) for o in old) + r")(?![\w-])"
    )
    tops = sorted({Path(m.old_root).parts[0] for m in moves})
    # Quoted top-level roots and globs ("packages", 'apps', "packages/*") in tooling,
    # but not a mapping key such as {"packages": ...}.
    bare = re.compile(r"[\"'](" + "|".join(re.escape(t) for t in tops) + r"(?:/\*)?)[\"'](?!\s*:)")
    for name in _tracked(root):
        if name.startswith(STALE_EXEMPT):
            continue
        is_doc = name.endswith(".md")
        if is_doc and name.startswith(DOC_HISTORY):
            continue
        try:
            text = (root / name).read_text(encoding="utf-8")
        except (UnicodeDecodeError, FileNotFoundError, IsADirectoryError):
            continue
        patterns = [full] if is_doc or name.startswith("ui/") else [full, bare]
        found = report.doc_references if is_doc else report.stale_references
        for number, line in enumerate(text.splitlines(), start=1):
            for pattern in patterns:
                found.extend((name, number, m.group(1)) for m in pattern.finditer(line))
    return report


def check_plugins(root: Path, moves: Sequence[PluginMove] = PLUGIN_MOVES) -> Report:
    """Broken links, and old plugin module paths left in code, config and current docs."""
    report = Report()
    _check_links(root, report)
    pattern, _ = _plugin_pattern(moves)
    for name in _tracked(root):
        if name.startswith(PLUGIN_EXEMPT):
            continue
        is_doc = name.endswith(".md")
        if is_doc and name.startswith(DOC_HISTORY):
            continue
        try:
            text = (root / name).read_text(encoding="utf-8")
        except (UnicodeDecodeError, FileNotFoundError, IsADirectoryError):
            continue
        found = report.stale_references
        if is_doc or not name.endswith(PLUGIN_REWRITE_SUFFIXES):
            found = report.doc_references
        for number, line in enumerate(text.splitlines(), start=1):
            found.extend((name, number, m.group(0)) for m in pattern.finditer(line))
    return report


def _move_set(name: str) -> str:
    if name not in MOVE_SETS:
        raise MoveError(f"unknown move set: {name} (known: {', '.join(MOVE_SETS)})")
    return name


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--root", type=Path, default=ROOT)
    sub = parser.add_subparsers(dest="command", required=True)
    layouter = sub.add_parser("layout")
    layouter.add_argument("--set", default=DEFAULT_SET, help=f"move set: {', '.join(MOVE_SETS)}")
    links = sub.add_parser("links")
    links.add_argument("--layout", action="store_true", help="rewrite after `layout`")
    links.add_argument("--move", nargs="+", default=[], help="documents to git mv")
    links.add_argument("--to", help="target folder for --move")
    checker = sub.add_parser("check")
    checker.add_argument("--old", nargs="*", default=[], help="more old paths to report")
    checker.add_argument("--docs", action="store_true", help="also fail on doc mentions")
    checker.add_argument("--set", default=DEFAULT_SET, help=f"move set: {', '.join(MOVE_SETS)}")
    args = parser.parse_args(argv)
    root: Path = args.root.resolve()

    if args.command == "layout":
        if _move_set(args.set) == "plugins":
            changed = layout_plugins(root)
            print(f"moved {len(PLUGIN_MOVES)} plugin packages; rewrote {len(changed)} files")
            for name in changed:
                print(f"  {name}")
            return 0
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
    if _move_set(args.set) == "plugins":
        if args.old:
            parser.error("--old applies to the packages set only")
        report = check_plugins(root)
    else:
        report = check(root, MOVES, args.old)
    for name, target in report.broken_links:
        print(f"broken link: {name}: {target}")
    for name, target in report.read_only_broken_links:
        print(f"broken link (read-only history, not fixed): {name}: {target}")
    for name, number, path in report.stale_references:
        print(f"old path: {name}:{number}: {path}")
    for name, number, path in report.doc_references:
        print(f"old path in doc: {name}:{number}: {path}")
    print(
        f"{len(report.broken_links)} broken links, "
        f"{len(report.stale_references)} old-path references in code and config, "
        f"{len(report.doc_references)} in current docs, "
        f"{len(report.read_only_broken_links)} broken links in read-only history"
    )
    return 0 if (report.ok_with_docs if args.docs else report.ok) else 1


if __name__ == "__main__":
    sys.exit(main())
