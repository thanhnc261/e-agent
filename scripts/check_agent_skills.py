"""Validate the ag-* agent skills: structure, discovery links and citation integrity.

Structural checks only. They cannot judge whether a criterion is a good standard
or whether a cited source supports it; owner review and spot checks do that.
Spec: docs/superpowers/specs/2026-10-11-ag-ux-skills-design.md.
"""

from __future__ import annotations

import argparse
import datetime
import re
import sys
from dataclasses import dataclass
from pathlib import Path

NAME_RE = re.compile(r"^ag-[a-z0-9]+(?:-[a-z0-9]+)*$")
MAX_DESCRIPTION = 400
YAML_INDICATORS = ">|'\"[{*&!%@`"
MAX_TOTAL_DESCRIPTION = 2000
CRITERION = r"AG-[A-Z0-9]+-\d+"
DEF_RE = re.compile(rf"^### ({CRITERION}) — \S", re.M)
REF_RE = re.compile(rf"\b({CRITERION})\b")
CITATION_RE = re.compile(r"\b([Ss]-\d+)\b(\s*\([^)]+\))?")
CANONICAL_SOURCE_RE = re.compile(r"S-\d{2}")
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
PRODUCT_RE = re.compile(
    r"(?<![A-Za-z0-9])e[-_]agent|Odoo|ApprovalPresentation|RunState|ActionState",
    re.IGNORECASE,
)
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
    if description and (
        description[0] in YAML_INDICATORS or ": " in description or " #" in description
    ):
        problems.append(Problem(where, "description must be a single plain YAML scalar"))
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


def _is_date(text: str) -> bool:
    try:
        datetime.date.fromisoformat(text)
    except ValueError:
        return False
    return True


def _parse_sources(root: Path, path: Path, problems: list[Problem]) -> dict[str, tuple[str, str]]:
    sources: dict[str, tuple[str, str]] = {}
    seen: set[str] = set()
    where = _rel(root, path)
    for line in path.read_text().splitlines():
        if not line.strip().startswith("| S-"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) != 7 or not CANONICAL_SOURCE_RE.fullmatch(cells[0]):
            problems.append(Problem(where, f"unparsable source row: {line.strip()[:40]}"))
            continue
        sid, _title, url, tier, accessed, reading, _notes = cells
        if sid in seen:
            problems.append(Problem(where, f"duplicate source {sid}"))
        seen.add(sid)
        if not url:
            problems.append(Problem(where, f"{sid} has no URL"))
        if tier not in TIERS:
            problems.append(Problem(where, f"{sid} tier '{tier}' not in {sorted(TIERS)}"))
        if not DATE_RE.match(accessed) or not _is_date(accessed):
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


def _fields(body: str, label: str, where: str, problems: list[Problem]) -> dict[str, str]:
    """Parse field lines; report duplicates and wrapped continuation lines."""
    fields: dict[str, str] = {}
    open_field: str | None = None
    for line in body.splitlines():
        m = FIELD_RE.match(line)
        if m:
            name = m.group(1)
            if name in fields:
                problems.append(Problem(where, f"{label} duplicate field '{name}'"))
            else:
                fields[name] = m.group(2)
            open_field = name
        elif not line.strip():
            open_field = None
        elif open_field is not None and not line.startswith("- **"):
            problems.append(
                Problem(
                    where,
                    f"{label} field '{open_field}' wraps onto a continuation line; "
                    "keep each field on one line",
                )
            )
            open_field = None
    return fields


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
        fields = _fields(body, cid, where, problems)
        for name in CRITERION_FIELDS:
            if not fields.get(name, "").strip():
                problems.append(Problem(where, f"{cid} missing field '{name}'"))
        readable = False
        readable_tiers: set[str] = set()
        for raw, locator in CITATION_RE.findall(fields.get("Sources", "")):
            if not CANONICAL_SOURCE_RE.fullmatch(raw):
                problems.append(
                    Problem(where, f"{cid} citation '{raw}' is not a canonical S-nn ID")
                )
                continue
            if raw not in sources:
                problems.append(Problem(where, f"{cid} cites unknown source {raw}"))
                continue
            if not locator:
                problems.append(Problem(where, f"{cid} citation {raw} has no locator"))
            tier, reading = sources[raw]
            if reading in {"full", "partial"}:
                readable = True
                readable_tiers.add(tier)
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
        if severity == "Blocker" and not readable_tiers & {"T1", "T2"}:
            problems.append(Problem(where, f"{cid} is Blocker without a readable T1/T2 source"))


def _check_states(root: Path, path: Path, problems: list[Problem]) -> None:
    where = _rel(root, path)
    blocks: dict[str, str] = {}
    for name, body in _blocks(path.read_text(), re.compile(r"^### (.+)$", re.M)):
        if name in blocks:
            problems.append(Problem(where, f"duplicate state '{name}'"))
        blocks.setdefault(name, body)
    for state in STATES:
        if state not in blocks:
            problems.append(Problem(where, f"missing state '{state}'"))
            continue
        fields = _fields(blocks[state], f"state '{state}'", where, problems)
        for name in STATE_FIELDS:
            if not fields.get(name, "").strip():
                problems.append(Problem(where, f"state '{state}' missing field '{name}'"))
        criteria = fields.get("Criteria", "")
        if criteria.strip() and not REF_RE.search(criteria):
            problems.append(Problem(where, f"state '{state}' Criteria lists no AG criterion"))


def check(root: Path) -> list[Problem]:
    problems: list[Problem] = []
    skills_dir = root / ".agents" / "skills"
    if not skills_dir.is_dir():
        return [Problem(".", "no .agents/skills directory")]
    skills = sorted(p for p in skills_dir.iterdir() if p.is_dir() and p.name.startswith("ag-"))
    total = sum(_check_skill(root, s, problems) for s in skills)
    claude_dir = root / ".claude" / "skills"
    if claude_dir.is_dir():
        names = {s.name for s in skills}
        for entry in sorted(claude_dir.iterdir()):
            if entry.name.startswith("ag-") and entry.name not in names:
                where = _rel(root, entry)
                problems.append(Problem(where, f"orphan link {where} has no source skill"))
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
        if refs in path.parents and path.name != PRODUCT_FILE:
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
