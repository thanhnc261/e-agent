import json

from e_agent_harness import state


def test_new_task_writes_contract_and_activates_it(repo) -> None:
    result = repo.invoke(
        "new-task", "1", "1c.1", "--feature", "F-1", "--paths", "src/pkg/**", "--gate", "quick"
    )
    assert result.code == 0, result
    contract = json.loads((repo.root / "harness/state/1/tasks/1c.1.json").read_text())
    assert contract["feature_ids"] == ["F-1"]
    assert contract["acceptance"] == ["run the suite"]
    assert contract["allowed_paths"][:1] == ["src/pkg/**"]
    assert "harness/state/**" in contract["allowed_paths"]
    assert "docs/plans/phase1.md" in contract["allowed_paths"]
    assert contract["base_commit"] == repo.base
    assert len(contract["context_digest"]) == 64
    assert state.load_active(state.Paths(repo.root)) == {"phase": "1", "task": "1c.1"}


def test_new_task_rejects_unknown_feature(repo) -> None:
    result = repo.invoke("new-task", "1", "1c.9", "--feature", "F-9", "--paths", "src/**")
    assert result.code == 1
    assert "unknown feature" in result.out and "F-9" in result.out


def test_new_task_refuses_second_active_task_without_replace(repo) -> None:
    assert repo.invoke("new-task", "1", "1c.1", "--feature", "F-1", "--paths", "src/**").code == 0
    second = repo.invoke("new-task", "1", "1c.2", "--feature", "F-2", "--paths", "src/**")
    assert second.code == 1
    assert "1c.1 is active" in second.out
    replaced = repo.invoke(
        "new-task", "1", "1c.2", "--feature", "F-2", "--paths", "src/**", "--replace"
    )
    assert replaced.code == 0
    assert state.load_active(state.Paths(repo.root))["task"] == "1c.2"


def test_new_task_uses_explicit_acceptance_when_given(repo) -> None:
    result = repo.invoke(
        "new-task",
        "1",
        "1c.1",
        "--feature",
        "F-1",
        "--paths",
        "src/**",
        "--acceptance",
        "pytest -q src passes",
        "--acceptance",
        "openapi unchanged",
    )
    assert result.code == 0
    contract = json.loads((repo.root / "harness/state/1/tasks/1c.1.json").read_text())
    assert contract["acceptance"] == ["pytest -q src passes", "openapi unchanged"]
