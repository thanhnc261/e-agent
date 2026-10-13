"""The status brief: what is going on and exactly one next action (harness plan H2)."""

from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass, field
from pathlib import Path

from e_agent_harness import closecheck, gate, gitinfo, progress, state
from e_agent_harness.digest import is_stale
from e_agent_harness.manifest import Manifest, validate_manifest

ENTRIES_SHOWN = 3


@dataclass
class StatusData:
    branch: str
    head: str
    clean: bool
    phase: str | None
    plan: str
    task_id: str | None
    allowed_paths: list[str] = field(default_factory=list)
    gate_set: str | None = None
    acceptance: list[str] = field(default_factory=list)
    stale: bool = False
    closed: bool = False
    next_feature: str | None = None
    has_evidence: bool = False
    bookkeeping_dirty: bool = False
    gate_ran: bool = False
    entries: list[progress.ProgressEntry] = field(default_factory=list)
    read_only: list[str] = field(default_factory=list)
    allowed_containers: list[str] = field(default_factory=list)
    denied_containers: list[str] = field(default_factory=list)
    manifest_problems: list[str] = field(default_factory=list)


def collect(paths: state.Paths, m: Manifest, repo_root: Path) -> StatusData:
    active = state.load_active(paths) or {}
    loaded = state.load_task(paths)
    data = StatusData(
        branch=gitinfo.branch(repo_root),
        head=gitinfo.head_sha(repo_root)[:7],
        clean=gate.code_is_clean(repo_root),
        bookkeeping_dirty=not gitinfo.is_clean(repo_root),
        phase=str(active["phase"]) if active.get("phase") else None,
        plan=m.authoritative.active_plan,
        task_id=str(loaded[0]["id"]) if loaded else None,
        read_only=list(m.protected.read_only),
        allowed_containers=list(m.environment.allowed_containers),
        denied_containers=list(m.environment.denied_containers),
        manifest_problems=validate_manifest(m, repo_root),
    )
    if loaded:
        contract = loaded[0]
        data.allowed_paths = list(contract["allowed_paths"])
        data.gate_set = str(contract["gate_set"])
        data.acceptance = list(contract["acceptance"])
        data.stale = is_stale(str(contract["context_digest"]), repo_root, m)
        data.closed = not closecheck.problems(paths, m, repo_root)
        data.gate_ran = any(paths.evidence(data.task_id or "").glob("*.json"))
        data.has_evidence = any(
            closecheck.evidence_ties_to_head(repo_root, state.read_json(f), data.task_id) is None
            for f in paths.evidence(data.task_id or "").glob("*.json")
        )
    phase = data.phase
    if phase and paths.features(phase).is_file():
        entries = state.read_json(paths.features(phase)).get("entries", [])
        data.next_feature = next((str(e["id"]) for e in entries if not e.get("passes")), None)
    if paths.progress.is_file():
        entries = progress.parse_progress(paths.progress.read_text(encoding="utf-8"))
        data.entries = entries[-ENTRIES_SHOWN:]
    return data


def next_action(d: StatusData) -> str:
    if d.manifest_problems:
        return "fix the manifest: e-agent-harness validate-context"
    if not d.task_id:
        return (
            "new-task <phase> <task-id> --feature <id> --paths <glob> "
            "(pick the next unfinished feature)"
        )
    if d.closed:
        follow = (
            f"new-task {d.phase} <task-id> --feature {d.next_feature} --paths <glob>"
            if d.next_feature
            else "the phase review: every feature passes"
        )
        return f"task {d.task_id} is closed: clear the context, then {follow}"
    if d.stale:
        return (
            "digest stale: authoritative files changed; re-materialise with "
            f"new-task {d.phase} {d.task_id} ... --replace"
        )
    if not d.clean:
        return f"commit the work, then run e-agent-harness gate {d.gate_set} on the clean tree"
    if not d.has_evidence:
        if d.bookkeeping_dirty and not d.gate_ran:
            step = d.acceptance[0] if d.acceptance else "the first acceptance step"
            return f"commit the harness bookkeeping (harness/state), then work on: {step}"
        return f"run e-agent-harness gate {d.gate_set}"
    return "run e-agent-harness checkpoint, write the handoff, then close-check; then /clear"


def _vi(d: StatusData, action: str) -> list[str]:
    tree = "sạch" if d.clean else "đang có thay đổi chưa commit"
    task = d.task_id or "chưa có task nào"
    return [
        "## Tóm tắt (ELI5)",
        f"- Nhánh `{d.branch}` tại {d.head}; phase {d.phase or '?'}; plan: {d.plan}.",
        f"- Task đang làm: {task}; cây làm việc {tree}.",
        f"- Việc tiếp theo duy nhất: {action}",
    ]


def _en(d: StatusData, action: str) -> list[str]:
    tree = "clean" if d.clean else "dirty"
    lines = ["## Status", f"- Branch {d.branch} at {d.head}; tree {tree}; plan {d.plan}."]
    if d.manifest_problems:
        lines += ["- Manifest problems:"] + [f"  - {p}" for p in d.manifest_problems]
    if d.task_id:
        digest_state = "STALE" if d.stale else "current"
        lines += [
            f"- Active task {d.task_id} (phase {d.phase}), gate set {d.gate_set}, "
            f"digest {digest_state}.",
            "- Allowed paths: " + ", ".join(d.allowed_paths),
            "- Acceptance: " + " | ".join(d.acceptance),
        ]
    else:
        lines.append("- No active task.")
    lines.append(
        "- Boundaries: read-only "
        + ", ".join(d.read_only)
        + "; containers allowed "
        + ", ".join(d.allowed_containers)
        + "; denied "
        + ", ".join(d.denied_containers)
        + "."
    )
    if d.entries:
        lines.append("- Recent progress:")
        lines += [f"  - {e.timestamp} {e.task}: {e.changed} → next: {e.next}" for e in d.entries]
    lines.append(f"- Next action: {action}")
    return lines


def render_text(d: StatusData, language_order: tuple[str, ...]) -> str:
    action = next_action(d)
    blocks = {"vi-eli5": _vi(d, action), "en": _en(d, action)}
    ordered = [blocks[lang] for lang in language_order if lang in blocks]
    return "\n".join(line for block in ordered for line in (*block, ""))


def estimate_tokens(text: str) -> int:
    return len(text) // 4 + 1


def render_hook(d: StatusData, budget: int) -> str:
    trimmed = dataclasses.replace(d)
    text = render_text(trimmed, ("vi-eli5", "en"))
    while estimate_tokens(text) > budget and trimmed.entries:
        trimmed.entries = trimmed.entries[1:]
        text = render_text(trimmed, ("vi-eli5", "en"))
    if estimate_tokens(text) > budget:
        text = text[: budget * 4 - 4] + " […]"
    title = f"phase-{d.phase or '?'}/{d.task_id or 'no-task'}"
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": text,
            "sessionTitle": title,
        }
    }
    return json.dumps(payload, ensure_ascii=False)
