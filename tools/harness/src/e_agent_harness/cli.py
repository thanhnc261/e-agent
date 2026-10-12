"""``e-agent-harness`` command line.

Each command prints problems one per line and returns an exit code; hook modes read
the hook JSON on stdin and exit 2 to deny.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TextIO

from e_agent_harness import manifest as mf
from e_agent_harness import scope, state, tasks


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="e-agent-harness")
    parser.add_argument(
        "--repo", type=Path, default=None, help="repository root (default: found from cwd)"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("validate-context", help="check the manifest against this checkout")
    new_task = sub.add_parser("new-task", help="materialise a task contract and make it active")
    new_task.add_argument("phase")
    new_task.add_argument("task_id")
    new_task.add_argument("--feature", action="append", default=[], required=True)
    new_task.add_argument(
        "--paths", action="append", default=[], required=True, help="allowed path glob"
    )
    new_task.add_argument("--acceptance", action="append", default=[])
    new_task.add_argument("--gate", default="quick", choices=["quick", "full", "pg", "e2e", "live"])
    new_task.add_argument("--replace", action="store_true", help="replace the active task")
    scope_p = sub.add_parser(
        "check-scope", help="changed paths must be inside the active task's scope"
    )
    scope_p.add_argument(
        "--hook", action="store_true", help="PreToolUse mode: hook JSON on stdin, exit 2 denies"
    )
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


def cmd_new_task(args: argparse.Namespace) -> int:
    root, paths, m = _context(args)
    active = state.load_active(paths)
    if active and active.get("task") and active["task"] != args.task_id and not args.replace:
        print(f"task {active['task']} is active; finish it with close-check or pass --replace")
        return 1
    try:
        contract = tasks.materialise(
            paths,
            m,
            root,
            phase=args.phase,
            task_id=args.task_id,
            feature_ids=args.feature,
            allowed_paths=args.paths,
            acceptance=args.acceptance,
            gate_set=args.gate,
            now=datetime.now(UTC),
        )
    except ValueError as exc:
        print(str(exc))
        return 1
    written = paths.task(args.phase, args.task_id).relative_to(root)
    print(f"task {contract['id']} materialised at {written}")
    return 0


def _resolve_for_hook(repo_root: Path) -> tuple[mf.Manifest, dict[str, Any] | None]:
    paths = state.Paths(repo_root)
    loaded = state.load_task(paths)
    return mf.load_manifest(paths.manifest), (loaded[0] if loaded else None)


def cmd_check_scope(args: argparse.Namespace) -> int:
    if args.hook:
        payload = json.load(args.stdin)
        code, reason = scope.hook_decision(payload, _resolve_for_hook)
        if code:
            print(reason, file=sys.stderr)
        return code
    root, paths, m = _context(args)
    loaded = state.load_task(paths)
    problems = scope.check_tree(loaded[0] if loaded else None, m, root)
    for problem in problems:
        print(problem)
    return 1 if problems else 0


COMMANDS = {
    "validate-context": cmd_validate_context,
    "new-task": cmd_new_task,
    "check-scope": cmd_check_scope,
}


def main(argv: list[str] | None = None, stdin: TextIO | None = None) -> int:
    args = _parser().parse_args(argv)
    args.stdin = stdin or sys.stdin
    return COMMANDS[args.command](args)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
