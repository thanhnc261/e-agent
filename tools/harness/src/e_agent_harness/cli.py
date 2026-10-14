"""``e-agent-harness`` command line.

Each command prints problems one per line and returns an exit code; hook modes read
the hook JSON on stdin and exit 2 to deny.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TextIO

from e_agent_harness import (
    closecheck,
    contracts,
    gate,
    gitinfo,
    progress,
    scope,
    state,
    status,
    tasks,
    tidy,
)
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
    new_task.add_argument("--gate", default="quick", help="a gate set from the manifest")
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
    va = sub.add_parser("validate", help="validate a JSON file against a contract schema")
    va.add_argument("schema")
    va.add_argument("file", type=Path)
    af = sub.add_parser("add-feature", help="append one feature entry to a phase feature list")
    af.add_argument("phase")
    af.add_argument("feature_id")
    af.add_argument("--category", required=True)
    af.add_argument("--description", required=True)
    af.add_argument("--step", action="append", default=[], required=True)
    sub.add_parser("tidy", help="format and lint the whole change once, before the commit")
    rf = sub.add_parser("refresh-task", help="new digests for the active task; base kept")
    rf.add_argument("--from-features", action="store_true", help="re-derive acceptance")
    am = sub.add_parser("amend-scope", help="add one allowed path to the active task")
    am.add_argument("--add", required=True, dest="glob")
    am.add_argument("--reason", required=True)
    st = sub.add_parser("status", help="the session brief: state, boundaries, one next action")
    st.add_argument("--format", dest="fmt", choices=["text", "hook"], default="text")
    st.add_argument("--session", default=None, help="judge the close ritual for this session")
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
    current = (active or {}).get("task")
    # A task whose close-check passes is closed and may be followed without --replace.
    switching = bool(current) and current != args.task_id and not args.replace
    closed = _marker(paths, root) == "closed" or not closecheck.problems(paths, m, root)
    if switching and not closed:
        print(f"task {current} is active; finish it with close-check or pass --replace")
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
    _clear_closed(paths)
    written = paths.task(args.phase, args.task_id).relative_to(root)
    print(f"task {contract['id']} materialised at {written}")
    return 0


def _contract_hash(paths: state.Paths) -> str | None:
    loaded = state.load_task(paths)
    return hashlib.sha256(loaded[1].read_bytes()).hexdigest() if loaded else None


def _mark(paths: state.Paths, root: Path, status_value: str) -> None:
    """Record the active task's lifecycle locally: "closed" or "reopened".

    The record is bound to the contract's content and to the commit it was made at, so a
    changed contract or a checkout of an earlier commit invalidates it.
    """
    active = state.load_active(paths) or {}
    state.write_json(
        paths.closed_marker,
        {
            "status": status_value,
            "phase": active.get("phase"),
            "task": active.get("task"),
            "contract_sha256": _contract_hash(paths),
            "commit": gitinfo.head_sha(root),
        },
    )


def _marker(paths: state.Paths, root: Path) -> str | None:
    """ "closed", "reopened", or None when there is no record that still applies."""
    active = state.load_active(paths)
    if not active or not paths.closed_marker.is_file():
        return None
    marker = state.read_json(paths.closed_marker)
    if not isinstance(marker, dict):
        return None
    same_task = marker.get("task") == active.get("task") and marker.get("phase") == active.get(
        "phase"
    )
    same_contract = marker.get("contract_sha256") == _contract_hash(paths)
    commit = str(marker.get("commit") or "")
    still_reachable = bool(commit) and gitinfo.is_ancestor(root, commit, "HEAD")
    if same_task and same_contract and still_reachable:
        value = marker.get("status")
        return value if value in {"closed", "reopened"} else None
    return None


def _mark_closed(paths: state.Paths) -> None:
    _mark(paths, paths.repo_root, "closed")


def _clear_closed(paths: state.Paths) -> None:
    if paths.closed_marker.is_file():
        paths.closed_marker.unlink()


def _resolve_for_hook(repo_root: Path) -> tuple[mf.Manifest, dict[str, Any] | None]:
    """The manifest and the contract whose scope applies to an edit.

    A closed task no longer holds unrelated work to its scope; protected paths are always
    guarded. Closure is recorded locally the first time it is seen (explicitly by
    close-check, or inferred here) so later edits that dirty the tree keep it closed;
    refresh-task records the task as reopened.
    """
    paths = state.Paths(repo_root)
    m = mf.load_manifest(paths.manifest)
    loaded = state.load_task(paths)
    if loaded is None:
        return m, None
    lifecycle = _marker(paths, repo_root)
    if lifecycle == "reopened":
        return m, loaded[0]
    if lifecycle == "closed":
        return m, None
    if not closecheck.problems(paths, m, repo_root):
        _mark(paths, repo_root, "closed")
        return m, None
    return m, loaded[0]


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
    contract = loaded[0] if loaded else None
    problems = scope.check_tree(contract, m, root)
    for problem in problems:
        print(problem)
    if problems:
        return 1
    print(f"ok: {len(scope.changed_paths(contract, root))} changed paths inside scope")
    return 0


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
    if contracts.parse_timestamp(evidence["finished_at"]) < contracts.parse_timestamp(
        evidence["started_at"]
    ):
        print("the clock went backwards during the gate; this evidence cannot close a task")
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
        timestamp=datetime.now(UTC).isoformat(timespec="microseconds"),
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
    try:
        paths.task("x", args.task_id)
    except ValueError as exc:
        print(str(exc))
        return 1
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
        if os.environ.get("E_AGENT_HARNESS_UNATTENDED") != "1":
            return 0  # attended sessions are never trapped
        try:
            payload = json.load(args.stdin)
            if not args.repo and payload.get("cwd"):
                args.repo = state.find_repo_root(Path(payload["cwd"]))
            root, paths, m = _context(args)
            session = str(payload.get("session_id") or "")
            found = closecheck.problems(paths, m, root, session=session)
        except Exception as exc:  # an enabled gate fails closed: invalid state blocks the stop
            print(f"close-check error: {exc}", file=sys.stderr)
            return 2
        if found:
            print("close-check: " + "; ".join(found), file=sys.stderr)
            return 2
        _mark_closed(paths)
        return 0
    root, paths, m = _context(args)
    found = closecheck.problems(paths, m, root, session=args.session)
    for problem in found:
        print(problem)
    if found:
        return 1
    _mark_closed(paths)
    print("ok: task may close")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    root, paths, m = _context(args)
    data = status.collect(paths, m, root, session=args.session)
    if args.fmt == "hook":
        print(status.render_hook(data, m.status.token_budget))
    else:
        print(status.render_text(data, m.status.language_order))
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    try:
        found = contracts.validate(args.schema, json.loads(args.file.read_text(encoding="utf-8")))
    except (KeyError, OSError, ValueError) as exc:
        print(str(exc).strip("'"))
        return 1
    for problem in found:
        print(problem)
    if found:
        return 1
    print(f"ok: {args.file} is a valid {args.schema}")
    return 0


def cmd_add_feature(args: argparse.Namespace) -> int:
    _root, paths, _m = _context(args)
    try:
        path = paths.features(args.phase)
    except ValueError as exc:
        print(str(exc))
        return 1
    doc = state.read_json(path) if path.is_file() else {"phase": args.phase, "entries": []}
    if any(e.get("id") == args.feature_id for e in doc["entries"]):
        print(f"feature {args.feature_id} already exists in {path.name}")
        return 1
    doc["entries"].append(
        {
            "id": args.feature_id,
            "category": args.category,
            "description": args.description,
            "steps": list(args.step),
            "passes": False,
        }
    )
    found = contracts.validate("features", doc)
    if found:
        for problem in found:
            print(problem)
        return 1
    state.write_json(path, doc)
    print(f"feature {args.feature_id} added to phase {args.phase}")
    return 0


def cmd_tidy(args: argparse.Namespace) -> int:
    root, paths, _m = _context(args)
    loaded = state.load_task(paths)
    code, report = tidy.tidy(loaded[0] if loaded else None, root)
    for line in report:
        print(line)
    return code


def cmd_refresh_task(args: argparse.Namespace) -> int:
    root, paths, m = _context(args)
    try:
        contract = tasks.refresh(paths, m, root, from_features=args.from_features)
    except ValueError as exc:
        print(str(exc))
        return 1
    _mark(paths, root, "reopened")  # refreshing reopens the task: its scope applies again
    print(f"task {contract['id']} refreshed (base {str(contract['base_commit'])[:7]} kept)")
    return 0


def cmd_amend_scope(args: argparse.Namespace) -> int:
    _root, paths, _m = _context(args)
    try:
        contract = tasks.amend_scope(paths, args.glob, args.reason, datetime.now(UTC))
    except ValueError as exc:
        print(str(exc))
        return 1
    print(f"task {contract['id']} scope += {args.glob}")
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
    "validate": cmd_validate,
    "add-feature": cmd_add_feature,
    "tidy": cmd_tidy,
    "refresh-task": cmd_refresh_task,
    "amend-scope": cmd_amend_scope,
}


def main(argv: list[str] | None = None, stdin: TextIO | None = None) -> int:
    args = _parser().parse_args(argv)
    args.stdin = stdin or sys.stdin
    try:
        return COMMANDS[args.command](args)
    except ValueError as exc:  # invalid ids, escaping state paths, unreadable manifests
        print(str(exc))
        return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
