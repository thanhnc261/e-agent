# Harness H2: CLI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** give the H1 durable state a command-line front end, `uv run e-agent-harness <cmd>`, so the session loop's mechanical steps (brief, task contract, scope check, gate evidence, checkpoint, close check, handoff, status) are commands that hooks and people run the same way.

**Architecture:** one `cli.py` dispatcher over small pure modules in `e_agent_harness` (`state`, `gitinfo`, `tasks`, `scope`, `gate`, `closecheck`, `status`). Every command returns an exit code and prints problems one per line; hook modes (`--hook`) read the hook's JSON on stdin, derive the repository from its `cwd`, and exit 2 with the reason on stderr when they deny. State lives in `harness/state/` (checked in: `active.json`, `progress.md`, `<phase>/features.json`, `<phase>/tasks/<id>.json`, `<phase>/handoffs/<id>.json`) and evidence in the git-ignored `evidence/`.

**Tech Stack:** Python 3.12 stdlib (`argparse`, `subprocess`, `json`, `re`, `datetime`), `jsonschema` (already a dependency), pytest with a scratch git repository fixture. No new dependencies.

**Spec:** [harness plan](2026-10-12-dev-harness.md), sections "Standard session loop", "Context strategy" and "Phase H2: harness CLI". H1 modules this plan builds on: `tools/harness/src/e_agent_harness/{manifest,digest,contracts,progress}.py`.

## Global Constraints

- **Separate from the product.** All code under `tools/harness/`; the import-linter contract "Product code never imports the development harness" stays kept. No product file changes.
- **Mechanical, not advisory.** Commands decide by code and exit non-zero on problems. The harness never commits, merges, pushes or rebases on its own.
- **No secrets in evidence.** Every captured command output passes through `gate.redact` before it is written or printed.
- **Hook modes never trap a session:** `checkpoint --hook` always exits 0; `close-check --hook` exits 0 unless `E_AGENT_HARNESS_UNATTENDED=1`, and exits 0 when the payload has `stop_hook_active: true`.
- **Token discipline.** `status --format hook` output stays within `status.token_budget` from the manifest (estimate: one token per four characters).
- **Gate after every task:** `uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run lint-imports && uv run pytest -q tests/harness tests/conformance`. Full `uv run pytest -q` at Task 8.
- **Commits:** branch `harness/h2-cli` off `main`; explicit `git add` paths; trailer `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- **No container is touched.** `live-check` tests use a scratch manifest whose `live` gate is `echo`.
- **TDD.** Every step below is RED then GREEN; a test that passes before its implementation exists is a finding about the test.

## Review Focus

1. **A hook payload whose `cwd` is a worktree, or whose `file_path` is absolute and outside the repository.** `check-scope --hook` must resolve the path against the payload's `cwd`, find that worktree's root, and deny anything outside it. Test: Task 3, `test_hook_denies_path_outside_repository`.
2. **A gate command that hangs or floods output.** `gate` must stop the command at its timeout, record exit code 124, and keep only the output tail. Test: Task 4, `test_gate_times_out_and_records_124`.
3. **A command that prints a credential** (`password=...`, a DSN with a password). Evidence must hold `[REDACTED]`. Test: Task 4, `test_gate_redacts_secrets_in_evidence`.
4. **A repository with no harness state at all** (fresh clone, no `harness/state/`). `status` must print a brief and name `new-task` as the next action; the hook format must fit the budget. Test: Task 7, `test_status_without_state_names_new_task` and `test_status_hook_fits_budget_on_real_repository`.
5. **Evidence recorded on an older commit.** `close-check` accepts it only when the tree was clean at the time and every change since touches bookkeeping paths only; code changed after the evidence is a rejection. Test: Task 6, `test_close_check_accepts_bookkeeping_only_after_evidence` and `test_close_check_rejects_code_changed_after_evidence`.

---

## File structure

| File | Responsibility |
|---|---|
| `tools/harness/src/e_agent_harness/cli.py` | argparse dispatch; `main(argv, stdin) -> int`; prints and exit codes only |
| `tools/harness/src/e_agent_harness/state.py` | state paths, JSON read/write, `active.json`, repository root discovery |
| `tools/harness/src/e_agent_harness/gitinfo.py` | thin `git` wrappers: head, branch, status files, diff names, ancestry |
| `tools/harness/src/e_agent_harness/tasks.py` | materialise a task contract from the feature list |
| `tools/harness/src/e_agent_harness/scope.py` | allowed-path and protected-path decisions for a tree and for a hook payload |
| `tools/harness/src/e_agent_harness/gate.py` | run a gate set, parse counts, redact, write evidence |
| `tools/harness/src/e_agent_harness/closecheck.py` | close-ritual checks and the evidence-to-HEAD rule |
| `tools/harness/src/e_agent_harness/status.py` | collect status, render text (vi-eli5 then en) and SessionStart hook JSON within budget |
| `tools/harness/src/e_agent_harness/schemas/gate-evidence.schema.json` | evidence file contract |
| `harness/samples/gate-evidence.{valid,invalid}.json` | samples for the conformance test |
| `tests/harness/conftest.py` | scratch git repository with a small manifest, features and files; `invoke()` helper |
| `tests/harness/test_<command>.py` | one test module per command |

Shared fixture contract (`tests/harness/conftest.py`), used by every task:

```python
"""Scratch repository for harness CLI tests: a real git repo with a small manifest."""

from __future__ import annotations

import io
import json
import subprocess
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import NamedTuple

import pytest

from e_agent_harness import cli

MANIFEST = """
[authoritative]
files = ["AGENTS.md", "CLAUDE.md", "docs/roadmap.md"]
active_plan = "docs/plans/phase1.md"
active_plan_required_sections = ["Global Constraints", "Review Focus"]

[protected]
read_only = ["archive/**"]
bump_required = ["addons/**"]
bump_file = "addons/e_agent_bridge/__manifest__.py"
secrets = [".env"]

[environment]
allowed_containers = ["odoo19-learning-*", "e-agent-ledger"]
denied_containers = ["odoo-bench*"]
denied_paths = ["**/ERP-Bench/**/solution/**"]

[gates]
quick = ["echo '3 passed, 1 skipped'"]
full = ["echo full ok"]
pg = ["echo pg ok"]
e2e = ["echo e2e ok"]
live = ["echo 'identity ok'"]

[roles]
implementer = "eng-implement"
reviewer = "eng-review"
verifier = "eng-verify"
sandbox = "live-sandbox"

[status]
token_budget = 600
language_order = ["vi-eli5", "en"]
"""

FEATURES = {
    "phase": "1",
    "entries": [
        {"id": "F-1", "category": "kernel", "description": "split module", "steps": ["run the suite"], "passes": False},
        {"id": "F-2", "category": "kernel", "description": "second feature", "steps": ["check openapi"], "passes": False},
    ],
}


class Result(NamedTuple):
    code: int
    out: str
    err: str


def git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True).stdout.strip()


class Repo:
    """A scratch repository plus the helpers every harness test uses."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.base = ""

    def write(self, rel: str, text: str) -> Path:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def commit(self, message: str) -> str:
        git(self.root, "add", "-A")
        git(self.root, "-c", "user.name=t", "-c", "user.email=t@example.org", "commit", "-q", "-m", message)
        return git(self.root, "rev-parse", "HEAD")

    def invoke_at(self, root: Path, *args: str, stdin: str = "") -> Result:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(["--repo", str(root), *args], stdin=io.StringIO(stdin))
        return Result(code, out.getvalue(), err.getvalue())

    def invoke(self, *args: str, stdin: str = "") -> Result:
        return self.invoke_at(self.root, *args, stdin=stdin)


@pytest.fixture
def repo(tmp_path: Path) -> Repo:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    r = Repo(root)
    r.write("AGENTS.md", "# rules\n")
    r.write("CLAUDE.md", "@AGENTS.md\n")
    r.write("docs/roadmap.md", "# roadmap\n\nPhase 1 plan: [plan](plans/phase1.md)\n")
    r.write("docs/plans/phase1.md", "# Phase 1\n\n## Global Constraints\n\n- none\n\n## Review Focus\n\n- none\n")
    r.write("addons/e_agent_bridge/__manifest__.py", "{'version': '1.0'}\n")
    r.write("archive/old.md", "old\n")
    r.write("src/pkg/mod.py", "X = 1\n")
    r.write("harness/context.toml", MANIFEST)
    r.write("harness/state/1/features.json", json.dumps(FEATURES, indent=2) + "\n")
    r.write(".gitignore", "/evidence/\n")
    r.base = r.commit("base")
    return r
```

Test modules import nothing from `conftest` (root pytest runs with `--import-mode=importlib`, where relative imports between test modules are unreliable); they take the untyped `repo` fixture and use its methods: `repo.invoke(...)`, `repo.write(...)`, `repo.commit(...)`, `repo.invoke_at(other_root, ...)`.

---

### Task 1: CLI skeleton, state paths, git helpers, `validate-context`

**Files:**
- Create: `tools/harness/src/e_agent_harness/cli.py`, `tools/harness/src/e_agent_harness/state.py`, `tools/harness/src/e_agent_harness/gitinfo.py`
- Create: `tests/harness/__init__.py` (empty), `tests/harness/conftest.py` (content above), `tests/harness/test_validate_context.py`
- Modify: `tools/harness/pyproject.toml` (add `[project.scripts]`)

**Interfaces:**
- Produces `state.find_repo_root(start: Path) -> Path` (walks up to the directory holding `harness/context.toml`, else `git rev-parse --show-toplevel`, else `ValueError`).
- Produces `state.Paths(repo_root)` with `.state`, `.active`, `.progress`, `.features(phase)`, `.task(phase, task_id)`, `.handoff(phase, task_id)`, `.evidence(task_id)`, `.live_evidence`; `state.read_json(path) -> Any`, `state.write_json(path, doc) -> None`, `state.load_active(paths) -> dict[str, Any] | None`, `state.save_active(paths, phase: str, task_id: str | None) -> None`, `state.load_task(paths) -> tuple[dict[str, Any], Path] | None`.
- Produces `gitinfo.head_sha(root) -> str`, `gitinfo.branch(root) -> str`, `gitinfo.status_files(root) -> list[str]`, `gitinfo.is_clean(root) -> bool`, `gitinfo.diff_names(root, base, head="HEAD") -> list[str]`, `gitinfo.is_ancestor(root, ancestor, descendant) -> bool`.
- Produces `cli.main(argv: list[str] | None = None, stdin: TextIO | None = None) -> int` with the global option `--repo <path>` and the subcommand `validate-context`.

- [ ] **Step 1: Write the failing tests**

`tests/harness/test_validate_context.py`:

```python
from pathlib import Path

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
    import pytest

    with pytest.raises(SystemExit) as exc:
        repo.invoke("no-such-command")
    assert exc.value.code == 2
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest -q tests/harness/test_validate_context.py`
Expected: collection error, `ModuleNotFoundError: No module named 'e_agent_harness.cli'`

- [ ] **Step 3: Write `state.py`**

```python
"""Harness state on disk: paths, JSON helpers, the active task pointer, repository root."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from e_agent_harness.manifest import MANIFEST_RELPATH

STATE_DIR = "harness/state"


def find_repo_root(start: Path) -> Path:
    """The nearest ancestor holding the manifest, else the git top level."""
    for candidate in (start, *start.parents):
        if (candidate / MANIFEST_RELPATH).is_file():
            return candidate
    proc = subprocess.run(
        ["git", "-C", str(start), "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode == 0 and proc.stdout.strip():
        return Path(proc.stdout.strip())
    raise ValueError(f"no repository with {MANIFEST_RELPATH} above {start}")


@dataclass(frozen=True)
class Paths:
    repo_root: Path

    @property
    def manifest(self) -> Path:
        return self.repo_root / MANIFEST_RELPATH

    @property
    def state(self) -> Path:
        return self.repo_root / STATE_DIR

    @property
    def active(self) -> Path:
        return self.state / "active.json"

    @property
    def progress(self) -> Path:
        return self.state / "progress.md"

    def features(self, phase: str) -> Path:
        return self.state / phase / "features.json"

    def task(self, phase: str, task_id: str) -> Path:
        return self.state / phase / "tasks" / f"{task_id}.json"

    def handoff(self, phase: str, task_id: str) -> Path:
        return self.state / phase / "handoffs" / f"{task_id}.json"

    def evidence(self, task_id: str) -> Path:
        return self.repo_root / "evidence" / "gates" / task_id

    @property
    def live_evidence(self) -> Path:
        return self.repo_root / "evidence" / "live"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, doc: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_active(paths: Paths) -> dict[str, Any] | None:
    if not paths.active.is_file():
        return None
    doc = read_json(paths.active)
    return doc if isinstance(doc, dict) else None


def save_active(paths: Paths, phase: str, task_id: str | None) -> None:
    write_json(paths.active, {"phase": phase, "task": task_id})


def load_task(paths: Paths) -> tuple[dict[str, Any], Path] | None:
    """The active task contract and its path, or None when no task is active."""
    active = load_active(paths)
    if not active or not active.get("task"):
        return None
    path = paths.task(str(active["phase"]), str(active["task"]))
    if not path.is_file():
        return None
    doc = read_json(path)
    return (doc, path) if isinstance(doc, dict) else None
```

- [ ] **Step 4: Write `gitinfo.py`**

```python
"""Thin git wrappers. Every function takes the repository root and shells out once."""

from __future__ import annotations

import subprocess
from pathlib import Path


def git(root: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, check=True
    )
    return proc.stdout.strip()


def head_sha(root: Path) -> str:
    return git(root, "rev-parse", "HEAD")


def branch(root: Path) -> str:
    return git(root, "rev-parse", "--abbrev-ref", "HEAD")


def status_files(root: Path) -> list[str]:
    """Changed, staged and untracked paths (renames report the new path)."""
    files: list[str] = []
    for line in git(root, "status", "--porcelain", "--untracked-files=all").splitlines():
        path = line[3:]
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        files.append(path.strip('"'))
    return sorted(set(files))


def is_clean(root: Path) -> bool:
    return not status_files(root)


def diff_names(root: Path, base: str, head: str = "HEAD") -> list[str]:
    out = git(root, "diff", "--name-only", f"{base}..{head}")
    return sorted(line for line in out.splitlines() if line)


def is_ancestor(root: Path, ancestor: str, descendant: str) -> bool:
    proc = subprocess.run(
        ["git", "-C", str(root), "merge-base", "--is-ancestor", ancestor, descendant],
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode == 0
```

- [ ] **Step 5: Write `cli.py` with `validate-context` only**

```python
"""``e-agent-harness`` command line. Each command prints problems one per line and
returns an exit code; hook modes read the hook JSON on stdin and exit 2 to deny."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TextIO

from e_agent_harness import manifest as mf
from e_agent_harness import state


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="e-agent-harness")
    parser.add_argument("--repo", type=Path, default=None, help="repository root (default: found from cwd)")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("validate-context", help="check the manifest against this checkout")
    return parser


def _context(args: argparse.Namespace) -> tuple[Path, state.Paths, mf.Manifest]:
    root = args.repo.resolve() if args.repo else state.find_repo_root(Path.cwd())
    paths = state.Paths(root)
    return root, paths, mf.load_manifest(paths.manifest)


def cmd_validate_context(args: argparse.Namespace) -> int:
    root, paths, m = _context(args)
    problems = mf.validate_manifest(m, root)
    roadmap = root / "docs" / "roadmap.md"
    plan_name = Path(m.authoritative.active_plan).name
    if roadmap.is_file() and plan_name not in roadmap.read_text(encoding="utf-8"):
        problems.append(f"roadmap does not link the active plan: {m.authoritative.active_plan}")
    for problem in problems:
        print(problem)
    if problems:
        return 1
    print(f"ok: manifest valid for {root}")
    return 0


COMMANDS = {"validate-context": cmd_validate_context}


def main(argv: list[str] | None = None, stdin: TextIO | None = None) -> int:
    args = _parser().parse_args(argv)
    args.stdin = stdin or sys.stdin
    return COMMANDS[args.command](args)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
```

Add to `tools/harness/pyproject.toml` after `dependencies`:

```toml
[project.scripts]
e-agent-harness = "e_agent_harness.cli:main"
```

Then `uv lock && uv sync --locked` so the console script exists.

Add to root `pyproject.toml` under `[tool.ruff.lint.per-file-ignores]` (the harness shells out to git and to gate commands from the committed manifest):

```toml
"tools/harness/**" = ["S603", "S607"]
"tools/harness/src/e_agent_harness/gate.py" = ["S602", "S603", "S607"]
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `uv run pytest -q tests/harness/test_validate_context.py`
Expected: `7 passed`

Run: `uv run e-agent-harness validate-context`
Expected: `ok: manifest valid for /Users/thanhnguyen/dev/projects/personal/e-agent` (the real roadmap links the Phase 1 plan)

- [ ] **Step 7: Gate and commit**

Run: `uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run lint-imports && uv run pytest -q tests/harness tests/conformance`
Expected: all green, `Contracts: 8 kept, 0 broken.`

```bash
git add tools/harness tests/harness uv.lock
git commit -m "feat(harness): CLI skeleton with validate-context, state paths and git helpers"
```

---

### Task 2: `new-task`

**Files:**
- Create: `tools/harness/src/e_agent_harness/tasks.py`, `tests/harness/test_new_task.py`
- Modify: `tools/harness/src/e_agent_harness/cli.py`

**Interfaces:**
- Consumes `state.Paths`, `state.read_json`, `state.write_json`, `state.save_active`, `gitinfo.head_sha`, `digest.context_digest`, `contracts.validate`.
- Produces `tasks.IMPLICIT_PATHS: tuple[str, ...] = ("harness/state/**", "docs/handoffs/**")` and `tasks.materialise(paths, m, repo_root, *, phase, task_id, feature_ids, allowed_paths, acceptance, gate_set, now) -> dict[str, Any]` which writes the contract, sets the active pointer and returns the contract. Raises `ValueError` with a readable message for unknown features, missing feature list, or a contract that fails its schema.
- CLI: `new-task <phase> <task-id> --feature F ... --paths GLOB ... [--acceptance STEP ...] [--gate quick|full|pg|e2e|live] [--replace]`. Refuses (exit 1) when another task is active unless `--replace`.

- [ ] **Step 1: Write the failing tests**

```python
import json

from e_agent_harness import state



def test_new_task_writes_contract_and_activates_it(repo) -> None:
    result = invoke(
        repo.root, "new-task", "1", "1c.1", "--feature", "F-1", "--paths", "src/pkg/**", "--gate", "quick"
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
    replaced = repo.invoke("new-task", "1", "1c.2", "--feature", "F-2", "--paths", "src/**", "--replace")
    assert replaced.code == 0
    assert state.load_active(state.Paths(repo.root))["task"] == "1c.2"


def test_new_task_uses_explicit_acceptance_when_given(repo) -> None:
    result = invoke(
        repo.root, "new-task", "1", "1c.1", "--feature", "F-1", "--paths", "src/**",
        "--acceptance", "pytest -q src passes", "--acceptance", "openapi unchanged",
    )
    assert result.code == 0
    contract = json.loads((repo.root / "harness/state/1/tasks/1c.1.json").read_text())
    assert contract["acceptance"] == ["pytest -q src passes", "openapi unchanged"]
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest -q tests/harness/test_new_task.py`
Expected: 4 failures, `SystemExit: 2` from argparse (`invalid choice: 'new-task'`)

- [ ] **Step 3: Write `tasks.py`**

```python
"""Materialise a task contract from the phase feature list (harness plan H2, new-task)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from e_agent_harness import contracts, gitinfo, state
from e_agent_harness.digest import context_digest
from e_agent_harness.manifest import Manifest

IMPLICIT_PATHS: tuple[str, ...] = ("harness/state/**", "docs/handoffs/**")


def materialise(
    paths: state.Paths,
    m: Manifest,
    repo_root: Path,
    *,
    phase: str,
    task_id: str,
    feature_ids: Sequence[str],
    allowed_paths: Sequence[str],
    acceptance: Sequence[str],
    gate_set: str,
    now: datetime,
) -> dict[str, Any]:
    features_path = paths.features(phase)
    if not features_path.is_file():
        raise ValueError(f"feature list missing: {features_path.relative_to(repo_root)}")
    entries = {e["id"]: e for e in state.read_json(features_path)["entries"]}
    unknown = [f for f in feature_ids if f not in entries]
    if unknown:
        raise ValueError(f"unknown feature id(s): {', '.join(unknown)}")
    steps = list(acceptance) or [step for f in feature_ids for step in entries[f]["steps"]]
    contract: dict[str, Any] = {
        "id": task_id,
        "phase": phase,
        "plan_ref": m.authoritative.active_plan,
        "feature_ids": list(feature_ids),
        "context_digest": context_digest(repo_root, m),
        "allowed_paths": [*allowed_paths, *IMPLICIT_PATHS, m.authoritative.active_plan],
        "acceptance": steps,
        "gate_set": gate_set,
        "base_commit": gitinfo.head_sha(repo_root),
        "created_at": now.isoformat(timespec="seconds"),
    }
    problems = contracts.validate("task", contract)
    if problems:
        raise ValueError("task contract invalid: " + "; ".join(problems))
    state.write_json(paths.task(phase, task_id), contract)
    state.save_active(paths, phase, task_id)
    return contract
```

- [ ] **Step 4: Add the command to `cli.py`**

Parser addition inside `_parser()`:

```python
    new_task = sub.add_parser("new-task", help="materialise a task contract and make it active")
    new_task.add_argument("phase")
    new_task.add_argument("task_id")
    new_task.add_argument("--feature", action="append", default=[], required=True)
    new_task.add_argument("--paths", action="append", default=[], required=True, help="allowed path glob")
    new_task.add_argument("--acceptance", action="append", default=[])
    new_task.add_argument("--gate", default="quick", choices=["quick", "full", "pg", "e2e", "live"])
    new_task.add_argument("--replace", action="store_true", help="replace the active task")
```

Command:

```python
def cmd_new_task(args: argparse.Namespace) -> int:
    root, paths, m = _context(args)
    active = state.load_active(paths)
    if active and active.get("task") and active["task"] != args.task_id and not args.replace:
        print(f"task {active['task']} is active; finish it with close-check or pass --replace")
        return 1
    try:
        contract = tasks.materialise(
            paths, m, root,
            phase=args.phase, task_id=args.task_id, feature_ids=args.feature,
            allowed_paths=args.paths, acceptance=args.acceptance, gate_set=args.gate,
            now=datetime.now(UTC),
        )
    except ValueError as exc:
        print(str(exc))
        return 1
    print(f"task {contract['id']} materialised at {paths.task(args.phase, args.task_id).relative_to(root)}")
    return 0
```

Imports to add: `from datetime import UTC, datetime` and `from e_agent_harness import tasks`. Register `"new-task": cmd_new_task` in `COMMANDS`.

- [ ] **Step 5: Run to verify pass**

Run: `uv run pytest -q tests/harness/test_new_task.py`
Expected: `4 passed`

- [ ] **Step 6: Gate and commit**

```bash
git add tools/harness tests/harness
git commit -m "feat(harness): new-task materialises a task contract and activates it"
```

---

### Task 3: `check-scope` (command and PreToolUse hook mode)

**Files:**
- Create: `tools/harness/src/e_agent_harness/scope.py`, `tests/harness/test_check_scope.py`
- Modify: `tools/harness/src/e_agent_harness/manifest.py` (public `path_matches`), `cli.py`

**Interfaces:**
- Produces `manifest.path_matches(path: str, pattern: str) -> bool` (the existing `_glob_match`, made public; keep `_glob_match = path_matches` for callers inside the module).
- Produces `scope.deny_reason(contract: dict | None, m: Manifest, relpath: str) -> str | None`: protected paths always deny; with a contract, a path outside `allowed_paths` denies; with no contract, only protected paths deny.
- Produces `scope.check_tree(contract, m, repo_root) -> list[str]`: every path in `gitinfo.diff_names(base_commit)` plus `gitinfo.status_files()` must pass `deny_reason`; a change under `protected.bump_required` without `protected.bump_file` in the same set is a problem.
- Produces `scope.hook_decision(payload: dict, m_for: Callable[[Path], tuple[Manifest, dict | None]]) -> tuple[int, str]`: returns `(0, "")` for tools other than `Edit`, `Write`, `NotebookEdit`; otherwise resolves the path against `payload["cwd"]`, finds the repository root with `state.find_repo_root`, denies `(2, reason)` for a path outside that root, and applies `deny_reason` with that root's manifest and active contract.
- CLI: `check-scope [--hook]`. Command mode exits 1 with problems; hook mode exits 2 with the reason on stderr.

- [ ] **Step 1: Write the failing tests**

```python
import json



def _activate(repo) -> None:
    assert repo.invoke("new-task", "1", "1c.1", "--feature", "F-1", "--paths", "src/pkg/**").code == 0


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
    assert repo.invoke("new-task", "1", "1c.1", "--feature", "F-1", "--paths", "addons/**").code == 0
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
    result = repo.invoke("check-scope", "--hook", stdin=_payload(repo, "Write", str(repo.root / "docs/other.md")))
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
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": "rm -rf archive"}, "cwd": str(repo.root)})
    assert repo.invoke("check-scope", "--hook", stdin=payload).code == 0


def test_hook_resolves_repository_from_payload_cwd_not_repo_flag(repo, tmp_path) -> None:
    _activate(repo)
    # The --repo flag points elsewhere; the payload's cwd is the repository that must decide.
    other = tmp_path / "other"
    other.mkdir()
    payload = json.dumps({"tool_name": "Edit", "tool_input": {"file_path": "archive/old.md"}, "cwd": str(repo.root)})
    result = repo.invoke_at(other, "check-scope", "--hook", stdin=payload)
    assert result.code == 2
    assert "protected path" in result.err
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest -q tests/harness/test_check_scope.py`
Expected: 10 failures (`invalid choice: 'check-scope'`)

- [ ] **Step 3: Expose `path_matches` in `manifest.py`**

Rename `_glob_match` to `path_matches` and add after it:

```python
_glob_match = path_matches
```

Run: `uv run pytest -q tests/conformance/test_harness_context.py`
Expected: `27 passed` (behaviour unchanged)

- [ ] **Step 4: Write `scope.py`**

```python
"""Scope decisions: which paths a task may change, as a tree check and as a hook."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from e_agent_harness import gitinfo, state
from e_agent_harness.manifest import Manifest, is_protected, normalize_relpath, path_matches

EDIT_TOOLS = ("Edit", "Write", "NotebookEdit")


def deny_reason(contract: dict[str, Any] | None, m: Manifest, relpath: str) -> str | None:
    norm = normalize_relpath(relpath)
    if is_protected(m, norm):
        return f"{norm}: protected path (read-only)"
    if contract is None:
        return None
    if not any(path_matches(norm, p) for p in contract["allowed_paths"]):
        return f"{norm}: outside the task's allowed paths"
    return None


def check_tree(contract: dict[str, Any] | None, m: Manifest, repo_root: Path) -> list[str]:
    changed = set(gitinfo.status_files(repo_root))
    if contract is not None:
        changed.update(gitinfo.diff_names(repo_root, contract["base_commit"]))
    problems = [r for r in (deny_reason(contract, m, p) for p in sorted(changed)) if r]
    bumped = {normalize_relpath(p) for p in changed}
    needs_bump = any(path_matches(p, pat) for p in bumped for pat in m.protected.bump_required)
    if needs_bump and normalize_relpath(m.protected.bump_file) not in bumped:
        problems.append(f"{m.protected.bump_file}: must change when files under "
                        f"{', '.join(m.protected.bump_required)} change")
    return problems


Resolver = Callable[[Path], tuple[Manifest, dict[str, Any] | None]]


def hook_decision(payload: dict[str, Any], resolve: Resolver) -> tuple[int, str]:
    """(exit code, reason). 2 denies. Only edit tools are judged."""
    if payload.get("tool_name") not in EDIT_TOOLS:
        return 0, ""
    tool_input = payload.get("tool_input") or {}
    raw = tool_input.get("file_path") or tool_input.get("notebook_path")
    if not raw:
        return 0, ""
    cwd = Path(payload.get("cwd") or Path.cwd())
    try:
        repo_root = state.find_repo_root(cwd).resolve()
    except ValueError as exc:
        return 2, str(exc)
    target = (Path(raw) if Path(raw).is_absolute() else cwd / raw).resolve()
    try:
        rel = target.relative_to(repo_root).as_posix()
    except ValueError:
        return 2, f"{target}: outside the repository {repo_root}"
    m, contract = resolve(repo_root)
    reason = deny_reason(contract, m, rel)
    return (2, reason) if reason else (0, "")
```

- [ ] **Step 5: Add the command to `cli.py`**

Parser:

```python
    scope_p = sub.add_parser("check-scope", help="changed paths must be inside the active task's scope")
    scope_p.add_argument("--hook", action="store_true", help="PreToolUse mode: hook JSON on stdin, exit 2 denies")
```

Command and helper:

```python
def _resolve_for_hook(repo_root: Path) -> tuple[mf.Manifest, dict[str, Any] | None]:
    paths = state.Paths(repo_root)
    loaded = state.load_task(paths)
    return mf.load_manifest(paths.manifest), (loaded[0] if loaded else None)


def cmd_check_scope(args: argparse.Namespace) -> int:
    if args.hook:
        payload = json.load(args.stdin)
        code, reason = scope.hook_decision(payload, _resolve_for_hook)
        if code:
            print(reason, file=sys.stderr)
        return code
    root, paths, m = _context(args)
    loaded = state.load_task(paths)
    problems = scope.check_tree(loaded[0] if loaded else None, m, root)
    for problem in problems:
        print(problem)
    return 1 if problems else 0
```

Imports: `import json`, `from typing import Any, TextIO`, `from e_agent_harness import scope`. Register `"check-scope": cmd_check_scope`.

- [ ] **Step 6: Run to verify pass**

Run: `uv run pytest -q tests/harness/test_check_scope.py`
Expected: `10 passed`

- [ ] **Step 7: Gate and commit**

```bash
git add tools/harness tests/harness
git commit -m "feat(harness): check-scope as a tree check and as a PreToolUse hook"
```

---

### Task 4: `gate` with evidence, redaction and timeout; `live-check`

**Files:**
- Create: `tools/harness/src/e_agent_harness/gate.py`, `tools/harness/src/e_agent_harness/schemas/gate-evidence.schema.json`, `harness/samples/gate-evidence.valid.json`, `harness/samples/gate-evidence.invalid.json`, `tests/harness/test_gate.py`
- Modify: `tools/harness/src/e_agent_harness/contracts.py` (`SCHEMAS` gains `"gate-evidence"`), `cli.py`

**Interfaces:**
- Produces `gate.redact(text: str) -> str`, `gate.parse_counts(text: str) -> dict[str, int]`, `gate.run_gate(m, set_name, repo_root, *, task_id, package=None, timeout=1800, keep_going=False, now) -> dict[str, Any]` (an evidence document, not yet written), `gate.write_evidence(directory: Path, evidence: dict) -> Path` (file name `<started_at with ':' replaced by '-'>.json`).
- Evidence document fields: `gate_set`, `task`, `commit`, `clean_tree`, `started_at`, `ok`, `commands: [{command, exit_code, seconds, output_tail, counts}]`.
- CLI: `gate <set> [--package PKG] [--timeout S] [--keep-going]` → writes under `evidence/gates/<task or no-task>/`, prints the path, exits 1 when any command failed. `live-check [--timeout S]` → runs set `live`, writes under `evidence/live/`.

- [ ] **Step 1: Write the failing tests**

```python
import json
from pathlib import Path

from e_agent_harness import gate



def _evidence_files(root: Path, task: str) -> list[Path]:
    return sorted((root / "evidence" / "gates" / task).glob("*.json"))


def test_gate_writes_evidence_tied_to_head_on_clean_tree(repo) -> None:
    result = repo.invoke("gate", "quick")
    assert result.code == 0, result
    files = _evidence_files(repo.root, "no-task")
    assert len(files) == 1
    doc = json.loads(files[0].read_text())
    assert doc["commit"] == repo.base
    assert doc["clean_tree"] is True
    assert doc["ok"] is True
    assert doc["commands"][0]["counts"] == {"passed": 3, "skipped": 1}
    assert str(files[0].relative_to(repo.root)) in result.out


def test_gate_records_dirty_tree_and_task_id(repo) -> None:
    assert repo.invoke("new-task", "1", "1c.1", "--feature", "F-1", "--paths", "src/**").code == 0
    repo.write("src/pkg/new.py", "Y = 2\n")
    assert repo.invoke("gate", "quick").code == 0
    doc = json.loads(_evidence_files(repo.root, "1c.1")[0].read_text())
    assert doc["clean_tree"] is False
    assert doc["task"] == "1c.1"


def test_gate_stops_at_first_failure_and_exits_1(repo) -> None:
    manifest = repo.root / "harness/context.toml"
    manifest.write_text(manifest.read_text().replace(
        'full = ["echo full ok"]', 'full = ["echo first", "python3 -c \'import sys; sys.exit(3)\'", "echo never"]'
    ))
    result = repo.invoke("gate", "full")
    assert result.code == 1
    doc = json.loads(_evidence_files(repo.root, "no-task")[0].read_text())
    assert [c["exit_code"] for c in doc["commands"]] == [0, 3]
    assert doc["ok"] is False


def test_gate_times_out_and_records_124(repo) -> None:
    manifest = repo.root / "harness/context.toml"
    manifest.write_text(manifest.read_text().replace('pg = ["echo pg ok"]', 'pg = ["sleep 5"]'))
    result = repo.invoke("gate", "pg", "--timeout", "1")
    assert result.code == 1
    doc = json.loads(_evidence_files(repo.root, "no-task")[0].read_text())
    assert doc["commands"][0]["exit_code"] == 124
    assert "timeout" in doc["commands"][0]["output_tail"]


def test_gate_redacts_secrets_in_evidence(repo) -> None:
    manifest = repo.root / "harness/context.toml"
    manifest.write_text(manifest.read_text().replace(
        'e2e = ["echo e2e ok"]',
        'e2e = ["echo password=hunter2 DSN postgresql://user:pw123@db/e_agent api_key: abc"]',
    ))
    assert repo.invoke("gate", "e2e").code == 0
    text = _evidence_files(repo.root, "no-task")[0].read_text()
    assert "hunter2" not in text and "pw123" not in text and "abc" not in text
    assert "[REDACTED]" in text


def test_gate_substitutes_package(repo) -> None:
    manifest = repo.root / "harness/context.toml"
    manifest.write_text(manifest.read_text().replace("quick = [\"echo '3 passed, 1 skipped'\"]", 'quick = ["echo testing {package}"]'))
    assert repo.invoke("gate", "quick", "--package", "packages/kernel").code == 0
    doc = json.loads(_evidence_files(repo.root, "no-task")[0].read_text())
    assert doc["commands"][0]["command"] == "echo testing packages/kernel"
    assert "testing packages/kernel" in doc["commands"][0]["output_tail"]


def test_live_check_writes_under_evidence_live(repo) -> None:
    result = repo.invoke("live-check")
    assert result.code == 0, result
    files = sorted((repo.root / "evidence" / "live").glob("*.json"))
    assert len(files) == 1
    assert json.loads(files[0].read_text())["gate_set"] == "live"


def test_parse_counts_reads_pytest_summary() -> None:
    assert gate.parse_counts("== 12 passed, 2 skipped, 1 failed in 3s ==") == {"passed": 12, "skipped": 2, "failed": 1}
    assert gate.parse_counts("no tests here") == {}


def test_output_tail_is_capped(repo) -> None:
    manifest = repo.root / "harness/context.toml"
    manifest.write_text(manifest.read_text().replace('full = ["echo full ok"]', 'full = ["seq 1 500"]'))
    assert repo.invoke("gate", "full").code == 0
    doc = json.loads(_evidence_files(repo.root, "no-task")[0].read_text())
    assert doc["commands"][0]["output_tail"].splitlines()[-1] == "500"
    assert len(doc["commands"][0]["output_tail"].splitlines()) <= gate.TAIL_LINES
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest -q tests/harness/test_gate.py`
Expected: 9 failures (`invalid choice: 'gate'` / `AttributeError: module 'e_agent_harness' has no attribute 'gate'`)

- [ ] **Step 3: Write the evidence schema and samples**

`tools/harness/src/e_agent_harness/schemas/gate-evidence.schema.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://e-agent.local/harness/gate-evidence.schema.json",
  "title": "Gate evidence",
  "type": "object",
  "additionalProperties": false,
  "required": ["gate_set", "task", "commit", "clean_tree", "started_at", "ok", "commands"],
  "properties": {
    "gate_set": {"type": "string", "minLength": 1},
    "task": {"type": "string", "minLength": 1},
    "commit": {"type": "string", "pattern": "^[0-9a-f]{40}$"},
    "clean_tree": {"type": "boolean"},
    "started_at": {"type": "string", "format": "date-time"},
    "ok": {"type": "boolean"},
    "commands": {
      "type": "array",
      "minItems": 1,
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["command", "exit_code", "seconds", "output_tail", "counts"],
        "properties": {
          "command": {"type": "string", "minLength": 1},
          "exit_code": {"type": "integer"},
          "seconds": {"type": "number", "minimum": 0},
          "output_tail": {"type": "string"},
          "counts": {"type": "object", "additionalProperties": {"type": "integer", "minimum": 0}}
        }
      }
    }
  }
}
```

`harness/samples/gate-evidence.valid.json`:

```json
{
  "gate_set": "quick",
  "task": "1c.1",
  "commit": "e5dca6f0000000000000000000000000000000000",
  "clean_tree": true,
  "started_at": "2026-10-13T06:00:00+00:00",
  "ok": true,
  "commands": [
    {"command": "uv run pytest -q packages/kernel", "exit_code": 0, "seconds": 4.2, "output_tail": "120 passed in 4.1s", "counts": {"passed": 120}}
  ]
}
```

`harness/samples/gate-evidence.invalid.json`:

```json
{"expect": "commit", "document": {"gate_set": "quick", "task": "1c.1", "commit": "e5dca6f", "clean_tree": true, "started_at": "2026-10-13T06:00:00+00:00", "ok": true, "commands": [{"command": "echo", "exit_code": 0, "seconds": 0.1, "output_tail": "", "counts": {}}]}}
```

In `contracts.py`: `SCHEMAS = ("plan", "task", "features", "handoff", "review", "progress-entry", "gate-evidence")`.

Run: `uv run pytest -q tests/conformance/test_harness_context.py`
Expected: `29 passed` (two new parametrised cases)

- [ ] **Step 4: Write `gate.py`**

```python
"""Run a gate set and record evidence tied to the commit (harness plan H2, gate)."""

from __future__ import annotations

import re
import subprocess
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from e_agent_harness import contracts, gitinfo
from e_agent_harness.manifest import Manifest

TAIL_LINES = 40
TIMEOUT_EXIT = 124
COUNT_RE = re.compile(r"(\d+) (passed|failed|skipped|errors?|xfailed|xpassed|warnings?)\b")
SECRET_RE = re.compile(
    r"(?i)((?:password|passwd|secret|token|api[_-]?key|authorization|bearer|dsn)\s*[=:]\s*)(\S+)"
)
URL_PASSWORD_RE = re.compile(r"(://[^:/\s@]+:)[^@\s]+@")

Runner = Callable[[str, Path, int], tuple[int, str]]


def redact(text: str) -> str:
    text = URL_PASSWORD_RE.sub(r"\1[REDACTED]@", text)
    return SECRET_RE.sub(r"\1[REDACTED]", text)


def parse_counts(text: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for number, label in COUNT_RE.findall(text):
        key = {"error": "errors", "warning": "warnings"}.get(label, label)
        counts[key] = int(number)
    return counts


def _tail(text: str) -> str:
    lines = text.splitlines()
    return "\n".join(lines[-TAIL_LINES:])


def run_shell(command: str, cwd: Path, timeout: int) -> tuple[int, str]:
    try:
        proc = subprocess.run(  # gate commands come from the committed manifest
            command, shell=True, cwd=cwd, capture_output=True, text=True, timeout=timeout, check=False
        )
    except subprocess.TimeoutExpired as exc:
        partial = (exc.stdout or b"") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        text = partial.decode(errors="replace") if isinstance(partial, bytes) else partial
        return TIMEOUT_EXIT, f"{text}\n[timeout after {timeout}s]"
    return proc.returncode, proc.stdout + proc.stderr


def run_gate(
    m: Manifest,
    set_name: str,
    repo_root: Path,
    *,
    task_id: str,
    package: str | None = None,
    timeout: int = 1800,
    keep_going: bool = False,
    now: datetime,
    runner: Runner = run_shell,
) -> dict[str, Any]:
    if set_name not in m.gates:
        raise ValueError(f"unknown gate set: {set_name} (have {', '.join(sorted(m.gates))})")
    evidence: dict[str, Any] = {
        "gate_set": set_name,
        "task": task_id,
        "commit": gitinfo.head_sha(repo_root),
        "clean_tree": gitinfo.is_clean(repo_root),
        "started_at": now.isoformat(timespec="seconds"),
        "ok": True,
        "commands": [],
    }
    for template in m.gates[set_name]:
        command = template.replace("{package}", package or ".")
        started = time.monotonic()
        code, output = runner(command, repo_root, timeout)
        evidence["commands"].append(
            {
                "command": redact(command),
                "exit_code": code,
                "seconds": round(time.monotonic() - started, 3),
                "output_tail": redact(_tail(output)),
                "counts": parse_counts(output),
            }
        )
        if code != 0:
            evidence["ok"] = False
            if not keep_going:
                break
    problems = contracts.validate("gate-evidence", evidence)
    if problems:
        raise ValueError("evidence invalid: " + "; ".join(problems))
    return evidence


def write_evidence(directory: Path, evidence: dict[str, Any]) -> Path:
    from e_agent_harness.state import write_json

    directory.mkdir(parents=True, exist_ok=True)
    stamp = str(evidence["started_at"]).replace(":", "-")
    path = directory / f"{stamp}.json"
    write_json(path, evidence)
    return path
```

- [ ] **Step 5: Add `gate` and `live-check` to `cli.py`**

Parser:

```python
    gate_p = sub.add_parser("gate", help="run a gate set and write evidence")
    gate_p.add_argument("set_name")
    gate_p.add_argument("--package", default=None)
    gate_p.add_argument("--timeout", type=int, default=1800)
    gate_p.add_argument("--keep-going", action="store_true")
    live_p = sub.add_parser("live-check", help="run the live gate set against the sandbox, redacted")
    live_p.add_argument("--timeout", type=int, default=1800)
```

Commands:

```python
def _run_gate(args: argparse.Namespace, set_name: str, directory_for: Callable[[state.Paths, str], Path],
              package: str | None, keep_going: bool) -> int:
    root, paths, m = _context(args)
    loaded = state.load_task(paths)
    task_id = loaded[0]["id"] if loaded else "no-task"
    try:
        evidence = gate.run_gate(
            m, set_name, root, task_id=task_id, package=package, timeout=args.timeout,
            keep_going=keep_going, now=datetime.now(UTC),
        )
    except ValueError as exc:
        print(str(exc))
        return 1
    path = gate.write_evidence(directory_for(paths, task_id), evidence)
    for entry in evidence["commands"]:
        print(f"[{entry['exit_code']}] {entry['command']}")
    print(f"evidence: {path.relative_to(root)} (commit {evidence['commit'][:7]}, clean_tree={evidence['clean_tree']})")
    return 0 if evidence["ok"] else 1


def cmd_gate(args: argparse.Namespace) -> int:
    return _run_gate(args, args.set_name, lambda p, t: p.evidence(t), args.package, args.keep_going)


def cmd_live_check(args: argparse.Namespace) -> int:
    return _run_gate(args, "live", lambda p, _t: p.live_evidence, None, False)
```

Imports: `from collections.abc import Callable`, `from e_agent_harness import gate`. Register both.

- [ ] **Step 6: Run to verify pass**

Run: `uv run pytest -q tests/harness/test_gate.py`
Expected: `9 passed` (the timeout test takes about one second)

- [ ] **Step 7: Gate and commit**

```bash
git add tools/harness harness/samples tests/harness
git commit -m "feat(harness): gate and live-check write redacted evidence tied to the commit"
```

---

### Task 5: `checkpoint` (command and PreCompact hook mode)

**Files:**
- Create: `tests/harness/test_checkpoint.py`
- Modify: `cli.py`

**Interfaces:**
- Consumes `progress.ProgressEntry`, `progress.append_entry`, `state.load_task`, `gitinfo.status_files`.
- CLI: `checkpoint [--next TEXT] [--changed TEXT] [--open TEXT] [--session ID] [--hook]`. Defaults: `changed` = comma-joined `status_files` or `no working-tree changes`; `next` = the active contract's first acceptance step, else `new-task`; `open` = `none`; `session` = `manual`. Newlines in any field are replaced by spaces. Hook mode reads the PreCompact payload, takes `session_id` from it, and always exits 0, printing a one-line error to stderr if anything fails.

- [ ] **Step 1: Write the failing tests**

```python
import json

from e_agent_harness import progress



def _entries(repo) -> list[progress.ProgressEntry]:
    return progress.parse_progress((repo.root / "harness/state/progress.md").read_text())


def test_checkpoint_appends_entry_with_defaults(repo) -> None:
    assert repo.invoke("new-task", "1", "1c.1", "--feature", "F-1", "--paths", "src/**").code == 0
    repo.write("src/pkg/new.py", "Y = 2\n")
    result = repo.invoke("checkpoint", "--session", "sess-1")
    assert result.code == 0, result
    (entry,) = _entries(repo)
    assert entry.task == "1c.1"
    assert entry.session == "sess-1"
    assert "src/pkg/new.py" in entry.changed
    assert entry.next == "run the suite"
    assert entry.open == "none"


def test_checkpoint_without_task_points_at_new_task(repo) -> None:
    assert repo.invoke("checkpoint").code == 0
    (entry,) = _entries(repo)
    assert entry.task == "none"
    assert entry.next == "new-task"
    assert entry.changed == "no working-tree changes"


def test_checkpoint_sanitises_newlines(repo) -> None:
    assert repo.invoke("checkpoint", "--next", "line one\nline two").code == 0
    (entry,) = _entries(repo)
    assert entry.next == "line one line two"


def test_checkpoint_hook_uses_session_id_and_never_fails(repo) -> None:
    payload = json.dumps({"session_id": "abc123", "trigger": "auto", "cwd": str(repo.root)})
    assert repo.invoke("checkpoint", "--hook", stdin=payload).code == 0
    assert _entries(repo)[0].session == "abc123"
    (repo.root / "harness/context.toml").unlink()  # anything broken: still exit 0
    result = repo.invoke("checkpoint", "--hook", stdin=payload)
    assert result.code == 0
    assert result.err.strip()
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest -q tests/harness/test_checkpoint.py`
Expected: 4 failures (`invalid choice: 'checkpoint'`)

- [ ] **Step 3: Add the command to `cli.py`**

Parser:

```python
    cp = sub.add_parser("checkpoint", help="append a progress entry for the active task")
    cp.add_argument("--next", dest="next_action", default=None)
    cp.add_argument("--changed", default=None)
    cp.add_argument("--open", dest="open_items", default="none")
    cp.add_argument("--session", default="manual")
    cp.add_argument("--hook", action="store_true", help="PreCompact mode: payload on stdin, always exits 0")
```

Command:

```python
def _one_line(text: str) -> str:
    return " ".join(text.split()) or "none"


def _append_checkpoint(args: argparse.Namespace, session: str) -> None:
    root, paths, _m = _context(args)
    loaded = state.load_task(paths)
    changed = args.changed or ", ".join(gitinfo.status_files(root)) or "no working-tree changes"
    next_action = args.next_action or (loaded[0]["acceptance"][0] if loaded else "new-task")
    entry = progress.ProgressEntry(
        timestamp=datetime.now(UTC).isoformat(timespec="seconds"),
        session=_one_line(session),
        task=loaded[0]["id"] if loaded else "none",
        changed=_one_line(changed),
        next=_one_line(next_action),
        open=_one_line(args.open_items),
    )
    progress.append_entry(paths.progress, entry)


def cmd_checkpoint(args: argparse.Namespace) -> int:
    if args.hook:
        try:
            payload = json.load(args.stdin)
            if not args.repo and payload.get("cwd"):
                args.repo = Path(payload["cwd"])
            _append_checkpoint(args, str(payload.get("session_id") or "hook"))
        except Exception as exc:  # a compaction hook must never block
            print(f"checkpoint skipped: {exc}", file=sys.stderr)
        return 0
    _append_checkpoint(args, args.session)
    print("checkpoint appended to harness/state/progress.md")
    return 0
```

Imports: `from e_agent_harness import gitinfo, progress`. Register `"checkpoint": cmd_checkpoint`.

Note: `_context` must find the repository from the payload `cwd` when `--repo` is absent; in tests `--repo` is always given, which is why the hook test passes `cwd` as well.

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest -q tests/harness/test_checkpoint.py`
Expected: `4 passed`

- [ ] **Step 5: Gate and commit**

```bash
git add tools/harness tests/harness
git commit -m "feat(harness): checkpoint appends progress entries, also from PreCompact"
```

---

### Task 6: `handoff` and `close-check` (with Stop hook mode)

**Files:**
- Create: `tools/harness/src/e_agent_harness/closecheck.py`, `tests/harness/test_close_check.py`
- Modify: `cli.py`

**Interfaces:**
- Produces `closecheck.BOOKKEEPING: tuple[str, ...] = ("harness/state/**", "docs/handoffs/**", "evidence/**")`.
- Produces `closecheck.evidence_ties_to_head(repo_root, evidence: dict) -> str | None`: `None` when the evidence was recorded on a clean tree at HEAD, or at an ancestor of HEAD after which only `BOOKKEEPING` paths changed; otherwise the reason.
- Produces `closecheck.handoff_problems(paths, repo_root, phase, task_id) -> list[str]`: handoff file missing, schema problems, missing evidence refs.
- Produces `closecheck.problems(paths, m, repo_root, *, session: str | None) -> list[str]`: no active task; tree not clean; progress log last entry not for this task (or not this session when given); each feature of the task with `passes: true` must cite evidence that exists and ties to HEAD; handoff problems.
- CLI: `handoff <task-id>` (exit 1 on problems) and `close-check [--session ID] [--hook]`. Hook mode: exit 0 when `E_AGENT_HARNESS_UNATTENDED` is not `1` or when the payload has `stop_hook_active: true`; otherwise exit 2 with the problems on stderr.

- [ ] **Step 1: Write the failing tests**

```python
import json
import os


HANDOFF = {
    "task": "1c.1",
    "changed": "split module",
    "evidence_refs": [],
    "open_items": [],
    "rulings": [],
    "outside_repo": [],
}


def _start(repo) -> None:
    assert repo.invoke("new-task", "1", "1c.1", "--feature", "F-1", "--paths", "src/**").code == 0
    repo.commit("task contract")


def _evidence_path(repo) -> str:
    assert repo.invoke("gate", "quick").code == 0
    (path,) = (repo.root / "evidence/gates/1c.1").glob("*.json")
    return str(path.relative_to(repo.root))


def _mark_passing(repo, evidence: str) -> None:
    features_path = repo.root / "harness/state/1/features.json"
    doc = json.loads(features_path.read_text())
    doc["entries"][0]["passes"] = True
    doc["entries"][0]["evidence"] = evidence
    features_path.write_text(json.dumps(doc, indent=2) + "\n")


def _bookkeeping(repo, evidence: str) -> None:
    _mark_passing(repo, evidence)
    handoff = dict(HANDOFF, evidence_refs=[evidence])
    repo.write("harness/state/1/handoffs/1c.1.json", json.dumps(handoff) + "\n")
    assert repo.invoke("checkpoint", "--session", "s1", "--next", "close").code == 0
    repo.commit("bookkeeping")


def test_close_check_accepts_bookkeeping_only_after_evidence(repo) -> None:
    _start(repo)
    repo.write("src/pkg/new.py", "Y = 2\n")
    repo.commit("feature code")
    evidence = _evidence_path(repo)  # clean tree at HEAD
    _bookkeeping(repo, evidence)  # only harness/state changes after the evidence
    result = repo.invoke("close-check", "--session", "s1")
    assert result.code == 0, result
    assert "ok" in result.out


def test_close_check_rejects_code_changed_after_evidence(repo) -> None:
    _start(repo)
    evidence = _evidence_path(repo)
    repo.write("src/pkg/new.py", "Y = 3\n")
    repo.commit("code after evidence")
    _bookkeeping(repo, evidence)
    result = repo.invoke("close-check")
    assert result.code == 1
    assert "code changed after evidence" in result.out and "src/pkg/new.py" in result.out


def test_close_check_rejects_evidence_from_dirty_tree(repo) -> None:
    _start(repo)
    repo.write("src/pkg/new.py", "Y = 2\n")
    evidence = _evidence_path(repo)  # dirty tree
    repo.commit("feature code")
    _bookkeeping(repo, evidence)
    result = repo.invoke("close-check")
    assert result.code == 1
    assert "dirty tree" in result.out


def test_close_check_rejects_passes_without_evidence(repo) -> None:
    _start(repo)
    features_path = repo.root / "harness/state/1/features.json"
    doc = json.loads(features_path.read_text())
    doc["entries"][0]["passes"] = True
    features_path.write_text(json.dumps(doc, indent=2) + "\n")
    repo.write("harness/state/1/handoffs/1c.1.json", json.dumps(HANDOFF) + "\n")
    assert repo.invoke("checkpoint").code == 0
    repo.commit("bookkeeping")
    result = repo.invoke("close-check")
    assert result.code == 1
    assert "F-1" in result.out and "evidence" in result.out


def test_close_check_lists_dirty_tree_missing_progress_and_handoff(repo) -> None:
    _start(repo)
    repo.write("src/pkg/new.py", "Y = 2\n")
    result = repo.invoke("close-check")
    assert result.code == 1
    assert "working tree is not clean" in result.out
    assert "progress log has no entry for task 1c.1" in result.out
    assert "handoff missing" in result.out


def test_close_check_requires_entry_from_this_session(repo) -> None:
    _start(repo)
    evidence = _evidence_path(repo)
    _bookkeeping(repo, evidence)  # session s1
    result = repo.invoke("close-check", "--session", "s2")
    assert result.code == 1
    assert "not from session s2" in result.out


def test_close_check_without_active_task(repo) -> None:
    result = repo.invoke("close-check")
    assert result.code == 1
    assert "no active task" in result.out


def test_handoff_command_validates_schema_and_evidence_refs(repo) -> None:
    _start(repo)
    repo.write("harness/state/1/handoffs/1c.1.json", json.dumps(dict(HANDOFF, evidence_refs=["evidence/gates/1c.1/nope.json"])) + "\n")
    result = repo.invoke("handoff", "1c.1")
    assert result.code == 1
    assert "evidence ref missing" in result.out
    repo.write("harness/state/1/handoffs/1c.1.json", json.dumps(HANDOFF) + "\n")
    assert repo.invoke("handoff", "1c.1").code == 0


def test_close_check_hook_is_inert_unless_unattended(repo, monkeypatch) -> None:
    _start(repo)
    repo.write("src/pkg/new.py", "Y = 2\n")
    payload = json.dumps({"session_id": "s1", "stop_hook_active": False, "cwd": str(repo.root)})
    monkeypatch.delenv("E_AGENT_HARNESS_UNATTENDED", raising=False)
    assert repo.invoke("close-check", "--hook", stdin=payload).code == 0
    monkeypatch.setenv("E_AGENT_HARNESS_UNATTENDED", "1")
    result = repo.invoke("close-check", "--hook", stdin=payload)
    assert result.code == 2
    assert "working tree is not clean" in result.err
    looping = json.dumps({"session_id": "s1", "stop_hook_active": True, "cwd": str(repo.root)})
    assert repo.invoke("close-check", "--hook", stdin=looping).code == 0
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest -q tests/harness/test_close_check.py`
Expected: 9 failures (`invalid choice: 'close-check'`)

- [ ] **Step 3: Write `closecheck.py`**

```python
"""Close ritual checks (harness plan H2, close-check and handoff)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from e_agent_harness import contracts, gitinfo, progress, state
from e_agent_harness.manifest import Manifest, path_matches

BOOKKEEPING: tuple[str, ...] = ("harness/state/**", "docs/handoffs/**", "evidence/**")


def _is_bookkeeping(path: str) -> bool:
    return any(path_matches(path, pattern) for pattern in BOOKKEEPING)


def evidence_ties_to_head(repo_root: Path, evidence: dict[str, Any]) -> str | None:
    if not evidence.get("clean_tree"):
        return "evidence was recorded on a dirty tree; commit first, then run the gate again"
    commit = str(evidence.get("commit", ""))
    head = gitinfo.head_sha(repo_root)
    if commit == head:
        return None
    if not gitinfo.is_ancestor(repo_root, commit, head):
        return f"evidence commit {commit[:7]} is not an ancestor of HEAD {head[:7]}"
    code_changes = [p for p in gitinfo.diff_names(repo_root, commit, head) if not _is_bookkeeping(p)]
    if code_changes:
        return f"code changed after evidence {commit[:7]}: {', '.join(code_changes)}"
    return None


def handoff_problems(paths: state.Paths, repo_root: Path, phase: str, task_id: str) -> list[str]:
    path = paths.handoff(phase, task_id)
    if not path.is_file():
        return [f"handoff missing: {path.relative_to(repo_root)}"]
    doc = state.read_json(path)
    problems = [f"handoff {p}" for p in contracts.validate("handoff", doc)]
    if not problems:
        for ref in doc.get("evidence_refs", []):
            if not (repo_root / ref).is_file():
                problems.append(f"handoff evidence ref missing: {ref}")
    return problems


def problems(paths: state.Paths, m: Manifest, repo_root: Path, *, session: str | None = None) -> list[str]:
    loaded = state.load_task(paths)
    if loaded is None:
        return ["no active task"]
    contract, _ = loaded
    task_id, phase = str(contract["id"]), str(contract["phase"])
    found: list[str] = []
    if not gitinfo.is_clean(repo_root):
        found.append("working tree is not clean")
    entries = progress.parse_progress(paths.progress.read_text(encoding="utf-8")) if paths.progress.is_file() else []
    last = entries[-1] if entries else None
    if last is None or last.task != task_id:
        found.append(f"progress log has no entry for task {task_id}")
    elif session and last.session != session:
        found.append(f"last progress entry is not from session {session}")
    features_path = paths.features(phase)
    entries_by_id: dict[str, Any] = (
        {e["id"]: e for e in state.read_json(features_path)["entries"]} if features_path.is_file() else {}
    )
    for fid in contract["feature_ids"]:
        feature = entries_by_id.get(fid)
        if not feature or not feature.get("passes"):
            continue
        ref = feature.get("evidence")
        if not ref:
            found.append(f"feature {fid} passes without an evidence reference")
            continue
        evidence_file = repo_root / ref
        if not evidence_file.is_file():
            found.append(f"feature {fid}: evidence missing: {ref}")
            continue
        reason = evidence_ties_to_head(repo_root, state.read_json(evidence_file))
        if reason:
            found.append(f"feature {fid}: {reason}")
    found.extend(handoff_problems(paths, repo_root, phase, task_id))
    return found
```

- [ ] **Step 4: Add `handoff` and `close-check` to `cli.py`**

Parser:

```python
    ho = sub.add_parser("handoff", help="validate a task's handoff document")
    ho.add_argument("task_id")
    cc = sub.add_parser("close-check", help="the close ritual: clean tree, progress, evidence, handoff")
    cc.add_argument("--session", default=None)
    cc.add_argument("--hook", action="store_true", help="Stop mode: inert unless E_AGENT_HARNESS_UNATTENDED=1")
```

Commands:

```python
def cmd_handoff(args: argparse.Namespace) -> int:
    root, paths, _m = _context(args)
    active = state.load_active(paths) or {}
    phase = str(active.get("phase") or _phase_of_task(paths, args.task_id) or "")
    found = closecheck.handoff_problems(paths, root, phase, args.task_id)
    for problem in found:
        print(problem)
    if found:
        return 1
    print(f"ok: handoff {args.task_id} valid")
    return 0


def _phase_of_task(paths: state.Paths, task_id: str) -> str | None:
    matches = sorted(paths.state.glob(f"*/tasks/{task_id}.json"))
    return matches[0].parent.parent.name if matches else None


def cmd_close_check(args: argparse.Namespace) -> int:
    if args.hook:
        payload = json.load(args.stdin)
        if os.environ.get("E_AGENT_HARNESS_UNATTENDED") != "1" or payload.get("stop_hook_active"):
            return 0
        if not args.repo and payload.get("cwd"):
            args.repo = Path(payload["cwd"])
        root, paths, m = _context(args)
        found = closecheck.problems(paths, m, root, session=str(payload.get("session_id") or ""))
        if found:
            print("close-check: " + "; ".join(found), file=sys.stderr)
            return 2
        return 0
    root, paths, m = _context(args)
    found = closecheck.problems(paths, m, root, session=args.session)
    for problem in found:
        print(problem)
    if found:
        return 1
    print("ok: task may close")
    return 0
```

Imports: `import os`, `from e_agent_harness import closecheck`. Register both.

- [ ] **Step 5: Run to verify pass**

Run: `uv run pytest -q tests/harness/test_close_check.py`
Expected: `9 passed`

- [ ] **Step 6: Gate and commit**

```bash
git add tools/harness tests/harness
git commit -m "feat(harness): close-check and handoff enforce the close ritual; Stop hook mode"
```

---

### Task 7: `status` (text and SessionStart hook formats, within budget)

**Files:**
- Create: `tools/harness/src/e_agent_harness/status.py`, `tests/harness/test_status.py`
- Modify: `cli.py`

**Interfaces:**
- Produces `status.StatusData` (dataclass: `branch`, `head`, `clean`, `phase`, `plan`, `task_id`, `allowed_paths`, `gate_set`, `acceptance`, `stale`, `has_evidence`, `entries` (last three `ProgressEntry`), `read_only`, `allowed_containers`, `denied_containers`, `manifest_problems`), `status.collect(paths, m, repo_root) -> StatusData`, `status.next_action(d) -> str`, `status.render_text(d, language_order) -> str`, `status.render_hook(d, budget) -> str` (JSON for SessionStart with `hookSpecificOutput.additionalContext` and `sessionTitle`), `status.estimate_tokens(text) -> int` (`len(text) // 4 + 1`).
- CLI: `status [--format text|hook]`.

- [ ] **Step 1: Write the failing tests**

```python
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
    assert repo.invoke("new-task", "1", "1c.1", "--feature", "F-1", "--paths", "src/pkg/**").code == 0
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
    text = json.loads(status.render_hook(data, m.status.token_budget))["hookSpecificOutput"]["additionalContext"]
    assert status.estimate_tokens(text) <= m.status.token_budget


def test_next_action_order(repo) -> None:
    paths = state.Paths(repo.root)
    m = mf.load_manifest(paths.manifest)
    assert status.next_action(status.collect(paths, m, repo.root)).startswith("new-task")
    assert repo.invoke("new-task", "1", "1c.1", "--feature", "F-1", "--paths", "src/**").code == 0
    assert status.next_action(status.collect(paths, m, repo.root)).startswith("commit the work")
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest -q tests/harness/test_status.py`
Expected: 6 failures (`cannot import name 'status'`)

- [ ] **Step 3: Write `status.py`**

```python
"""The status brief: what is going on and exactly one next action (harness plan H2)."""

from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass, field
from pathlib import Path

from e_agent_harness import gitinfo, progress, state
from e_agent_harness.digest import is_stale
from e_agent_harness.manifest import Manifest, validate_manifest

ENTRIES_SHOWN = 3


@dataclass
class StatusData:
    branch: str
    head: str
    clean: bool
    phase: str | None
    plan: str
    task_id: str | None
    allowed_paths: list[str] = field(default_factory=list)
    gate_set: str | None = None
    acceptance: list[str] = field(default_factory=list)
    stale: bool = False
    has_evidence: bool = False
    entries: list[progress.ProgressEntry] = field(default_factory=list)
    read_only: list[str] = field(default_factory=list)
    allowed_containers: list[str] = field(default_factory=list)
    denied_containers: list[str] = field(default_factory=list)
    manifest_problems: list[str] = field(default_factory=list)


def collect(paths: state.Paths, m: Manifest, repo_root: Path) -> StatusData:
    active = state.load_active(paths) or {}
    loaded = state.load_task(paths)
    data = StatusData(
        branch=gitinfo.branch(repo_root),
        head=gitinfo.head_sha(repo_root)[:7],
        clean=gitinfo.is_clean(repo_root),
        phase=str(active["phase"]) if active.get("phase") else None,
        plan=m.authoritative.active_plan,
        task_id=str(loaded[0]["id"]) if loaded else None,
        read_only=list(m.protected.read_only),
        allowed_containers=list(m.environment.allowed_containers),
        denied_containers=list(m.environment.denied_containers),
        manifest_problems=validate_manifest(m, repo_root),
    )
    if loaded:
        contract = loaded[0]
        data.allowed_paths = list(contract["allowed_paths"])
        data.gate_set = str(contract["gate_set"])
        data.acceptance = list(contract["acceptance"])
        data.stale = is_stale(str(contract["context_digest"]), repo_root, m)
        data.has_evidence = any(paths.evidence(data.task_id or "").glob("*.json"))
    if paths.progress.is_file():
        data.entries = progress.parse_progress(paths.progress.read_text(encoding="utf-8"))[-ENTRIES_SHOWN:]
    return data


def next_action(d: StatusData) -> str:
    if d.manifest_problems:
        return "fix the manifest: e-agent-harness validate-context"
    if not d.task_id:
        return "new-task <phase> <task-id> --feature <id> --paths <glob> (pick the next unfinished feature)"
    if d.stale:
        return f"digest stale: authoritative files changed; re-materialise with new-task {d.phase} {d.task_id} ... --replace"
    if not d.clean:
        return f"commit the work, then run e-agent-harness gate {d.gate_set} on the clean tree"
    if not d.has_evidence:
        return f"run e-agent-harness gate {d.gate_set}"
    return "run e-agent-harness checkpoint, write the handoff, then close-check; then /clear"


def _vi(d: StatusData, action: str) -> list[str]:
    tree = "sạch" if d.clean else "đang có thay đổi chưa commit"
    task = d.task_id or "chưa có task nào"
    return [
        "## Tóm tắt (ELI5)",
        f"- Nhánh `{d.branch}` tại {d.head}; phase {d.phase or '?'}; plan: {d.plan}.",
        f"- Task đang làm: {task}; cây làm việc {tree}.",
        f"- Việc tiếp theo duy nhất: {action}",
    ]


def _en(d: StatusData, action: str) -> list[str]:
    lines = ["## Status", f"- Branch {d.branch} at {d.head}; tree {'clean' if d.clean else 'dirty'}; plan {d.plan}."]
    if d.manifest_problems:
        lines += ["- Manifest problems:"] + [f"  - {p}" for p in d.manifest_problems]
    if d.task_id:
        lines += [
            f"- Active task {d.task_id} (phase {d.phase}), gate set {d.gate_set}, digest {'STALE' if d.stale else 'current'}.",
            "- Allowed paths: " + ", ".join(d.allowed_paths),
            "- Acceptance: " + " | ".join(d.acceptance),
        ]
    else:
        lines.append("- No active task.")
    lines += [
        "- Boundaries: read-only " + ", ".join(d.read_only)
        + "; containers allowed " + ", ".join(d.allowed_containers)
        + "; denied " + ", ".join(d.denied_containers) + ".",
    ]
    if d.entries:
        lines.append("- Recent progress:")
        lines += [f"  - {e.timestamp} {e.task}: {e.changed} → next: {e.next}" for e in d.entries]
    lines.append(f"- Next action: {action}")
    return lines


def render_text(d: StatusData, language_order: tuple[str, ...]) -> str:
    action = next_action(d)
    blocks = {"vi-eli5": _vi(d, action), "en": _en(d, action)}
    ordered = [blocks[lang] for lang in language_order if lang in blocks]
    return "\n".join(line for block in ordered for line in (*block, ""))


def estimate_tokens(text: str) -> int:
    return len(text) // 4 + 1


def render_hook(d: StatusData, budget: int) -> str:
    trimmed = dataclasses.replace(d)
    text = render_text(trimmed, ("vi-eli5", "en"))
    while estimate_tokens(text) > budget and trimmed.entries:
        trimmed.entries = trimmed.entries[1:]
        text = render_text(trimmed, ("vi-eli5", "en"))
    if estimate_tokens(text) > budget:
        text = text[: budget * 4 - 4] + " […]"
    title = f"phase-{d.phase or '?'}/{d.task_id or 'no-task'}"
    return json.dumps(
        {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text, "sessionTitle": title}},
        ensure_ascii=False,
    )
```

- [ ] **Step 4: Add the command to `cli.py`**

Parser:

```python
    st = sub.add_parser("status", help="the session brief: state, boundaries, one next action")
    st.add_argument("--format", dest="fmt", choices=["text", "hook"], default="text")
```

Command:

```python
def cmd_status(args: argparse.Namespace) -> int:
    root, paths, m = _context(args)
    data = status.collect(paths, m, root)
    if args.fmt == "hook":
        print(status.render_hook(data, m.status.token_budget))
    else:
        print(status.render_text(data, m.status.language_order))
    return 0
```

Import `from e_agent_harness import status`; register `"status": cmd_status`.

- [ ] **Step 5: Run to verify pass**

Run: `uv run pytest -q tests/harness/test_status.py`
Expected: `6 passed`

Run: `uv run e-agent-harness status`
Expected: a Vietnamese summary, then the English block, next action starting with `new-task` (the real repository has no active task).

- [ ] **Step 6: Gate and commit**

```bash
git add tools/harness tests/harness
git commit -m "feat(harness): status brief in text and SessionStart hook formats within budget"
```

---

### Task 8: documentation, full gate, handoff

**Files:**
- Modify: `docs/superpowers/plans/2026-10-12-dev-harness.md` (H2 section: Done line, ruling on live flows and the close-ritual order), `README.md` (commands), `.gitignore` (confirm `/evidence/` already covers `evidence/gates` and `evidence/live`; no change expected)
- Create: `docs/handoffs/2026-10-13-harness-h2.md`, `harness/state/.gitkeep` is **not** needed: `harness/state/` appears when the first task is materialised.

- [ ] **Step 1: Harness plan H2 section**

Add after the command table:

```markdown
**Done 2026-10-13** (branch `harness/h2-cli`, [handoff](../../handoffs/2026-10-13-harness-h2.md)). Rulings recorded there:
- `live-check` runs the manifest's `live` gate set (identity, environment) with redaction and writes under `evidence/live/`; the configured live flows wait for the H5 pilot, which has the live profile.
- Close-ritual order: commit the code, run `gate` on the clean tree, then checkpoint, handoff and a bookkeeping commit. `close-check` accepts evidence from an ancestor commit only when every later change is bookkeeping (`harness/state/**`, `docs/handoffs/**`, `evidence/**`).
- A contract's `allowed_paths` always include `harness/state/**`, `docs/handoffs/**` and the active plan, written into the contract so nothing is implicit.
- "Plan updated if acceptance changed" is not checked by code: re-materialising with `--replace` makes the change visible in git.
```

- [ ] **Step 2: README commands**

Under the verification commands add:

```bash
uv run e-agent-harness status                 # dev-harness brief: state, boundaries, one next action
uv run e-agent-harness validate-context       # manifest vs checkout
uv run e-agent-harness gate quick --package packages/kernel   # evidence under evidence/gates/
```

- [ ] **Step 3: Full gate**

Run: `uv sync --locked && uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run lint-imports && uv run pytest -q`
Expected: all green; pytest count = previous 510 + 49 new harness tests + 2 conformance cases, 30 skipped.

Run: `uv build tools/harness --out-dir <scratchpad>/h2-dist && unzip -l <scratchpad>/h2-dist/*.whl | grep -c schema.json`
Expected: `7`

- [ ] **Step 4: Handoff**

`docs/handoffs/2026-10-13-harness-h2.md` with: summary (plan link, branch, execution mode), what changed (commit table), what was verified (gate output verbatim), rulings (the four above plus any made during execution), deferred minors, open items for the owner (H3 skills, H4 hooks and settings, the first real feature list for roadmap Phase 1c in H5), changes outside the repository (none).

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/plans/2026-10-12-dev-harness.md README.md docs/handoffs/2026-10-13-harness-h2.md
git commit -m "docs(harness): H2 done; README commands; H2 handoff"
```

---

## Self-review

- **Spec coverage.** `validate-context` (T1), `new-task` (T2), `check-scope` command and hook (T3), `gate` evidence with commit and clean flag (T4), `live-check` (T4, flows deferred by ruling), `checkpoint` with PreCompact mode (T5), `close-check` with Stop mode and `handoff` (T6), `status` text and hook within budget (T7). Exit criteria: unit tests per command (T1–T7), planted out-of-scope change rejected both ways (T3), evidence matches HEAD on a clean tree and `close-check` rejects a `passes` flip without evidence (T4, T6), `status --format hook` within budget on the real repository (T7).
- **Placeholders.** None; every step carries code or a command with its expected output.
- **Type consistency.** `state.Paths`, `state.load_task -> tuple[dict, Path] | None`, `gate.run_gate(..., now=datetime)`, `closecheck.problems(..., session=)`, `status.collect/render_text/render_hook` are used with the same names and shapes across tasks; `manifest.path_matches` is introduced in T3 and consumed in T6.
- **Review Focus.** Each of the five lines names its test and task.
