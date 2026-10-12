import json

from e_agent_harness import progress


def _entries(repo) -> list[progress.ProgressEntry]:
    return progress.parse_progress((repo.root / "harness/state/progress.md").read_text())


def test_checkpoint_appends_entry_with_defaults(repo) -> None:
    assert repo.invoke("new-task", "1", "1c.1", "--feature", "F-1", "--paths", "src/**").code == 0
    repo.write("src/pkg/new.py", "Y = 2\n")
    result = repo.invoke("checkpoint", "--session", "sess-1")
    assert result.code == 0, result
    (entry,) = _entries(repo)
    assert entry.task == "1c.1"
    assert entry.session == "sess-1"
    assert "src/pkg/new.py" in entry.changed
    assert entry.next == "run the suite"
    assert entry.open == "none"


def test_checkpoint_without_task_points_at_new_task(repo) -> None:
    assert repo.invoke("checkpoint").code == 0
    (entry,) = _entries(repo)
    assert entry.task == "none"
    assert entry.next == "new-task"
    assert entry.changed == "no working-tree changes"


def test_checkpoint_sanitises_newlines(repo) -> None:
    assert repo.invoke("checkpoint", "--next", "line one\nline two").code == 0
    (entry,) = _entries(repo)
    assert entry.next == "line one line two"


def test_checkpoint_hook_uses_session_id_and_never_fails(repo) -> None:
    payload = json.dumps({"session_id": "abc123", "trigger": "auto", "cwd": str(repo.root)})
    assert repo.invoke("checkpoint", "--hook", stdin=payload).code == 0
    assert _entries(repo)[0].session == "abc123"
    (repo.root / "harness/context.toml").unlink()  # anything broken: still exit 0
    result = repo.invoke("checkpoint", "--hook", stdin=payload)
    assert result.code == 0
    assert result.err.strip()


def test_checkpoint_hook_finds_repository_from_subdirectory(repo) -> None:
    payload = json.dumps(
        {"session_id": "s9", "trigger": "auto", "cwd": str(repo.root / "src" / "pkg")}
    )
    result = repo.invoke_raw("checkpoint", "--hook", stdin=payload)
    assert result.code == 0
    assert result.err == ""
    assert _entries(repo)[0].session == "s9"
