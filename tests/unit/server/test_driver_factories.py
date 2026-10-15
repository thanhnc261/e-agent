"""The scripted driver comes from the domain pack's driver factory (R-2 part 1, ADR 0026).

Bootstrap builds the model driver itself and resolves every other ``driver.kind``
through the admitted plugins' factories; the scripted driver's refs come from
the task preset, overridden by the profile's ``refs``.
"""

from __future__ import annotations

import inspect
from typing import Any

import pytest
from e_agent.contracts.run import RunState
from e_agent.erp import plugin as erp_plugin
from e_agent.kernel.errors import ErrorCode, KernelError
from e_agent.plugins.erp.simulator import fixture_profile_path
from e_agent.sdk.ports import AgentDriver, DriverRequest
from e_agent.server import bootstrap
from e_agent.server.bootstrap import build_runtime
from e_agent.server.profile import DriverConfig, Profile, load_profile
from pydantic import ValidationError


def _profile(**driver: Any) -> Profile:
    data = load_profile(fixture_profile_path()).model_dump(mode="json")
    data["driver"] |= driver
    return Profile.model_validate(data)


async def test_scripted_driver_resolved_from_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    requests: list[DriverRequest] = []
    contributed = erp_plugin.DRIVER_FACTORIES["scripted"]

    def recording(request: DriverRequest) -> AgentDriver:
        requests.append(request)
        return contributed(request)

    monkeypatch.setitem(erp_plugin.DRIVER_FACTORIES, "scripted", recording)
    profile = _profile(refs={"product_ref": "product:NEW"})
    rt = await build_runtime(profile, task_kind="shortage", driver_mode="invalid-then-repair")
    assert rt.registry.driver_factories["scripted"] is recording
    [request] = requests
    assert request.connection_id == profile.connections[0].connection_id
    assert request.mode == "invalid-then-repair"
    assert request.task_kind == "shortage"
    # The preset's defaults, in its order, with the profile's refs over them.
    preset = rt.registry.task_presets["shortage"]
    assert list(request.refs) == list(preset.default_refs)
    assert request.refs == {**preset.default_refs, "product_ref": "product:NEW"}
    assert rt.versions["driver"] == "scripted-erp-driver"


def test_bootstrap_no_longer_imports_scripted_driver() -> None:
    source = inspect.getsource(bootstrap)
    assert "ScriptedErpDriver" not in source
    assert "scripted_tasks" not in source
    assert "demand:d-001" not in source and "product:widget-a" not in source


@pytest.mark.parametrize(
    ("task", "state"),
    [
        ("draft-po", RunState.WAITING_APPROVAL),
        ("quotation", RunState.WAITING_APPROVAL),
        ("shortage", RunState.SUCCEEDED),
        ("late-orders", RunState.SUCCEEDED),
    ],
)
async def test_scripted_driver_runs_against_any_enabled_erp_provider(
    task: str, state: RunState
) -> None:
    # The fixture provider here; the Odoo provider in the live check.
    rt = await build_runtime(load_profile(fixture_profile_path()), task_kind=task)
    preset = rt.registry.task_presets[task]
    run = await rt.coordinator.start_run(rt.operator, preset.prompt, rt.scope)
    assert run.state is state


async def test_unknown_driver_kind_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    # The profile names the scripted driver, but no admitted plugin contributes it.
    monkeypatch.delitem(erp_plugin.DRIVER_FACTORIES, "scripted")
    with pytest.raises(KernelError) as exc:
        await build_runtime(load_profile(fixture_profile_path()))
    assert exc.value.code is ErrorCode.STARTUP_REJECTED
    assert "scripted" in exc.value.safe_message


def test_old_ref_keys_move_into_refs() -> None:
    driver = DriverConfig.model_validate(
        {"demand_ref": "demand:OLD", "product_ref": "product:OLD", "refs": {"as_of": "2026-01-01"}}
    )
    assert driver.refs == {
        "as_of": "2026-01-01",
        "demand_ref": "demand:OLD",
        "product_ref": "product:OLD",
    }
    assert not hasattr(driver, "demand_ref") and not hasattr(driver, "product_ref")
    # An old key equal to its refs entry is the same setting, as the live check writes it.
    same = DriverConfig.model_validate(
        {"demand_ref": "demand:X", "refs": {"demand_ref": "demand:X"}}
    )
    assert same.refs == {"demand_ref": "demand:X"}
    # A null old key sets nothing.
    assert DriverConfig.model_validate({"product_ref": None}).refs == {}
    # Through the profile loader too.
    assert _profile(demand_ref="demand:OLD").driver.refs == {"demand_ref": "demand:OLD"}


@pytest.mark.parametrize("key", ["demand_ref", "product_ref"])
def test_old_ref_key_conflicting_with_refs_refused(key: str) -> None:
    with pytest.raises(ValidationError) as exc:
        DriverConfig.model_validate({key: "x:OLD", "refs": {key: "x:NEW"}})
    assert key in str(exc.value)
