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


def _contract(repo) -> dict:
    return json.loads((repo.root / "harness/state/1/tasks/1c.1.json").read_text())


def _edit_feature_steps(repo, steps: list[str]) -> None:
    path = repo.root / "harness/state/1/features.json"
    doc = json.loads(path.read_text())
    doc["entries"][0]["steps"] = steps
    path.write_text(json.dumps(doc, indent=2) + "\n")


def test_contract_pins_features_digest(repo) -> None:
    assert repo.invoke("new-task", "1", "1c.1", "--feature", "F-1", "--paths", "src/**").code == 0
    assert len(_contract(repo)["features_digest"]) == 64


def test_status_and_close_check_flag_changed_acceptance(repo) -> None:
    assert repo.invoke("new-task", "1", "1c.1", "--feature", "F-1", "--paths", "src/**").code == 0
    _edit_feature_steps(repo, ["run the suite", "check the new invariant"])
    assert "refresh-task --from-features" in repo.invoke("status").out
    out = repo.invoke("close-check").out
    assert "acceptance changed since the task was materialised" in out


def test_refresh_task_keeps_base_and_paths(repo) -> None:
    assert repo.invoke("new-task", "1", "1c.1", "--feature", "F-1", "--paths", "src/**").code == 0
    before = _contract(repo)
    repo.write(
        "docs/plans/phase1.md", (repo.root / "docs/plans/phase1.md").read_text() + "\nnote\n"
    )
    repo.commit("plan note mid-task")
    assert "stale" in repo.invoke("status").out
    result = repo.invoke("refresh-task")
    assert result.code == 0, result
    after = _contract(repo)
    assert after["context_digest"] != before["context_digest"]
    for key in ("base_commit", "created_at", "allowed_paths", "acceptance"):
        assert after[key] == before[key], key
    assert "stale" not in repo.invoke("status").out


def test_refresh_task_from_features_rederives_acceptance(repo) -> None:
    assert repo.invoke("new-task", "1", "1c.1", "--feature", "F-1", "--paths", "src/**").code == 0
    _edit_feature_steps(repo, ["run the suite", "check the new invariant"])
    assert repo.invoke("refresh-task", "--from-features").code == 0
    assert _contract(repo)["acceptance"] == ["run the suite", "check the new invariant"]
    assert "refresh-task" not in repo.invoke("status").out


def test_amend_scope_adds_glob_with_reason(repo) -> None:
    assert repo.invoke("new-task", "1", "1c.1", "--feature", "F-1", "--paths", "src/**").code == 0
    repo.write("scripts/tool.py", "pass\n")
    assert repo.invoke("check-scope").code == 1
    result = repo.invoke(
        "amend-scope", "--add", "scripts/tool.py", "--reason", "false positive in tool"
    )
    assert result.code == 0, result
    contract = _contract(repo)
    assert "scripts/tool.py" in contract["allowed_paths"]
    (change,) = contract["scope_changes"]
    assert change["glob"] == "scripts/tool.py" and change["reason"] == "false positive in tool"
    assert contract["base_commit"] == repo.base
    assert repo.invoke("check-scope").code == 0


def test_amend_scope_requires_an_active_task(repo) -> None:
    result = repo.invoke("amend-scope", "--add", "x/**", "--reason", "r")
    assert result.code == 1
    assert "no active task" in result.out


def test_new_task_dedupes_paths(repo) -> None:
    result = repo.invoke(
        "new-task",
        "1",
        "1c.1",
        "--feature",
        "F-1",
        "--paths",
        "src/**",
        "--paths",
        "docs/handoffs/**",
        "--paths",
        "src/**",
    )
    assert result.code == 0
    paths = _contract(repo)["allowed_paths"]
    assert len(paths) == len(set(paths))


def test_old_contract_without_new_fields_loads(repo) -> None:
    assert repo.invoke("new-task", "1", "1c.1", "--feature", "F-1", "--paths", "src/**").code == 0
    path = repo.root / "harness/state/1/tasks/1c.1.json"
    doc = json.loads(path.read_text())
    doc.pop("features_digest")
    path.write_text(json.dumps(doc) + "\n")
    from e_agent_harness import contracts

    assert contracts.validate("task", doc) == []
    assert "refresh-task" not in repo.invoke("status").out
    assert repo.invoke("check-scope").code == 0


def test_plain_refresh_keeps_feature_drift(repo) -> None:
    assert repo.invoke("new-task", "1", "1c.1", "--feature", "F-1", "--paths", "src/**").code == 0
    _edit_feature_steps(repo, ["run the suite", "check the new invariant"])
    assert repo.invoke("refresh-task").code == 0
    assert "refresh-task --from-features" in repo.invoke("status").out
    assert _contract(repo)["acceptance"] == ["run the suite"]
