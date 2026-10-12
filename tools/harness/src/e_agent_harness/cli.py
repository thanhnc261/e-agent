"""``e-agent-harness`` command line.

Each command prints problems one per line and returns an exit code; hook modes read
the hook JSON on stdin and exit 2 to deny.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TextIO

from e_agent_harness import closecheck, gate, gitinfo, progress, scope, state, status, tasks
from e_agent_harness import manifest as mf


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
    gate_p = sub.add_parser("gate", help="run a gate set and write evidence")
    gate_p.add_argument("set_name")
    gate_p.add_argument("--package", default=None)
    gate_p.add_argument("--timeout", type=int, default=1800)
    gate_p.add_argument("--keep-going", action="store_true")
    live_p = sub.add_parser(
        "live-check", help="run the live gate set against the sandbox, redacted"
    )
    live_p.add_argument("--timeout", type=int, default=1800)
    cp = sub.add_parser("checkpoint", help="append a progress entry for the active task")
    cp.add_argument("--next", dest="next_action", default=None)
    cp.add_argument("--changed", default=None)
    cp.add_argument("--open", dest="open_items", default="none")
    cp.add_argument("--session", default="manual")
    cp.add_argument(
        "--hook", action="store_true", help="PreCompact mode: payload on stdin, always exits 0"
    )
    ho = sub.add_parser("handoff", help="validate a task's handoff document")
    ho.add_argument("task_id")
    cc = sub.add_parser(
        "close-check", help="the close ritual: clean tree, progress, evidence, handoff"
    )
    cc.add_argument("--session", default=None)
    cc.add_argument(
        "--hook", action="store_true", help="Stop mode: inert unless E_AGENT_HARNESS_UNATTENDED=1"
    )
    st = sub.add_parser("status", help="the session brief: state, boundaries, one next action")
    st.add_argument("--format", dest="fmt", choices=["text", "hook"], default="text")
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
        try:
            payload = json.load(args.stdin)
            code, reason = scope.hook_decision(payload, _resolve_for_hook)
        except Exception as exc:  # fail closed: a broken check must not let an edit through
            code, reason = 2, f"check-scope error: {exc}"
        if code:
            print(reason, file=sys.stderr)
        return code
    root, paths, m = _context(args)
    loaded = state.load_task(paths)
    problems = scope.check_tree(loaded[0] if loaded else None, m, root)
    for problem in problems:
        print(problem)
    return 1 if problems else 0


def _run_gate(
    args: argparse.Namespace,
    set_name: str,
    directory_for: Callable[[state.Paths, str], Path],
    package: str | None,
    keep_going: bool,
) -> int:
    root, paths, m = _context(args)
    loaded = state.load_task(paths)
    task_id = str(loaded[0]["id"]) if loaded else "no-task"
    try:
        evidence = gate.run_gate(
            m,
            set_name,
            root,
            task_id=task_id,
            package=package,
            timeout=args.timeout,
            keep_going=keep_going,
            now=datetime.now(UTC),
        )
    except ValueError as exc:
        print(str(exc))
        return 1
    path = gate.write_evidence(directory_for(paths, task_id), evidence)
    for entry in evidence["commands"]:
        print(f"[{entry['exit_code']}] {entry['command']}")
    print(
        f"evidence: {path.relative_to(root)} "
        f"(commit {evidence['commit'][:7]}, clean_tree={evidence['clean_tree']})"
    )
    return 0 if evidence["ok"] else 1


def cmd_gate(args: argparse.Namespace) -> int:
    return _run_gate(args, args.set_name, lambda p, t: p.evidence(t), args.package, args.keep_going)


def cmd_live_check(args: argparse.Namespace) -> int:
    return _run_gate(args, "live", lambda p, _t: p.live_evidence, None, False)


def _one_line(text: str) -> str:
    return " ".join(text.split()) or "none"


def _append_checkpoint(args: argparse.Namespace, session: str) -> None:
    root, paths, _m = _context(args)
    loaded = state.load_task(paths)
    changed = args.changed or ", ".join(gitinfo.status_files(root)) or "no working-tree changes"
    next_action = args.next_action or (str(loaded[0]["acceptance"][0]) if loaded else "new-task")
    entry = progress.ProgressEntry(
        timestamp=datetime.now(UTC).isoformat(timespec="seconds"),
        session=_one_line(session),
        task=str(loaded[0]["id"]) if loaded else "none",
        changed=_one_line(changed),
        next=_one_line(next_action),
        open=_one_line(args.open_items),
    )
    progress.append_entry(paths.progress, entry)


def cmd_checkpoint(args: argparse.Namespace) -> int:
    if args.hook:
        try:
            payload = json.load(args.stdin)
            if not args.repo and payload.get("cwd"):
                args.repo = state.find_repo_root(Path(payload["cwd"]))
            _append_checkpoint(args, str(payload.get("session_id") or "hook"))
        except Exception as exc:  # a compaction hook must never block
            print(f"checkpoint skipped: {exc}", file=sys.stderr)
        return 0
    _append_checkpoint(args, args.session)
    print("checkpoint appended to harness/state/progress.md")
    return 0


def _phase_of_task(paths: state.Paths, task_id: str) -> str | None:
    matches = sorted(paths.state.glob(f"*/tasks/{task_id}.json"))
    return matches[0].parent.parent.name if matches else None


def cmd_handoff(args: argparse.Namespace) -> int:
    root, paths, _m = _context(args)
    active = state.load_active(paths) or {}
    if active.get("task") == args.task_id:
        phase = str(active.get("phase") or "")
    else:
        phase = str(_phase_of_task(paths, args.task_id) or active.get("phase") or "")
    found = closecheck.handoff_problems(paths, root, phase, args.task_id)
    for problem in found:
        print(problem)
    if found:
        return 1
    print(f"ok: handoff {args.task_id} valid")
    return 0


def cmd_close_check(args: argparse.Namespace) -> int:
    if args.hook:
        payload = json.load(args.stdin)
        unattended = os.environ.get("E_AGENT_HARNESS_UNATTENDED") == "1"
        if not unattended or payload.get("stop_hook_active"):
            return 0
        if not args.repo and payload.get("cwd"):
            args.repo = state.find_repo_root(Path(payload["cwd"]))
        root, paths, m = _context(args)
        found = closecheck.problems(paths, m, root, session=str(payload.get("session_id") or ""))
        if found:
            print("close-check: " + "; ".join(found), file=sys.stderr)
            return 2
        return 0
    root, paths, m = _context(args)
    found = closecheck.problems(paths, m, root, session=args.session)
    for problem in found:
        print(problem)
    if found:
        return 1
    print("ok: task may close")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    root, paths, m = _context(args)
    data = status.collect(paths, m, root)
    if args.fmt == "hook":
        print(status.render_hook(data, m.status.token_budget))
    else:
        print(status.render_text(data, m.status.language_order))
    return 0


COMMANDS = {
    "validate-context": cmd_validate_context,
    "new-task": cmd_new_task,
    "check-scope": cmd_check_scope,
    "gate": cmd_gate,
    "live-check": cmd_live_check,
    "checkpoint": cmd_checkpoint,
    "handoff": cmd_handoff,
    "close-check": cmd_close_check,
    "status": cmd_status,
}


def main(argv: list[str] | None = None, stdin: TextIO | None = None) -> int:
    args = _parser().parse_args(argv)
    args.stdin = stdin or sys.stdin
    return COMMANDS[args.command](args)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
