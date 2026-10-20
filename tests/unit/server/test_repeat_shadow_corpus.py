"""`kernel_repeat: shadow` over the fixture corpus (ADR 0031 §5, Task 3d.6).

The real consumer of ``repeat.compared``: every release-report case, plus a driver that
re-proposes the same blocked draft PO until the repair budget ends the run, runs through the
real kernel, SHACL validators, policy and fake ERP in ``shadow``. Each write proposal's
comparison says whether the repeat rule would have short-circuited it and whether validation
then gave the same findings. Zero disagreements is the evidence that the ERP validators are
a function of their input, the assumption ``on`` relies on. The test fails on an empty
corpus and on a corpus with no repeat in it (PR-31): zero comparisons prove nothing.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from e_agent.contracts.features import FeatureMode

REPO = Path(__file__).resolve().parents[3]
_spec = importlib.util.spec_from_file_location(
    "release_report_3d6", REPO / "scripts" / "release_report.py"
)
assert _spec is not None and _spec.loader is not None
rr = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = rr  # dataclasses resolve annotations through sys.modules
_spec.loader.exec_module(rr)

ALWAYS_INVALID = rr.Case(
    "ERP-03",
    "draft-po",
    "unapproved offer re-proposed until the repair budget ends the run",
    "FAILED",
    mode="always-invalid",
    expect_blocked_rule="PR-003",
    expect_outcomes=(),
    writes=0,
)
CORPUS = [*rr.CASES, ALWAYS_INVALID]


async def test_repeat_shadow_agrees_with_validation() -> None:
    results = [await rr.run_case(case, kernel_repeat=FeatureMode.SHADOW) for case in CORPUS]
    columns = [r["repeat"] for r in results if r["repeat"] is not None]
    compared = sum(c["compared"] for c in columns)
    would_repeat = sum(c["would_repeat"] for c in columns)
    disagreements = sum(c["disagreements"] for c in columns)
    failures = sum(c["shadow_failures"] for c in columns)
    print(
        f"repeat shadow: {len(results)} cases, {compared} write proposals compared, "
        f"{would_repeat} would repeat, {disagreements} disagreements"
    )
    assert len(results) == len(rr.CASES) + 1 > 1
    assert [r["case"] for r in results if not r["passed"]] == []  # shadow changes no case
    assert compared > 0 and would_repeat > 0  # PR-31: a corpus without a repeat proves nothing
    assert (disagreements, failures) == (0, 0)
    report = rr.build_report(await rr.build_runtime(rr.fixture_profile()), results)
    assert report["repeat_disagreements"] == 0
