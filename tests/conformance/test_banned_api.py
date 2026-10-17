"""Ruff's banned-api rule keeps ``os.environ`` out of product code (PR-37, ENG-ARCH-6)."""

from __future__ import annotations

import subprocess
import tomllib
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
ALLOWED_ENV_FILES = {
    "src/e_agent/server/environment.py",
    "src/e_agent/adapters/secretstore_local/store.py",
}


def _ruff(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["uv", "run", "ruff", "check", "--config", str(REPO / "pyproject.toml"), *args],
        cwd=cwd,
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
    scratch = tmp_path / "src" / "e_agent" / "scratch" / "probe.py"
    scratch.parent.mkdir(parents=True)
    scratch.write_text(source, "utf-8")
    result = _ruff("--select", "TID251", "--no-cache", str(scratch), cwd=tmp_path)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "TID251" in result.stdout
    assert "probe.py" in result.stdout


def test_banned_api_allowlist_is_pinned() -> None:
    config = tomllib.loads((REPO / "pyproject.toml").read_text("utf-8"))
    ruff = config["tool"]["ruff"]["lint"]
    ignores = ruff["per-file-ignores"]
    allowed = {
        pattern
        for pattern, codes in ignores.items()
        if "TID251" in codes and pattern.startswith("src/")
    }
    assert allowed, "no TID251 exemptions under src/: the pin would pass on nothing"
    assert allowed == ALLOWED_ENV_FILES
    banned = ruff["flake8-tidy-imports"]["banned-api"]
    assert {"os.environ", "os.getenv"} <= set(banned)
    assert "TID251" in ruff["select"]
