# `ag-ux-foundations` (Phase 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the product-neutral agentic UI/UX standard (`ag-ux-foundations`) from primary sources. Make it discoverable by both Codex and Claude Code, and guard its structure and citations with an automated check.

**Architecture:** The skill is Markdown under `.agents/skills/ag-ux-foundations/`, the single source; `.claude/skills/ag-ux-foundations` is a symlink to it. Criteria have stable `AG-*` IDs. Each criterion cites `S-nn` sources with locators, and each source records its tier and reading level in `sources.md`. A stdlib-only Python validator (`scripts/check_agent_skills.py`) enforces structure, links, IDs, citations, the severity rule and product neutrality. A pytest module exercises it with fixtures and runs it against the repository.

**Tech Stack:** Markdown; Python 3.12 stdlib (`re`, `pathlib`, `dataclasses`, `argparse`); pytest via `uv run`; ruff.

**Spec:** [docs/superpowers/specs/2026-10-11-ag-ux-skills-design.md](../../../../docs/superpowers/specs/2026-10-11-ag-ux-skills-design.md). Read §1–§5, §7 and §8 phase 1 before starting.

**Scope:** spec phase 1 only. Phases 2–5 (`ag-ux-review` with the gap audit, brief, mockup, implement, docs alignment) each get their own plan after the owner reviews this standard (Task 9).

## Global Constraints

- **Authority:** e-agent's UI is a skeleton and an audit target only. No criterion may be derived from current e-agent code, enums, folder tree, mockups, design system or frontend guide (spec §1–2).
- **Tier R:** accepted ADRs, AGENTS.md rules and owner decisions are binding. They live only in `references/e-agent.md`. A conflict with them is recorded as an ADR proposal, never as a silent override.
- **Tiers:** T1 normative/governance, T2 research-grade human-AI guidelines, T3 vendor guidance and engineering references, T4 practitioner libraries and articles.
- **Severity rule:** `Max severity: Blocker` requires at least one cited source of tier T1 or T2. T3/T4-only criteria are capped at High (spec §6).
- **Primary sources only.** Read each source at its origin before citing it, and record the reading level as `full`, `partial`, `summary-only` or `unreadable`. Never list a source's contents from memory. A criterion must cite at least one source read at `full` or `partial`.
- **Neutrality:** every file under `references/` except `e-agent.md` is product-neutral. It contains none of: `e-agent`, `e_agent`, `Odoo`, `ApprovalPresentation`, `RunState`, `ActionState`.
- **Language:** all skill content is English (AGENTS.md).
- **Discovery:**
  - Codex scans `$CWD/.agents/skills` up to the repo root and follows symlinks.
  - Frontmatter is `name` and `description` only.
  - `name` equals the directory name and matches `^ag-[a-z0-9]+(-[a-z0-9]+)*$`.
  - Each description is ≤ 400 characters; all `ag-*` descriptions together are ≤ 2,000 characters.
- **Agent neutrality:** skill bodies name no agent-specific tools (no `WebFetch`, `WebSearch`, `apply_patch`, `$ag-…` invocations, "Bash tool").
- **Dirty working tree.** The repository has about 200 unrelated uncommitted changes. Every commit uses explicit paths (`git add <path>…`); never `git add -A`, `git add .` or `git commit -a`.
- **Commit trailer:** end commit messages with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

These input classes and failure modes are most likely to bite a user, most likely first. Each has a test in Task 1 unless noted.

1. **A criterion that cites only sources nobody could read** (`summary-only`/`unreadable`) looks authoritative but is unsupported. Expected: the validator rejects it (`test_criterion_needs_readable_source`).
2. **A citation with no locator** (`S-03` instead of `S-03 (Art. 14(4)(e))`) cannot be spot-checked, so reviewers cannot confirm that the source says what the criterion claims. Expected: rejected (`test_source_citation_needs_locator`).
3. **Description budget overflow:** Codex shortens descriptions first and may drop skills when the list exceeds its budget. Expected: per-skill and total limits are enforced (`test_description_limits`).
4. **A broken or misdirected `.claude/skills` symlink** (copied directory, wrong target, absent on checkout without symlink support). Claude silently loses the skill. Expected: rejected (`test_claude_link_must_resolve_to_source`). Whether Claude Code *follows* symlinked skills is verified manually in Task 8, because no unit test can prove it.
5. **Product identifiers leaking into the neutral standard** make option C (the neutral core) costly and let skeleton details become "standard". Expected: rejected (`test_neutral_files_reject_product_terms`).

---

## File Structure

| Path | Responsibility |
|---|---|
| `scripts/check_agent_skills.py` | Structural validator; `check(root) -> list[Problem]`; CLI exit code |
| `tests/conformance/test_agent_skills.py` | Fixture tests per rule, plus a repository check |
| `.agents/skills/ag-ux-foundations/SKILL.md` | Entry point: purpose, reading order, authority rules (≤ 120 lines) |
| `.agents/skills/ag-ux-foundations/references/sources.md` | Source canon: `S-nn` rows with tier, access date, reading level |
| `.agents/skills/ag-ux-foundations/references/standard.md` | Interaction criteria `AG-DISC…AG-SOC` |
| `.agents/skills/ag-ux-foundations/references/design-system.md` | `AG-DS-*` design-system requirements |
| `.agents/skills/ag-ux-foundations/references/frontend.md` | `AG-FE-*` rules, stack-decision table, Baseline rule, update process, trends backlog |
| `.agents/skills/ag-ux-foundations/references/state-model.md` | Normative 13-state agentic task model |
| `.agents/skills/ag-ux-foundations/references/patterns.md` | Practitioner patterns mapped to `AG-*` with apply/limit/exclude decisions |
| `.agents/skills/ag-ux-foundations/references/metrics.md` | Evaluation metrics `M-n` with methods |
| `.agents/skills/ag-ux-foundations/references/e-agent.md` | Tier-R requirements `EA-n` for e-agent |
| `.claude/skills/ag-ux-foundations` | Symlink → `../../.agents/skills/ag-ux-foundations` |
| `AGENTS.md` | New short "UI/UX skills" section |

### Shared formats (all tasks use these exactly)

**Criterion block.** Used in `standard.md`, `design-system.md` and `frontend.md`. The heading uses an em dash `—`; field lines appear in this order:

```markdown
### AG-APPR-1 — Exact consequential action

- **Statement:** Before any consequential action, the user sees the exact action: target system and resource, operation, every material value, consequences and reversibility.
- **Sources:** S-08 (G16), S-03 (Art. 14(4)(c)), S-13 (Approval Queues & Escalation: decision-ready context)
- **Enforcement:** test, review
- **Max severity:** Blocker
- **Evidence:** Screenshot or DOM of the decision surface showing each element; conformance test name if automated.
- **Notes:** (optional) reconciliation or limits.
```

- **Sources:** comma-separated `S-nn (locator)`. Every `S-nn` must be followed by a parenthesised locator.
- **Enforcement:** comma-separated subset of `gate`, `test`, `review`.
- **Max severity:** one of `Low`, `Medium`, `High`, `Blocker`.

**Source row** (`sources.md`), a 7-column table:

```markdown
| ID | Source | URL | Tier | Accessed | Reading level | Notes |
|---|---|---|---|---|---|---|
| S-03 | EU AI Act, Article 14 (Human oversight) | https://artificialintelligenceact.eu/article/14/ | T1 | 2026-10-11 | full | Binding for high-risk systems from 2027-12-02 (Annex III) |
```

**State block** (`state-model.md`):

```markdown
### Awaiting decision

- **User need:** …
- **Presentation:** …
- **Allowed actions:** …
- **Forbidden:** …
- **Criteria:** AG-APPR-1, AG-APPR-4
```

---

### Task 1: Skill validator and its tests

**Files:**
- Create: `scripts/check_agent_skills.py`
- Create: `tests/conformance/test_agent_skills.py`

**Interfaces:**
- Produces: `check(root: Path) -> list[Problem]`; `Problem(path: str, message: str)` with `__str__` → `"path: message"`; CLI `uv run python scripts/check_agent_skills.py [--root PATH]`, exit 0 when there are no problems, otherwise 1 with one problem per line. Tasks 2–8 run the CLI after each content change.

- [ ] **Step 1: Write the failing tests**

Create `tests/conformance/test_agent_skills.py`:

```python
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
        "See [standard](../../../../docs/superpowers/plans/references/standard.md).\n"
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
    root = make_repo(tmp_path, extra={"metrics.md": "# M\n\nSee [x](../../../../docs/superpowers/plans/missing.md).\n"})
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/conformance/test_agent_skills.py -v`

Expected: collection ERROR, `FileNotFoundError` for `scripts/check_agent_skills.py`.

- [ ] **Step 3: Write the implementation**

Create `scripts/check_agent_skills.py`:

```python
"""Validate the ag-* agent skills: structure, discovery links and citation integrity.

Structural checks only. They cannot judge whether a criterion is a good standard
or whether a cited source supports it; owner review and spot checks do that.
Spec: docs/superpowers/specs/2026-10-11-ag-ux-skills-design.md.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

NAME_RE = re.compile(r"^ag-[a-z0-9]+(?:-[a-z0-9]+)*$")
MAX_DESCRIPTION = 400
MAX_TOTAL_DESCRIPTION = 2000
CRITERION = r"AG-[A-Z0-9]+-\d+"
DEF_RE = re.compile(rf"^### ({CRITERION}) — \S", re.M)
REF_RE = re.compile(rf"\b({CRITERION})\b")
CITATION_RE = re.compile(r"\b(S-\d{2})\b(\s*\([^)]+\))?")
LINK_RE = re.compile(r"\]\(([^)\s]+)\)")
FIELD_RE = re.compile(r"^- \*\*([^*:]+):\*\*\s*(.*)$", re.M)
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TIERS = {"T1", "T2", "T3", "T4"}
READING = {"full", "partial", "summary-only", "unreadable"}
ENFORCEMENT = {"gate", "test", "review"}
SEVERITIES = {"Low", "Medium", "High", "Blocker"}
CRITERION_FIELDS = ("Statement", "Sources", "Enforcement", "Max severity", "Evidence")
CRITERION_FILES = ("standard.md", "design-system.md", "frontend.md")
STATES = (
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
STATE_FIELDS = ("User need", "Presentation", "Allowed actions", "Forbidden", "Criteria")
PRODUCT_RE = re.compile(r"e-agent|e_agent|Odoo|ApprovalPresentation|RunState|ActionState")
PRODUCT_FILE = "e-agent.md"
AGENT_TERMS = ("WebFetch", "WebSearch", "apply_patch", "$ag-", "Bash tool")


@dataclass(frozen=True)
class Problem:
    path: str
    message: str

    def __str__(self) -> str:
        return f"{self.path}: {self.message}"


def _frontmatter(text: str) -> dict[str, str] | None:
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---\n", 4)
    if end < 0:
        return None
    pairs: dict[str, str] = {}
    for line in text[4:end].splitlines():
        key, sep, value = line.partition(":")
        if sep:
            pairs[key.strip()] = value.strip()
    return pairs


def _rel(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _check_skill(root: Path, skill: Path, problems: list[Problem]) -> int:
    skill_md = skill / "SKILL.md"
    if not skill_md.is_file():
        problems.append(Problem(_rel(root, skill), "missing SKILL.md"))
        return 0
    meta = _frontmatter(skill_md.read_text())
    where = _rel(root, skill_md)
    if meta is None:
        problems.append(Problem(where, "missing frontmatter"))
        return 0
    extra = sorted(set(meta) - {"name", "description"})
    if extra:
        problems.append(Problem(where, f"unexpected frontmatter keys: {', '.join(extra)}"))
    name = meta.get("name", "")
    if name != skill.name:
        problems.append(Problem(where, f"name '{name}' does not match directory '{skill.name}'"))
    if not NAME_RE.match(skill.name):
        problems.append(Problem(where, f"directory '{skill.name}' does not match ag-* naming"))
    description = meta.get("description", "")
    if not description:
        problems.append(Problem(where, "empty description"))
    elif len(description) > MAX_DESCRIPTION:
        problems.append(
            Problem(where, f"description is {len(description)} characters (max {MAX_DESCRIPTION})")
        )
    link = root / ".claude" / "skills" / skill.name
    if not link.is_symlink():
        problems.append(Problem(_rel(root, link), f"{_rel(root, link)} is not a symlink"))
    elif link.resolve() != skill.resolve():
        problems.append(
            Problem(_rel(root, link), f"does not resolve to .agents/skills/{skill.name}")
        )
    return len(description)


def _check_links(root: Path, path: Path, text: str, problems: list[Problem]) -> None:
    for target in LINK_RE.findall(text):
        if re.match(r"^[a-z]+:", target) or target.startswith("#"):
            continue
        file_part = target.split("#", 1)[0]
        if file_part and not (path.parent / file_part).exists():
            problems.append(Problem(_rel(root, path), f"broken link '{target}'"))


def _parse_sources(root: Path, path: Path, problems: list[Problem]) -> dict[str, tuple[str, str]]:
    sources: dict[str, tuple[str, str]] = {}
    for line in path.read_text().splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) != 7 or not re.match(r"^S-\d{2}$", cells[0]):
            continue
        sid, _title, _url, tier, accessed, reading, _notes = cells
        where = _rel(root, path)
        if tier not in TIERS:
            problems.append(Problem(where, f"{sid} tier '{tier}' not in {sorted(TIERS)}"))
        if not DATE_RE.match(accessed):
            problems.append(Problem(where, f"{sid} accessed '{accessed}' is not YYYY-MM-DD"))
        if reading not in READING:
            problems.append(
                Problem(where, f"{sid} reading level '{reading}' not in {sorted(READING)}")
            )
        sources[sid] = (tier, reading)
    return sources


def _blocks(text: str, start_re: re.Pattern[str]) -> list[tuple[str, str]]:
    matches = list(start_re.finditer(text))
    out = []
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[m.end() : end]
        stop = re.search(r"^#{2,3} ", body, re.M)
        out.append((m.group(1), body[: stop.start()] if stop else body))
    return out


def _check_criteria(
    root: Path,
    path: Path,
    sources: dict[str, tuple[str, str]],
    defined: set[str],
    problems: list[Problem],
) -> None:
    where = _rel(root, path)
    for cid, body in _blocks(path.read_text(), DEF_RE):
        if cid in defined:
            problems.append(Problem(where, f"duplicate criterion {cid}"))
        defined.add(cid)
        fields = dict(FIELD_RE.findall(body))
        for name in CRITERION_FIELDS:
            if not fields.get(name, "").strip():
                problems.append(Problem(where, f"{cid} missing field '{name}'"))
        tiers: set[str] = set()
        readable = False
        for sid, locator in CITATION_RE.findall(fields.get("Sources", "")):
            if sid not in sources:
                problems.append(Problem(where, f"{cid} cites unknown source {sid}"))
                continue
            if not locator:
                problems.append(Problem(where, f"{cid} citation {sid} has no locator"))
            tier, reading = sources[sid]
            tiers.add(tier)
            readable = readable or reading in {"full", "partial"}
        if fields.get("Sources") and not readable:
            problems.append(Problem(where, f"{cid} has no source read at full or partial"))
        for kind in (k.strip() for k in fields.get("Enforcement", "").split(",") if k.strip()):
            if kind not in ENFORCEMENT:
                problems.append(
                    Problem(where, f"{cid} enforcement '{kind}' not in {sorted(ENFORCEMENT)}")
                )
        severity = fields.get("Max severity", "").strip()
        if severity and severity not in SEVERITIES:
            problems.append(
                Problem(where, f"{cid} max severity '{severity}' not in {sorted(SEVERITIES)}")
            )
        if severity == "Blocker" and not tiers & {"T1", "T2"}:
            problems.append(Problem(where, f"{cid} is Blocker without a T1/T2 source"))


def _check_states(root: Path, path: Path, problems: list[Problem]) -> None:
    where = _rel(root, path)
    blocks = dict(_blocks(path.read_text(), re.compile(r"^### (.+)$", re.M)))
    for state in STATES:
        if state not in blocks:
            problems.append(Problem(where, f"missing state '{state}'"))
            continue
        fields = dict(FIELD_RE.findall(blocks[state]))
        for name in STATE_FIELDS:
            if not fields.get(name, "").strip():
                problems.append(Problem(where, f"state '{state}' missing field '{name}'"))


def check(root: Path) -> list[Problem]:
    problems: list[Problem] = []
    skills_dir = root / ".agents" / "skills"
    if not skills_dir.is_dir():
        return [Problem(".", "no .agents/skills directory")]
    skills = sorted(p for p in skills_dir.iterdir() if p.is_dir() and p.name.startswith("ag-"))
    total = sum(_check_skill(root, s, problems) for s in skills)
    if total > MAX_TOTAL_DESCRIPTION:
        problems.append(
            Problem(
                ".agents/skills",
                f"total description length {total} exceeds {MAX_TOTAL_DESCRIPTION}",
            )
        )
    files = sorted(f for s in skills for f in s.rglob("*.md"))
    refs = skills_dir / "ag-ux-foundations" / "references"
    sources: dict[str, tuple[str, str]] = {}
    if (refs / "sources.md").is_file():
        sources = _parse_sources(root, refs / "sources.md", problems)
    defined: set[str] = set()
    for name in CRITERION_FILES:
        if (refs / name).is_file():
            _check_criteria(root, refs / name, sources, defined, problems)
    if (refs / "state-model.md").is_file():
        _check_states(root, refs / "state-model.md", problems)
    for path in files:
        text = path.read_text()
        where = _rel(root, path)
        _check_links(root, path, text, problems)
        for cid in sorted(set(REF_RE.findall(text)) - defined):
            problems.append(Problem(where, f"unknown criterion {cid}"))
        for term in AGENT_TERMS:
            if term in text:
                problems.append(Problem(where, f"agent-specific term '{term}'"))
        if path.parent == refs and path.name != PRODUCT_FILE:
            for term in sorted(set(PRODUCT_RE.findall(text))):
                problems.append(Problem(where, f"product term '{term}'"))
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)
    problems = check(args.root.resolve())
    for problem in problems:
        print(problem)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
```

The neutral-file test expects the message `patterns.md: product term 'Odoo'`. `Problem.__str__` prints the path relative to root (`.agents/skills/ag-ux-foundations/references/patterns.md: product term 'Odoo'`), and the test uses substring matching, so it passes.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/conformance/test_agent_skills.py -v`

Expected: 26 passed, 1 skipped (`test_repository_skills_conform`, because `.agents/skills` does not exist yet). This code was dry-run on 2026-10-11 in a scratch copy with exactly this result.

- [ ] **Step 5: Lint**

Run: `uv run ruff check scripts/check_agent_skills.py tests/conformance/test_agent_skills.py && uv run ruff format --check scripts/check_agent_skills.py tests/conformance/test_agent_skills.py`

Expected: `All checks passed!` and `2 files already formatted` (also dry-run verified). If format reports differences, run `uv run ruff format` on these two files only and re-run the tests.

- [ ] **Step 6: Commit**

```bash
git add scripts/check_agent_skills.py tests/conformance/test_agent_skills.py
git commit -m "test: structural validator for ag-* agent skills

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Source canon (`sources.md`)

**Files:**
- Create: `.agents/skills/ag-ux-foundations/references/sources.md`

**Interfaces:**
- Consumes: the source-row format; the validator CLI from Task 1.
- Produces: source IDs `S-01`…`S-20` with tier and reading level, which Tasks 3–7 cite. Keep these IDs fixed; add new sources only as `S-21`+.

- [ ] **Step 1: Read every source at its origin**

For each row below, open the URL itself (not a summary) and read the parts the criteria will cite. Record the reading level honestly:
- `full`: the whole relevant document was read.
- `partial`: named sections only; list them in Notes.
- `summary-only`: only a secondary summary was available.
- `unreadable`: blocked; record the reason (for example "HTTP 403").

Retry known-difficult sources once in a different way:
- Apple HIG is client-rendered; try `https://developer.apple.com/tutorials/data/design/human-interface-guidelines/generative-ai.json`.
- For the Microsoft paper, try the ACM DL page `https://dl.acm.org/doi/10.1145/3290605.3300233`.

Do not paraphrase content from memory anywhere.

| ID | Source | URL | Tier |
|---|---|---|---|
| S-01 | W3C WCAG 2.2 | https://www.w3.org/TR/WCAG22/ | T1 |
| S-02 | W3C WAI-ARIA Authoring Practices Guide | https://www.w3.org/WAI/ARIA/apg/ | T1 |
| S-03 | EU AI Act, Article 14 (Human oversight) | https://artificialintelligenceact.eu/article/14/ | T1 |
| S-04 | EU AI Act, Article 50 (Transparency obligations) | https://artificialintelligenceact.eu/article/50/ | T1 |
| S-05 | NIST AI Risk Management Framework 1.0 | https://www.nist.gov/itl/ai-risk-management-framework | T1 |
| S-06 | OWASP Top 10 for Agentic Applications (2026) | https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/ | T1 |
| S-07 | ISO 9241-110:2020 Interaction principles | https://www.iso.org/standard/75258.html | T1 |
| S-08 | Amershi et al., Guidelines for Human-AI Interaction (CHI 2019) and HAX library | https://www.microsoft.com/en-us/haxtoolkit/library/ | T2 |
| S-09 | Google PAIR People + AI Guidebook | https://pair.withgoogle.com/guidebook-v2/ | T2 |
| S-10 | Microsoft Design, UX design for agents (2025-04-11) | https://microsoft.design/articles/ux-design-for-agents/ | T3 |
| S-11 | IBM Carbon for AI | https://www.carbondesignsystem.com/building-blocks/foundations/carbon-for-ai | T3 |
| S-12 | Apple HIG, Generative AI | https://developer.apple.com/design/human-interface-guidelines/generative-ai | T3 |
| S-13 | Agentic Design, UI/UX & Human-AI Interaction patterns | https://agentic-design.ai/patterns/ui-ux-patterns | T4 |
| S-14 | UX Pilot, Enterprise UX design | https://uxpilot.ai/blogs/enterprise-ux-design | T4 |
| S-15 | Vasquez, Agentic UX: 7 principles | https://medium.com/design-bootcamp/agentic-ux-7-principles-for-designing-systems-with-agents-019512c2caa9 | T4 |
| S-16 | web.dev Baseline | https://web.dev/baseline | T3 |
| S-17 | Design Tokens Community Group format (2025.10) | https://www.designtokens.org/tr/2025.10/format/ | T3 |
| S-18 | OpenAPI Specification 3.1 | https://spec.openapis.org/oas/v3.1.0 | T1 |
| S-19 | web.dev Core Web Vitals (INP) | https://web.dev/articles/inp | T3 |
| S-20 | React docs, Choosing the State Structure | https://react.dev/learn/choosing-the-state-structure | T3 |

Notes to carry where verified:
- **S-03:** binding for high-risk systems from 2027-12-02 (Annex III) or 2028-08-02 (Annex I); used here as a design bar.
- **S-04:** applies from 2026-08-02.
- **S-13:** list the sub-pages read, at minimum the 32 pattern slugs. Read every sub-page you cite (the pattern index page alone does not support a criterion).
- **S-15:** if it is still unreadable, mark it `unreadable`. It may then appear only in `patterns.md` prose, never as a criterion's only source.

- [ ] **Step 2: Write `sources.md`**

Write a title, then one paragraph stating the tier meanings and the reading-level vocabulary from Global Constraints. Then write the 7-column table in the exact source-row format, one row per source, with `Accessed` set to the date you actually read it.

- [ ] **Step 3: Validate**

Run: `uv run python scripts/check_agent_skills.py`

Expected: problems only of the kind "missing SKILL.md", "no symlink" or "unknown criterion" (later tasks fix those). There must be **no** `tier`, `accessed` or `reading level` problems for `sources.md`.

- [ ] **Step 4: Commit**

```bash
git add .agents/skills/ag-ux-foundations/references/sources.md
git commit -m "docs(skills): ag-ux-foundations source canon with reading levels

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Interaction criteria, part 1 (disclosure, context, status, control)

**Files:**
- Create: `.agents/skills/ag-ux-foundations/references/standard.md`

**Interfaces:**
- Consumes: `S-nn` IDs from Task 2.
- Produces: criterion IDs `AG-DISC-1..3`, `AG-CTX-1..2`, `AG-STAT-1..4`, `AG-CTRL-1..5`, which Tasks 5–7 reference.

- [ ] **Step 1: Write the file header**

Start `standard.md` with:
- `# Agentic UI/UX standard`.
- A paragraph explaining how to read a criterion block (format above) and that criteria are product-neutral.
- The severity rule (Blocker needs a T1/T2 source).
- The conflict rules from spec §2, written neutrally ("a product's binding requirements" instead of the product name).
- The reconciliation of "confidence and reasoning" from spec §2, written neutrally.
- `## Disclose and set expectations` as the first group heading.

- [ ] **Step 2: Write each criterion, verifying its sources**

For every row below:
1. Open each cited source at the locator.
2. Confirm the source supports the statement. If it supports less, narrow the statement. If no T1/T2 source supports it, lower `Max severity` to High.
3. Write the block in the criterion format. The heading title is the short title shown.

**`## Disclose and set expectations`**

| ID — title | Statement | Sources (verify locators) | Enforcement | Max severity |
|---|---|---|---|---|
| AG-DISC-1 — AI interaction disclosed | People are informed they are interacting with an AI system, clearly and distinguishably, at the latest at first interaction, in an accessible form | S-04 (Art. 50(1), 50(5)), S-08 (G1), S-11 (AI identity) | review | Blocker |
| AG-DISC-2 — Capabilities and limits stated | The entry surface states what the agent can do, which systems it can act on, and what it cannot do, in the user's context | S-08 (G1), S-03 (Art. 14(4)(a)), S-10 (Core: transparency) | review | Blocker |
| AG-DISC-3 — Performance claims only where measured | How well the agent performs is stated only from measured evaluation, with its scope; unmeasured quality claims are absent | S-08 (G2), S-05 (Valid and reliable; Accountable and transparent) | review | High |

**`## Context and timing`**

| ID — title | Statement | Sources | Enforcement | Max severity |
|---|---|---|---|---|
| AG-CTX-1 — Invoked in the work context | The agent is reachable inside the user's current workflow, and launching it carries the relevant context (for example the open record) without re-entry | S-08 (G4), S-10 (Space: accessible), S-15 (embed in workflows), S-01 (SC 3.3.7 Redundant Entry) | review | High |
| AG-CTX-2 — Proactivity timed and actionable | Proactive engagement is timed to the user's context, does not interrupt focused work, and arrives as an actionable artifact rather than a bare alert | S-08 (G3), S-10 (Now: nudging more than notifying) | review | Medium |

**`## Status and activity`**

| ID — title | Statement | Sources | Enforcement | Max severity |
|---|---|---|---|---|
| AG-STAT-1 — Status always visible | The agent's current state is always visible, in plain language that matches the normative state model | S-10 (Core: status visible), S-03 (Art. 14(4)(a) monitor operation), S-07 (self-descriptiveness) | test, review | Blocker |
| AG-STAT-2 — Activity from real events only | Progress and activity reflect only real system events; no simulated progress, estimated times or invented activity text | S-03 (Art. 14(4)(a)), S-05 (Accountable and transparent), S-13 (Agent Status: watch out) | review | Blocker |
| AG-STAT-3 — Staleness is distinct | Lost connection, reconnection and stale data are shown distinctly and never presented as current or complete | S-07 (self-descriptiveness), S-01 (SC 4.1.3) | test, review | High |
| AG-STAT-4 — Accessible status announcements | State changes are announced politely to assistive technology without moving focus; streamed text is not announced token by token | S-01 (SC 4.1.3), S-02 (live regions) | test | Blocker |

**`## Control and oversight`**

| ID — title | Statement | Sources | Enforcement | Max severity |
|---|---|---|---|---|
| AG-CTRL-1 — Stop to a safe state | The user can stop the agent at any time; stopping reaches a defined safe state and reports the status of any in-flight action | S-03 (Art. 14(4)(e)), S-06 (ASI10 Rogue agents) | test, review | Blocker |
| AG-CTRL-2 — Efficient invocation, dismissal and correction | Users can invoke, dismiss and correct the agent (edit a proposal, refine the request) without restarting the task | S-08 (G7, G8, G9) | review | High |
| AG-CTRL-3 — Initiative is visible | Who currently holds initiative (user or agent) is always visible; the agent never takes over input without a visible handoff | S-13 (Mixed-Initiative), S-10 (Core: control) | review | High |
| AG-CTRL-4 — Override, disregard, reverse | The user can reject any proposal, disregard any output and, where the action allows, reverse it; whether reversal is possible is stated before acting | S-03 (Art. 14(4)(d)), S-08 (G9) | review | Blocker |
| AG-CTRL-5 — Global controls | Users can set agent preferences and turn agent capabilities off, and can see those settings | S-08 (G17), S-10 (Core: turn agents on or off) | review | Medium |

- [ ] **Step 3: Validate**

Run: `uv run python scripts/check_agent_skills.py`

Expected: no problems that mention `standard.md`. Problems about other missing files may remain.

- [ ] **Step 4: Commit**

```bash
git add .agents/skills/ag-ux-foundations/references/standard.md
git commit -m "docs(skills): AG disclosure, context, status and control criteria

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Interaction criteria, part 2 (decisions, explanation, uncertainty, over time, trust boundary, accessibility, enterprise, social)

**Files:**
- Modify: `.agents/skills/ag-ux-foundations/references/standard.md` (append groups)

**Interfaces:**
- Consumes: `S-nn` IDs; the criterion format.
- Produces: `AG-APPR-1..7`, `AG-EXPL-1..4`, `AG-UNC-1..4`, `AG-MEM-1..4`, `AG-ID-1..4`, `AG-A11Y-1..4`, `AG-ENT-1..4`, `AG-SOC-1..2`.

- [ ] **Step 1: Write each criterion, verifying its sources** (same procedure as Task 3, Step 2)

**`## Consequential actions and decisions`**

| ID — title | Statement | Sources | Enforcement | Max severity |
|---|---|---|---|---|
| AG-APPR-1 — Exact consequential action | Before any consequential action the user sees the exact action: target system and resource, operation, every material value, consequences and reversibility | S-08 (G16), S-03 (Art. 14(4)(c)), S-13 (Approval Queues & Escalation: decision-ready context) | test, review | Blocker |
| AG-APPR-2 — One decision, one exact action | Each decision authorizes exactly the action shown; a grouped decision lists every action it covers | S-06 (ASI02 Tool misuse; ASI09 Human-agent trust exploitation), S-03 (Art. 14(4)(c)) | test | Blocker |
| AG-APPR-3 — No hidden material terms | Material terms are never only inside collapsed disclosure, truncation or unindicated scroll regions on the decision surface | S-06 (ASI09), S-01 (SC 1.4.10) | test, review | Blocker |
| AG-APPR-4 — Friction against automation bias | Friction is proportional to risk: irreversible actions need explicit confirmation; approve is never the default focus or pre-selected; no approval from a notification alone | S-03 (Art. 14(4)(b)), S-06 (ASI09), S-11 (mindful friction) | test, review | Blocker |
| AG-APPR-5 — Invalidated decisions are visible | When facts behind a pending decision change, or the decision expires, it is visibly invalidated and requires re-review | S-06 (ASI09), S-13 (Approval Queues: state rehydration) | test | Blocker |
| AG-APPR-6 — Decided, executed and verified are separate | Labels distinguish decided, executed (committed) and verified outcome; success is claimed only after independent verification | S-03 (Art. 14(4)(a), 14(4)(c)), S-05 (Valid and reliable) | test, review | Blocker |
| AG-APPR-7 — Risk tier comes from policy | The approval requirement or risk tier shown comes from system policy; the interface never lowers it or offers a path around it | S-06 (ASI03 Identity & privilege abuse), S-13 (Approval Queues: risk tiers) | test | Blocker |

**`## Explanation and evidence`**

| ID — title | Statement | Sources | Enforcement | Max severity |
|---|---|---|---|---|
| AG-EXPL-1 — Source-grounded rationale | "Why" is explained by the facts used, rules applied and their findings, attributable to sources; model chain-of-thought is never presented as explanation | S-08 (G11), S-05 (Explainable and interpretable), S-11 (explainability) | review | High |
| AG-EXPL-2 — Inspectable sources | Each claim links to its source with observation time; restricted or missing sources are stated rather than omitted | S-08 (G11), S-11 (source attribution), S-13 (Trust and Transparency) | review | High |
| AG-EXPL-3 — Progressive explanation | Explanation starts with a summary, details on demand, at most three levels, and critical information is never only in a collapsed level | S-13 (Progressive Disclosure), S-11 (progressive explainability) | review | Medium |
| AG-EXPL-4 — Calibrated uncertainty only | Uncertainty is expressed qualitatively, or numerically only when calibrated against measured accuracy | S-08 (G2), S-10 (Core: embrace uncertainty), S-13 (Confidence Visualization: false precision) | review | High |

**`## Uncertainty and failure`**

| ID — title | Statement | Sources | Enforcement | Max severity |
|---|---|---|---|---|
| AG-UNC-1 — Clarify when in doubt | An ambiguous or under-specified request produces a focused clarification that keeps the task context, not a guess | S-08 (G10), S-15 (gather timely inputs) | review | High |
| AG-UNC-2 — Uncertain outcome is explicit | When an action's effect is unknown, the interface says so, explains the possible effect and offers a safe check; it never offers a blind retry of a possibly-completed action | S-06 (ASI08 Cascading failures), S-07 (use error robustness) | test, review | Blocker |
| AG-UNC-3 — Actionable, persistent errors | Errors state problem, cause and an authorized next step, in plain language, next to the affected action; a transient notice is never the only record | S-01 (SC 3.3.1, 3.3.3), S-13 (Error Handling and Recovery), S-07 (use error robustness) | test, review | Blocker |
| AG-UNC-4 — Missing is never defaulted | Missing access or data is stated with how to resolve it; it is never shown as an empty, zero, granted or connected value | S-07 (self-descriptiveness), S-05 (Valid and reliable) | test, review | High |

**`## Over time`**

| ID — title | Statement | Sources | Enforcement | Max severity |
|---|---|---|---|---|
| AG-MEM-1 — Work survives context changes | Recent interactions, drafts and the active task survive navigation, layout or appearance changes and return visits within the retention policy | S-08 (G12), S-10 (Past: history) | test | High |
| AG-MEM-2 — Adapt cautiously and visibly | Learning or adaptation is visible, reversible and user-controlled; behavior never changes silently | S-08 (G13, G14) | review | Medium |
| AG-MEM-3 — Granular feedback | Users can give feedback on a specific output or action | S-08 (G15), S-09 (Feedback + Control) | review | Medium |
| AG-MEM-4 — Notify about changes | Changes to capabilities, policies or behavior are announced to affected users | S-08 (G18) | review | Medium |

**`## Trust boundary`**

| ID — title | Statement | Sources | Enforcement | Max severity |
|---|---|---|---|---|
| AG-ID-1 — Origin is distinguishable | AI-generated content, system-verified facts and user content are visually and semantically distinguishable | S-04 (Art. 50(2)), S-11 (AI identity), S-13 (Trust and Transparency: AI content markers) | review | Blocker |
| AG-ID-2 — Untrusted content is inert | Model output and retrieved or user-supplied content render as inert text: no active markup, auto-loaded remote resources or controls, and nothing that can imitate system UI or a decision surface | S-06 (ASI01 Agent goal hijack; ASI09) | test | Blocker |
| AG-ID-3 — Identity and connection are not model-chosen | The acting identity, credentials and connection are chosen by system policy, shown to the user, and never selected by model output | S-06 (ASI03) | test | Blocker |
| AG-ID-4 — No secrets in the client | Secrets and credentials are never displayed, logged to the client, placed in URLs or persisted in browser storage | S-06 (ASI03), S-05 (Secure and resilient) | test | Blocker |

**`## Accessibility`**

| ID — title | Statement | Sources | Enforcement | Max severity |
|---|---|---|---|---|
| AG-A11Y-1 — WCAG 2.2 AA in every state | Every state of every surface conforms to WCAG 2.2 Level AA | S-01 (Conformance, Level AA) | test, review | Blocker |
| AG-A11Y-2 — APG interaction semantics | Dialogs, disclosures, tabs, menus and listboxes follow APG patterns, including the explicit choice between modal and non-modal dialogs and focus on open, close and return | S-02 (Dialog, Disclosure, Tabs, Listbox patterns) | test | Blocker |
| AG-A11Y-3 — Reflow, resize and user preferences | Surfaces reflow at 320 CSS px, support 200% text, and honour forced colours and reduced motion | S-01 (SC 1.4.10, 1.4.4, 2.3.3) | test | Blocker |
| AG-A11Y-4 — Not colour alone; sufficient contrast | Status and meaning never rely on colour alone; text, non-text and focus indicators meet contrast and are not obscured | S-01 (SC 1.4.1, 1.4.3, 1.4.11, 2.4.11) | test | Blocker |

**`## Enterprise use`**

| ID — title | Statement | Sources | Enforcement | Max severity |
|---|---|---|---|---|
| AG-ENT-1 — Role-appropriate views | The interface reflects the user's role; unavailable actions are absent or explained, never enabled and then failing | S-14 (role-based access), S-07 (suitability for the user's tasks) | test, review | High |
| AG-ENT-2 — Efficiency with learnability | Frequent tasks have short keyboard-operable paths; icon-only controls have accessible names and visible labels or tooltips; contextual help is available | S-14 (efficiency, contextual help), S-07 (learnability), S-01 (SC 3.2.6) | review | Medium |
| AG-ENT-3 — Consistent across placements | Components and behavior are consistent across every placement (embedded, docked, full page) | S-14 (design system), S-07 (conformity with user expectations) | test, review | Medium |
| AG-ENT-4 — Localization and long content | All copy is localizable; long translated strings and long identifiers do not break layout or truncate meaning | S-07 (suitability), S-01 (SC 1.4.10) | test | Medium |

**`## Social context`**

| ID — title | Statement | Sources | Enforcement | Max severity |
|---|---|---|---|---|
| AG-SOC-1 — Match social and domain norms | Tone and terminology match the users' professional and cultural norms | S-08 (G5), S-10 (Now: tailor to norms) | review | Medium |
| AG-SOC-2 — Mitigate social biases | Content and suggestions about people avoid reinforcing social biases | S-08 (G6), S-05 (Fair, with harmful bias managed) | review | High |

- [ ] **Step 2: Validate**

Run: `uv run python scripts/check_agent_skills.py`

Expected: no problems that mention `standard.md`.

- [ ] **Step 3: Self-check neutrality and evidence wording**

Run: `grep -n -E "e-agent|e_agent|Odoo|ApprovalPresentation|RunState|ActionState" .agents/skills/ag-ux-foundations/references/standard.md`

Expected: no output.

- [ ] **Step 4: Commit**

```bash
git add .agents/skills/ag-ux-foundations/references/standard.md
git commit -m "docs(skills): AG decision, explanation, uncertainty, trust, a11y and enterprise criteria

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Normative state model, patterns and metrics

**Files:**
- Create: `.agents/skills/ag-ux-foundations/references/state-model.md`
- Create: `.agents/skills/ag-ux-foundations/references/patterns.md`
- Create: `.agents/skills/ag-ux-foundations/references/metrics.md`

**Interfaces:**
- Consumes: criterion IDs from Tasks 3–4; `S-13` sub-pages.
- Produces: the 13 state names exactly as listed in the validator's `STATES`, which later skills and the gap audit map to; metric IDs `M-1..M-7`.

- [ ] **Step 1: Write `state-model.md`**

Open with:
- `# Normative agentic task-state model`.
- A paragraph stating that a product conforms by mapping its own states to these, that each mapping is dated, and that one product state may map to only one normative state.

Then write one state block per state, in this order, with exactly these headings: Ready, Working, Needs input, Blocked by rules, Awaiting decision, Decision invalidated, Rejected, Executing, Verifying, Outcome uncertain, Failed, Cancelled or stopped, Verified complete. Use this content:

| State | User need | Presentation | Allowed actions | Forbidden | Criteria |
|---|---|---|---|---|---|
| Ready | Know what the agent can do here | Capability and limits statement, a few admitted examples, composer | Start a task; open settings | Empty dashboards; claims of unmeasured quality | AG-DISC-1, AG-DISC-2, AG-CTX-1 |
| Working | Know work is active and whether to intervene | Plain-language state and real milestones; expandable activity | Stop; continue other work | Simulated progress or ETA; invented activity text | AG-STAT-1, AG-STAT-2, AG-CTRL-1 |
| Needs input | Supply missing information | Focused question with the relevant context; original task kept | Answer; edit request; stop | Guessing; losing the draft | AG-UNC-1, AG-MEM-1 |
| Blocked by rules | Understand what rule blocked the proposal and what can change | Rule findings with sources and an authorized next step | Revise request; stop | Offering approval of a blocked proposal | AG-EXPL-1, AG-UNC-3 |
| Awaiting decision | Understand purpose, impact and the exact change | Business summary above the exact action and every material term | Approve with explicit confirmation; reject; ask | Hidden material terms; default-focused approve | AG-APPR-1, AG-APPR-2, AG-APPR-3, AG-APPR-4 |
| Decision invalidated | Know the pending decision no longer applies | Clear invalidation reason; what changed | Re-review a fresh proposal; stop | Approving the stale version | AG-APPR-5 |
| Rejected | Know nothing was executed | Rejection recorded; next options | Revise; start new task | Silent retry of the rejected action | AG-CTRL-4 |
| Executing | Know the approved action is being carried out | "Executing" distinct from "approved" | Stop (with in-flight status reported) | Showing success | AG-APPR-6, AG-CTRL-1 |
| Verifying | Know the result is being independently checked | "Verifying" distinct from "executed" | Wait; stop where safe | Showing success before verification | AG-APPR-6 |
| Outcome uncertain | Know the effect is unknown and what is safe | Explanation of the possible effect; safe check | Run a check; escalate | Blind retry or resend | AG-UNC-2 |
| Failed | Know what failed and what to do | Problem, cause and authorized next step, persistent | Retry only where safe; revise; escalate | Toast-only failure; raw traces | AG-UNC-3 |
| Cancelled or stopped | Know the safe state reached | What stopped and the status of any in-flight action | Start again; inspect | Implying nothing happened when an action was in flight | AG-CTRL-1 |
| Verified complete | Know the actual verified result | Verified result with reference and evidence; next action | Inspect evidence; follow up | Claiming more than was verified | AG-APPR-6, AG-EXPL-2 |

- [ ] **Step 2: Write `patterns.md`**

Write `# Agentic UI/UX patterns`, then a paragraph saying patterns are tier-4 application guidance and that decisions cite `AG-*` criteria. Then add one entry per pattern for all 32 patterns in S-13.

Entry format:

```markdown
### Approval Queues & Escalation Chains

- **Decision:** apply
- **Criteria:** AG-APPR-1, AG-APPR-5, AG-APPR-7
- **Application:** Render the risk tier assigned by system policy; package decisions with summary, exact change, impact and reversibility; show expiry and escalation.
- **Limits:** The interface never assigns or lowers a tier.
- **Source:** S-13 (risk-tiered-approval-escalation)
```

Decisions (re-read each sub-page you cite before writing):

- **apply:** Human-in-the-Loop; Approval Queues & Escalation Chains; Mixed-Initiative Interface; Agent Status & Activity; Progressive Disclosure; Trust and Transparency; Error Handling and Recovery; Chat Interface; Conversational Interface; Onboarding and Education; Accessibility in Agent Design; Ambient Agent; Cross-Platform Agent UX; Privacy and Security UX; Progressive Consent & Communication.
- **limit:**
  - Confidence Visualization: AG-EXPL-4, calibrated only.
  - Visual Reasoning: evidence chain only, AG-EXPL-1.
  - Adaptive Interface: explicit preferences only, AG-MEM-2.
  - Human On the Loop: operator surfaces, AG-STAT-1, AG-CTRL-1.
  - Monitoring and Control: same as Human On the Loop.
  - Transparent Data Handling: AG-EXPL-2.
  - AG-UI Protocol: reference only; adopt only by an explicit stream-contract decision.
- **exclude (safety):** Generative UI. Model-generated executable or decision UI violates AG-ID-2 and AG-APPR-1.
- **exclude (not applicable yet):** Agent Collaboration UX; Multimodal Interaction; Realtime Voice Agents; Context Window Management UI; Privacy-by-Design Principles dashboarding; Granular Privacy Controls; User Empowerment Privacy Dashboard; Regulatory Compliance UX; Advanced Privacy Technologies UX. Each records the trigger that would make it applicable.

Close with a short section, "Secondary principles (S-14, S-15)", that maps the UX Pilot practices and the Vasquez principles to `AG-*` IDs. Mark Vasquez as summary-only if Task 2 recorded it so.

- [ ] **Step 3: Write `metrics.md`**

Write `# Evaluation metrics`, then one block per metric:

```markdown
### M-3 — Approval comprehension

- **Measures:** Whether the approver can state what will change, where, and whether it is reversible, before approving.
- **Method:** Moderated task test with role-matched participants; scored against the exact action.
- **Criteria:** AG-APPR-1, AG-APPR-3
```

Metrics:
- **M-1** Task completion time (instrumented flow or moderated test)
- **M-2** Error rate (instrumented)
- **M-3** Approval comprehension (moderated)
- **M-4** Oversight effectiveness: seeded bad proposals caught, and stop/override success (moderated with seeded errors; S-03 Art. 14(4)(b))
- **M-5** Trust calibration: reliance matches measured reliability (moderated; S-09 trust calibration)
- **M-6** Recovery success from failed and uncertain outcomes (moderated or instrumented)
- **M-7** Clarification count per task (instrumented)

State that browser tests verify mechanics and do not measure these metrics.

- [ ] **Step 4: Validate**

Run: `uv run python scripts/check_agent_skills.py`

Expected: no problems that mention `state-model.md`, `patterns.md` or `metrics.md`.

- [ ] **Step 5: Commit**

```bash
git add .agents/skills/ag-ux-foundations/references/state-model.md .agents/skills/ag-ux-foundations/references/patterns.md .agents/skills/ag-ux-foundations/references/metrics.md
git commit -m "docs(skills): normative state model, pattern decisions and UX metrics

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Design-system and frontend standards

**Files:**
- Create: `.agents/skills/ag-ux-foundations/references/design-system.md`
- Create: `.agents/skills/ag-ux-foundations/references/frontend.md`

**Interfaces:**
- Consumes: `S-01`, `S-02`, `S-04`, `S-06`, `S-07`, `S-11`, `S-14`, `S-16`…`S-20`.
- Produces: `AG-DS-1..6` and `AG-FE-1..11`.

- [ ] **Step 1: Write `design-system.md`** (criterion format; verify sources as in Task 3)

Header paragraph: a candidate design system is adopted only if it meets these requirements.

| ID — title | Statement | Sources | Enforcement | Max severity |
|---|---|---|---|---|
| AG-DS-1 — Semantic tokens | Visual values are semantic tokens in DTCG format; components use no literal colour values | S-17 (format), S-11 (Carbon for AI tokens) | gate, test | High |
| AG-DS-2 — Verified themes | Light, dark and high-contrast themes each pass text, non-text and focus contrast | S-01 (SC 1.4.3, 1.4.11) | test | Blocker |
| AG-DS-3 — Density without losing target size | A density scale exists, and compact density keeps targets at or above the WCAG minimum | S-01 (SC 2.5.8), S-14 (dense components) | test | Blocker |
| AG-DS-4 — AI-origin treatment is scoped | The AI identity treatment applies only to AI-originated elements, never to verified facts or decision terms | S-11 (AI identity), S-04 (Art. 50(2)) | review | High |
| AG-DS-5 — Status semantics | Status and severity use icon, text and colour together, on one consistent scale | S-01 (SC 1.4.1) | test, review | Blocker |
| AG-DS-6 — Motion with reduced alternatives | Motion is tokenized and has reduced-motion alternatives; nothing essential depends on animation | S-01 (SC 2.3.3, 2.2.2) | test | High |

- [ ] **Step 2: Write `frontend.md`**

Sections, in order:

1. **`## Durable rules`**, in the criterion format:

| ID — title | Statement | Sources | Enforcement | Max severity |
|---|---|---|---|---|
| AG-FE-1 — Server authority | Client state can never promote a result to verified, grant permission or approve implicitly | S-06 (ASI03, ASI09) | test | Blocker |
| AG-FE-2 — One owner per state | Each piece of state has one owner; derived values are computed, not mirrored | S-20 (avoid redundant and duplicated state) | review | Medium |
| AG-FE-3 — Typed, validated wire contracts | Client types are generated from the API schema; unknown or malformed shapes produce an explicit unsupported state | S-18 (Schema Object) | gate, test | High |
| AG-FE-4 — Exclusive UI states | Mutually exclusive UI states are modelled as one discriminated union; missing values are never defaulted to empty, zero or granted | S-07 (self-descriptiveness) | review | High |
| AG-FE-5 — Accessible primitives | Interactive primitives implement APG patterns, through a conformant library or with equivalent tests | S-02 (patterns) | test | Blocker |
| AG-FE-6 — Container-relative layout | Layout responds to its container, not only the viewport, so narrow embedded placements reflow | S-01 (SC 1.4.10), S-16 (container queries status) | test | High |
| AG-FE-7 — Embedding isolation | Embedded surfaces keep styles, focus and portals inside their isolation boundary and depend on no host-page globals | S-02 (focus management) | test | High |
| AG-FE-8 — Baseline adoption | CSS/DOM features are used when Baseline Widely available; Newly available only with a tested fallback; Limited availability only by recorded decision | S-16 (statuses) | review | Medium |
| AG-FE-9 — Test strategy | Behavior is covered by unit, component and browser conformance tests plus automated accessibility checks, and human accessibility checks before release | S-01 (Conformance), S-02 (patterns) | review | High |
| AG-FE-10 — No sensitive client persistence | No secrets, task text or sensitive data in URLs, browser storage or client telemetry | S-06 (ASI03) | test | Blocker |
| AG-FE-11 — Responsiveness budget | Interaction responsiveness is measured against INP thresholds and streaming never blocks input; optimise only after measuring | S-19 (INP thresholds) | test | Medium |

2. **`## Stack decisions`**: a table with columns Decision | Current choice | Standard followed | Revisit trigger | Upstream to watch. The rows cover component accessibility library, styling approach, token pipeline, state store, routing, component gallery and test runner. Put `see the consuming product's binding requirements` in "Current choice", and add a sentence that each product records its current choices in its own reference (for e-agent, `e-agent.md`). No version numbers.
3. **`## Update process`**:
   - Record a "Last reviewed: YYYY-MM-DD" line.
   - Triggers: a major version of a listed dependency, a Baseline status change for a backlog item, and a 6-month cadence.
   - Verify claims against official release notes or current documentation.
   - A durable-rule change needs owner approval.
4. **`## Trends backlog`**: each item has "Question", "Evaluate by" and "Baseline status (verify)", with no decision implied. Items: CSS container queries; React Compiler; `popover` and anchor positioning inside a shadow root; View Transitions with reduced motion.

- [ ] **Step 3: Validate**

Run: `uv run python scripts/check_agent_skills.py`

Expected: no problems that mention `design-system.md` or `frontend.md`.

- [ ] **Step 4: Commit**

```bash
git add .agents/skills/ag-ux-foundations/references/design-system.md .agents/skills/ag-ux-foundations/references/frontend.md
git commit -m "docs(skills): design-system and frontend standards with Baseline rule

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Binding e-agent requirements (`e-agent.md`)

**Files:**
- Create: `.agents/skills/ag-ux-foundations/references/e-agent.md`

**Interfaces:**
- Consumes: `AG-*` IDs; repository ADRs and AGENTS.md.
- Produces: `EA-1..EA-11`, the tier-R list that review and gap audits treat as non-weakenable.

- [ ] **Step 1: Read the binding sources**

Read `AGENTS.md`; `docs/ui-architecture.md` §4.2–4.3; ADRs 0006, 0007, 0011, 0013, 0014, 0015 and 0016; and `research/16-conversation-workspace-revision.md`. Note the exact section that states each requirement below.

- [ ] **Step 2: Write `e-agent.md`**

Open with:
- `# e-agent binding requirements (tier R)`.
- A paragraph saying these are binding, may only be changed through an ADR, and that the current UI implementation is audited against them and the standard.

Then one block per requirement:

```markdown
### EA-2 — Exact one-action approval

- **Requirement:** The decision surface renders the complete server-owned approval presentation for exactly one action; the client never reinterprets terms.
- **Binding source:** [ADR 0006](../../../../../docs/adr/0006-approval-digest-canonicalization.md), [UI architecture §4.2](../../../../../docs/ui-architecture.md)
- **Standard cross-reference:** AG-APPR-1, AG-APPR-2, AG-FE-1
- **Kind:** ADR
```

Requirements:

| ID | Requirement | Kind | Cross-reference |
|---|---|---|---|
| EA-1 | Server is authoritative for capabilities, connections, scope, exact action versions, approval and verification | ADR | AG-FE-1, AG-APPR-7 |
| EA-2 | Exact one-action approval rendered from the server presentation | ADR | AG-APPR-1, AG-APPR-2 |
| EA-3 | Approved, committed and verified are separate states and labels | ADR / AGENTS.md | AG-APPR-6 |
| EA-4 | `UNKNOWN` outcomes are never blindly resent; read-back reconciliation only | AGENTS.md | AG-UNC-2 |
| EA-5 | No hidden model reasoning, simulated progress or uncalibrated confidence is displayed | ADR | AG-EXPL-1, AG-STAT-2, AG-EXPL-4 |
| EA-6 | UI packages contain no provider identifiers; names and icons come from manifests | AGENTS.md | AG-ENT-3 |
| EA-7 | No model-generated approval renderer or arbitrary JSON-to-UI | ADR | AG-ID-2 |
| EA-8 | Missing access or information is shown explicitly | ADR | AG-UNC-4 |
| EA-9 | Appearance and placement switching is separate from business state and keeps in-progress work | ADR | AG-MEM-1 |
| EA-10 | Conversation is the primary surface; the artifact opens in a closable workspace | Owner decision | AG-CTX-1 |
| EA-11 | Sample or fixture data is always labelled as sample | Owner decision | AG-ID-1 |

Use the actual ADR or section where each requirement is stated (from Step 1). If a requirement is not actually stated in any binding source, either change its Kind to `Owner decision` and cite the research document plus "owner approval 2026-10-11", or drop it and say so in the handoff note.

End with a section, `## Current stack choices`. It records the e-agent stack choices that `frontend.md` defers here (React, React Aria Components, DTCG token compiler, namespaced plain CSS, external store, hash routes, Vite gallery, Vitest, Playwright). Each is marked "current choice: audited against AG-FE-*", with no versions.

- [ ] **Step 3: Validate**

Run: `uv run python scripts/check_agent_skills.py`

Expected: no problems that mention `e-agent.md` (the product-term rule exempts it; links to ADRs must resolve).

- [ ] **Step 4: Commit**

```bash
git add .agents/skills/ag-ux-foundations/references/e-agent.md
git commit -m "docs(skills): e-agent binding requirements cross-referenced to the AG standard

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: Entry point, discovery and repository conformance

**Files:**
- Create: `.agents/skills/ag-ux-foundations/SKILL.md`
- Create: `.claude/skills/ag-ux-foundations` (symlink)
- Modify: `AGENTS.md` (append a section after "Plugins and knowledge")
- Modify: `tests/conformance/test_agent_skills.py` (remove the skip in `test_repository_skills_conform`)

**Interfaces:**
- Consumes: all reference files.
- Produces: the discoverable skill `ag-ux-foundations`, and the repository conformance test that Phase 2+ skills must keep passing.

- [ ] **Step 1: Make the repository test strict (failing first)**

In `tests/conformance/test_agent_skills.py`, replace the body of `test_repository_skills_conform` with:

```python
def test_repository_skills_conform():
    assert messages(REPO) == []
```

Run: `uv run pytest tests/conformance/test_agent_skills.py::test_repository_skills_conform -v`

Expected: FAIL listing `missing SKILL.md` and the missing symlink.

- [ ] **Step 2: Write `SKILL.md`** (≤ 120 lines)

```markdown
---
name: ag-ux-foundations
description: Agentic enterprise UI/UX standard (AG-* criteria, state model, patterns, design-system and frontend rules). Read before any agentic UI brief, mockup, implementation or review; cite criteria by ID.
---

# Agentic UI/UX foundations

This is the standard that agentic UI/UX work is built and reviewed against. It is product-neutral; a product's binding requirements live in one separate reference.

## Authority

- The standard defines what good looks like. A product's current implementation is an audit target, never a source of criteria.
- A product's binding requirements (accepted architecture decisions, repository rules, owner decisions) cannot be weakened. Where the standard conflicts with one, propose a decision change; do not override it.
- Where the standard is stricter than the implementation, record a gap and build to the standard.
- Cite criteria by ID (`AG-…`). Do not copy criterion text into other documents.

## Reading order

1. [standard.md](../../../../docs/superpowers/plans/references/standard.md): interaction criteria.
2. [state-model.md](../../../../docs/superpowers/plans/references/state-model.md): the normative task states.
3. [e-agent.md](../../../../docs/superpowers/plans/references/e-agent.md): binding requirements for this repository.
4. As the task needs: [patterns.md](../../../../docs/superpowers/plans/references/patterns.md), [design-system.md](../../../../docs/superpowers/plans/references/design-system.md), [frontend.md](../../../../docs/superpowers/plans/references/frontend.md), [metrics.md](../../../../docs/superpowers/plans/references/metrics.md), [sources.md](../../../../docs/superpowers/plans/references/sources.md).

## Rules for every use

- A Blocker finding must rest on a T1 or T2 source, or a binding requirement.
- Never present model chain-of-thought, simulated progress or uncalibrated confidence.
- Never claim success before independent verification.
- Read a new source at its origin and record its reading level in `sources.md` before citing it.
- Browser checks prove mechanics, not design quality or usability; say so in every report.

## Changing the standard

Add or edit criteria only with sources read at `full` or `partial`, keep IDs stable (retire, never renumber), update `sources.md`, and run the repository's skill check. Durable-rule changes need owner approval.
```

Check the description's length: it must be ≤ 400 characters (the validator enforces this).

- [ ] **Step 3: Create the symlink**

Run:

```bash
mkdir -p .claude/skills && ln -s ../../.agents/skills/ag-ux-foundations .claude/skills/ag-ux-foundations && ls -l .claude/skills/
```

Expected: `ag-ux-foundations -> ../../.agents/skills/ag-ux-foundations`.

- [ ] **Step 4: Add the AGENTS.md section**

Insert after the "Plugins and knowledge" section (before "## Development and verification"):

```markdown
## UI/UX skills

Agentic UI/UX work uses the `ag-*` skills in `.agents/skills/` (linked for Claude under `.claude/skills/`). Start from `ag-ux-foundations`; it holds the standard (`AG-*` criteria) that the current UI is audited and built against, and the binding e-agent requirements. Each stage skill stops at an owner gate. Validate skill changes with `uv run python scripts/check_agent_skills.py`.
```

- [ ] **Step 5: Run the full check and tests**

Run: `uv run python scripts/check_agent_skills.py && uv run pytest tests/conformance/test_agent_skills.py -v`

Expected: the CLI prints nothing and exits 0; all tests PASS, including `test_repository_skills_conform`.

- [ ] **Step 6: Verify discovery in both agents (manual)**

- **Codex:** run `codex` from the repository root, open `/skills`, and confirm that `ag-ux-foundations` is listed with its description.
- **Claude Code:** start a new session in the repository and confirm the skill appears in the available skills (or invoke it as `/ag-ux-foundations`). If Claude Code does not list a symlinked skill, stop and report it. The fallback (a generated copy plus a drift check) needs owner approval because it changes the spec's layout.

Record both results, with the exact output, in the Task 9 handoff.

- [ ] **Step 7: Commit**

```bash
git add .agents/skills/ag-ux-foundations/SKILL.md .claude/skills/ag-ux-foundations AGENTS.md tests/conformance/test_agent_skills.py
git commit -m "feat(skills): ag-ux-foundations entry point, discovery links and conformance

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

`AGENTS.md` already had uncommitted owner changes before this plan (the `git status` snapshot lists it as modified). Before committing, run `git diff AGENTS.md`. If it contains changes other than the new section, commit only the section with `git add -p AGENTS.md`, or ask the owner. Never commit their unrelated edits.

---

### Task 9: Owner review gate

**Files:** none (handoff only)

- [ ] **Step 1: Spot-check citations**

Pick 10 criteria at random (include at least 3 Blockers). For each, open the cited locator and confirm that the source supports the statement. Record pass/fail per criterion. Fix any failure through the Task 3 procedure, then re-run the CLI.

- [ ] **Step 2: Hand off to the owner**

Report:
- the criteria counts per file;
- the sources by reading level (list every `summary-only`/`unreadable` source);
- the spot-check results;
- the discovery results from Task 8, Step 6;
- the real output of `uv run python scripts/check_agent_skills.py` and `uv run pytest tests/conformance/test_agent_skills.py`;
- any requirement dropped or re-kinded in Task 7.

State the limits: the check is structural, the spot check is a sample, and no usability evidence exists.

**Stop.** The owner reviews the standard. Phase 2 (`ag-ux-review` and the gap audit) gets its own plan only after approval.
