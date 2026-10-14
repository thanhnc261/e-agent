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
    (path,) = (repo.root / "harness/state/evidence/gates/1c.1").glob("*.json")
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
    bad = dict(HANDOFF, evidence_refs=["harness/state/evidence/gates/1c.1/nope.json"])
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
    # A continued stop is checked again: only a closed task may stop (Claude Code caps the
    # number of consecutive blocks itself).
    assert repo.invoke("close-check", "--hook", stdin=looping).code == 2


def test_close_check_rejects_failed_gate_evidence(repo) -> None:
    _start(repo)
    manifest = repo.root / "harness/context.toml"
    manifest.write_text(
        manifest.read_text().replace(
            "quick = [\"echo '3 passed, 1 skipped'\"]", 'quick = ["false"]'
        )
    )
    repo.commit("failing gate")
    assert repo.invoke("gate", "quick").code == 1
    (path,) = (repo.root / "harness/state/evidence/gates/1c.1").glob("*.json")
    evidence = str(path.relative_to(repo.root))
    _bookkeeping(repo, evidence)
    result = repo.invoke("close-check")
    assert result.code == 1
    assert "failed gate" in result.out


def test_close_check_rejects_evidence_recorded_for_another_task(repo) -> None:
    _start(repo)
    evidence = _evidence_path(repo)
    path = repo.root / evidence
    doc = json.loads(path.read_text())
    doc["task"] = "other"
    path.write_text(json.dumps(doc) + "\n")
    _bookkeeping(repo, evidence)
    result = repo.invoke("close-check")
    assert result.code == 1
    assert "recorded for task other" in result.out


def test_handoff_command_finds_task_in_another_phase(repo) -> None:
    _start(repo)
    repo.write("harness/state/1/handoffs/1c.1.json", json.dumps(HANDOFF) + "\n")
    features2 = {
        "phase": "2",
        "entries": [
            {"id": "F-9", "category": "x", "description": "d", "steps": ["s"], "passes": False}
        ],
    }
    repo.write("harness/state/2/features.json", json.dumps(features2) + "\n")
    assert (
        repo.invoke(
            "new-task", "2", "2a.1", "--feature", "F-9", "--paths", "src/**", "--replace"
        ).code
        == 0
    )
    assert repo.invoke("handoff", "1c.1").code == 0


def test_close_check_hook_finds_repository_from_subdirectory(repo, monkeypatch) -> None:
    _start(repo)
    repo.write("src/pkg/new.py", "Y = 2\n")
    monkeypatch.setenv("E_AGENT_HARNESS_UNATTENDED", "1")
    payload = json.dumps(
        {"session_id": "s1", "stop_hook_active": False, "cwd": str(repo.root / "src")}
    )
    result = repo.invoke_raw("close-check", "--hook", stdin=payload)
    assert result.code == 2
    assert "working tree is not clean" in result.err


def test_close_check_passes_in_a_fresh_clone(repo, tmp_path) -> None:
    from tests.harness.conftest import git

    _start(repo)
    repo.write("src/pkg/new.py", "Y = 2\n")
    repo.commit("feature code")
    evidence = _evidence_path(repo)
    _bookkeeping(repo, evidence)  # commits the evidence file with the bookkeeping
    clone = tmp_path / "clone"
    git(tmp_path, "clone", "-q", str(repo.root), str(clone))
    result = repo.invoke_at(clone, "close-check", "--session", "s1")
    assert result.code == 0, result


def _closed(repo) -> None:
    _start(repo)
    repo.write("src/pkg/new.py", "Y = 2\n")
    repo.commit("feature code")
    _bookkeeping(repo, _evidence_path(repo))
    assert repo.invoke("close-check", "--session", "s1").code == 0


def test_status_reports_closed_task_and_names_the_next_feature(repo) -> None:
    _closed(repo)
    result = repo.invoke("status")
    assert "task 1c.1 is closed" in result.out
    assert "F-2" in result.out  # the next unfinished feature


def test_new_task_after_close_needs_no_replace(repo) -> None:
    _closed(repo)
    result = repo.invoke("new-task", "1", "1c.2", "--feature", "F-2", "--paths", "src/**")
    assert result.code == 0, result


def test_new_task_still_refuses_an_open_task(repo) -> None:
    _start(repo)
    result = repo.invoke("new-task", "1", "1c.2", "--feature", "F-2", "--paths", "src/**")
    assert result.code == 1
    assert "1c.1 is active" in result.out


def test_close_check_requires_every_contracted_feature_to_pass(repo) -> None:
    _start(repo)
    repo.write("harness/state/1/handoffs/1c.1.json", json.dumps(HANDOFF) + "\n")
    assert repo.invoke("checkpoint", "--session", "s1").code == 0
    repo.commit("bookkeeping without a gate")
    result = repo.invoke("close-check", "--session", "s1")
    assert result.code == 1
    assert "feature F-1 does not pass yet" in result.out
    assert "is closed" not in repo.invoke("status").out
    second = repo.invoke("new-task", "1", "1c.2", "--feature", "F-2", "--paths", "src/**")
    assert second.code == 1


def test_close_check_rejects_evidence_from_another_gate_set(repo) -> None:
    assert (
        repo.invoke(
            "new-task", "1", "1c.1", "--feature", "F-1", "--paths", "src/**", "--gate", "full"
        ).code
        == 0
    )
    repo.commit("task contract")
    evidence = _evidence_path(repo)  # runs gate quick, the smoke set
    _bookkeeping(repo, evidence)
    result = repo.invoke("close-check", "--session", "s1")
    assert result.code == 1
    assert "gate set quick" in result.out and "full" in result.out


def test_status_walks_the_close_sequence(repo) -> None:
    _start(repo)
    repo.write("src/pkg/new.py", "Y = 2\n")
    repo.commit("feature code")
    evidence = _evidence_path(repo)
    assert "set F-1 passes" in repo.invoke("status").out
    _mark_passing(repo, evidence)
    assert "write the handoff" in repo.invoke("status").out
    repo.write(
        "harness/state/1/handoffs/1c.1.json",
        json.dumps(dict(HANDOFF, evidence_refs=[evidence])) + "\n",
    )
    assert "checkpoint" in repo.invoke("status").out
    assert repo.invoke("checkpoint", "--session", "s1", "--next", "close").code == 0
    assert "commit the bookkeeping" in repo.invoke("status").out
    repo.commit("bookkeeping")
    assert repo.invoke("close-check", "--session", "s1").code == 0
    assert "is closed" in repo.invoke("status").out


def test_status_after_reopening_a_closed_task(repo) -> None:
    _closed(repo)
    repo.write("src/pkg/new.py", "Y = 3\n")  # a review fix
    repo.commit("review fix")
    assert "run e-agent-harness gate" in repo.invoke("status").out
    new_evidence = _latest_evidence(repo)
    out = repo.invoke("status").out
    assert "set F-1 passes" in out, out  # the old evidence reference is stale
    _mark_passing(repo, new_evidence)
    out = repo.invoke("status").out
    assert "checkpoint" in out, out  # the earlier checkpoint predates the new gate


def test_status_asks_for_a_checkpoint_from_the_current_session(repo) -> None:
    _closed(repo)  # checkpointed by s1
    out = repo.invoke("status", "--session", "s2").out
    assert "is closed" not in out
    assert "checkpoint" in out


def test_close_check_rejects_a_stale_contract(repo) -> None:
    _start(repo)
    repo.write("AGENTS.md", "# rules changed mid-task\n")
    repo.write("src/pkg/new.py", "Y = 2\n")
    repo.commit("code and a rule change")
    _bookkeeping(repo, _evidence_path(repo))
    result = repo.invoke("close-check", "--session", "s1")
    assert result.code == 1
    assert "refresh-task" in result.out


def test_close_check_requires_a_checkpoint_after_the_gate(repo) -> None:
    _start(repo)
    repo.write("src/pkg/new.py", "Y = 2\n")
    repo.commit("feature code")
    assert repo.invoke("checkpoint", "--session", "s1", "--next", "gate").code == 0
    repo.commit("early checkpoint")
    evidence = _evidence_path(repo)
    _mark_passing(repo, evidence)
    repo.write(
        "harness/state/1/handoffs/1c.1.json",
        json.dumps(dict(HANDOFF, evidence_refs=[evidence])) + "\n",
    )
    repo.commit("bookkeeping without a closing checkpoint")
    result = repo.invoke("close-check", "--session", "s1")
    assert result.code == 1
    assert "checkpoint after the gate" in result.out


def _latest_evidence(repo) -> str:
    assert repo.invoke("gate", "quick").code == 0
    newest = max(
        (repo.root / "harness/state/evidence/gates/1c.1").glob("*.json"),
        key=lambda p: p.stat().st_mtime_ns,
    )
    return str(newest.relative_to(repo.root))


def test_checkpoint_during_a_running_gate_does_not_count(repo) -> None:
    _start(repo)
    repo.write("src/pkg/new.py", "Y = 2\n")
    repo.commit("feature code")
    evidence = _evidence_path(repo)
    path = repo.root / evidence
    doc = json.loads(path.read_text())
    assert "finished_at" in doc
    doc["finished_at"] = "2999-01-01T00:00:00+00:00"  # the gate is still running
    path.write_text(json.dumps(doc) + "\n")
    _bookkeeping(repo, evidence)  # checkpoint now: during the gate
    result = repo.invoke("close-check", "--session", "s1")
    assert result.code == 1
    assert "checkpoint after the gate" in result.out
    assert "checkpoint" in repo.invoke("status", "--session", "s1").out


def test_evidence_times_compare_as_instants() -> None:
    from e_agent_harness import closecheck

    older_text_later = {"started_at": "2026-10-13T12:00:00Z"}
    newer = {"started_at": "2026-10-13T12:00:00.500000+00:00"}
    other_offset = {"started_at": "2026-10-13T13:00:00+02:00"}  # 11:00Z
    assert closecheck.newest([older_text_later, newer, other_offset]) is newer
    finished = {
        "started_at": "2026-10-13T12:00:00+00:00",
        "finished_at": "2026-10-13T12:10:00+00:00",
    }
    assert closecheck.newest([newer, finished]) is finished


def test_enabled_stop_hook_blocks_on_invalid_state(repo, monkeypatch) -> None:
    import os

    _start(repo)
    monkeypatch.setenv("E_AGENT_HARNESS_UNATTENDED", "1")
    payload = json.dumps({"session_id": "s1", "stop_hook_active": False, "cwd": str(repo.root)})
    (repo.root / "research").mkdir()
    os.symlink("../../research/progress.md", repo.root / "harness/state/progress.md")
    result = repo.invoke_raw("close-check", "--hook", stdin=payload)
    assert result.code == 2, result
    assert "escapes" in result.err
    (repo.root / "harness/state/progress.md").unlink()
    (repo.root / "harness/state/active.json").write_text("{not json")
    result = repo.invoke_raw("close-check", "--hook", stdin=payload)
    assert result.code == 2, result
    assert "close-check error" in result.err
    result = repo.invoke_raw("close-check", "--hook", stdin="{not json")
    assert result.code == 2


def test_disabled_stop_hook_never_blocks(repo, monkeypatch) -> None:
    monkeypatch.delenv("E_AGENT_HARNESS_UNATTENDED", raising=False)
    assert repo.invoke_raw("close-check", "--hook", stdin="{not json").code == 0
    looping = json.dumps({"stop_hook_active": True, "cwd": str(repo.root)})
    assert repo.invoke_raw("close-check", "--hook", stdin=looping).code == 0


def test_closed_task_stays_closed_for_the_scope_hook(repo) -> None:
    _closed(repo)

    def write(path: str) -> int:
        payload = json.dumps(
            {"tool_name": "Write", "tool_input": {"file_path": path}, "cwd": str(repo.root)}
        )
        return repo.invoke("check-scope", "--hook", stdin=payload).code

    assert write("docs/a.md") == 0
    repo.write("docs/a.md", "unrelated work\n")  # the tree is dirty now
    assert write("docs/b.md") == 0
    assert write("archive/old.md") == 2
    assert repo.invoke("refresh-task").code == 0  # reopening the task brings its scope back
    assert write("docs/c.md") == 2


def test_lowercase_z_timestamps_parse_everywhere() -> None:
    from e_agent_harness import closecheck, contracts

    doc = {"started_at": "2026-10-13T12:01:00z"}
    assert contracts.parse_timestamp("2026-10-13T12:01:00z").utcoffset().total_seconds() == 0
    assert closecheck.evidence_time(doc) == contracts.parse_timestamp("2026-10-13T12:01:00+00:00")
    assert closecheck.newest([doc, {"started_at": "2026-10-13T12:00:00Z"}]) is doc


def _write_code(repo, path: str) -> int:
    payload = json.dumps(
        {"tool_name": "Write", "tool_input": {"file_path": path}, "cwd": str(repo.root)}
    )
    return repo.invoke("check-scope", "--hook", stdin=payload).code


def test_closed_marker_does_not_survive_a_rollback(repo) -> None:
    from tests.harness.conftest import git

    _start(repo)
    repo.write("src/pkg/new.py", "Y = 2\n")
    before_close = repo.commit("feature code")
    _bookkeeping(repo, _evidence_path(repo))
    assert repo.invoke("close-check", "--session", "s1").code == 0
    assert _write_code(repo, "docs/a.md") == 0
    git(repo.root, "checkout", "-q", before_close)  # back to the unfinished task
    assert _write_code(repo, "docs/a.md") == 2
    assert repo.invoke("new-task", "1", "1c.2", "--feature", "F-2", "--paths", "src/**").code == 1


def test_inferred_closure_is_durable_in_a_fresh_clone(repo, tmp_path) -> None:
    from tests.harness.conftest import Repo, git

    _closed(repo)
    clone_root = tmp_path / "clone"
    git(tmp_path, "clone", "-q", str(repo.root), str(clone_root))
    clone = Repo(clone_root)
    assert _write_code(clone, "docs/a.md") == 0  # closure inferred, and recorded
    clone.write("docs/a.md", "unrelated\n")
    assert _write_code(clone, "docs/b.md") == 0


def test_refresh_reopens_even_on_a_clean_tree(repo) -> None:
    _closed(repo)
    assert repo.invoke("refresh-task").code == 0  # nothing changed: the tree stays clean
    assert repo.invoke("close-check", "--session", "s1").code == 0  # would infer closure
    assert repo.invoke("refresh-task").code == 0
    assert _write_code(repo, "docs/c.md") == 2


def test_rematerialising_a_reopened_task_keeps_it_open(repo) -> None:
    _closed(repo)
    assert repo.invoke("refresh-task").code == 0
    again = repo.invoke("new-task", "1", "1c.1", "--feature", "F-1", "--paths", "src/**")
    assert again.code == 0, again
    assert _write_code(repo, "docs/c.md") == 2


def test_switching_from_an_open_task_needs_close_check(repo) -> None:
    _closed(repo)
    assert repo.invoke("new-task", "1", "1c.1", "--feature", "F-1", "--paths", "src/**").code == 0
    result = repo.invoke("new-task", "1", "1c.2", "--feature", "F-2", "--paths", "src/**")
    assert result.code == 1
    assert "1c.1 is active" in result.out
