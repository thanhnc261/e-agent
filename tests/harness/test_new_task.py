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


def test_replace_keeps_base_commit_and_created_at_for_the_same_task(repo) -> None:
    assert repo.invoke("new-task", "1", "1c.1", "--feature", "F-1", "--paths", "src/**").code == 0
    first = json.loads((repo.root / "harness/state/1/tasks/1c.1.json").read_text())
    repo.write("docs/other.md", "out of scope\n")
    repo.commit("drift")
    assert (
        repo.invoke(
            "new-task", "1", "1c.1", "--feature", "F-1", "--paths", "src/**", "--replace"
        ).code
        == 0
    )
    again = json.loads((repo.root / "harness/state/1/tasks/1c.1.json").read_text())
    assert again["base_commit"] == first["base_commit"] == repo.base
    assert again["created_at"] == first["created_at"]
    assert repo.invoke("check-scope").code == 1  # the drift is still visible


def test_new_task_accepts_manifest_gate_sets(repo) -> None:
    manifest = repo.root / "harness/context.toml"
    manifest.write_text(
        manifest.read_text().replace("[roles]", 'ui = ["echo ui ok"]\n\n[roles]', 1)
    )
    result = repo.invoke(
        "new-task", "1", "1c.1", "--feature", "F-1", "--paths", "ui/**", "--gate", "ui"
    )
    assert result.code == 0, result
    contract = json.loads((repo.root / "harness/state/1/tasks/1c.1.json").read_text())
    assert contract["gate_set"] == "ui"


def test_new_task_rejects_unknown_gate_set(repo) -> None:
    result = repo.invoke(
        "new-task", "1", "1c.1", "--feature", "F-1", "--paths", "src/**", "--gate", "nope"
    )
    assert result.code == 1
    assert "unknown gate set: nope" in result.out
