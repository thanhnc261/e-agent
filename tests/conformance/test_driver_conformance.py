"""Driver conformance (Task 3f.1, target architecture U2 and G7): every `AgentDriver` passes
the same cases on the same host inputs.

`test_every_driver_passes_conformance` runs every case in ``driver_cases`` against each
driver's adapter: the pydantic-ai driver on recorded model responses and the ERP scripted
driver. A case that does not apply to a driver is declared by its adapter with the reason and
reported, never skipped silently. The test prints the case count and the pass and
not-applicable counts per driver, and fails on zero cases (PR-31). A third-party driver joins
by adding an adapter (`driver_cases.adapters`).
"""

from __future__ import annotations

import pytest

from tests.conformance.driver_cases import CASES, TOPICS, DriverAdapter
from tests.conformance.driver_cases.adapters import (
    ADAPTERS,
    AUTHORED,
    NOT_APPLICABLE,
    SCENARIOS,
    SCRIPTED,
)
from tests.conformance.driver_cases.world import erp_world


@pytest.fixture(params=sorted(ADAPTERS))
async def adapter(request: pytest.FixtureRequest) -> DriverAdapter:
    """One adapter per driver, built on the fixture profile's ERP tool specs."""
    world = await erp_world()
    built: DriverAdapter = ADAPTERS[request.param](world)
    assert built.not_applicable == NOT_APPLICABLE[built.name]
    return built


async def test_every_driver_passes_conformance(adapter: DriverAdapter) -> None:
    assert CASES, "the driver conformance suite has no cases"
    case_ids = {c.case_id for c in CASES}
    unknown = set(adapter.not_applicable) - case_ids
    assert not unknown, f"{adapter.name} declares unknown cases not applicable: {unknown}"
    passed: list[str] = []
    skipped: list[str] = []
    failed: list[str] = []
    for case in CASES:
        reason = adapter.not_applicable.get(case.case_id)
        if reason is not None:
            assert reason.strip(), f"{case.case_id}: a not-applicable case needs a reason"
            skipped.append(f"{case.case_id}: {reason}")
            continue
        try:
            await case.run(adapter, await erp_world())
        except Exception as exc:  # every failure is reported, not only the first
            failed.append(f"{case.case_id}: {type(exc).__name__}: {exc}")
        else:
            passed.append(case.case_id)
    print(
        f"driver conformance [{adapter.name}]: {len(CASES)} cases, {len(passed)} passed, "
        f"{len(skipped)} not applicable, {len(failed)} failed"
    )
    for line in skipped:
        print(f"  not applicable: {line}")
    for line in failed:
        print(f"  FAILED {line}")
    assert passed, f"{adapter.name} passed no case"
    assert not failed, "\n".join(failed)


def test_every_case_runs_somewhere() -> None:
    """Each topic has a case, and no case is declared not applicable for every driver: a
    case no driver runs would pass vacuously."""
    assert CASES and TOPICS
    print(f"driver conformance: {len(CASES)} cases over {len(TOPICS)} topics")
    assert {c.topic for c in CASES} == set(TOPICS)
    assert set(NOT_APPLICABLE) == set(ADAPTERS)
    for case in CASES:
        declared = [name for name, cases in NOT_APPLICABLE.items() if case.case_id in cases]
        assert len(declared) < len(ADAPTERS), f"{case.case_id} runs on no driver"
        assert case.checks.strip(), case.case_id


def test_scenarios_are_mapped() -> None:
    """Every scripted scenario is also a recorded one, and every authored response says what
    it checks (PR-29)."""
    assert set(SCRIPTED) <= set(SCENARIOS)
    assert AUTHORED and all(doc and doc.strip() for doc in AUTHORED.values())
    print(
        f"scenarios: {len(SCENARIOS)} recorded, {len(SCRIPTED)} scripted, {len(AUTHORED)} authored"
    )
