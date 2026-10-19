"""The release report lists the defaulted effect declarations (ADR 0029 Operations, 2c.8a R-3)."""

import importlib.util
import sys
from pathlib import Path
from typing import Any

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
NO_REPAIRS = {"validation": 0, "no_action": 0, "plain_text": 0, "stale": 0, "answer": 0}


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
            "attempts": 2,
            "repairs": 1,
            "terminal_refusals": 0,
            "rate": 0.5,
            "kinds": {**NO_REPAIRS, "validation": 1},
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
        event(4, RunEventType.VALIDATION_COMPLETED, {"status": "FAIL"}, "w1"),
        event(5, created, {}, "w2"),
        event(6, outcome, {"status": "FAILED"}, "w2"),  # a failed write is no repair
    ]
    assert rr.repair_metrics(events) == {
        "attempts": 3,
        "repairs": 2,
        "terminal_refusals": 0,
        "rate": 0.6667,
        "kinds": {**NO_REPAIRS, "validation": 1, "answer": 1},
    }
    assert rr.repair_metrics([])["rate"] is None
    assert rr.context_columns(events) is None


def _event(seq: int, kind: Any, payload: dict, action: str | None = None) -> Any:
    from datetime import UTC, datetime

    from e_agent.contracts.events import RunEvent

    return RunEvent(
        event_id=f"e{seq}",
        tenant_id="t",
        run_id="r",
        sequence=seq,
        type=kind,
        occurred_at=datetime(2026, 10, 20, tzinfo=UTC),
        action_id=action,
        payload=payload,
    )


def _run(*specs: tuple[Any, dict] | tuple[Any, dict, str]) -> list[Any]:
    return [_event(seq, *spec) for seq, spec in enumerate(specs, start=1)]


def _kernel(rule_id: str) -> dict:
    return {"status": "FAIL", "findings": [{"rule_id": rule_id, "status": "FAIL"}]}


def _failed(code: str) -> tuple[Any, dict]:
    from e_agent.contracts.events import RunEventType

    return (RunEventType.RUN_STATE_CHANGED, {"to": "FAILED", "reason_code": code})


def test_repair_metrics_match_kernel_repairs() -> None:
    """D3-31, review 3f.2 R1-2: a repair is exactly what ``cont.repairs`` counts, a refusal
    returned to the driver. Counted: a failed proposal validation, a first-step dispatch
    STALE the kernel returned (RUNNING, ``stale``), a plain-text ``KERNEL-VERIFICATION``
    turn, a no-action ``KERNEL-*`` refusal and a failed answer check. Not counted: a later
    plan step (``step_index > 0``, ``KERNEL-PLAN-STEP-CHANGED``, ``KERNEL-PLAN-LINEAGE``),
    the ``KERNEL-ACCEPTANCE`` ending, a status-less event, and the refusal that ended the
    run, which is a terminal refusal."""
    from e_agent.contracts.events import RunEventType

    created, validated = RunEventType.PROPOSAL_CREATED, RunEventType.VALIDATION_COMPLETED
    state, outcome = RunEventType.RUN_STATE_CHANGED, RunEventType.OUTCOME_REPORTED
    events = _run(
        (created, {"step_index": None}, "w1"),
        (validated, {"status": "FAIL", "findings": []}, "w1"),  # validation repair
        (created, {"step_index": 0}, "w2"),
        (validated, {"status": "PASS", "findings": []}, "w2"),
        (validated, {"status": "STALE", "reason": "revision moved"}, "w2"),
        (state, {"to": "RUNNING", "reason_code": "stale"}),  # the STALE went back
        (created, {"step_index": 0}, "p0"),
        (validated, {"status": "PASS", "findings": []}, "p0"),
        (created, {"step_index": 1}, "p1"),  # a later plan step, kernel-made
        (validated, {"status": "FAIL", "findings": []}, "p1"),
        (validated, {"status": "STALE", "reason": "deadline"}, "p1"),
        (validated, _kernel("KERNEL-PLAN-STEP-CHANGED")),
        (validated, _kernel("KERNEL-PLAN-LINEAGE")),
        (validated, _kernel("KERNEL-VERIFICATION")),  # plain-text repair, an attempt
        (validated, _kernel("KERNEL-ACCEPTANCE")),
        (validated, {"findings": []}),  # no status: no refusal
        (validated, _kernel("KERNEL-ARGS")),  # no-action repair, an attempt (event 16)
        (created, {"kind": "answer"}, "a1"),
        (outcome, {"status": "FAILED"}, "a1"),  # answer repair
        (created, {}, "w3"),
        (validated, {"status": "FAIL", "findings": []}, "w3"),  # the budget is spent
        _failed("validation_failed"),
    )
    assert rr.repair_metrics(events, max_repairs=5) == {
        "attempts": 7,
        "repairs": 5,
        "terminal_refusals": 1,
        "rate": 0.7143,
        "kinds": {"validation": 1, "no_action": 1, "plain_text": 1, "stale": 1, "answer": 1},
    }
    # a STALE that failed the run went back to no one, and is no terminal refusal either
    stale = _run(
        (created, {}, "w1"),
        (validated, {"status": "PASS", "findings": []}, "w1"),
        (validated, {"status": "STALE", "reason": "revision moved"}, "w1"),
        _failed("stale"),
    )
    assert rr.repair_metrics(stale) == {
        "attempts": 1,
        "repairs": 0,
        "terminal_refusals": 0,
        "rate": 0.0,
        "kinds": NO_REPAIRS,
    }
    print(f"repair metrics over {len(events) + len(stale)} synthetic events")


def test_repair_metrics_terminal_only_by_reason_code() -> None:
    """Review 3f.2 R1-1: a refusal is terminal only when the run's FAILED record has
    ``validation_failed``, ``verification_failed`` or ``policy_denied``, and the kernel's
    own test (policy denial, or the budget spent) held at it; never by adjacency."""
    from e_agent.contracts.events import RunEventType

    created, validated = RunEventType.PROPOSAL_CREATED, RunEventType.VALIDATION_COMPLETED
    outcome = RunEventType.OUTCOME_REPORTED
    blocked = (validated, {"status": "FAIL", "findings": []}, "w1")
    # returned, then the next turn exhausted a budget: a repair, even with no budget left
    exhausted = _run(
        (created, {}, "w1"),
        blocked,
        (RunEventType.BUDGET_EXHAUSTED, {"budget": "max_driver_turns"}),
        _failed("budget_exhausted"),
    )
    for budget in (0, 2):
        metrics = rr.repair_metrics(exhausted, max_repairs=budget)
        assert (metrics["repairs"], metrics["terminal_refusals"]) == (1, 0)
    # a policy denial is terminal within the budget, whatever its validation status
    for status in ("FAIL", "PASS"):
        denied = _run(
            (created, {}, "w1"),
            (validated, {"status": status, "findings": [], "policy_reasons": ["r"]}, "w1"),
            _failed("policy_denied"),
        )
        metrics = rr.repair_metrics(denied)
        assert (metrics["repairs"], metrics["terminal_refusals"]) == (0, 1)
    plan_denied = _run(
        (validated, {"status": "FAIL", "findings": [], "policy_reasons": ["r"]}),
        _failed("policy_denied"),
    )
    metrics = rr.repair_metrics(plan_denied)
    assert (metrics["attempts"], metrics["repairs"], metrics["terminal_refusals"]) == (1, 0, 1)
    # two answer repairs, then a plain-text reply past the budget ends the run with no
    # event of its own: both answers went back, so neither is terminal
    answers = _run(
        (created, {"kind": "answer"}, "a1"),
        (outcome, {"status": "FAILED"}, "a1"),
        (created, {"kind": "answer"}, "a2"),
        (outcome, {"status": "FAILED"}, "a2"),
        _failed("verification_failed"),
    )
    metrics = rr.repair_metrics(answers)
    assert (metrics["repairs"], metrics["terminal_refusals"]) == (2, 0)
    # a third failed answer past the budget is the terminal one
    third = [
        *answers[:-1],
        _event(5, created, {"kind": "answer"}, "a3"),
        _event(6, outcome, {"status": "FAILED"}, "a3"),
        _event(7, *_failed("verification_failed")),
    ]
    metrics = rr.repair_metrics(third)
    assert (metrics["attempts"], metrics["repairs"], metrics["terminal_refusals"]) == (3, 2, 1)
    no_verifier = _run((validated, _kernel("KERNEL-VERIFIER")), _failed("verification_failed"))
    metrics = rr.repair_metrics(no_verifier)
    assert (metrics["attempts"], metrics["repairs"], metrics["terminal_refusals"]) == (1, 0, 1)


def test_repair_rate_is_at_most_one() -> None:
    """Review 3f.2 R1-3: one attempt per driver proposal plus one per counted no-action
    refusal, so every repair has its own attempt. Event 16's case, refusals of attempts that
    made no action, now has a denominator."""
    from e_agent.contracts.events import RunEventType

    created, validated = RunEventType.PROPOSAL_CREATED, RunEventType.VALIDATION_COMPLETED
    state = RunEventType.RUN_STATE_CHANGED
    no_action = _run(
        (validated, _kernel("KERNEL-ARGS")),
        (validated, _kernel("KERNEL-CONNECTION")),
        (validated, _kernel("KERNEL-VERIFICATION")),
    )
    stale_after_pass = _run(
        (created, {}, "w1"),
        (validated, {"status": "PASS", "findings": []}, "w1"),
        (validated, {"status": "STALE", "reason": "moved"}, "w1"),
        (state, {"to": "RUNNING", "reason_code": "stale"}),
    )
    runs = [no_action, stale_after_pass]
    rates = [rr.repair_metrics(events, max_repairs=9)["rate"] for events in runs]
    assert rates == [1.0, 1.0]
    assert all(rate is not None and rate <= 1 for rate in rates)


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
    assert all(c["repairs"]["attempts"] > 0 for c in cases)
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


# -- Task 3e.4: the grounding counts (ADR 0033 §5) --------------------------------------------
def test_grounding_columns_sum_counts() -> None:
    from datetime import UTC, datetime

    from e_agent.contracts.events import RunEvent, RunEventType
    from e_agent.contracts.grounding import CitationCounts, GroundingCompared, RefCounts

    def event(seq: int, kind: RunEventType, payload: dict) -> RunEvent:
        return RunEvent(
            event_id=f"e{seq}",
            tenant_id="t",
            run_id="r",
            sequence=seq,
            type=kind,
            occurred_at=datetime(2026, 10, 20, tzinfo=UTC),
            payload=payload,
        )

    cited = CitationCounts(cited=3, resolved=1, unresolved=1, mismatched=1)
    answer = GroundingCompared(citations=cited).model_dump(mode="json")
    write = GroundingCompared().model_dump(mode="json")
    write["rationale"]["rules"] = RefCounts(cited=2, resolved=1, unresolved=1).model_dump()
    compared, failed = RunEventType.GROUNDING_COMPARED, RunEventType.GROUNDING_SHADOW_FAILED
    events = [
        event(1, compared, answer),
        event(2, compared, write),
        event(3, failed, {"stage": "check", "message": "m"}),
    ]
    columns = rr.grounding_columns(events)
    assert columns == {
        "compared": 2,
        "shadow_failures": 1,
        "citations": {"cited": 3, "resolved": 1, "unresolved": 1, "mismatched": 1},
        "rationale_evidence": {"cited": 0, "resolved": 0, "unresolved": 0},
        "rationale_rules": {"cited": 2, "resolved": 1, "unresolved": 1},
    }
    assert rr.unresolved_refs(columns) == 3
    assert rr.grounding_columns(events[:0]) is None


async def test_release_report_grounding_counts_only_in_shadow() -> None:
    """With ``grounded_answers: shadow`` the scripted driver cites its answers and gives its
    draft PO a rationale; every case still passes and every ref resolves. In ``off`` the
    report has no grounding columns."""
    from e_agent.contracts.features import FeatureMode

    off = await rr.run_case(rr.CASES[0])
    assert off["passed"] and off["grounding"] is None
    procurement = [c for c in rr.CASES if c.kind in {"shortage", "recommend", "draft-po"}]
    results = [await rr.run_case(c, grounded_answers=FeatureMode.SHADOW) for c in procurement]
    assert results and all(r["passed"] for r in results)
    grounding = [r["grounding"] for r in results]
    assert all(g is not None and g["compared"] > 0 for g in grounding)
    cited = sum(g["citations"]["cited"] for g in grounding)
    refs = sum(g["rationale_evidence"]["cited"] + g["rationale_rules"]["cited"] for g in grounding)
    assert cited > 0 and refs > 0
    rt = await build_runtime(load_profile(fixture_profile_path()))
    report = rr.build_report(rt, results, grounded_answers=FeatureMode.SHADOW)
    assert (report["grounded_answers"], report["grounding_unresolved"]) == ("shadow", 0)
    assert rr.build_report(rt, [off])["grounding_unresolved"] is None
    print(f"grounding counts: {len(results)} cases, {cited} citations, {refs} rationale refs")


def test_phase3_baseline_has_no_grounding_columns() -> None:
    import json

    report = json.loads(BASELINE.read_text(encoding="utf-8"))
    assert report["grounded_answers"] == "off" and report["grounding_unresolved"] is None
    assert report["cases"] and all(c["grounding"] is None for c in report["cases"])
