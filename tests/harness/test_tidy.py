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


def _fake_runs(monkeypatch, fail_on: str | None = None) -> list[list[str]]:
    import subprocess

    from e_agent_harness import tidy

    calls: list[list[str]] = []

    def run(args, root):
        calls.append(list(args))
        failed = fail_on is not None and fail_on in args
        return subprocess.CompletedProcess(args, 2 if failed else 0, "", "boom" if failed else "")

    monkeypatch.setattr(tidy, "_run", run)
    return calls


def test_tidy_formats_only_changed_ui_files_inside_the_prettier_scope(repo, monkeypatch) -> None:
    _ruff_config(repo)
    repo.write("ui/package.json", "{}")
    repo.write("ui/.prettierscope", "# migrated\npackages/a\n")
    repo.commit("ui")
    repo.write("ui/packages/a/x.ts", "const x=1\n")
    repo.write("ui/packages/b/y.ts", "const y=1\n")
    calls = _fake_runs(monkeypatch)
    assert repo.invoke("tidy").code == 0
    (pnpm,) = [c for c in calls if c[0] == "pnpm"]
    assert pnpm == ["pnpm", "--dir", "ui", "format", "packages/a/x.ts"]


def test_tidy_skips_ui_files_outside_the_prettier_scope(repo, monkeypatch) -> None:
    _ruff_config(repo)
    repo.write("ui/package.json", "{}")
    repo.write("ui/.prettierscope", "packages/a\n")
    repo.commit("ui")
    repo.write("ui/packages/b/y.ts", "const y=1\n")
    calls = _fake_runs(monkeypatch)
    assert repo.invoke("tidy").code == 0
    assert not [c for c in calls if c[0] == "pnpm"]


def test_tidy_reports_a_failed_formatter(repo, monkeypatch) -> None:
    _ruff_config(repo)
    repo.write("src/pkg/new.py", "x = 1\n")
    _fake_runs(monkeypatch, fail_on="format")
    result = repo.invoke("tidy")
    assert result.code == 1
    assert "ruff format failed" in result.out and "boom" in result.out


def test_tidy_matches_real_prettier_scope_globs(repo, monkeypatch) -> None:
    _ruff_config(repo)
    repo.write("ui/package.json", "{}")
    repo.write("ui/.prettierscope", "apps/web/src/**/*.tsx\npackages/ui-core/src/selectors/*.ts\n")
    repo.commit("ui")
    repo.write("ui/apps/web/src/pages/Overview.tsx", "x\n")
    repo.write("ui/apps/web/src/App.tsx", "x\n")
    repo.write("ui/packages/ui-core/src/selectors/a.ts", "x\n")
    repo.write("ui/packages/ui-core/src/selectors/deep/b.ts", "x\n")  # outside: * is one level
    calls = _fake_runs(monkeypatch)
    assert repo.invoke("tidy").code == 0
    (pnpm,) = [c for c in calls if c[0] == "pnpm"]
    assert pnpm[4:] == [
        "apps/web/src/App.tsx",
        "apps/web/src/pages/Overview.tsx",
        "packages/ui-core/src/selectors/a.ts",
    ]


def test_r13_tidy_never_writes_through_a_symlink(repo, tmp_path) -> None:
    ugly = "x=1\n"
    outside = tmp_path / "shared.py"
    outside.write_text(ugly)
    inside = repo.root / "src" / "pkg" / "kept.py"
    inside.parent.mkdir(parents=True, exist_ok=True)
    inside.write_text(ugly)
    repo.commit("an unchanged file")
    (repo.root / "src" / "pkg" / "linked.py").symlink_to(outside)
    (repo.root / "src" / "pkg" / "alias.py").symlink_to(inside)
    outside_dir = tmp_path / "pkgdir"
    outside_dir.mkdir()
    (outside_dir / "mod.py").write_text(ugly)
    (repo.root / "src" / "linkdir").symlink_to(outside_dir)
    result = repo.invoke("tidy")
    assert outside.read_text() == ugly
    assert inside.read_text() == ugly
    assert (outside_dir / "mod.py").read_text() == ugly
    assert "skipped src/pkg/linked.py: reached through a symlink" in result.out
    assert "skipped src/pkg/alias.py: reached through a symlink" in result.out
