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
            "accepted": 1,
            "terminal_refusals": 0,
            "policy_denied": 0,
            "rate": 0.5,
        }
    )
    context = shadow["context"]
    assert context["turns"] >= 2 and context["shadow_failures"] == 0
    assert 0 < context["pack_tokens"] <= context["unbounded_tokens"]
    assert context["tokens_used"] == "unknown"
    print(f"shadow context columns over {context['turns']} turns")


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


def _run(*specs: tuple[Any, ...]) -> list[Any]:
    return [_event(seq, *spec) for seq, spec in enumerate(specs, start=1)]


def _specs() -> dict[str, Any]:
    from e_agent.contracts.events import RunEventType as T

    def created(action: str, **payload: Any) -> tuple[Any, ...]:
        return (T.PROPOSAL_CREATED, payload, action)

    def validated(action: str | None, status: str, state: str | None, **extra: Any) -> tuple:
        payload = {"status": status, "findings": [], "action_state": state, **extra}
        return (T.VALIDATION_COMPLETED, payload, action)

    def outcome(action: str, status: str) -> tuple[Any, ...]:
        return (T.OUTCOME_REPORTED, {"status": status}, action)

    def end(to: str, code: str) -> tuple[Any, ...]:
        return (T.RUN_STATE_CHANGED, {"to": to, "reason_code": code})

    return {"created": created, "validated": validated, "outcome": outcome, "end": end, "T": T}


def _metrics(events: list[Any], repairs: int | None) -> tuple[Any, ...]:
    m = rr.repair_metrics(events, repairs)
    assert m["rate"] is None or 0 <= m["rate"] <= 1  # review 3f.2 R1-3: at most 1
    return m["attempts"], m["repairs"], m["accepted"], m["terminal_refusals"], m["policy_denied"]


def test_attempts_count_each_success_kind_once() -> None:
    """Review 3f.2 R2: the denominator is accepted + repaired + terminally refused attempts.
    Accepted: a first-step proposal its validation left VALIDATED whose write no
    verification failed, an answer that verified, a GROUNDED end. A later plan step, an
    action a dispatch STALE blocked, and a write whose verification failed are not."""
    k = _specs()
    created, validated, outcome, end = k["created"], k["validated"], k["outcome"], k["end"]
    write = _run(
        created("w1"),
        validated("w1", "PASS", "VALIDATED"),
        outcome("w1", "VERIFIED"),
        end("SUCCEEDED", "verified"),
    )
    answer = _run(created("a1", kind="answer"), outcome("a1", "VERIFIED"), end("SUCCEEDED", "a"))
    grounded = _run(end("SUCCEEDED", "grounded"))
    plan = _run(
        created("p0", step_index=0),
        validated("p0", "PASS", "VALIDATED"),
        created("p1", step_index=1),  # kernel-made: no attempt
        validated("p1", "PASS", "VALIDATED"),
        end("SUCCEEDED", "verified"),
    )
    stale = _run(  # the STALE went back (a repair); its action ends BLOCKED, not accepted
        created("w1"),
        validated("w1", "PASS", "VALIDATED"),
        validated("w1", "STALE", "BLOCKED"),
        end("RUNNING", "stale"),
        created("w2"),
        validated("w2", "PASS", "VALIDATED"),
        end("SUCCEEDED", "verified"),
    )
    unverified = _run(  # a write the verifier refused: the run's terminal refusal, once
        created("w1"),
        validated("w1", "PASS", "VALIDATED"),
        outcome("w1", "FAILED"),
        end("FAILED", "verification_failed"),
    )
    assert _metrics(write, 0) == (1, 0, 1, 0, 0)
    assert _metrics(answer, 0) == (1, 0, 1, 0, 0)
    assert _metrics(grounded, 0) == (1, 0, 1, 0, 0)
    assert _metrics(plan, 0) == (1, 0, 1, 0, 0)
    assert _metrics(stale, 1) == (2, 1, 1, 0, 0)
    assert _metrics(unverified, 0) == (1, 0, 0, 1, 0)
    assert rr.repair_metrics([], 0)["rate"] is None  # never divides by zero


def test_terminal_refusals_and_policy_denial() -> None:
    """Review 3f.2 R2: one terminal refusal per run that FAILED validation_failed or
    verification_failed; policy_denied has its own key and is neither a repair nor a
    terminal refusal. The repairs are the kernel's counter, passed in as it stored it."""
    k = _specs()
    created, validated, outcome, end, T = (
        k["created"],
        k["validated"],
        k["outcome"],
        k["end"],
        k["T"],
    )
    exhausted = _run(  # returned, then the next turn's budget check ended the run
        created("w1"),
        validated("w1", "FAIL", "BLOCKED"),
        (T.BUDGET_EXHAUSTED, {"budget": "max_driver_turns"}),
        end("FAILED", "budget_exhausted"),
    )
    raised = _run(  # the verifier raised: UNKNOWN, a repair within the budget
        created("a1", kind="answer"),
        outcome("a1", "UNKNOWN"),
        created("a2", kind="answer"),
        outcome("a2", "VERIFIED"),
        end("SUCCEEDED", "answered"),
    )
    raised_past = _run(  # past the budget the third UNKNOWN is the terminal refusal
        created("a1", kind="answer"),
        outcome("a1", "UNKNOWN"),
        created("a2", kind="answer"),
        outcome("a2", "UNKNOWN"),
        created("a3", kind="answer"),
        outcome("a3", "UNKNOWN"),
        end("FAILED", "verification_failed"),
    )
    lineage = _run(  # a plan-time KERNEL-PLAN-LINEAGE refusal, returned before any action
        validated(None, "FAIL", None),
        created("w1"),
        validated("w1", "PASS", "VALIDATED"),
        outcome("w1", "VERIFIED"),
        end("SUCCEEDED", "verified"),
    )
    blocked = _run(
        created("w1"),
        validated("w1", "FAIL", "BLOCKED"),
        created("w2"),
        validated("w2", "FAIL", "BLOCKED"),
        created("w3"),
        validated("w3", "FAIL", "BLOCKED"),
        end("FAILED", "validation_failed"),
    )
    denied = _run(
        created("w1"),
        validated("w1", "PASS", "BLOCKED", policy_reasons=["r"]),
        end("FAILED", "policy_denied"),
    )
    assert _metrics(exhausted, 1) == (1, 1, 0, 0, 0)
    assert _metrics(raised, 1) == (2, 1, 1, 0, 0)
    assert _metrics(raised_past, 2) == (3, 2, 0, 1, 0)
    assert _metrics(lineage, 1) == (2, 1, 1, 0, 0)
    assert _metrics(blocked, 2) == (3, 2, 0, 1, 0)
    assert _metrics(denied, 0) == (0, 0, 0, 0, 1)
    unknown = rr.repair_metrics(blocked, None)
    expected = ("unknown", "unknown", None)
    assert (unknown["attempts"], unknown["repairs"], unknown["rate"]) == expected
    assert rr.overall_rate([{"repairs": unknown}]) is None  # an unknown is never 0


async def test_kernel_repair_counter_is_current_at_run_end() -> None:
    """The stored ``cont.repairs`` is current when the run ends, also right after an
    increment: a blocked proposal is returned, then the next turn's budget check ends the
    run BUDGET_EXHAUSTED with no driver call between."""
    case = rr.CASES[4]  # ERP-03 blocked by PR-003, then repaired
    profile = rr.fixture_profile()
    budgets = profile.budgets.model_copy(update={"max_driver_turns": 2})
    rt = await build_runtime(
        profile.model_copy(update={"budgets": budgets}),
        driver_mode=case.mode,
        plugin_settings={"fixture-erp": {"scenario": "valid", "lose_response_after_commit": False}},
        task_kind=case.kind,
    )
    run = await rt.coordinator.start_run(rt.operator, case.name, rt.scope)
    assert (run.state.value, run.reason_code) == ("FAILED", "budget_exhausted")
    repairs = await rr.kernel_repairs(rt.store, rt.operator.tenant_id, run.run_id)
    assert repairs == 1
    events = await rt.store.list_events(rt.operator.tenant_id, run.run_id)
    assert _metrics(events, repairs) == (1, 1, 0, 0, 0)
    over = await rr.run_case(rr.CASES[5])  # over budget: two repairs, then the terminal one
    assert over["repairs"] == {
        "attempts": 3,
        "repairs": 2,
        "accepted": 0,
        "terminal_refusals": 1,
        "policy_denied": 0,
        "rate": 0.6667,
    }


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
