"""The context ablation runs the fixture corpus in both arms (Task 3f.2, research 03 §8)."""

import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
REPORT = REPO / "evals" / "reports" / "phase3-context-ablation.json"
_spec = importlib.util.spec_from_file_location(
    "context_ablation_3f2", REPO / "scripts" / "context_ablation.py"
)
assert _spec is not None and _spec.loader is not None
ca = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = ca  # dataclasses resolve annotations through sys.modules
_spec.loader.exec_module(ca)


async def test_ablation_runs_both_arms() -> None:
    """Every corpus case runs once per arm, paired by position; zero cases is a failure
    (PR-31). ``off`` records no context columns, ``on`` records its packs."""
    cases = ca.rr.CASES
    arms = await ca.run_arms(cases)
    assert set(arms) == {"off", "on"}
    counts = {arm: len(results) for arm, results in arms.items()}
    assert counts == {"off": len(cases), "on": len(cases)} and len(cases) > 0
    assert all(r["context"] is None for r in arms["off"])
    assert all(r["context"] is not None and r["context"]["turns"] > 0 for r in arms["on"])
    assert all(r["context"]["fallbacks"] == 0 for r in arms["on"])
    report = await ca.build_ablation(arms)
    assert {arm: report["arms"][arm]["cases"] for arm in ("off", "on")} == counts
    assert ca.exit_code(report) == 0
    print(f"ablation: {counts['off']} cases per arm")


async def test_ablation_fails_on_zero_cases() -> None:
    arms = await ca.run_arms([])
    report = await ca.build_ablation(arms)
    assert report["arms"]["off"]["cases"] == report["arms"]["on"]["cases"] == 0
    assert ca.exit_code(report) == 1


async def test_ablation_is_deterministic() -> None:
    """Two runs give byte-identical reports: no ids, digests or timestamps reach them."""
    cases = ca.rr.CASES[3:5]  # a draft PO, and one blocked then repaired
    first = ca.dumps(await ca.build_ablation(await ca.run_arms(cases)))
    second = ca.dumps(await ca.build_ablation(await ca.run_arms(cases)))
    assert first == second and "act_" not in first and "jcs-sha256" not in first


def test_recorded_ablation_is_labelled_fixture() -> None:
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    assert report["environment"] == "fixture"
    assert "Not live model" in report["note"] and "no claim beyond" in report["note"]
    assert "estimate" in report["token_note"]
    assert report["versions"]["model"] is None
    arms = report["arms"]
    assert arms["off"]["context_assembler"] == "off" and arms["on"]["context_assembler"] == "on"
    assert arms["off"]["cases"] == arms["on"]["cases"] == len(report["cases"]) > 0
    assert arms["off"]["passed"] == arms["off"]["cases"]
    assert arms["off"]["pack_tokens_estimate"] == "unknown"
    assert isinstance(arms["on"]["pack_tokens_estimate"], int)
    print(f"recorded ablation: {len(report['cases'])} cases per arm")
