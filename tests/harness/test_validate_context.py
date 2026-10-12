import pytest

from e_agent_harness import gitinfo, state


def test_validate_context_passes_on_scratch_repo(repo) -> None:
    result = repo.invoke("validate-context")
    assert result.code == 0, result
    assert "ok" in result.out


def test_validate_context_lists_problems_and_exits_1(repo) -> None:
    (repo.root / "AGENTS.md").unlink()
    result = repo.invoke("validate-context")
    assert result.code == 1
    assert "authoritative file missing: AGENTS.md" in result.out


def test_validate_context_requires_roadmap_to_link_the_active_plan(repo) -> None:
    repo.write("docs/roadmap.md", "# roadmap without a plan link\n")
    result = repo.invoke("validate-context")
    assert result.code == 1
    assert "roadmap does not link the active plan" in result.out


def test_find_repo_root_walks_up(repo) -> None:
    nested = repo.root / "src" / "pkg"
    assert state.find_repo_root(nested) == repo.root


def test_active_round_trip(repo) -> None:
    paths = state.Paths(repo.root)
    assert state.load_active(paths) is None
    state.save_active(paths, "1", "1c.1")
    assert state.load_active(paths) == {"phase": "1", "task": "1c.1"}


def test_gitinfo_reports_tree_state(repo) -> None:
    assert gitinfo.is_clean(repo.root)
    assert gitinfo.head_sha(repo.root) == repo.base
    assert gitinfo.branch(repo.root) == "main"
    repo.write("src/pkg/new.py", "Y = 2\n")
    assert gitinfo.status_files(repo.root) == ["src/pkg/new.py"]
    head = repo.commit("add new")
    assert gitinfo.diff_names(repo.root, repo.base) == ["src/pkg/new.py"]
    assert gitinfo.is_ancestor(repo.root, repo.base, head)
    assert not gitinfo.is_ancestor(repo.root, head, repo.base)


def test_unknown_command_exits_2(repo) -> None:
    with pytest.raises(SystemExit) as exc:
        repo.invoke("no-such-command")
    assert exc.value.code == 2
