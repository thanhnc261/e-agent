"""Model route data boundary and the hosted-route startup rule (ADR 0030, Task 3b.1)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from e_agent.contracts.data import DataProcessing
from e_agent.contracts.features import FeatureMode, Features
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


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost@evil.com/v1",
        "http://127.0.0.1.nip.io/v1",
        "http://localhost./v1",
        "http://[::ffff:127.0.0.1]/v1",
        "http://0.0.0.0:11434/v1",
    ],
)
def test_loopback_bypass_attempts_are_not_local(url: str) -> None:
    assert effective_boundary(_driver(provider="ollama"), url) == ("hosted:unknown", "default")


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
    # no toggle exempts the rule until masking lands (Task 3d.5)
    # the adapter only dials loopback, where a LiteLLM proxy is hosted:unknown unless declared
    monkeypatch.delenv("E_AGENT_LITELLM_URL", raising=False)
    declared = _profile(provider="litellm").model_copy(update={"data_processing": DECLARATION})
    runtime = await build_runtime(declared)
    assert runtime.route is not None and runtime.route.boundary == "hosted:unknown"


async def test_hosted_route_refused_at_startup_even_with_context_assembler_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ADR 0030's ``on`` exemption waits for masking (Task 3d.5): until then ``on`` changes
    nothing at startup (review ruling B1-2)."""
    monkeypatch.setenv("E_AGENT_OLLAMA_URL", "http://secret-host.example.com:11434/v1")
    on = Features(context_assembler=FeatureMode.ON)
    with pytest.raises(KernelError) as err:
        await build_runtime(_profile(provider="ollama").model_copy(update={"features": on}))
    assert err.value.code is ErrorCode.STARTUP_REJECTED
    assert "data_processing" in str(err.value) and "secret-host" not in str(err.value)


async def test_runtime_hands_the_route_facts_to_the_kernel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The per-call route check (ADR 0032 §9) reads the facts readiness reports."""
    runtime = await build_runtime(load_profile(fixture_profile_path()))
    assert runtime.coordinator._route == runtime.route_facts()
    monkeypatch.delenv("E_AGENT_LITELLM_URL", raising=False)
    declared = _profile(provider="litellm").model_copy(update={"data_processing": DECLARATION})
    runtime = await build_runtime(declared)
    assert runtime.coordinator._route == runtime.route_facts()
    assert runtime.coordinator._route["data_boundary"] == "hosted:unknown"
    assert runtime.coordinator._route["data_processing_declared"] is True


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


async def test_committed_profiles_pass_the_route_rule(monkeypatch: pytest.MonkeyPatch) -> None:
    """The rule accepts all three without a declaration. The live example needs the
    sandbox to start, so it gets the rule alone; the two fixture-environment profiles start."""
    monkeypatch.delenv("E_AGENT_OLLAMA_URL", raising=False)
    paths = (fixture_profile_path(), PROFILES / "dev-ollama.json", PROFILES / "live.example.json")
    checked = 0
    for path in paths:
        profile = load_profile(path)
        assert profile.data_processing is None, path
        assert check_route_boundary(profile).boundary == "local", path
        checked += 1
    assert checked == 3, f"checked {checked} committed profiles"
    for path in (fixture_profile_path(), PROFILES / "dev-ollama.json"):  # fixture environments
        runtime = await build_runtime(load_profile(path))
        assert runtime.route is not None and runtime.route.boundary == "local", path
