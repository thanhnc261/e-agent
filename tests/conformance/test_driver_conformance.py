"""Driver conformance (Task 3f.1, target architecture U2 and G7): every `AgentDriver` passes
the same cases on the same host inputs.

`test_every_driver_passes_conformance` runs every case in ``driver_cases`` against each
driver's adapter: the pydantic-ai driver on recorded model responses and the ERP scripted
driver. A case that does not apply to a driver is declared by its adapter with a typed reason
(`NotApplicable`) that the case accepts, and the suite checks the claim against the adapter's
subject before it accepts it (`runner.check_claim`); a false, unknown or unaccepted
declaration fails the suite. The test prints the case count and the pass and not-applicable
counts per driver, and fails on zero cases (PR-31). A third-party driver joins by adding an
adapter (`driver_cases.adapters`).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from typing import Any

import pytest

from tests.conformance.driver_cases import CASES, TOPICS, DriverAdapter
from tests.conformance.driver_cases.adapters import (
    ADAPTERS,
    AUTHORED,
    NOT_APPLICABLE,
    SCENARIOS,
    SCRIPTED,
    PydanticAdapter,
)
from tests.conformance.driver_cases.harness import NotApplicable
from tests.conformance.driver_cases.runner import SuiteResult, run_conformance
from tests.conformance.driver_cases.world import erp_world


@pytest.fixture(params=sorted(ADAPTERS))
async def adapter(request: pytest.FixtureRequest) -> DriverAdapter:
    """One adapter per driver, built on the fixture profile's ERP tool specs."""
    world = await erp_world()
    built: DriverAdapter = ADAPTERS[request.param](world)
    assert built.not_applicable == NOT_APPLICABLE[built.name]
    return built


def _report(name: str, result: SuiteResult) -> None:
    print(
        f"driver conformance [{name}]: {len(CASES)} cases, {len(result.passed)} passed, "
        f"{len(result.not_applicable)} not applicable, {len(result.failed)} failed"
    )
    for line in result.not_applicable:
        print(f"  not applicable: {line}")
    for line in result.failed:
        print(f"  FAILED {line}")


async def test_every_driver_passes_conformance(adapter: DriverAdapter) -> None:
    result = await run_conformance(adapter)
    _report(adapter.name, result)
    assert result.passed, f"{adapter.name} passed no case"
    assert not result.failed, "\n".join(result.failed)
    assert len(result.passed) + len(result.not_applicable) == len(CASES)


def test_every_case_runs_somewhere() -> None:
    """Each topic has a case, and no case is declared not applicable for every driver: a
    case no driver runs would pass vacuously. Each declaration is a reason its case accepts."""
    assert CASES and TOPICS
    print(f"driver conformance: {len(CASES)} cases over {len(TOPICS)} topics")
    assert {c.topic for c in CASES} == set(TOPICS)
    assert set(NOT_APPLICABLE) == set(ADAPTERS)
    needs = {c.case_id: c.needs for c in CASES}
    for name, declared in NOT_APPLICABLE.items():
        for case_id, reason in declared.items():
            assert reason in needs[case_id], f"{name}: {case_id} does not accept {reason}"
    for case in CASES:
        skipped = [name for name, cases in NOT_APPLICABLE.items() if case.case_id in cases]
        assert len(skipped) < len(ADAPTERS), f"{case.case_id} runs on no driver"
        assert case.checks.strip(), case.case_id


def test_scenarios_are_mapped() -> None:
    """Every scripted scenario is also a recorded one, and every authored response says what
    it checks (PR-29)."""
    assert set(SCRIPTED) <= set(SCENARIOS)
    assert AUTHORED and all(doc and doc.strip() for doc in AUTHORED.values())
    print(
        f"scenarios: {len(SCENARIOS)} recorded, {len(SCRIPTED)} scripted, {len(AUTHORED)} authored"
    )


# -- the suite refuses what a third-party adapter could get wrong (review R1-1) -------------
@dataclasses.dataclass
class ThirdParty(PydanticAdapter):
    """A third-party adapter: the pydantic-ai driver, with its own declarations."""

    name: str = "third-party"
    declared: Mapping[str, Any] = dataclasses.field(default_factory=dict)

    def __post_init__(self) -> None:
        self.not_applicable = dict(self.declared)


async def _third_party(declared: Mapping[str, Any]) -> SuiteResult:
    result = await run_conformance(ThirdParty(await erp_world(), declared=declared))
    _report("third-party", result)
    return result


async def test_a_false_no_model_claim_fails_the_suite() -> None:
    """A driver with a model that declares the hygiene case NO_MODEL fails, and the case
    does not count as not applicable."""
    result = await _third_party({"hygiene.no_hidden_reasoning": NotApplicable.NO_MODEL})
    [failure] = result.failed
    assert failure.startswith("hygiene.no_hidden_reasoning: false NO_MODEL claim")
    assert not result.not_applicable


@pytest.mark.parametrize(
    ("declared", "expected"),
    [
        ({"budget.tokens_respected": NotApplicable.NO_TOKEN_SPEND}, "false NO_TOKEN_SPEND"),
        ({"resume.rendering_marker": NotApplicable.NO_CONTINUATION}, "false NO_CONTINUATION"),
        ({"protocol.identity": NotApplicable.NO_MODEL}, "is not a reason this case accepts"),
        ({"hygiene.no_hidden_reasoning": "it is hard"}, "unknown not-applicable reason"),
        ({"no.such.case": NotApplicable.NO_MODEL}, "no such case"),
    ],
)
async def test_every_bad_declaration_fails_the_suite(
    declared: Mapping[str, Any], expected: str
) -> None:
    result = await _third_party(declared)
    assert len(result.failed) == 1 and expected in result.failed[0], result.failed
    assert not result.not_applicable


async def test_zero_cases_fail() -> None:
    with pytest.raises(AssertionError, match="no cases"):
        await run_conformance(ThirdParty(await erp_world()), cases=())
