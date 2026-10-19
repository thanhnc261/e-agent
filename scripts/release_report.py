"""Release qualification task matrix (I14) on the fixture environment.

Runs every ERP task through the real kernel, SHACL engine, policy, approval,
ledger and verifiers with the scripted driver and fake ERP, including negative
cases, and writes a JSON report. It is deterministic evidence of the *host*
safety path only: no model and no live ERP are involved (environment=fixture).
Live Odoo evidence comes from tests/integration/test_odoo_live*.py; live model
evidence from scripts/qualify_model.py (ADR 0010).

    uv run python scripts/release_report.py --out evals/reports/fixture-release.json

Each case also reports its repairs and token use, and, with ``--context-assembler shadow``,
the context columns from the run's ``context.compared`` events (ADR 0032 §7, Task 3d.3), and,
with ``--kernel-repeat shadow``, the repeat columns and disagreement count from its
``repeat.compared`` events (ADR 0031 §5, Task 3d.6). The Phase 3 ``off`` baseline is this
report recorded with the toggles ``off``:

    uv run python scripts/release_report.py --out evals/reports/phase3-baseline.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass
from typing import Any

from e_agent.contracts.approval import ApprovalDecision
from e_agent.contracts.events import RunEvent, RunEventType
from e_agent.contracts.features import FeatureMode
from e_agent.contracts.run import RunState
from e_agent.kernel.evidence import defaulted_payload
from e_agent.kernel.progress import project_progress
from e_agent.plugins.erp.simulator import fixture_profile_path
from e_agent.server.bootstrap import build_runtime
from e_agent.server.profile import load_profile


@dataclass(frozen=True)
class Case:
    task_id: str
    kind: str
    name: str
    expect_state: str
    mode: str = "valid"
    scenario: str | None = None
    decision: str | None = "approved"
    fault: bool = False
    expect_blocked_rule: str | None = None
    expect_outcomes: tuple[str, ...] = ("VERIFIED",)
    writes: int = 1


CASES = [
    Case("ERP-01", "shortage", "verified shortage answer", "SUCCEEDED", writes=0),
    Case(
        "ERP-01",
        "shortage",
        "wrong answer fails verification, then corrected",
        "SUCCEEDED",
        mode="wrong-answer-then-correct",
        expect_outcomes=("FAILED", "VERIFIED"),
        writes=0,
    ),
    Case("ERP-02", "recommend", "verified offer recommendation", "SUCCEEDED", writes=0),
    Case("ERP-03", "draft-po", "draft PO approved and verified", "SUCCEEDED"),
    Case(
        "ERP-03",
        "draft-po",
        "unapproved offer blocked by PR-003, then repaired",
        "SUCCEEDED",
        mode="invalid-then-repair",
        expect_blocked_rule="PR-003",
    ),
    Case(
        "ERP-03",
        "draft-po",
        "over budget blocked",
        "FAILED",
        scenario="over-budget",
        expect_blocked_rule="PR-004",
        expect_outcomes=(),
        writes=0,
    ),
    Case(
        "ERP-03",
        "draft-po",
        "rejection writes nothing",
        "FAILED",
        decision="rejected",
        expect_outcomes=(),
        writes=0,
    ),
    Case(
        "ERP-03",
        "draft-po",
        "lost response reconciled without a second write",
        "SUCCEEDED",
        fault=True,
    ),
    Case("ERP-04", "amend-rfq", "draft RFQ amended and verified", "SUCCEEDED"),
    Case(
        "ERP-04",
        "amend-rfq",
        "stale revision blocked by AM-002, then repaired",
        "SUCCEEDED",
        mode="invalid-then-repair",
        expect_blocked_rule="AM-002",
    ),
    Case(
        "ERP-04",
        "amend-rfq",
        "confirmed RFQ blocked by AM-001",
        "FAILED",
        scenario="rfq-confirmed",
        expect_blocked_rule="AM-001",
        expect_outcomes=(),
        writes=0,
    ),
    Case("ERP-05", "quotation", "draft quotation created and verified", "SUCCEEDED"),
    Case(
        "ERP-05",
        "quotation",
        "off-list price blocked by SQ-003, then repaired",
        "SUCCEEDED",
        mode="invalid-then-repair",
        expect_blocked_rule="SQ-003",
    ),
    Case(
        "ERP-05",
        "quotation",
        "unsaleable product blocked by SQ-002",
        "FAILED",
        scenario="unsaleable-product",
        expect_blocked_rule="SQ-002",
        expect_outcomes=(),
        writes=0,
    ),
    Case("ERP-06", "late-orders", "verified late-orders answer", "SUCCEEDED", writes=0),
    Case(
        "ERP-06",
        "late-orders",
        "wrong answer fails verification, then corrected",
        "SUCCEEDED",
        mode="wrong-answer-then-correct",
        expect_outcomes=("FAILED", "VERIFIED"),
        writes=0,
    ),
    Case("ERP-07", "crm-lead", "lead created and verified", "SUCCEEDED"),
    Case(
        "ERP-07",
        "crm-lead",
        "owner outside team blocked by CL-002, then repaired",
        "SUCCEEDED",
        mode="invalid-then-repair",
        expect_blocked_rule="CL-002",
    ),
    Case(
        "ERP-07",
        "crm-lead",
        "lost response reconciled without a duplicate lead",
        "SUCCEEDED",
        fault=True,
    ),
    Case("ERP-08", "overdue-invoices", "verified overdue-invoices answer", "SUCCEEDED", writes=0),
    Case(
        "ERP-08",
        "overdue-invoices",
        "wrong totals fail verification, then corrected",
        "SUCCEEDED",
        mode="wrong-answer-then-correct",
        expect_outcomes=("FAILED", "VERIFIED"),
        writes=0,
    ),
]


METRICS_NOTE = (
    "repairs.rate is (failed_validations + failed_answer_checks) / proposals: how often the "
    "kernel sent a proposal or answer back. model_tokens is what the run's events record of "
    "the driver's token use ('unknown' when they record none, never 0). context is null "
    "unless context_assembler is shadow; its pack_tokens and unbounded_tokens are the "
    "kernel estimator's sums over the run's driver turns, not model-reported tokens. repeat is "
    "null unless kernel_repeat is shadow; a disagreement is a write proposal the repeat rule "
    "would have short-circuited whose validation then gave other findings."
)


def fixture_profile(
    context_assembler: FeatureMode = FeatureMode.OFF, kernel_repeat: FeatureMode = FeatureMode.OFF
) -> Any:
    profile = load_profile(fixture_profile_path())
    features = profile.features.model_copy(
        update={"context_assembler": context_assembler, "kernel_repeat": kernel_repeat}
    )
    return profile.model_copy(update={"features": features})


def repair_metrics(events: list[RunEvent]) -> dict[str, Any]:
    """Proposals, the kernel's refusals of them, and the repair rate (METRICS_NOTE)."""
    answers = {
        e.action_id
        for e in events
        if e.type is RunEventType.PROPOSAL_CREATED and e.payload.get("kind") == "answer"
    }
    proposals = sum(e.type is RunEventType.PROPOSAL_CREATED for e in events)
    failed_validations = sum(
        e.type is RunEventType.VALIDATION_COMPLETED and e.payload.get("status") != "PASS"
        for e in events
    )
    failed_answer_checks = sum(
        e.type is RunEventType.OUTCOME_REPORTED
        and e.payload.get("status") == "FAILED"
        and e.action_id in answers
        for e in events
    )
    repairs = failed_validations + failed_answer_checks
    return {
        "proposals": proposals,
        "failed_validations": failed_validations,
        "failed_answer_checks": failed_answer_checks,
        "rate": round(repairs / proposals, 4) if proposals else None,
    }


def context_columns(events: list[RunEvent]) -> dict[str, Any] | None:
    """The ``context.compared`` columns of a shadow run; None when the run recorded none."""
    compared = [e.payload for e in events if e.type is RunEventType.CONTEXT_COMPARED]
    failed = [e for e in events if e.type is RunEventType.CONTEXT_SHADOW_FAILED]
    if not compared and not failed:
        return None
    deltas = [p["tokens_used_delta"] for p in compared]
    return {
        "turns": len(compared),
        "shadow_failures": len(failed),
        "pack_tokens": sum(sum(p["pack_tokens"].values()) for p in compared),
        "unbounded_tokens": sum(sum(p["unbounded_tokens"].values()) for p in compared),
        "tokens_used": sum(deltas) if deltas and None not in deltas else "unknown",
        "dropped": sum(sum(p["dropped"].values()) for p in compared),
        "masked": sum(p["drop_reasons"]["class_route"] for p in compared),
        "omitted_observations": sum(len(p["omitted_evidence"]) for p in compared),
    }


def repeat_columns(events: list[RunEvent]) -> dict[str, Any] | None:
    """The ``repeat.compared`` columns of a ``kernel_repeat: shadow`` run; None when the run
    recorded none. A disagreement: the rule would have repeated, validation differed."""
    compared = [e.payload for e in events if e.type is RunEventType.REPEAT_COMPARED]
    failed = [e for e in events if e.type is RunEventType.REPEAT_SHADOW_FAILED]
    if not compared and not failed:
        return None
    return {
        "compared": len(compared),
        "would_repeat": sum(p["would_repeat"] is True for p in compared),
        "disagreements": sum(
            p["would_repeat"] is True and p["same_findings"] is not True for p in compared
        ),
        "shadow_failures": len(failed),
    }


async def run_case(
    case: Case,
    context_assembler: FeatureMode = FeatureMode.OFF,
    kernel_repeat: FeatureMode = FeatureMode.OFF,
) -> dict[str, Any]:
    rt = await build_runtime(
        fixture_profile(context_assembler, kernel_repeat),
        driver_mode=case.mode,
        plugin_settings={
            "fixture-erp": {
                "scenario": case.scenario or "valid",
                "lose_response_after_commit": case.fault,
            }
        },
        task_kind=case.kind,
    )
    run = await rt.coordinator.start_run(rt.operator, case.name, rt.scope)
    if run.state is RunState.WAITING_APPROVAL and case.decision:
        pres = await rt.coordinator.pending_approval(rt.operator.tenant_id, run.run_id)
        run = await rt.coordinator.decide(
            actor=rt.operator,
            run_id=run.run_id,
            action_id=pres.action_id,
            action_digest=pres.digest,
            expected_run_revision=pres.run_revision,
            decision=ApprovalDecision(case.decision),
        )
    if run.state is RunState.NEEDS_RECONCILIATION:
        run = await rt.coordinator.reconcile(rt.operator, run.run_id)
    events = await rt.store.list_events(rt.operator.tenant_id, run.run_id)
    blocked = [
        {f["rule_id"] for f in e.payload.get("findings", []) if f["status"] == "FAIL"}
        for e in events
        if e.type == "validation.completed"
    ]
    outcomes = tuple(e.payload["status"] for e in events if e.type == "outcome.reported")
    writes = rt.diagnostics().get("fixture-erp", {}).get("create_calls", -1)
    checks = {
        "final_state": run.state.value == case.expect_state,
        "outcomes": outcomes == case.expect_outcomes,
        "provider_writes": writes == case.writes,
        "blocked_rule": case.expect_blocked_rule is None
        or bool(blocked and case.expect_blocked_rule in blocked[0]),
    }
    return {
        "task": case.task_id,
        "case": case.name,
        "driver_mode": case.mode,
        "scenario": case.scenario or "valid",
        "final_state": run.state.value,
        "reason": run.reason,
        "outcomes": list(outcomes),
        "first_blocked_rules": sorted(blocked[0]) if blocked else [],
        "provider_write_calls": writes,
        "repairs": repair_metrics(events),
        "model_tokens": project_progress(events, []).budgets_used.model_tokens,
        "context": context_columns(events),
        "repeat": repeat_columns(events),
        "checks": checks,
        "passed": all(checks.values()),
    }


def summarize(results: list[dict[str, Any]], out: str) -> tuple[int, str]:
    lines = []
    for r in results:
        mark = "ok " if r["passed"] else "FAIL"
        lines.append(f"{mark} {r['task']} {r['case']}: {r['final_state']}\n")
    passed = sum(r["passed"] for r in results)
    lines.append(f"{passed}/{len(results)} cases passed -> {out}\n")
    # Zero cases is a failure, not a pass (PR-31, ENG-EVID-4).
    return (0 if results and passed == len(results) else 1), "".join(lines)


def build_report(
    rt: Any,
    results: list[dict[str, Any]],
    context_assembler: FeatureMode = FeatureMode.OFF,
    kernel_repeat: FeatureMode = FeatureMode.OFF,
) -> dict[str, Any]:
    """The release report: the case results, the runtime's versions, and the write effects
    its admission accepted on their defaults, which release evidence lists (ADR 0029
    Operations)."""
    proposals = sum(r.get("repairs", {}).get("proposals", 0) for r in results)
    repairs = sum(
        r["repairs"]["failed_validations"] + r["repairs"]["failed_answer_checks"]
        for r in results
        if "repairs" in r
    )
    repeats = [r["repeat"] for r in results if r.get("repeat") is not None]
    return {
        "report": "e-agent-release-matrix-v1",
        "environment": "fixture",
        "note": (
            "Deterministic host-path evidence (scripted driver, fake ERP). "
            "Not live model or live ERP evidence."
        ),
        "context_assembler": context_assembler.value,
        "kernel_repeat": kernel_repeat.value,
        "metrics_note": METRICS_NOTE,
        "repair_rate": round(repairs / proposals, 4) if proposals else None,
        "repeat_disagreements": sum(r["disagreements"] for r in repeats) if repeats else None,
        "versions": rt.versions,
        "defaulted_declarations": defaulted_payload(rt.registry.report.defaulted_declarations),
        "passed": sum(r["passed"] for r in results),
        "total": len(results),
        "cases": results,
    }


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="evals/reports/fixture-release.json")
    parser.add_argument(
        "--context-assembler",
        choices=[FeatureMode.OFF.value, FeatureMode.SHADOW.value],
        default=FeatureMode.OFF.value,
        help="the context_assembler mode the cases run with (shadow adds the context columns)",
    )
    parser.add_argument(
        "--kernel-repeat",
        choices=[FeatureMode.OFF.value, FeatureMode.SHADOW.value],
        default=FeatureMode.OFF.value,
        help="the kernel_repeat mode the cases run with (shadow adds the repeat columns)",
    )
    args = parser.parse_args()
    mode, repeat = FeatureMode(args.context_assembler), FeatureMode(args.kernel_repeat)
    results = [await run_case(c, mode, repeat) for c in CASES]
    rt = await build_runtime(fixture_profile(mode, repeat))
    report = build_report(rt, results, mode, repeat)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    code, text = summarize(results, args.out)
    sys.stdout.write(text)
    return code


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
