"""tidy: format and lint the whole change once, before the commit (harness H4.6)."""

UGLY = "import sys\nimport os\n\nprint(os.sep, sys.argv)\nx=1\n"
TIDY = "import os\nimport sys\n\nprint(os.sep, sys.argv)\nx = 1\n"
RUFF = '[lint]\nselect = ["E", "F", "I"]\n'


def _ruff_config(repo) -> None:
    repo.write("ruff.toml", RUFF)
    repo.commit("ruff config")


def test_tidy_formats_and_fixes_changed_python(repo) -> None:
    _ruff_config(repo)
    path = repo.write("src/pkg/new.py", UGLY)
    result = repo.invoke("tidy")
    assert result.code == 0, result
    assert path.read_text() == TIDY
    assert "1 Python file" in result.out


def test_tidy_leaves_unchanged_files_alone(repo) -> None:
    _ruff_config(repo)
    committed = repo.write("src/pkg/old.py", UGLY)
    repo.commit("an untidy file that is not part of this change")
    repo.write("src/pkg/new.py", UGLY)
    assert repo.invoke("tidy").code == 0
    assert committed.read_text() == UGLY


def test_tidy_covers_files_committed_since_the_task_base(repo) -> None:
    _ruff_config(repo)
    assert repo.invoke("new-task", "1", "1c.1", "--feature", "F-1", "--paths", "src/**").code == 0
    repo.commit("contract")
    path = repo.write("src/pkg/early.py", UGLY)
    repo.commit("committed before tidy")
    assert repo.invoke("tidy").code == 0
    assert path.read_text() == TIDY


def test_tidy_reports_what_it_cannot_fix(repo) -> None:
    _ruff_config(repo)
    repo.write("src/pkg/bad.py", "def f():\n    return undefined_name\n")
    result = repo.invoke("tidy")
    assert result.code == 1
    assert "F821" in result.out


def test_tidy_ignores_deleted_and_non_python_files(repo) -> None:
    _ruff_config(repo)
    (repo.root / "src/pkg/mod.py").unlink()
    repo.write("docs/notes.md", "# notes\n")
    repo.write("ui/app.ts", "const x=1\n")  # no ui/package.json here: the UI step is skipped
    result = repo.invoke("tidy")
    assert result.code == 0, result
    assert "nothing to tidy" in result.out or "0 Python files" in result.out
