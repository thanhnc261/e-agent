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
        {
            "id": "F-1",
            "category": "kernel",
            "description": "split module",
            "steps": ["run the suite"],
            "passes": False,
        },
        {
            "id": "F-2",
            "category": "kernel",
            "description": "second feature",
            "steps": ["check openapi"],
            "passes": False,
        },
    ],
}


class Result(NamedTuple):
    code: int
    out: str
    err: str


def git(root: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(root), *args], check=True, capture_output=True, text=True
    )
    return proc.stdout.strip()


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
        git(
            self.root,
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@example.org",
            "commit",
            "-q",
            "-m",
            message,
        )
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
    r.write(
        "docs/plans/phase1.md",
        "# Phase 1\n\n## Global Constraints\n\n- none\n\n## Review Focus\n\n- none\n",
    )
    r.write("addons/e_agent_bridge/__manifest__.py", "{'version': '1.0'}\n")
    r.write("archive/old.md", "old\n")
    r.write("src/pkg/mod.py", "X = 1\n")
    r.write("harness/context.toml", MANIFEST)
    r.write("harness/state/1/features.json", json.dumps(FEATURES, indent=2) + "\n")
    r.write(".gitignore", "/evidence/\n")
    r.base = r.commit("base")
    return r
