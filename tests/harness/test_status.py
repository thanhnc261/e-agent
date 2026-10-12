import json
from pathlib import Path

from e_agent_harness import manifest as mf
from e_agent_harness import state, status

REAL_REPO = Path(__file__).resolve().parents[2]


def test_status_without_state_names_new_task(repo) -> None:
    result = repo.invoke("status")
    assert result.code == 0, result
    assert "Tóm tắt" in result.out  # vi-eli5 first
    assert "new-task" in result.out
    assert "odoo-bench*" in result.out  # boundary reminder


def test_status_shows_active_task_and_next_action(repo) -> None:
    assert (
        repo.invoke("new-task", "1", "1c.1", "--feature", "F-1", "--paths", "src/pkg/**").code == 0
    )
    repo.write("src/pkg/new.py", "Y = 2\n")
    result = repo.invoke("status")
    assert "1c.1" in result.out and "src/pkg/**" in result.out
    assert "commit the work" in result.out  # dirty tree → commit, then gate


def test_status_flags_stale_digest(repo) -> None:
    assert repo.invoke("new-task", "1", "1c.1", "--feature", "F-1", "--paths", "src/**").code == 0
    repo.write("AGENTS.md", "# rules changed\n")
    result = repo.invoke("status")
    assert "stale" in result.out
    assert "--replace" in result.out


def test_status_hook_format_is_sessionstart_json_within_budget(repo) -> None:
    assert repo.invoke("new-task", "1", "1c.1", "--feature", "F-1", "--paths", "src/**").code == 0
    for i in range(10):
        assert repo.invoke("checkpoint", "--next", f"step {i} " + "x" * 200).code == 0
    result = repo.invoke("status", "--format", "hook")
    doc = json.loads(result.out)
    out = doc["hookSpecificOutput"]
    assert out["hookEventName"] == "SessionStart"
    assert out["sessionTitle"] == "phase-1/1c.1"
    assert status.estimate_tokens(out["additionalContext"]) <= 600
    assert "step 9" in out["additionalContext"]  # newest entry survives trimming


def test_status_hook_fits_budget_on_real_repository() -> None:
    paths = state.Paths(REAL_REPO)
    m = mf.load_manifest(paths.manifest)
    data = status.collect(paths, m, REAL_REPO)
    rendered = json.loads(status.render_hook(data, m.status.token_budget))
    text = rendered["hookSpecificOutput"]["additionalContext"]
    assert status.estimate_tokens(text) <= m.status.token_budget


def test_next_action_order(repo) -> None:
    paths = state.Paths(repo.root)
    m = mf.load_manifest(paths.manifest)
    assert status.next_action(status.collect(paths, m, repo.root)).startswith("new-task")
    assert repo.invoke("new-task", "1", "1c.1", "--feature", "F-1", "--paths", "src/**").code == 0
    assert status.next_action(status.collect(paths, m, repo.root)).startswith("commit the work")
