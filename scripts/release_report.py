"""Release qualification task matrix (I14) on the fixture environment.

Runs every ERP task through the real kernel, SHACL engine, policy, approval,
ledger and verifiers with the scripted driver and fake ERP, including negative
cases, and writes a JSON report. It is deterministic evidence of the *host*
safety path only: no model and no live ERP are involved (environment=fixture).
Live Odoo evidence comes from tests/integration/test_odoo_live*.py; live model
evidence from scripts/qualify_model.py (ADR 0010).

    uv run python scripts/release_report.py --out evals/reports/fixture-release.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass
from typing import Any

from e_agent.contracts.approval import ApprovalDecision
from e_agent.contracts.run import RunState
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


async def run_case(case: Case) -> dict[str, Any]:
    rt = await build_runtime(
        load_profile(),
        scenario=case.scenario,
        driver_mode=case.mode,
        lose_response_after_commit=case.fault,
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
    writes = rt.fake_erp.create_calls if rt.fake_erp else -1
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
        "checks": checks,
        "passed": all(checks.values()),
    }


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="evals/reports/fixture-release.json")
    args = parser.parse_args()
    results = [await run_case(c) for c in CASES]
    rt = await build_runtime(load_profile())
    report = {
        "report": "e-agent-release-matrix-v1",
        "environment": "fixture",
        "note": (
            "Deterministic host-path evidence (scripted driver, fake ERP). "
            "Not live model or live ERP evidence."
        ),
        "versions": rt.versions,
        "passed": sum(r["passed"] for r in results),
        "total": len(results),
        "cases": results,
    }
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    for r in results:
        mark = "ok " if r["passed"] else "FAIL"
        sys.stdout.write(f"{mark} {r['task']} {r['case']}: {r['final_state']}\n")
    sys.stdout.write(f"{report['passed']}/{report['total']} cases passed -> {args.out}\n")
    return 0 if report["passed"] == report["total"] else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
