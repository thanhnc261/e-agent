"""Ruff's banned-api rule keeps ``os.environ`` (PR-37, ENG-ARCH-6) and bare
``asyncio.create_task`` (PR-38, ENG-ARCH-7) out of product code."""

from __future__ import annotations

import re
import subprocess
import tomllib
from collections import Counter
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
BANNED = ("os.environ", "os.getenv", "asyncio.create_task")
# Every exemption under src/ is a line-level noqa comment for TID251 on one of these lines,
# counted per (file, banned API); no file under src/ is exempt as a whole.
# Only the command-line entry points are exempt as whole files (they stay out of the bans' scope).
OUT_OF_SCOPE = {"**/tests/**", "scripts/**", "tools/harness/**", ".claude/hooks/**"}
ALLOWED_LINES = Counter(
    {
        ("src/e_agent/server/environment.py", "os.environ"): 2,
        ("src/e_agent/adapters/secretstore_local/store.py", "os.environ"): 3,
        ("src/e_agent/sdk/tasks.py", "asyncio.create_task"): 1,
    }
)


def _ruff(*args: str, cwd: Path, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["uv", "run", "ruff", "check", "--config", str(REPO / "pyproject.toml"), *args],
        cwd=cwd,
        input=stdin,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize(
    "source",
    [
        'import os\n\nVALUE = os.environ.get("X")\n',
        'import os\n\nVALUE = os.getenv("X")\n',
    ],
    ids=["environ", "getenv"],
)
def test_os_environ_banned_in_product_code(tmp_path: Path, source: str) -> None:
    _assert_banned(tmp_path, source)


@pytest.mark.parametrize(
    "source",
    [
        "import asyncio\n\n\nasync def go() -> None:\n    asyncio.create_task(go())\n",
        "from asyncio import create_task\n\n\nasync def go() -> None:\n    create_task(go())\n",
    ],
    ids=["attribute", "import"],
)
def test_create_task_banned_in_product_code(tmp_path: Path, source: str) -> None:
    _assert_banned(tmp_path, source)


def _assert_banned(tmp_path: Path, source: str) -> None:
    scratch = tmp_path / "src" / "e_agent" / "scratch" / "probe.py"
    scratch.parent.mkdir(parents=True)
    scratch.write_text(source, "utf-8")
    result = _ruff("--select", "TID251", "--no-cache", str(scratch), cwd=tmp_path)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "TID251" in result.stdout
    assert "probe.py" in result.stdout


def _noqa_tid251_lines() -> Counter[tuple[str, str]]:
    found: Counter[tuple[str, str]] = Counter()
    files = sorted((REPO / "src" / "e_agent").rglob("*.py"))
    assert files, "no product files scanned"
    for path in files:
        rel = path.relative_to(REPO).as_posix()
        for line in path.read_text("utf-8").splitlines():
            if not re.search(r"#\s*(ruff\s*:\s*)?noqa\b", line, re.IGNORECASE):
                continue
            codes = re.search(r"noqa\s*:\s*([A-Z0-9, ]+)", line, re.IGNORECASE)
            if codes is None:
                found[(rel, "blanket noqa")] += 1  # a bare noqa would hide TID251 too
                continue
            if "TID251" not in codes.group(1).upper():
                continue
            apis = [api for api in BANNED if api in line]
            found[(rel, apis[0] if len(apis) == 1 else "unidentified")] += 1
    return found


def test_banned_api_allowlist_is_pinned() -> None:
    config = tomllib.loads((REPO / "pyproject.toml").read_text("utf-8"))
    ruff = config["tool"]["ruff"]["lint"]
    file_level = {
        pattern for pattern, codes in ruff["per-file-ignores"].items() if "TID251" in codes
    }
    assert file_level == OUT_OF_SCOPE, "no file under src/ is exempt from TID251"
    found = _noqa_tid251_lines()
    assert sum(found.values()) > 0, "no TID251 exemptions found: the pin would pass on nothing"
    assert found == ALLOWED_LINES
    banned = ruff["flake8-tidy-imports"]["banned-api"]
    assert set(BANNED) <= set(banned)
    assert "TID251" in ruff["select"]


CREATE_TASK_PROBE = (
    "\nimport asyncio\n\n\nasync def _probe() -> None:\n    asyncio.create_task(_probe())\n"
)


@pytest.mark.parametrize(
    ("rel", "extra"),
    [
        ("src/e_agent/server/environment.py", CREATE_TASK_PROBE),
        ("src/e_agent/adapters/secretstore_local/store.py", CREATE_TASK_PROBE),
        ("src/e_agent/sdk/tasks.py", '\nimport os\n\nPROBE = os.environ.get("X")\n'),
    ],
    ids=["environment-create_task", "secretstore-create_task", "tasks-environ"],
)
def test_allowed_files_still_ban_the_other_api(rel: str, extra: str) -> None:
    """An exempt line does not exempt its file: a new banned call there is still flagged."""
    source = (REPO / rel).read_text("utf-8") + extra
    probe_line = len(source.splitlines())
    result = _ruff(
        "--select",
        "TID251",
        "--no-cache",
        "--output-format",
        "concise",
        "--stdin-filename",
        rel,
        "-",
        cwd=REPO,
        stdin=source,
    )
    assert result.returncode == 1, result.stdout + result.stderr
    flagged = [line for line in result.stdout.splitlines() if "TID251" in line]
    assert len(flagged) == 1, result.stdout
    assert flagged[0].startswith(f"{rel}:{probe_line}:"), result.stdout
