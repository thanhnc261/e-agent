"""The Phase 1 mover script on a scratch git repository (plan Task 1a.2)."""

import importlib.util
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("repo_move", REPO / "scripts" / "repo_move.py")
assert _spec is not None
assert _spec.loader is not None
rm = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = rm  # dataclasses resolve annotations through sys.modules
_spec.loader.exec_module(rm)

KERNEL_PYPROJECT = """[project]
name = "e-agent-kernel"
version = "0.1.0"
dependencies = ["e-agent-contracts>=0.1,<0.2"]

[build-system]
requires = ["uv_build>=0.11,<0.12"]
build-backend = "uv_build"

[tool.uv.build-backend]
module-name = "e_agent.kernel"
"""

SERVER_PYPROJECT = """[project]
name = "e-agent-server"
version = "0.1.0"

[project.scripts]
e-agent = "e_agent.server.cli:main"

[build-system]
requires = ["uv_build>=0.11,<0.12"]
build-backend = "uv_build"

[tool.uv.build-backend]
module-name = "e_agent.server"
"""

MOVES = (
    rm.Move("packages/kernel", "kernel"),
    rm.Move("packages/adapter-odoo", "adapters/odoo"),
    rm.Move("apps/server", "server"),
)


def git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.email=t@example.invalid", "-c", "user.name=t", *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def write(root: Path, rel: str, text: str = "") -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    write(tmp_path, "packages/kernel/pyproject.toml", KERNEL_PYPROJECT)
    write(tmp_path, "packages/kernel/src/e_agent/kernel/__init__.py")
    write(tmp_path, "packages/kernel/src/e_agent/kernel/coordinator.py", "X = 1\n")
    write(tmp_path, "packages/kernel/tests/__init__.py")
    write(tmp_path, "packages/kernel/tests/test_k.py", "def test_k(): pass\n")
    write(
        tmp_path,
        "packages/adapter-odoo/pyproject.toml",
        KERNEL_PYPROJECT.replace("kernel", "adapter-odoo"),
    )
    write(tmp_path, "packages/adapter-odoo/src/e_agent/adapters/odoo/__init__.py")
    write(tmp_path, "packages/adapter-odoo/src/e_agent/adapters/odoo/e_agent_plugin.json", "{}")
    write(tmp_path, "packages/adapter-odoo/tests/__init__.py")
    write(tmp_path, "apps/server/pyproject.toml", SERVER_PYPROJECT)
    write(tmp_path, "apps/server/src/e_agent/server/__init__.py")
    write(tmp_path, "apps/server/tests/__init__.py")
    write(
        tmp_path,
        "docs/design.md",
        "See [kernel](../packages/kernel/src/e_agent/kernel/coordinator.py#L1), "
        "[odoo tests](../packages/adapter-odoo/tests/), [web](https://example.org/x) "
        "and [top](#top).\n",
    )
    write(tmp_path, "docs/plan.md", "[design](design.md) and [plan](plan.md#steps)\n")
    write(tmp_path, "archive/old.md", "[design](../docs/design.md)\n")
    git(tmp_path, "init", "-q")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "init")
    return tmp_path


def test_layout_moves_code_tests_and_configs_with_git_history(repo: Path) -> None:
    (repo / "packages/kernel/src/e_agent/kernel/__pycache__").mkdir()
    (repo / "packages/kernel/src/e_agent/kernel/__pycache__/c.pyc").write_bytes(b"x")
    rm.layout(repo, MOVES)

    assert (repo / "src/e_agent/kernel/coordinator.py").read_text() == "X = 1\n"
    assert (repo / "src/e_agent/adapters/odoo/e_agent_plugin.json").is_file()
    assert (repo / "src/e_agent/server/__init__.py").is_file()
    assert (repo / "tests/unit/kernel/test_k.py").is_file()
    assert (repo / "tests/unit/adapters/odoo/__init__.py").is_file()
    assert (repo / "tests/unit/server/__init__.py").is_file()
    assert (repo / "tests/unit/__init__.py").is_file()
    assert (repo / "tests/unit/adapters/__init__.py").is_file()
    assert not (repo / "src/e_agent/__init__.py").exists()
    assert not (repo / "src/e_agent/adapters/__init__.py").exists()
    assert not (repo / "packages").exists()
    assert not (repo / "apps").exists()
    status = git(repo, "status", "--porcelain")
    assert "R  packages/kernel/src/e_agent/kernel/coordinator.py -> src/e_agent/kernel/" in status
    assert "dists/kernel/pyproject.toml" in status
    assert "??" not in status


def test_layout_generates_hatchling_configs_from_the_old_project_table(repo: Path) -> None:
    rm.layout(repo, MOVES)

    text = (repo / "dists/kernel/pyproject.toml").read_text(encoding="utf-8")
    config = tomllib.loads(text)
    assert config["project"] == tomllib.loads(KERNEL_PYPROJECT)["project"]
    assert config["build-system"]["build-backend"] == "hatchling.build"
    assert "uv" not in config.get("tool", {})
    wheel = config["tool"]["hatch"]["build"]["targets"]["wheel"]
    assert wheel["dev-mode-dirs"] == ["../../src"]
    # A static force-include would also be copied into the editable install and
    # shadow src/; the hook adds the sub-tree to standard wheels only.
    assert "force-include" not in wheel
    assert wheel["hooks"]["custom"] == {
        "path": "../_hooks/src_tree.py",
        "package": "e_agent/kernel",
    }
    odoo = tomllib.loads((repo / "dists/adapter-odoo/pyproject.toml").read_text())
    assert odoo["tool"]["hatch"]["build"]["targets"]["wheel"]["hooks"]["custom"]["package"] == (
        "e_agent/adapters/odoo"
    )
    server = tomllib.loads((repo / "dists/server/pyproject.toml").read_text())
    assert server["project"]["scripts"] == {"e-agent": "e_agent.server.cli:main"}
    hook = (repo / "dists/_hooks/src_tree.py").read_text(encoding="utf-8")
    assert 'version != "standard"' in hook
    assert "dists/_hooks/src_tree.py" in git(repo, "status", "--porcelain")


def test_layout_refuses_to_delete_leftover_untracked_files(repo: Path) -> None:
    write(repo, "packages/kernel/notes.txt", "local")
    with pytest.raises(rm.MoveError, match=r"packages/kernel/notes\.txt"):
        rm.layout(repo, MOVES)
    assert (repo / "packages/kernel/src/e_agent/kernel/coordinator.py").is_file()


def test_layout_refuses_untracked_files_that_git_mv_would_carry(repo: Path) -> None:
    write(repo, "packages/kernel/tests/scratch.txt", "local")
    with pytest.raises(rm.MoveError, match=r"packages/kernel/tests/scratch\.txt"):
        rm.layout(repo, MOVES)


def test_links_resolve_from_the_old_place_of_a_document_inside_moved_code(repo: Path) -> None:
    write(
        repo, "packages/kernel/src/e_agent/kernel/NOTES.md", "[plan](../../../../../docs/plan.md)\n"
    )
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "notes")
    rm.layout(repo, MOVES)
    rm.rewrite_links(repo, rm.layout_mapping(MOVES))

    assert (repo / "src/e_agent/kernel/NOTES.md").read_text() == "[plan](../../../docs/plan.md)\n"


def test_links_rewrite_after_the_layout_move(repo: Path) -> None:
    rm.layout(repo, MOVES)
    changed = rm.rewrite_links(repo, rm.layout_mapping(MOVES))

    assert changed == ["docs/design.md"]
    text = (repo / "docs/design.md").read_text()
    assert "[kernel](../src/e_agent/kernel/coordinator.py#L1)" in text
    assert "[odoo tests](../tests/unit/adapters/odoo/)" in text
    assert "[web](https://example.org/x)" in text
    assert "[top](#top)" in text


def test_links_move_documents_and_rewrite_both_directions(repo: Path) -> None:
    rm.move_documents(repo, ["docs/design.md"], "docs/design")

    assert (repo / "docs/design/design.md").is_file()
    assert "[design](design/design.md)" in (repo / "docs/plan.md").read_text()
    moved = (repo / "docs/design/design.md").read_text()
    assert "(../../packages/kernel/src/e_agent/kernel/coordinator.py#L1)" in moved
    assert (repo / "archive/old.md").read_text() == "[design](../docs/design.md)\n"


def test_links_skip_fenced_code(repo: Path) -> None:
    write(repo, "docs/code.md", "```md\n[x](../packages/kernel/)\n```\n")
    git(repo, "add", "docs/code.md")
    rm.layout(repo, MOVES)
    rm.rewrite_links(repo, rm.layout_mapping(MOVES))

    assert "(../packages/kernel/)" in (repo / "docs/code.md").read_text()
    assert rm.check(repo, MOVES).broken_links == []


def test_check_reports_broken_links_and_stale_references(repo: Path) -> None:
    rm.layout(repo, MOVES)
    write(repo, "Makefile", "test:\n\tuv run pytest packages/kernel\n")
    write(repo, "ui/packages/x/package.json", '{"name": "ui-packages-are-fine"}\n')
    write(repo, "ui/packages/x/t.ts", 'new URL("../../../packages/kernel/v.json")\n')
    git(repo, "add", "Makefile", "ui/packages/x/package.json", "ui/packages/x/t.ts")

    report = rm.check(repo, MOVES)
    assert ("docs/design.md", "../packages/kernel/src/e_agent/kernel/coordinator.py") in (
        report.broken_links
    )
    assert ("Makefile", 2, "packages/kernel") in report.stale_references
    assert ("ui/packages/x/t.ts", 1, "packages/kernel") in report.stale_references
    assert all(path != "ui/packages/x/package.json" for path, _, _ in report.stale_references)
    assert all(path != "archive/old.md" for path, _ in report.broken_links)

    rm.rewrite_links(repo, rm.layout_mapping(MOVES))
    write(repo, "Makefile", "test:\n\tuv run pytest tests/unit/kernel\n")
    write(repo, "ui/packages/x/t.ts", 'new URL("../../../src/e_agent/kernel/v.json")\n')
    assert rm.check(repo, MOVES).ok


def test_links_leave_footnotes_prose_and_unclosed_backticks_alone(repo: Path) -> None:
    write(
        repo,
        "docs/a.md",
        "[^1]: See the notes\n"
        "[Note]: this is prose\n"
        '[ref]: ../packages/kernel/ "Kernel"\n'
        "a lone ` backtick then [k](../packages/kernel/)\n"
        "[t](../packages/kernel/ 'title') and [p](../packages/kernel/ (title))\n"
        "````md\n```\n[f](../packages/kernel/)\n````\n",
    )
    git(repo, "add", "docs/a.md")
    rm.layout(repo, MOVES)
    rm.rewrite_links(repo, rm.layout_mapping(MOVES))

    lines = (repo / "docs/a.md").read_text().split("\n")
    assert lines[0] == "[^1]: See the notes"
    assert lines[1] == "[Note]: this is prose"
    assert lines[2] == '[ref]: ../src/e_agent/kernel/ "Kernel"'
    assert lines[3] == "a lone ` backtick then [k](../src/e_agent/kernel/)"
    assert lines[4] == "[t](../src/e_agent/kernel/ 'title') and [p](../src/e_agent/kernel/ (title))"
    assert lines[7] == "[f](../packages/kernel/)"


def test_check_finds_bare_roots_and_globs_but_not_ui_trees_or_prose(repo: Path) -> None:
    rm.layout(repo, MOVES)
    write(
        repo,
        "pyproject.toml",
        'members = ["packages/*", "tools/harness"]\n'
        'testpaths = ["packages", "apps", "tests"]\n'
        "# Core packages never import agent frameworks\n",
    )
    write(
        repo,
        "scripts/q.py",
        'for base in (root / "packages", root / "src"):\n    pass\nmeta = {"packages": {}}\n',
    )
    write(repo, "ui/pnpm-workspace.yaml", 'packages:\n  - "packages/*"\n  - "apps/*"\n')
    git(repo, "add", "pyproject.toml", "scripts/q.py", "ui/pnpm-workspace.yaml")

    stale = rm.check(repo, MOVES).stale_references
    assert ("pyproject.toml", 1, "packages/*") in stale
    assert ("pyproject.toml", 2, "packages") in stale
    assert ("pyproject.toml", 2, "apps") in stale
    assert ("scripts/q.py", 1, "packages") in stale
    assert ("scripts/q.py", 3, "packages") not in stale  # a key, not a path
    assert all(line != 3 for path, line, _ in stale if path == "pyproject.toml")
    assert all(not path.startswith("ui/") for path, _, _ in stale)


def test_check_reports_doc_mentions_separately_and_skips_history(repo: Path) -> None:
    rm.layout(repo, MOVES)
    rm.rewrite_links(repo, rm.layout_mapping(MOVES))
    write(repo, "README.md", "```sh\nuv run pytest -q packages/kernel\n```\n")
    write(repo, "docs/reviews/old.md", "We reviewed packages/kernel.\n")
    write(repo, "research/r.md", "[gone](../docs/missing.md)\n")
    git(repo, "add", "README.md", "docs/reviews/old.md", "research/r.md")

    report = rm.check(repo, MOVES)
    assert report.doc_references == [("README.md", 2, "packages/kernel")]
    assert report.read_only_broken_links == [("research/r.md", "../docs/missing.md")]
    assert report.ok
    assert not report.ok_with_docs
