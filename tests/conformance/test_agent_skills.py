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
    assert any("AG-TEST-1 is Blocker without a T1/T2 source" in m for m in messages(root))


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
    if not (REPO / ".agents" / "skills").is_dir():
        pytest.skip("skills not created yet (Task 8 removes this skip)")
    assert messages(REPO) == []
