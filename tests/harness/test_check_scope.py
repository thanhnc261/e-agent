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
