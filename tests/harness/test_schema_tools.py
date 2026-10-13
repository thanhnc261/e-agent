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
