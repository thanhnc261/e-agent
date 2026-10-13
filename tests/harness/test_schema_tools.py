import json

from e_agent_harness import contracts


def test_validate_command_reports_problems(repo) -> None:
    bad = repo.write("tmp/features.json", json.dumps({"phase": "1", "entries": [{"id": "F-x"}]}))
    result = repo.invoke("validate", "features", str(bad))
    assert result.code == 1
    assert "entries/0" in result.out
    good = repo.root / "harness/state/1/features.json"
    result = repo.invoke("validate", "features", str(good))
    assert result.code == 0
    assert "ok" in result.out


def test_validate_command_rejects_unknown_schema(repo) -> None:
    result = repo.invoke("validate", "nope", str(repo.root / "harness/state/1/features.json"))
    assert result.code == 1
    assert "unknown contract schema" in result.out


def test_add_feature_appends_valid_entry(repo) -> None:
    result = repo.invoke(
        "add-feature",
        "1",
        "F-1-R1",
        "--category",
        "review",
        "--description",
        "fix the phase review findings",
        "--step",
        "review JSON verdict accept",
        "--step",
        "gate full passes",
    )
    assert result.code == 0, result
    doc = json.loads((repo.root / "harness/state/1/features.json").read_text())
    entry = doc["entries"][-1]
    assert entry == {
        "id": "F-1-R1",
        "category": "review",
        "description": "fix the phase review findings",
        "steps": ["review JSON verdict accept", "gate full passes"],
        "passes": False,
    }
    assert contracts.validate("features", doc) == []


def test_add_feature_refuses_duplicate_id(repo) -> None:
    args = ("add-feature", "1", "F-1", "--category", "x", "--description", "d", "--step", "s")
    result = repo.invoke(*args)
    assert result.code == 1
    assert "F-1 already exists" in result.out


def test_add_feature_creates_a_missing_list(repo) -> None:
    result = repo.invoke(
        "add-feature", "2", "F-2-1", "--category", "k", "--description", "d", "--step", "s"
    )
    assert result.code == 0, result
    doc = json.loads((repo.root / "harness/state/2/features.json").read_text())
    assert doc["phase"] == "2" and [e["id"] for e in doc["entries"]] == ["F-2-1"]


def test_date_time_format_is_enforced() -> None:
    entry = {
        "timestamp": "2026-10-13T06:00:00+00:00",
        "session": "s",
        "task": "t",
        "changed": "c",
        "next": "n",
        "open": "none",
    }
    assert contracts.validate("progress-entry", entry) == []
    assert contracts.validate("progress-entry", dict(entry, timestamp="2026-10-13T06:00:00Z")) == []
    for bad in ("yesterday", "2026-10-13", "2026-10-13T06:00:00"):
        problems = contracts.validate("progress-entry", dict(entry, timestamp=bad))
        assert any(p.startswith("timestamp:") for p in problems), bad


def test_path_like_identifiers_are_refused(repo, tmp_path) -> None:
    common = ("--category", "x", "--description", "d", "--step", "s")
    for phase in ("../../research", "/tmp/outside", "a/b", ".."):
        result = repo.invoke("add-feature", phase, "F-x", *common)
        assert result.code == 1, phase
        assert "invalid" in result.out
    assert not (repo.root / "research").exists()
    result = repo.invoke("new-task", "1", "../escape", "--feature", "F-1", "--paths", "src/**")
    assert result.code == 1
    assert "invalid" in result.out


def test_state_symlinks_cannot_escape(repo) -> None:
    import os

    (repo.root / "research").mkdir()
    os.symlink("../../research", repo.root / "harness/state/review")
    common = ("--category", "x", "--description", "d", "--step", "s")
    result = repo.invoke("add-feature", "review", "F-x", *common)
    assert result.code == 1
    assert "escapes" in result.out
    assert not (repo.root / "research/features.json").exists()
    target = repo.root / "research/elsewhere.json"
    target.write_text("{}")
    (repo.root / "harness/state/2").mkdir()
    os.symlink(target, repo.root / "harness/state/2/features.json")
    result = repo.invoke("add-feature", "2", "F-y", *common)
    assert result.code == 1
    assert target.read_text() == "{}"


def test_state_directory_symlink_is_refused(repo) -> None:
    import os
    import shutil

    (repo.root / "research").mkdir()
    shutil.move(str(repo.root / "harness/state"), str(repo.root / "research/state"))
    os.symlink("../research/state", repo.root / "harness/state")
    common = ("--category", "x", "--description", "d", "--step", "s")
    result = repo.invoke("add-feature", "1", "F-x", *common)
    assert result.code == 1
    assert "escapes" in result.out
    assert repo.invoke("checkpoint").code == 1


def test_live_evidence_and_progress_symlinks_are_refused(repo) -> None:
    import os

    (repo.root / "research").mkdir()
    (repo.root / "harness/state/evidence").mkdir(parents=True)
    os.symlink("../../../research", repo.root / "harness/state/evidence/live")
    result = repo.invoke("live-check")
    assert result.code == 1
    assert "escapes" in result.out
    assert not list((repo.root / "research").glob("*.json"))
    os.symlink("../../research/progress.md", repo.root / "harness/state/progress.md")
    result = repo.invoke("checkpoint")
    assert result.code == 1
    assert not (repo.root / "research/progress.md").exists()
