"""The release report lists the defaulted effect declarations (ADR 0029 Operations, 2c.8a R-3)."""

import importlib.util
import sys
from pathlib import Path

from e_agent.plugins.erp.simulator import fixture_profile_path
from e_agent.server.bootstrap import build_runtime
from e_agent.server.profile import load_profile

from ..server.test_api import FIXTURE_DEFAULTED

REPO = Path(__file__).resolve().parents[3]
_spec = importlib.util.spec_from_file_location(
    "release_report_2c8a", REPO / "scripts" / "release_report.py"
)
assert _spec is not None and _spec.loader is not None
rr = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = rr  # dataclasses resolve annotations through sys.modules
_spec.loader.exec_module(rr)


async def test_release_report_lists_defaulted_declarations() -> None:
    rt = await build_runtime(load_profile(fixture_profile_path()))
    result = {"passed": True, "task": "ERP-01", "case": "a", "final_state": "SUCCEEDED"}
    report = rr.build_report(rt, [result])
    assert report["defaulted_declarations"] == FIXTURE_DEFAULTED
    assert (report["passed"], report["total"], report["cases"]) == (1, 1, [result])
    assert report["versions"] == rt.versions
    print(f"release report lists {len(FIXTURE_DEFAULTED)} defaulted declarations")


# -- Task 3d.3: repairs, token use and the context columns (ADR 0032 §7) --------------------
BASELINE = REPO / "evals" / "reports" / "phase3-baseline.json"


async def test_release_report_context_columns_only_in_shadow() -> None:
    from e_agent.contracts.features import FeatureMode

    case = rr.CASES[4]  # ERP-03 blocked by PR-003, then repaired
    assert case.mode == "invalid-then-repair"
    off = await rr.run_case(case)
    shadow = await rr.run_case(case, FeatureMode.SHADOW)
    assert off["passed"] and shadow["passed"]
    assert off["context"] is None
    assert off["model_tokens"] == shadow["model_tokens"] == "unknown"  # the scripted driver
    assert (
        off["repairs"]
        == shadow["repairs"]
        == {
            "proposals": 2,
            "failed_validations": 1,
            "failed_answer_checks": 0,
            "rate": 0.5,
        }
    )
    context = shadow["context"]
    assert context["turns"] >= 2 and context["shadow_failures"] == 0
    assert 0 < context["pack_tokens"] <= context["unbounded_tokens"]
    assert context["tokens_used"] == "unknown"
    print(f"shadow context columns over {context['turns']} turns")


def test_repair_metrics_count_answer_checks_and_never_divide_by_zero() -> None:
    from datetime import UTC, datetime

    from e_agent.contracts.events import RunEvent, RunEventType

    def event(seq: int, kind: RunEventType, payload: dict, action: str | None = None) -> RunEvent:
        return RunEvent(
            event_id=f"e{seq}",
            tenant_id="t",
            run_id="r",
            sequence=seq,
            type=kind,
            occurred_at=datetime(2026, 10, 19, tzinfo=UTC),
            action_id=action,
            payload=payload,
        )

    created, outcome = RunEventType.PROPOSAL_CREATED, RunEventType.OUTCOME_REPORTED
    events = [
        event(1, created, {"kind": "answer"}, "a1"),
        event(2, outcome, {"status": "FAILED"}, "a1"),
        event(3, created, {}, "w1"),
        event(4, RunEventType.VALIDATION_COMPLETED, {"status": "FAIL"}),
        event(5, created, {}, "w2"),
        event(6, outcome, {"status": "FAILED"}, "w2"),  # a failed write is no repair
    ]
    assert rr.repair_metrics(events) == {
        "proposals": 3,
        "failed_validations": 1,
        "failed_answer_checks": 1,
        "rate": 0.6667,
    }
    assert rr.repair_metrics([])["rate"] is None
    assert rr.context_columns(events) is None


def test_phase3_baseline_is_off_fixture_evidence() -> None:
    import json

    report = json.loads(BASELINE.read_text(encoding="utf-8"))
    assert report["environment"] == "fixture"
    assert report["context_assembler"] == "off"
    assert "Not live model" in report["note"]
    cases = report["cases"]
    assert len(cases) == report["total"] == len(rr.CASES) > 0
    assert report["passed"] == report["total"]
    assert all(c["context"] is None for c in cases)
    assert all(c["repairs"]["proposals"] > 0 for c in cases)
    assert all(c["model_tokens"] == "unknown" for c in cases)
    assert report["repair_rate"] is not None
    print(f"phase3 baseline: {len(cases)} cases, repair rate {report['repair_rate']}")


# -- Task 3d.6: the repeat columns and the disagreement count (ADR 0031 §5) -----------------
def test_repeat_columns_count_disagreements() -> None:
    from datetime import UTC, datetime

    from e_agent.contracts.events import RunEvent, RunEventType

    def event(seq: int, kind: RunEventType, payload: dict) -> RunEvent:
        return RunEvent(
            event_id=f"e{seq}",
            tenant_id="t",
            run_id="r",
            sequence=seq,
            type=kind,
            occurred_at=datetime(2026, 10, 19, tzinfo=UTC),
            payload=payload,
        )

    compared, failed = RunEventType.REPEAT_COMPARED, RunEventType.REPEAT_SHADOW_FAILED
    events = [
        event(1, compared, {"would_repeat": False, "repeat_of": None, "same_findings": None}),
        event(2, compared, {"would_repeat": True, "repeat_of": "a1", "same_findings": True}),
        event(3, compared, {"would_repeat": True, "repeat_of": "a1", "same_findings": False}),
        event(4, failed, {"stage": "check", "message": "m"}),
    ]
    assert rr.repeat_columns(events) == {
        "compared": 3,
        "would_repeat": 2,
        "disagreements": 1,
        "shadow_failures": 1,
    }
    assert rr.repeat_columns(events[:0]) is None


async def test_release_report_repeat_disagreements_only_in_shadow() -> None:
    from e_agent.contracts.features import FeatureMode

    rt = await build_runtime(load_profile(fixture_profile_path()))
    plain = {"passed": True, "task": "ERP-01", "case": "a", "final_state": "SUCCEEDED"}
    assert rr.build_report(rt, [{**plain, "repeat": None}])["repeat_disagreements"] is None
    columns = {"compared": 2, "would_repeat": 1, "disagreements": 1, "shadow_failures": 0}
    report = rr.build_report(rt, [{**plain, "repeat": columns}], kernel_repeat=FeatureMode.SHADOW)
    assert (report["kernel_repeat"], report["repeat_disagreements"]) == ("shadow", 1)
    off = await rr.run_case(rr.CASES[4])  # ERP-03 blocked by PR-003, then repaired
    assert off["passed"] and off["repeat"] is None


# -- Task 3e.2: a GROUNDED end is counted apart from VERIFIED (ADR 0033 §3, PR-19) ----------
async def test_release_report_counts_grounded_separately() -> None:
    """A grounded run writes no ``outcome.reported``: the report counts it as its own end,
    never as ``verified``, even if a result also lists a VERIFIED outcome."""
    rt = await build_runtime(load_profile(fixture_profile_path()))
    results = [
        {"final_state": "SUCCEEDED", "reason_code": "verified", "outcomes": ["VERIFIED"]},
        {"final_state": "SUCCEEDED", "reason_code": "answered", "outcomes": ["FAILED", "VERIFIED"]},
        {"final_state": "SUCCEEDED", "reason_code": "grounded", "outcomes": []},
        {"final_state": "SUCCEEDED", "reason_code": "grounded", "outcomes": ["VERIFIED"]},
        {"final_state": "FAILED", "reason_code": "validation_failed", "outcomes": []},
    ]
    ends = [rr.end_class(r) for r in results]
    assert ends == ["verified", "verified", "grounded", "grounded", "failed"]
    report = rr.build_report(rt, [{**r, "passed": True} for r in results])
    assert report["ends"] == {"failed": 1, "grounded": 2, "verified": 2}
    case = await rr.run_case(rr.CASES[0])  # ERP-01: a verified shortage answer
    assert (case["reason_code"], rr.end_class(case)) == ("answered", "verified")
    print(f"release report ends counted over {len(results)} results")
