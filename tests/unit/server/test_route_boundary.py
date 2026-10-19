"""Model route data boundary and the hosted-route startup rule (ADR 0030, Task 3b.1)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from e_agent.contracts.data import DataProcessing
from e_agent.kernel.errors import ErrorCode, KernelError
from e_agent.plugins.erp.simulator import fixture_profile_path
from e_agent.server.api import create_app
from e_agent.server.bootstrap import build_runtime, check_route_boundary, effective_boundary
from e_agent.server.profile import DriverConfig, Profile, load_profile
from fastapi.testclient import TestClient

PROFILES = Path(__file__).resolve().parents[3] / "profiles"
DECLARATION = DataProcessing(data_owner="Acme Procurement", legal_basis="contract", region="eu")


def _driver(**kw: Any) -> DriverConfig:
    return DriverConfig(kind="pydantic-ai", model="m", **kw)


def _profile(**driver: Any) -> Profile:
    base = load_profile(fixture_profile_path())
    return base.model_copy(update={"driver": _driver(**driver)})


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost:11434/v1",
        "http://LOCALHOST/v1",
        "http://127.0.0.1:11434/v1",
        "http://127.8.9.10/v1",
        "http://[::1]:11434/v1",
    ],
)
def test_loopback_ollama_is_local_verified(url: str) -> None:
    assert effective_boundary(_driver(provider="ollama"), url) == ("local", "verified")


def test_scripted_driver_is_local_verified() -> None:
    assert effective_boundary(DriverConfig(), None) == ("local", "verified")


@pytest.mark.parametrize(
    "url", ["http://gpu.example.com:11434/v1", "http://10.0.0.5/v1", "http://localhost.evil.com/v1"]
)
def test_undeclared_remote_route_is_hosted_unknown(url: str) -> None:
    assert effective_boundary(_driver(provider="ollama"), url) == ("hosted:unknown", "default")


def test_litellm_defaults_to_hosted_unknown() -> None:
    cfg = _driver(provider="litellm")
    assert effective_boundary(cfg, "http://localhost:4000") == ("hosted:unknown", "default")


def test_declared_boundary_is_reported_declared() -> None:
    litellm = _driver(provider="litellm", data_boundary="local")
    assert effective_boundary(litellm, "http://localhost:4000") == ("local", "declared")
    remote = _driver(provider="ollama", data_boundary="hosted:eu")
    assert effective_boundary(remote, "http://localhost:11434/v1") == ("hosted:eu", "declared")
    # ADR 0030: a loopback ollama route stays verified when the profile also declares local
    both = _driver(provider="ollama", data_boundary="local")
    assert effective_boundary(both, "http://127.0.0.1:11434/v1") == ("local", "verified")


def test_malformed_boundary_is_refused() -> None:
    with pytest.raises(ValueError, match="data_boundary"):
        _driver(data_boundary="cloud")


async def test_hosted_route_without_data_processing_fails_startup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("E_AGENT_OLLAMA_URL", "http://secret-host.example.com:11434/v1")
    with pytest.raises(KernelError) as err:
        await build_runtime(_profile(provider="ollama"))
    assert err.value.code is ErrorCode.STARTUP_REJECTED
    assert "data_processing" in str(err.value)
    assert "secret-host" not in str(err.value)  # names the setting, never its value
    # context_assembler does not exist yet (Task 3b.2) and no toggle exempts the rule (Task 3d.5)
    # the adapter only dials loopback, where a LiteLLM proxy is hosted:unknown unless declared
    monkeypatch.delenv("E_AGENT_LITELLM_URL", raising=False)
    declared = _profile(provider="litellm").model_copy(update={"data_processing": DECLARATION})
    runtime = await build_runtime(declared)
    assert runtime.route is not None and runtime.route.boundary == "hosted:unknown"


async def test_local_only_refuses_hosted_route(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("E_AGENT_OLLAMA_URL", "http://secret-host.example.com:11434/v1")
    profile = _profile(provider="ollama").model_copy(
        update={"local_only": True, "data_processing": DECLARATION}
    )
    with pytest.raises(KernelError) as err:
        await build_runtime(profile)
    assert err.value.code is ErrorCode.STARTUP_REJECTED
    assert "local_only" in str(err.value) and "secret-host" not in str(err.value)
    monkeypatch.setenv("E_AGENT_OLLAMA_URL", "http://localhost:11434/v1")
    assert (await build_runtime(profile)).route is not None


def test_readiness_reports_boundary_and_basis(monkeypatch: pytest.MonkeyPatch) -> None:
    with TestClient(create_app(lambda: build_runtime(load_profile(fixture_profile_path())))) as c:
        body = c.get("/health/ready").json()
    assert body["data_boundary"] == "local"
    assert body["data_boundary_basis"] == "verified"
    assert body["data_processing_declared"] is False

    monkeypatch.delenv("E_AGENT_LITELLM_URL", raising=False)
    hosted = _profile(provider="litellm").model_copy(update={"data_processing": DECLARATION})
    with TestClient(create_app(lambda: build_runtime(hosted))) as c:
        body = c.get("/health/ready").json()
    assert body["data_boundary"] == "hosted:unknown"
    assert body["data_boundary_basis"] == "default"
    assert body["data_processing_declared"] is True


def test_committed_profiles_are_local(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("E_AGENT_OLLAMA_URL", raising=False)
    paths = (fixture_profile_path(), PROFILES / "dev-ollama.json", PROFILES / "live.example.json")
    checked = 0
    for path in paths:
        profile = load_profile(path)
        assert profile.data_processing is None, path
        assert json.loads(Path(path).read_text("utf-8")).get("local_only", False) is False
        # the startup rule: every committed profile is local without a declaration
        route = check_route_boundary(profile)
        assert route.boundary == "local", path
        checked += 1
    assert checked == 3, f"checked {checked} committed profiles"
