import json

HANDOFF = {
    "task": "1c.1",
    "changed": "split module",
    "evidence_refs": [],
    "open_items": [],
    "rulings": [],
    "outside_repo": [],
}


def _start(repo) -> None:
    assert repo.invoke("new-task", "1", "1c.1", "--feature", "F-1", "--paths", "src/**").code == 0
    repo.commit("task contract")


def _evidence_path(repo) -> str:
    assert repo.invoke("gate", "quick").code == 0
    (path,) = (repo.root / "evidence/gates/1c.1").glob("*.json")
    return str(path.relative_to(repo.root))


def _mark_passing(repo, evidence: str) -> None:
    features_path = repo.root / "harness/state/1/features.json"
    doc = json.loads(features_path.read_text())
    doc["entries"][0]["passes"] = True
    doc["entries"][0]["evidence"] = evidence
    features_path.write_text(json.dumps(doc, indent=2) + "\n")


def _bookkeeping(repo, evidence: str) -> None:
    _mark_passing(repo, evidence)
    handoff = dict(HANDOFF, evidence_refs=[evidence])
    repo.write("harness/state/1/handoffs/1c.1.json", json.dumps(handoff) + "\n")
    assert repo.invoke("checkpoint", "--session", "s1", "--next", "close").code == 0
    repo.commit("bookkeeping")


def test_close_check_accepts_bookkeeping_only_after_evidence(repo) -> None:
    _start(repo)
    repo.write("src/pkg/new.py", "Y = 2\n")
    repo.commit("feature code")
    evidence = _evidence_path(repo)  # clean tree at HEAD
    _bookkeeping(repo, evidence)  # only harness/state changes after the evidence
    result = repo.invoke("close-check", "--session", "s1")
    assert result.code == 0, result
    assert "ok" in result.out


def test_close_check_rejects_code_changed_after_evidence(repo) -> None:
    _start(repo)
    evidence = _evidence_path(repo)
    repo.write("src/pkg/new.py", "Y = 3\n")
    repo.commit("code after evidence")
    _bookkeeping(repo, evidence)
    result = repo.invoke("close-check")
    assert result.code == 1
    assert "code changed after evidence" in result.out and "src/pkg/new.py" in result.out


def test_close_check_rejects_evidence_from_dirty_tree(repo) -> None:
    _start(repo)
    repo.write("src/pkg/new.py", "Y = 2\n")
    evidence = _evidence_path(repo)  # dirty tree
    repo.commit("feature code")
    _bookkeeping(repo, evidence)
    result = repo.invoke("close-check")
    assert result.code == 1
    assert "dirty tree" in result.out


def test_close_check_rejects_passes_without_evidence(repo) -> None:
    _start(repo)
    features_path = repo.root / "harness/state/1/features.json"
    doc = json.loads(features_path.read_text())
    doc["entries"][0]["passes"] = True
    features_path.write_text(json.dumps(doc, indent=2) + "\n")
    repo.write("harness/state/1/handoffs/1c.1.json", json.dumps(HANDOFF) + "\n")
    assert repo.invoke("checkpoint").code == 0
    repo.commit("bookkeeping")
    result = repo.invoke("close-check")
    assert result.code == 1
    assert "F-1" in result.out and "evidence" in result.out


def test_close_check_lists_dirty_tree_missing_progress_and_handoff(repo) -> None:
    _start(repo)
    repo.write("src/pkg/new.py", "Y = 2\n")
    result = repo.invoke("close-check")
    assert result.code == 1
    assert "working tree is not clean" in result.out
    assert "progress log has no entry for task 1c.1" in result.out
    assert "handoff missing" in result.out


def test_close_check_requires_entry_from_this_session(repo) -> None:
    _start(repo)
    evidence = _evidence_path(repo)
    _bookkeeping(repo, evidence)  # session s1
    result = repo.invoke("close-check", "--session", "s2")
    assert result.code == 1
    assert "not from session s2" in result.out


def test_close_check_without_active_task(repo) -> None:
    result = repo.invoke("close-check")
    assert result.code == 1
    assert "no active task" in result.out


def test_handoff_command_validates_schema_and_evidence_refs(repo) -> None:
    _start(repo)
    bad = dict(HANDOFF, evidence_refs=["evidence/gates/1c.1/nope.json"])
    repo.write("harness/state/1/handoffs/1c.1.json", json.dumps(bad) + "\n")
    result = repo.invoke("handoff", "1c.1")
    assert result.code == 1
    assert "evidence ref missing" in result.out
    repo.write("harness/state/1/handoffs/1c.1.json", json.dumps(HANDOFF) + "\n")
    assert repo.invoke("handoff", "1c.1").code == 0


def test_close_check_hook_is_inert_unless_unattended(repo, monkeypatch) -> None:
    _start(repo)
    repo.write("src/pkg/new.py", "Y = 2\n")
    payload = json.dumps({"session_id": "s1", "stop_hook_active": False, "cwd": str(repo.root)})
    monkeypatch.delenv("E_AGENT_HARNESS_UNATTENDED", raising=False)
    assert repo.invoke("close-check", "--hook", stdin=payload).code == 0
    monkeypatch.setenv("E_AGENT_HARNESS_UNATTENDED", "1")
    result = repo.invoke("close-check", "--hook", stdin=payload)
    assert result.code == 2
    assert "working tree is not clean" in result.err
    looping = json.dumps({"session_id": "s1", "stop_hook_active": True, "cwd": str(repo.root)})
    assert repo.invoke("close-check", "--hook", stdin=looping).code == 0
