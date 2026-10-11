"""Structural conformance of the ag-* agent skills (spec 2026-10-11 §4-§5).

These tests prove the validator's rules; they cannot judge whether a criterion
is a good standard or whether a source supports it. Owner review does that.
"""

import importlib.util
import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "check_agent_skills", REPO / "scripts" / "check_agent_skills.py"
)
assert _spec is not None
assert _spec.loader is not None
cas = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = cas  # dataclasses resolve annotations through sys.modules
_spec.loader.exec_module(cas)

SOURCES = """# Sources

| ID | Source | URL | Tier | Accessed | Reading level | Notes |
|---|---|---|---|---|---|---|
| S-01 | WCAG 2.2 | https://www.w3.org/TR/WCAG22/ | T1 | 2026-10-11 | full | |
| S-07 | Summary-only normative source | https://example.org/s7 | T1 | 2026-10-11 | summary-only | |
| S-08 | Human-AI guidelines | https://example.org/hai | T2 | 2026-10-11 | partial | |
| S-13 | Pattern library | https://example.org/p | T4 | 2026-10-11 | full | |
| S-15 | Unreadable article | https://example.org/u | T4 | 2026-10-11 | unreadable | 403 |
"""

GOOD_CRITERION = """### AG-TEST-1 — Example

- **Statement:** Something testable.
- **Sources:** S-01 (SC 4.1.3), S-13 (Agent Status)
- **Enforcement:** test, review
- **Max severity:** Blocker
- **Evidence:** A screenshot.
"""


def make_repo(
    tmp_path: Path,
    *,
    standard: str = GOOD_CRITERION,
    extra: dict[str, str] | None = None,
    description: str = "Use when designing agentic UI.",
    link: bool = True,
) -> Path:
    skill = tmp_path / ".agents" / "skills" / "ag-ux-foundations"
    refs = skill / "references"
    refs.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        f"---\nname: ag-ux-foundations\ndescription: {description}\n---\n\n# Foundations\n\n"
        "See [standard](references/standard.md).\n"
    )
    (refs / "sources.md").write_text(SOURCES)
    (refs / "standard.md").write_text("# Standard\n\n## Group\n\n" + standard)
    for name, text in (extra or {}).items():
        (refs / name).parent.mkdir(parents=True, exist_ok=True)
        (refs / name).write_text(text)
    if link:
        claude = tmp_path / ".claude" / "skills"
        claude.mkdir(parents=True)
        os.symlink("../../.agents/skills/ag-ux-foundations", claude / "ag-ux-foundations")
    return tmp_path


def messages(root: Path) -> list[str]:
    return [str(p) for p in cas.check(root)]


def test_valid_fixture_has_no_problems(tmp_path):
    assert messages(make_repo(tmp_path)) == []


def test_missing_skills_dir_is_a_problem(tmp_path):
    assert any("no .agents/skills" in m for m in messages(tmp_path))


def test_frontmatter_name_must_match_directory(tmp_path):
    root = make_repo(tmp_path)
    skill_md = root / ".agents/skills/ag-ux-foundations/SKILL.md"
    skill_md.write_text(skill_md.read_text().replace("name: ag-ux-foundations", "name: ag-other"))
    assert any("name 'ag-other' does not match directory" in m for m in messages(root))


def test_frontmatter_rejects_extra_keys(tmp_path):
    root = make_repo(tmp_path)
    skill_md = root / ".agents/skills/ag-ux-foundations/SKILL.md"
    skill_md.write_text(skill_md.read_text().replace("---\n\n#", "license: MIT\n---\n\n#"))
    assert any("unexpected frontmatter keys: license" in m for m in messages(root))


def test_description_limits(tmp_path):
    root = make_repo(tmp_path, description="x" * 401)
    assert any("description is 401 characters" in m for m in messages(root))


def test_total_description_budget(tmp_path):
    root = make_repo(tmp_path, description="y" * 400)
    for i in range(5):
        d = root / ".agents/skills" / f"ag-extra-{i}"
        d.mkdir()
        (d / "SKILL.md").write_text(f"---\nname: ag-extra-{i}\ndescription: {'z' * 400}\n---\n")
        os.symlink(f"../../.agents/skills/ag-extra-{i}", root / ".claude/skills" / f"ag-extra-{i}")
    assert any("total description length 2400 exceeds 2000" in m for m in messages(root))


def test_claude_link_must_resolve_to_source(tmp_path):
    root = make_repo(tmp_path, link=False)
    assert any(".claude/skills/ag-ux-foundations is not a symlink" in m for m in messages(root))


def test_claude_link_wrong_target(tmp_path):
    root = make_repo(tmp_path, link=False)
    claude = root / ".claude" / "skills"
    claude.mkdir(parents=True)
    (root / "elsewhere").mkdir()
    os.symlink("../../elsewhere", claude / "ag-ux-foundations")
    assert any("does not resolve to .agents/skills/ag-ux-foundations" in m for m in messages(root))


def test_broken_relative_link(tmp_path):
    root = make_repo(tmp_path, extra={"metrics.md": "# M\n\nSee [x](missing.md).\n"})
    assert any("broken link 'missing.md'" in m for m in messages(root))


def test_external_and_anchor_links_are_not_checked(tmp_path):
    root = make_repo(
        tmp_path, extra={"metrics.md": "[a](https://x.org) [b](#top) [c](mailto:a@b.c)\n"}
    )
    assert messages(root) == []


def test_criterion_requires_all_fields(tmp_path):
    root = make_repo(
        tmp_path, standard=GOOD_CRITERION.replace("- **Evidence:** A screenshot.\n", "")
    )
    assert any("AG-TEST-1 missing field 'Evidence'" in m for m in messages(root))


def test_duplicate_criterion_id(tmp_path):
    root = make_repo(tmp_path, standard=GOOD_CRITERION + "\n" + GOOD_CRITERION)
    assert any("duplicate criterion AG-TEST-1" in m for m in messages(root))


def test_unknown_criterion_reference(tmp_path):
    root = make_repo(tmp_path, extra={"patterns.md": "# P\n\nMaps to AG-TEST-9.\n"})
    assert any("unknown criterion AG-TEST-9" in m for m in messages(root))


def test_unknown_source_reference(tmp_path):
    root = make_repo(tmp_path, standard=GOOD_CRITERION.replace("S-13 (Agent Status)", "S-99 (x)"))
    assert any("AG-TEST-1 cites unknown source S-99" in m for m in messages(root))


def test_source_citation_needs_locator(tmp_path):
    root = make_repo(tmp_path, standard=GOOD_CRITERION.replace("S-01 (SC 4.1.3)", "S-01"))
    assert any("AG-TEST-1 citation S-01 has no locator" in m for m in messages(root))


def test_invalid_enforcement(tmp_path):
    root = make_repo(tmp_path, standard=GOOD_CRITERION.replace("test, review", "lint"))
    assert any("AG-TEST-1 enforcement 'lint' not in" in m for m in messages(root))


def test_invalid_severity(tmp_path):
    root = make_repo(tmp_path, standard=GOOD_CRITERION.replace("Blocker", "Critical"))
    assert any("AG-TEST-1 max severity 'Critical' not in" in m for m in messages(root))


def test_blocker_requires_tier_one_or_two(tmp_path):
    root = make_repo(tmp_path, standard=GOOD_CRITERION.replace("S-01 (SC 4.1.3), ", ""))
    assert any("AG-TEST-1 is Blocker without a readable T1/T2 source" in m for m in messages(root))


def test_criterion_needs_readable_source(tmp_path):
    crit = GOOD_CRITERION.replace("S-01 (SC 4.1.3), S-13 (Agent Status)", "S-15 (principle 7)")
    crit = crit.replace("Blocker", "High")
    root = make_repo(tmp_path, standard=crit)
    assert any("AG-TEST-1 has no source read at full or partial" in m for m in messages(root))


def test_source_row_validation(tmp_path):
    bad = SOURCES.replace("| T1 | 2026-10-11 | full |", "| T9 | yesterday | skimmed |")
    root = make_repo(tmp_path, extra={"sources.md": bad})
    found = messages(root)
    assert any("S-01 tier 'T9'" in m for m in found)
    assert any("S-01 accessed 'yesterday'" in m for m in found)
    assert any("S-01 reading level 'skimmed'" in m for m in found)


def test_neutral_files_reject_product_terms(tmp_path):
    root = make_repo(tmp_path, extra={"patterns.md": "# P\n\nAs done in the Odoo bridge.\n"})
    assert any("patterns.md: product term 'Odoo'" in m for m in messages(root))


def test_product_file_may_name_product(tmp_path):
    root = make_repo(
        tmp_path, extra={"e-agent.md": "# e-agent\n\nApprovalPresentation is exact.\n"}
    )
    assert messages(root) == []


@pytest.mark.parametrize(
    ("text", "term"),
    [("WebFetch", "WebFetch"), ("apply_patch", "apply_patch"), ("$ag-ux-review", "$ag-")],
)
def test_skill_bodies_reject_agent_specific_tools(tmp_path, text, term):
    root = make_repo(tmp_path, extra={"metrics.md": f"# M\n\nRun {text} first.\n"})
    assert any(f"agent-specific term '{term}'" in m for m in messages(root))


def test_state_model_requires_all_states_and_fields(tmp_path):
    root = make_repo(
        tmp_path, extra={"state-model.md": "# States\n\n### Ready\n\n- **User need:** x\n"}
    )
    found = messages(root)
    assert any("state 'Ready' missing field 'Presentation'" in m for m in found)
    assert any("missing state 'Verified complete'" in m for m in found)


def test_repository_skills_conform():
    assert messages(REPO) == []


# --- Fix round 1 (review findings 1-6) ---

FULL_STATE_NAMES = (
    "Ready",
    "Working",
    "Needs input",
    "Blocked by rules",
    "Awaiting decision",
    "Decision invalidated",
    "Rejected",
    "Executing",
    "Verifying",
    "Outcome uncertain",
    "Failed",
    "Cancelled or stopped",
    "Verified complete",
)


def state_block(name: str, criteria: str = "AG-TEST-1") -> str:
    return (
        f"### {name}\n\n- **User need:** x\n- **Presentation:** x\n"
        f"- **Allowed actions:** x\n- **Forbidden:** x\n- **Criteria:** {criteria}\n\n"
    )


def test_product_terms_match_case_insensitively(tmp_path):
    root = make_repo(tmp_path, extra={"patterns.md": "# P\n\nAs in the odoo bridge and E-Agent.\n"})
    found = messages(root)
    assert any("patterns.md: product term 'odoo'" in m for m in found)
    assert any("patterns.md: product term 'E-Agent'" in m for m in found)


def test_neutrality_covers_subdirectories(tmp_path):
    root = make_repo(tmp_path, extra={"sub/x.md": "# X\n\nOdoo here.\n"})
    assert any("references/sub/x.md: product term 'Odoo'" in m for m in messages(root))


def test_product_term_not_matched_inside_words(tmp_path):
    text = "# P\n\nSee single-agent and realtime-voice-agents.\n"
    root = make_repo(tmp_path, extra={"patterns.md": text})
    assert not any("product term" in m for m in messages(root))


@pytest.mark.parametrize("text", ["e-agent", "E-Agent", "(e_agent)"])
def test_product_term_at_word_start_is_reported(tmp_path, text):
    root = make_repo(tmp_path, extra={"patterns.md": f"# P\n\nAs in {text}.\n"})
    assert any("product term" in m for m in messages(root))


@pytest.mark.parametrize(
    "description",
    [
        "Use when: x",
        "> folded",
        "| literal",
        "'quoted'",
        '"quoted"',
        "Use # no",
        "[list] x",
        "{map} x",
        "*alias x",
        "&anchor x",
        "!tag x",
        "%directive x",
        "@at x",
        "`tick` x",
    ],
)
def test_description_must_be_plain_scalar(tmp_path, description):
    root = make_repo(tmp_path, description=description)
    assert any("description must be a single plain YAML scalar" in m for m in messages(root))


def test_unparsable_source_row(tmp_path):
    bad = (
        SOURCES
        + "| S-16 | only three | cells |\n"
        + "| S-1 | x | https://x.org | T1 | 2026-10-11 | full | |\n"
    )
    root = make_repo(tmp_path, extra={"sources.md": bad})
    found = messages(root)
    assert any("unparsable source row: | S-16 | only three | cells |" in m for m in found)
    assert any("unparsable source row: | S-1 | x | https://x.org" in m for m in found)


def test_duplicate_source_id(tmp_path):
    dup = SOURCES + "| S-01 | Again | https://example.org/again | T1 | 2026-10-11 | full | |\n"
    root = make_repo(tmp_path, extra={"sources.md": dup})
    assert any("duplicate source S-01" in m for m in messages(root))


def test_source_requires_url(tmp_path):
    bad = SOURCES.replace("https://www.w3.org/TR/WCAG22/", "")
    root = make_repo(tmp_path, extra={"sources.md": bad})
    assert any("S-01 has no URL" in m for m in messages(root))


def test_impossible_date_rejected(tmp_path):
    bad = SOURCES.replace("| T1 | 2026-10-11 |", "| T1 | 2026-13-45 |")
    root = make_repo(tmp_path, extra={"sources.md": bad})
    assert any("S-01 accessed '2026-13-45' is not YYYY-MM-DD" in m for m in messages(root))


@pytest.mark.parametrize("raw", ["S-1", "s-01"])
def test_citation_must_be_canonical(tmp_path, raw):
    crit = GOOD_CRITERION.replace("S-01 (SC 4.1.3)", f"{raw} (SC 4.1.3)")
    root = make_repo(tmp_path, standard=crit)
    assert any(
        f"AG-TEST-1 citation '{raw}' is not a canonical S-nn ID" in m for m in messages(root)
    )


def test_duplicate_state_heading(tmp_path):
    text = "# States\n\n" + "".join(state_block(s) for s in FULL_STATE_NAMES)
    text += state_block("Ready")
    root = make_repo(tmp_path, extra={"state-model.md": text})
    assert any("duplicate state 'Ready'" in m for m in messages(root))


def test_state_criteria_must_cite_an_ag_id(tmp_path):
    text = "# States\n\n" + state_block("Working", criteria="none yet")
    root = make_repo(tmp_path, extra={"state-model.md": text})
    assert any("state 'Working' Criteria lists no AG criterion" in m for m in messages(root))


def test_full_state_model_is_clean(tmp_path):
    text = "# States\n\n" + "".join(state_block(s) for s in FULL_STATE_NAMES)
    root = make_repo(tmp_path, extra={"state-model.md": text})
    assert messages(root) == []


def test_cli_exit_codes_and_output(tmp_path, capsys):
    ok = make_repo(tmp_path / "ok")
    assert cas.main(["--root", str(ok)]) == 0
    assert capsys.readouterr().out == ""

    bad = make_repo(tmp_path / "bad", extra={"patterns.md": "# P\n\nOdoo.\n"})
    expected = messages(bad)
    assert expected
    assert cas.main(["--root", str(bad)]) == 1
    assert capsys.readouterr().out.splitlines() == expected


# --- Final review fixes (I-7 and related) ---


def test_summary_only_tier_one_source_does_not_license_blocker(tmp_path):
    crit = GOOD_CRITERION.replace("S-01 (SC 4.1.3)", "S-07 (Art. 14)")
    root = make_repo(tmp_path, standard=crit)
    assert any("AG-TEST-1 is Blocker without a readable T1/T2 source" in m for m in messages(root))


def test_readable_tier_two_source_licenses_blocker(tmp_path):
    crit = GOOD_CRITERION.replace("S-01 (SC 4.1.3)", "S-08 (G1)")
    assert messages(make_repo(tmp_path, standard=crit)) == []


def test_wrapped_sources_line_is_rejected(tmp_path):
    crit = GOOD_CRITERION.replace(
        "- **Sources:** S-01 (SC 4.1.3), S-13 (Agent Status)",
        "- **Sources:** S-01 (SC 4.1.3),\n  S-99, S-07",
    )
    root = make_repo(tmp_path, standard=crit)
    assert any(
        "AG-TEST-1 field 'Sources' wraps onto a continuation line; keep each field on one line" in m
        for m in messages(root)
    )


def test_wrapped_state_field_is_rejected(tmp_path):
    text = "# States\n\n" + state_block("Working").replace(
        "- **Forbidden:** x\n", "- **Forbidden:** x\ncontinued\n"
    )
    root = make_repo(tmp_path, extra={"state-model.md": text})
    assert any(
        "state 'Working' field 'Forbidden' wraps onto a continuation" in m for m in messages(root)
    )


def test_blank_line_and_next_heading_are_not_continuations(tmp_path):
    root = make_repo(
        tmp_path, standard=GOOD_CRITERION + "\n" + GOOD_CRITERION.replace("AG-TEST-1", "AG-TEST-2")
    )
    assert messages(root) == []


def test_duplicate_field_in_criterion(tmp_path):
    crit = GOOD_CRITERION + "- **Evidence:** Again.\n"
    root = make_repo(tmp_path, standard=crit)
    assert any("AG-TEST-1 duplicate field 'Evidence'" in m for m in messages(root))


def test_duplicate_field_in_state(tmp_path):
    text = "# States\n\n" + state_block("Working").replace(
        "- **Criteria:** AG-TEST-1\n", "- **Criteria:** AG-TEST-1\n- **Criteria:** AG-TEST-1\n"
    )
    root = make_repo(tmp_path, extra={"state-model.md": text})
    assert any("state 'Working' duplicate field 'Criteria'" in m for m in messages(root))
