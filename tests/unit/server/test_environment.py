"""Environment reads go through one helper that names the variable, never its value (PR-37)."""

from __future__ import annotations

import pytest
from e_agent.kernel.errors import ErrorCode, KernelError
from e_agent.plugins.erp.simulator import fixture_profile_path
from e_agent.server.bootstrap import open_store
from e_agent.server.environment import optional_env, require_env
from e_agent.server.profile import StoreConfig, load_profile

VAR = "E_AGENT_TEST_H2_VAR"


async def test_missing_dsn_env_reports_variable_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("E_AGENT_TEST_H2_DSN", raising=False)
    base = load_profile(fixture_profile_path())
    profile = base.model_copy(
        update={"store": StoreConfig(kind="postgres", dsn_env="E_AGENT_TEST_H2_DSN")}
    )
    with pytest.raises(KernelError) as caught:
        await open_store(profile)
    assert caught.value.code is ErrorCode.STARTUP_REJECTED
    assert "E_AGENT_TEST_H2_DSN" in caught.value.safe_message


def test_require_env_returns_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(VAR, "secret-value")
    assert require_env(VAR) == "secret-value"


@pytest.mark.parametrize("value", [None, ""])
def test_require_env_refuses_missing_or_empty_without_echoing(
    monkeypatch: pytest.MonkeyPatch, value: str | None
) -> None:
    if value is None:
        monkeypatch.delenv(VAR, raising=False)
    else:
        monkeypatch.setenv(VAR, value)
    with pytest.raises(KernelError) as caught:
        require_env(VAR, purpose="for the proxy")
    assert caught.value.code is ErrorCode.STARTUP_REJECTED
    assert caught.value.safe_message == f"{VAR} is not set for the proxy"


def test_optional_env_default_and_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(VAR, raising=False)
    assert optional_env(VAR) is None
    assert optional_env(VAR, "dflt") == "dflt"
    monkeypatch.setenv(VAR, "")
    assert optional_env(VAR, "dflt") == ""
    monkeypatch.setenv(VAR, "v")
    assert optional_env(VAR, "dflt") == "v"
