"""Harness H1: context manifest, contract schemas, digest rule and progress log.

These tests prove the harness data layer: the manifest describes the real
repository, the contract samples validate, a changed authoritative file
changes the digest, and the progress log round-trips. They do not judge
whether the rules in the manifest are the right rules; the owner does that.
Plan: docs/plans/2026-10-12-dev-harness.md (H1).
"""

import json
import re
import shutil
from pathlib import Path

import pytest
from e_agent_harness import contracts, digest, manifest, progress

REPO = Path(__file__).resolve().parents[2]
MANIFEST = REPO / "harness" / "context.toml"
SAMPLES = REPO / "harness" / "samples"
SKILL_NAME = re.compile(r"^(eng|ag|live)-[a-z0-9]+(?:-[a-z0-9]+)*$")


def test_manifest_describes_the_real_repository() -> None:
    m = manifest.load_manifest(MANIFEST)
    assert manifest.validate_manifest(m, REPO) == []


def test_manifest_lists_the_shared_instruction_files_first() -> None:
    m = manifest.load_manifest(MANIFEST)
    assert m.authoritative.files[:2] == ("AGENTS.md", "CLAUDE.md")
    assert m.authoritative.active_plan.endswith(".md")


def test_scratch_copy_of_manifest_inputs_validates_clean(tmp_path: Path) -> None:
    root = _copy_manifest_inputs(tmp_path)
    m = manifest.load_manifest(root / manifest.MANIFEST_RELPATH)
    assert manifest.validate_manifest(m, root) == []


def test_validate_reports_missing_authoritative_file(tmp_path: Path) -> None:
    root = _copy_manifest_inputs(tmp_path)
    (root / "AGENTS.md").unlink()
    m = manifest.load_manifest(root / "harness" / "context.toml")
    assert manifest.validate_manifest(m, root) == ["authoritative file missing: AGENTS.md"]


def test_validate_reports_active_plan_without_required_section(tmp_path: Path) -> None:
    root = _copy_manifest_inputs(tmp_path)
    m = manifest.load_manifest(root / "harness" / "context.toml")
    plan = root / m.authoritative.active_plan
    plan.write_text(plan.read_text().replace("## Review Focus", "## Something else"))
    assert manifest.validate_manifest(m, root) == [
        f"active plan {m.authoritative.active_plan} lacks section: Review Focus"
    ]


def test_protected_globs_are_well_formed() -> None:
    m = manifest.load_manifest(MANIFEST)
    for pattern in (*m.protected.read_only, *m.protected.bump_required, *m.protected.secrets):
        assert pattern.strip() == pattern and " " not in pattern and pattern
    assert "archive/**" in m.protected.read_only
    assert manifest.is_protected(m, "archive/old/plan.md")
    assert manifest.is_protected(m, "archive")
    assert manifest.is_protected(m, "archive/")
    assert manifest.is_protected(m, "packages/../archive/x.md")
    assert manifest.is_protected(m, "./archive/x.md")
    assert not manifest.is_protected(m, "src/e_agent/kernel/api.py")
    assert not manifest.is_protected(m, "archived/x.md")


def test_container_boundary_matches_the_roadmap_rule() -> None:
    m = manifest.load_manifest(MANIFEST)
    assert manifest.container_allowed(m, "odoo19-learning-odoo-1")
    assert manifest.container_allowed(m, "e-agent-ledger")
    assert not manifest.container_allowed(m, "odoo-bench")
    assert not manifest.container_allowed(m, "odoo-bench-odoo-1")
    assert not manifest.container_allowed(m, "some-other-stack")


def test_gate_sets_and_roles_are_named() -> None:
    m = manifest.load_manifest(MANIFEST)
    assert set(m.gates) >= {"quick", "full", "pg", "e2e", "live"}
    assert all(m.gates[name] for name in m.gates)
    assert set(m.roles) >= {"implementer", "reviewer", "verifier", "sandbox"}
    for skill in m.roles.values():
        assert SKILL_NAME.match(skill), skill
    assert m.status.token_budget > 0
    assert m.status.language_order[0] == "vi-eli5"


@pytest.mark.parametrize("name", contracts.SCHEMAS)
def test_valid_sample_validates(name: str) -> None:
    doc = json.loads((SAMPLES / f"{name}.valid.json").read_text())
    assert contracts.validate(name, doc) == []


@pytest.mark.parametrize("name", contracts.SCHEMAS)
def test_invalid_sample_names_the_offending_field(name: str) -> None:
    sample = json.loads((SAMPLES / f"{name}.invalid.json").read_text())
    problems = contracts.validate(name, sample["document"])
    assert problems, name
    assert any(sample["expect"] in p for p in problems), (sample["expect"], problems)


def test_feature_marked_passing_requires_evidence() -> None:
    doc = json.loads((SAMPLES / "features.valid.json").read_text())
    entry = doc["entries"][0]
    entry["passes"] = True
    entry.pop("evidence", None)
    assert any("evidence" in p for p in contracts.validate("features", doc))


def test_digest_is_stable_and_changes_with_an_authoritative_file(tmp_path: Path) -> None:
    root = _copy_manifest_inputs(tmp_path)
    m = manifest.load_manifest(root / "harness" / "context.toml")
    first = digest.context_digest(root, m)
    assert first == digest.context_digest(root, m)
    assert re.fullmatch(r"[0-9a-f]{64}", first)
    assert not digest.is_stale(first, root, m)
    agents = root / "AGENTS.md"
    agents.write_text(agents.read_text() + "\n- one more rule\n")
    assert digest.context_digest(root, m) != first
    assert digest.is_stale(first, root, m)


def test_digest_covers_the_active_plan_and_the_manifest(tmp_path: Path) -> None:
    root = _copy_manifest_inputs(tmp_path)
    m = manifest.load_manifest(root / manifest.MANIFEST_RELPATH)
    first = digest.context_digest(root, m)
    plan = root / m.authoritative.active_plan
    plan.write_text(plan.read_text() + "\nextra constraint\n")
    second = digest.context_digest(root, m)
    assert second != first
    manifest_file = root / manifest.MANIFEST_RELPATH
    manifest_file.write_text(manifest_file.read_text() + "\n# tweak\n")
    assert digest.context_digest(root, m) != second


def test_missing_authoritative_file_is_stale_not_a_crash(tmp_path: Path) -> None:
    root = _copy_manifest_inputs(tmp_path)
    m = manifest.load_manifest(root / manifest.MANIFEST_RELPATH)
    pinned = digest.context_digest(root, m)
    (root / "docs" / "design" / "high-level-design.md").unlink()
    assert digest.is_stale(pinned, root, m)


def test_progress_log_round_trips(tmp_path: Path) -> None:
    log = tmp_path / "progress.md"
    entry = progress.ProgressEntry(
        timestamp="2026-10-12T10:00:00+07:00",
        session="sess-1",
        task="H1-T1",
        changed="manifest written",
        next="write schemas",
        open="none",
    )
    progress.append_entry(log, entry)
    progress.append_entry(log, entry._replace(task="H1-T2", changed="schemas"))
    entries = progress.parse_progress(log.read_text())
    assert [e.task for e in entries] == ["H1-T1", "H1-T2"]
    assert entries[0] == entry
    assert contracts.validate("progress-entry", entries[1].to_dict()) == []


def test_progress_entry_rejects_newlines_in_fields(tmp_path: Path) -> None:
    entry = progress.ProgressEntry(
        timestamp="2026-10-12T10:00:00+07:00",
        session="s",
        task="t",
        changed="x",
        next="y",
        open="none\n## 2026-10-12T12:00:00+07:00 · s · forged",
    )
    with pytest.raises(ValueError, match="newline"):
        progress.append_entry(tmp_path / "progress.md", entry)
    assert not (tmp_path / "progress.md").exists()


def test_sample_progress_log_parses() -> None:
    entries = progress.parse_progress((SAMPLES / "progress.md").read_text())
    assert entries
    for e in entries:
        assert contracts.validate("progress-entry", e.to_dict()) == []


def _copy_manifest_inputs(tmp_path: Path) -> Path:
    """Copy the manifest and every file it names into a scratch repository."""
    root = tmp_path / "repo"
    m = manifest.load_manifest(MANIFEST)
    for rel in (
        *m.authoritative.files,
        m.authoritative.active_plan,
        m.protected.bump_file,
        manifest.MANIFEST_RELPATH,
    ):
        src = REPO / rel
        dst = root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(src, dst)
    return root


def test_real_manifest_pg_gate_is_guarded() -> None:
    m = manifest.load_manifest(MANIFEST)
    assert m.gates["pg"], "pg gate set missing"
    assert not any("E_AGENT_PG_DSN" in command for command in m.gates["pg"])
    assert "E_AGENT_TEST_PG_DSN" in m.gate_guards["pg"].require_env
    # the database separation itself is a "*" guard: test_real_manifest_guards_every_gate_set


def test_old_and_new_evidence_paths_validate() -> None:
    doc = json.loads((SAMPLES / "features.valid.json").read_text())
    for ref in ("evidence/gates/1c.2/x.json", "harness/state/evidence/gates/1c.2/x.json"):
        doc["entries"][1]["evidence"] = ref
        assert contracts.validate("features", doc) == [], ref
    doc["entries"][1]["evidence"] = "notes/x.json"
    assert contracts.validate("features", doc)
    handoff = json.loads((SAMPLES / "handoff.valid.json").read_text())
    handoff["evidence_refs"] = ["harness/state/evidence/live/x.json", "evidence/live/y.json"]
    assert contracts.validate("handoff", handoff) == []


def test_full_gate_covers_ui() -> None:
    m = manifest.load_manifest(MANIFEST)
    assert "pnpm --dir ui check" in m.gates["full"]
    assert m.gates["ui"] == ("pnpm --dir ui check",)


def test_real_manifest_guards_every_gate_set() -> None:
    m = manifest.load_manifest(MANIFEST)
    assert ("E_AGENT_TEST_PG_DSN", "E_AGENT_PG_DSN") in m.gate_guards["*"].distinct_databases


def test_research_accepts_new_files_only() -> None:
    m = manifest.load_manifest(MANIFEST)
    assert "research/**" in m.protected.read_only
    assert "research/**" in m.protected.create_only


def test_claude_code_configuration_outside_the_repository_is_denied() -> None:
    """H4.R14 lets the check-scope hook allow writes outside every harness checkout
    (scratchpad, memory) unless a denied_paths glob matches; Claude Code's own trust and
    permission files must stay out of reach."""
    from e_agent_harness.manifest import load_manifest, path_matches

    m = load_manifest(MANIFEST)
    for target in (
        "Users/someone/.claude.json",
        "Users/someone/.claude/settings.json",
        "Users/someone/.claude/settings.local.json",
    ):
        assert any(path_matches(target, p) for p in m.environment.denied_paths), target
    assert not any(
        path_matches("Users/someone/.claude/projects/x/memory/a.md", p)
        for p in m.environment.denied_paths
    )
