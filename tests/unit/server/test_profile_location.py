"""The server ships no profile: a caller gives a path or E_AGENT_PROFILE (ADR 0026, D4)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from e_agent.kernel.errors import ErrorCode, KernelError
from e_agent.plugins.erp.simulator import fixture_profile_path
from e_agent.server.profile import load_profile

REPO = Path(__file__).resolve().parents[3]
IMPLICIT_DEFAULT = re.compile(r"\bload_profile\(\s*\)")


def test_load_profile_requires_path_or_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("E_AGENT_PROFILE", raising=False)
    with pytest.raises(KernelError) as caught:
        load_profile()
    assert caught.value.code is ErrorCode.STARTUP_REJECTED
    assert "--profile" in caught.value.safe_message
    assert "E_AGENT_PROFILE" in caught.value.safe_message


def test_empty_path_is_refused_not_replaced_by_the_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("E_AGENT_PROFILE", str(REPO / "profiles" / "dev-ollama.json"))
    with pytest.raises(KernelError) as caught:
        load_profile("")
    assert caught.value.code is ErrorCode.STARTUP_REJECTED
    monkeypatch.setenv("E_AGENT_PROFILE", "")
    with pytest.raises(KernelError):
        load_profile()


def test_env_profile_is_used(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("E_AGENT_PROFILE", str(REPO / "profiles" / "dev-ollama.json"))
    assert load_profile().driver.kind == "pydantic-ai"
    # An explicit path wins over the environment.
    assert load_profile(fixture_profile_path()).environment == "fixture"


def test_server_package_ships_no_profile() -> None:
    server = REPO / "src" / "e_agent" / "server"
    assert sorted(p.name for p in server.rglob("*.json")) == []
    assert fixture_profile_path().is_file()


def test_no_caller_uses_the_implicit_default() -> None:
    scanned = 0
    offenders = []
    for top in ("src", "tests", "scripts"):
        for path in sorted((REPO / top).rglob("*.py")):
            if path == Path(__file__).resolve():
                continue  # the tests above call it without arguments on purpose
            scanned += 1
            text = path.read_text("utf-8")
            offenders += [
                f"{path.relative_to(REPO)}:{text.count(chr(10), 0, m.start()) + 1}"
                for m in IMPLICIT_DEFAULT.finditer(text)
            ]
    print(f"scanned {scanned} files")
    assert scanned > 0
    assert offenders == []
