"""Startup guards on the profile (Task 2c.7, ADR 0025, owner decision D3).

A live profile admits at most one write per run: no UI yet presents a multi-step plan and
recomputes its digest (Phase 5), so ``max_admitted_writes > 1`` is refused at startup.
Fixture profiles may raise it to run plans.
"""

from pathlib import Path

import pytest
from e_agent.kernel.errors import ErrorCode, KernelError
from e_agent.plugins.erp.simulator import fixture_profile_path
from e_agent.server.bootstrap import build_runtime, check_live_write_budget
from e_agent.server.profile import Profile, load_profile

LIVE_EXAMPLE = Path(__file__).resolve().parents[3] / "profiles" / "live.example.json"


def _budget(profile: Profile, writes: int) -> Profile:
    budgets = profile.budgets.model_copy(update={"max_admitted_writes": writes})
    return profile.model_copy(update={"budgets": budgets})


async def test_live_profile_refuses_multi_write_budget() -> None:
    live = load_profile(LIVE_EXAMPLE)
    assert live.environment == "live"
    with pytest.raises(KernelError) as direct:
        check_live_write_budget(_budget(live, 2))
    assert direct.value.code is ErrorCode.STARTUP_REJECTED
    assert "max_admitted_writes" in str(direct.value)
    with pytest.raises(KernelError) as startup:
        await build_runtime(_budget(live, 2))
    assert startup.value.code is ErrorCode.STARTUP_REJECTED
    assert "max_admitted_writes" in str(startup.value)


def test_live_profile_with_one_write_passes_the_guard() -> None:
    check_live_write_budget(_budget(load_profile(LIVE_EXAMPLE), 1))


async def test_fixture_profile_may_admit_two_writes() -> None:
    fixture = _budget(load_profile(fixture_profile_path()), 2)
    assert fixture.environment == "fixture"
    check_live_write_budget(fixture)
    rt = await build_runtime(fixture)
    assert rt.profile.budgets.max_admitted_writes == 2
