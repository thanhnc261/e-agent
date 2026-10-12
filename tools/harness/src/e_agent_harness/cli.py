"""``e-agent-harness`` command line.

Each command prints problems one per line and returns an exit code; hook modes read
the hook JSON on stdin and exit 2 to deny.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TextIO

from e_agent_harness import manifest as mf
from e_agent_harness import state


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="e-agent-harness")
    parser.add_argument(
        "--repo", type=Path, default=None, help="repository root (default: found from cwd)"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("validate-context", help="check the manifest against this checkout")
    return parser


def _context(args: argparse.Namespace) -> tuple[Path, state.Paths, mf.Manifest]:
    root = args.repo.resolve() if args.repo else state.find_repo_root(Path.cwd())
    paths = state.Paths(root)
    return root, paths, mf.load_manifest(paths.manifest)


def cmd_validate_context(args: argparse.Namespace) -> int:
    root, _paths, m = _context(args)
    problems = mf.validate_manifest(m, root)
    roadmap = root / "docs" / "roadmap.md"
    plan_name = Path(m.authoritative.active_plan).name
    if roadmap.is_file() and plan_name not in roadmap.read_text(encoding="utf-8"):
        problems.append(f"roadmap does not link the active plan: {m.authoritative.active_plan}")
    for problem in problems:
        print(problem)
    if problems:
        return 1
    print(f"ok: manifest valid for {root}")
    return 0


COMMANDS = {"validate-context": cmd_validate_context}


def main(argv: list[str] | None = None, stdin: TextIO | None = None) -> int:
    args = _parser().parse_args(argv)
    args.stdin = stdin or sys.stdin
    return COMMANDS[args.command](args)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
