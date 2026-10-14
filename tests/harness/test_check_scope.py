import json


def _activate(repo) -> None:
    assert (
        repo.invoke("new-task", "1", "1c.1", "--feature", "F-1", "--paths", "src/pkg/**").code == 0
    )


def test_check_scope_passes_for_in_scope_change(repo) -> None:
    _activate(repo)
    repo.write("src/pkg/new.py", "Y = 2\n")
    result = repo.invoke("check-scope")
    assert result.code == 0, result


def test_check_scope_rejects_out_of_scope_and_protected_changes(repo) -> None:
    _activate(repo)
    repo.write("docs/other.md", "x\n")
    repo.write("archive/old.md", "changed\n")
    result = repo.invoke("check-scope")
    assert result.code == 1
    assert "docs/other.md: outside the task's allowed paths" in result.out
    assert "archive/old.md: protected path" in result.out


def test_check_scope_sees_committed_changes_since_base(repo) -> None:
    _activate(repo)
    repo.write("docs/other.md", "x\n")
    repo.commit("out of scope, committed")
    result = repo.invoke("check-scope")
    assert result.code == 1
    assert "docs/other.md" in result.out


def test_check_scope_requires_bridge_bump_for_addons_change(repo) -> None:
    assert (
        repo.invoke("new-task", "1", "1c.1", "--feature", "F-1", "--paths", "addons/**").code == 0
    )
    repo.write("addons/e_agent_bridge/models.py", "pass\n")
    result = repo.invoke("check-scope")
    assert result.code == 1
    assert "addons/e_agent_bridge/__manifest__.py" in result.out
    repo.write("addons/e_agent_bridge/__manifest__.py", "{'version': '1.1'}\n")
    assert repo.invoke("check-scope").code == 0


def test_check_scope_without_task_only_guards_protected_paths(repo) -> None:
    repo.write("docs/other.md", "x\n")
    assert repo.invoke("check-scope").code == 0
    repo.write("archive/old.md", "changed\n")
    assert repo.invoke("check-scope").code == 1


def _payload(repo, tool: str, path: str) -> str:
    return json.dumps({"tool_name": tool, "tool_input": {"file_path": path}, "cwd": str(repo.root)})


def test_hook_allows_in_scope_edit_silently(repo) -> None:
    _activate(repo)
    result = repo.invoke("check-scope", "--hook", stdin=_payload(repo, "Edit", "src/pkg/mod.py"))
    assert result == (0, "", "")


def test_hook_denies_out_of_scope_edit_with_reason_on_stderr(repo) -> None:
    _activate(repo)
    target = str(repo.root / "docs/other.md")
    result = repo.invoke("check-scope", "--hook", stdin=_payload(repo, "Write", target))
    assert result.code == 2
    assert "outside the task's allowed paths" in result.err


def test_hook_denies_path_outside_repository(repo) -> None:
    _activate(repo)
    outside = repo.root.parent / "elsewhere.py"
    result = repo.invoke("check-scope", "--hook", stdin=_payload(repo, "Edit", str(outside)))
    assert result.code == 2
    assert "outside the repository" in result.err


def test_hook_ignores_other_tools(repo) -> None:
    _activate(repo)
    payload = json.dumps(
        {"tool_name": "Bash", "tool_input": {"command": "rm -rf archive"}, "cwd": str(repo.root)}
    )
    assert repo.invoke("check-scope", "--hook", stdin=payload).code == 0


def test_hook_resolves_repository_from_payload_cwd_not_repo_flag(repo, tmp_path) -> None:
    _activate(repo)
    # The --repo flag points elsewhere; the payload's cwd is the repository that must decide.
    other = tmp_path / "other"
    other.mkdir()
    payload = json.dumps(
        {"tool_name": "Edit", "tool_input": {"file_path": "archive/old.md"}, "cwd": str(repo.root)}
    )
    result = repo.invoke_at(other, "check-scope", "--hook", stdin=payload)
    assert result.code == 2
    assert "protected path" in result.err


def test_hook_fails_closed_on_corrupt_state(repo) -> None:
    _activate(repo)
    (repo.root / "harness/state/active.json").write_text("{not json")
    result = repo.invoke("check-scope", "--hook", stdin=_payload(repo, "Edit", "src/pkg/mod.py"))
    assert result.code == 2
    assert "check-scope error" in result.err


def test_check_scope_prints_ok_with_count(repo) -> None:
    _activate(repo)
    repo.write("src/pkg/new.py", "Y = 2\n")
    result = repo.invoke("check-scope")
    assert result.code == 0
    assert "ok: 3 changed paths inside scope" in result.out  # contract, active.json, new.py


def test_hook_denies_backslash_paths(repo) -> None:
    _activate(repo)
    payload = _payload(repo, "Write", "archive/..\\src\\pkg\\owned.py")
    result = repo.invoke("check-scope", "--hook", stdin=payload)
    assert result.code == 2
    assert "backslash" in result.err


def test_hook_after_close_guards_only_protected_paths(repo) -> None:
    _activate(repo)
    repo.commit("contract")
    repo.write("src/pkg/new.py", "Y = 2\n")
    repo.commit("work")
    assert repo.invoke("gate", "quick").code == 0
    (evidence,) = (repo.root / "harness/state/evidence/gates/1c.1").glob("*.json")
    features = repo.root / "harness/state/1/features.json"
    doc = json.loads(features.read_text())
    doc["entries"][0].update(passes=True, evidence=str(evidence.relative_to(repo.root)))
    features.write_text(json.dumps(doc) + "\n")
    handoff = {
        "task": "1c.1",
        "changed": "x",
        "evidence_refs": [str(evidence.relative_to(repo.root))],
        "open_items": [],
        "rulings": [],
        "outside_repo": [],
    }
    repo.write("harness/state/1/handoffs/1c.1.json", json.dumps(handoff) + "\n")
    assert repo.invoke("checkpoint", "--session", "s").code == 0
    repo.commit("bookkeeping")
    assert repo.invoke("close-check", "--session", "s").code == 0
    # The task is closed: unrelated work is not held to its scope, protected paths still are.
    assert (
        repo.invoke("check-scope", "--hook", stdin=_payload(repo, "Write", "docs/notes.md")).code
        == 0
    )
    denied = repo.invoke("check-scope", "--hook", stdin=_payload(repo, "Write", "archive/old.md"))
    assert denied.code == 2


def _create_only_research(repo) -> None:
    manifest = repo.root / "harness/context.toml"
    text = manifest.read_text().replace(
        'read_only = ["archive/**"]',
        'read_only = ["archive/**", "research/**"]\ncreate_only = ["research/**"]',
    )
    manifest.write_text(text)
    repo.write("research/01-old-study.md", "kept as written\n")
    repo.commit("research baseline")


def test_hook_allows_a_new_file_under_create_only(repo) -> None:
    _create_only_research(repo)
    new = repo.invoke("check-scope", "--hook", stdin=_payload(repo, "Write", "research/02-new.md"))
    assert new.code == 0, new
    old = repo.invoke(
        "check-scope", "--hook", stdin=_payload(repo, "Edit", "research/01-old-study.md")
    )
    assert old.code == 2
    assert "protected path" in old.err


def test_create_only_new_files_still_need_the_task_scope(repo) -> None:
    _create_only_research(repo)
    _activate(repo)  # scope src/pkg/** only
    result = repo.invoke(
        "check-scope", "--hook", stdin=_payload(repo, "Write", "research/02-new.md")
    )
    assert result.code == 2
    assert "outside the task's allowed paths" in result.err


def test_tree_check_allows_new_and_refuses_changed_create_only_files(repo) -> None:
    _create_only_research(repo)
    repo.write("research/02-new.md", "a new study\n")
    assert repo.invoke("check-scope").code == 0
    repo.commit("new study")
    repo.write("research/01-old-study.md", "rewritten\n")
    result = repo.invoke("check-scope")
    assert result.code == 1
    assert "research/01-old-study.md: protected path" in result.out


def test_renaming_an_existing_report_is_refused(repo) -> None:
    from tests.harness.conftest import git

    _create_only_research(repo)
    git(repo.root, "mv", "research/01-old-study.md", "research/03-renamed.md")
    result = repo.invoke("check-scope")
    assert result.code == 1
    assert "research/01-old-study.md: protected path" in result.out


def test_committed_rename_since_the_base_is_refused(repo) -> None:
    from tests.harness.conftest import git

    _create_only_research(repo)
    assert (
        repo.invoke("new-task", "1", "1c.1", "--feature", "F-1", "--paths", "research/**").code == 0
    )
    repo.commit("contract")
    git(repo.root, "mv", "research/01-old-study.md", "research/03-renamed.md")
    repo.commit("rename")
    result = repo.invoke("check-scope")
    assert result.code == 1
    assert "research/01-old-study.md: protected path" in result.out


def test_unknown_base_commit_never_counts_as_new(repo) -> None:
    _create_only_research(repo)
    assert (
        repo.invoke("new-task", "1", "1c.1", "--feature", "F-1", "--paths", "research/**").code == 0
    )
    contract_path = repo.root / "harness/state/1/tasks/1c.1.json"
    contract = json.loads(contract_path.read_text())
    contract["base_commit"] = "0123456789abcdef0123456789abcdef01234567"  # not in this clone
    contract_path.write_text(json.dumps(contract) + "\n")
    old = repo.invoke(
        "check-scope", "--hook", stdin=_payload(repo, "Write", "research/01-old-study.md")
    )
    assert old.code == 2
