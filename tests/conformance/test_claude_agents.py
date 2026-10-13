"""The committed Claude Code subagents (harness H4)."""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
AGENTS = ROOT / ".claude" / "agents"
SKILLS = ROOT / ".agents" / "skills"
NAMES = ("explorer", "verifier", "reviewer", "sandbox-operator")
READ_ONLY = ("explorer", "verifier", "reviewer")


def _frontmatter(path: Path) -> tuple[dict[str, object], str]:
    """The small YAML subset the agent files use: scalars and `- item` lists."""
    text = path.read_text()
    assert text.startswith("---\n"), path
    head, body = text[4:].split("\n---\n", 1)
    meta: dict[str, object] = {}
    key = None
    for line in head.splitlines():
        if line.startswith("  - ") and key:
            items = meta.setdefault(key, [])
            assert isinstance(items, list)
            items.append(line[4:].strip())
        elif ":" in line:
            key, _, value = line.partition(":")
            key = key.strip()
            meta[key] = value.strip() if value.strip() else []
    return meta, body


def _skill_flag(name: str) -> str | None:
    meta, _ = _frontmatter(SKILLS / name / "SKILL.md")
    flag = meta.get("disable-model-invocation")
    return flag if isinstance(flag, str) else None


@pytest.mark.parametrize("name", NAMES)
def test_agent_identity(name: str) -> None:
    meta, body = _frontmatter(AGENTS / f"{name}.md")
    assert meta["name"] == name
    description = meta["description"]
    assert isinstance(description, str) and 20 <= len(description) <= 200
    assert body.strip()


@pytest.mark.parametrize("name", READ_ONLY)
def test_read_only_agents_cannot_edit(name: str) -> None:
    meta, _ = _frontmatter(AGENTS / f"{name}.md")
    disallowed = {t.strip() for t in str(meta.get("disallowedTools", "")).split(",")}
    assert {"Edit", "Write", "NotebookEdit"} <= disallowed


@pytest.mark.parametrize("name", NAMES)
def test_agents_preload_only_invocable_skills(name: str) -> None:
    meta, _ = _frontmatter(AGENTS / f"{name}.md")
    skills = meta.get("skills", [])
    assert isinstance(skills, list)
    for skill in skills:
        assert (SKILLS / skill / "SKILL.md").is_file(), skill
        assert _skill_flag(skill) != "true", f"{skill} cannot be preloaded"


def test_role_skills() -> None:
    def skills(name: str) -> list:
        value = _frontmatter(AGENTS / f"{name}.md")[0].get("skills", [])
        return value if isinstance(value, list) else []

    assert "eng-verify" in skills("verifier")
    assert "eng-review" in skills("reviewer")
    _, body = _frontmatter(AGENTS / "sandbox-operator.md")
    assert ".agents/skills/live-sandbox/SKILL.md" in body  # manual-only skill: read, not preloaded


def test_reviewer_is_a_fresh_context() -> None:
    meta, body = _frontmatter(AGENTS / "reviewer.md")
    assert "fork" not in meta
    assert "fresh_context" in body


def test_descriptions_stay_small() -> None:
    total = sum(len(str(_frontmatter(AGENTS / f"{n}.md")[0]["description"])) for n in NAMES)
    assert total <= 700
