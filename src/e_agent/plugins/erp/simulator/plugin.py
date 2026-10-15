"""Plugin factory: the simulator executor for the scenario a profile names."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from e_agent.sdk.errors import InvalidPluginSettings
from e_agent.sdk.ports import PluginContribution, PluginServices

from .fake_erp import FakeErp
from .scenarios import SCENARIOS

SETTINGS = frozenset({"scenario", "lose_response_after_commit"})


def create_plugin(services: PluginServices) -> PluginContribution:
    settings = services.settings
    unknown = sorted(set(settings) - SETTINGS)
    if unknown:
        raise InvalidPluginSettings(f"unknown settings {unknown}; known: {sorted(SETTINGS)}")
    scenario = settings.get("scenario", "valid")
    if not isinstance(scenario, str) or scenario not in SCENARIOS:
        raise InvalidPluginSettings(f"unknown scenario {scenario!r}; known: {sorted(SCENARIOS)}")
    lose = settings.get("lose_response_after_commit", False)
    if not isinstance(lose, bool):
        raise InvalidPluginSettings("lose_response_after_commit must be true or false")
    erp = FakeErp(SCENARIOS[scenario], lose_response_after_commit=lose)

    def diagnostics() -> Mapping[str, Any]:
        return {"create_calls": erp.create_calls}

    return PluginContribution(executors=(erp,), diagnostics=diagnostics)
