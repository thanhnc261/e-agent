"""Release qualification task matrix (I14) on the fixture environment.

Runs every ERP task through the real kernel, SHACL engine, policy, approval,
ledger and verifiers with the scripted driver and fake ERP, including negative
cases, and writes a JSON report. It is deterministic evidence of the *host*
safety path only: no model and no live ERP are involved (environment=fixture).
Live Odoo evidence comes from tests/integration/test_odoo_live*.py; live model
evidence from scripts/qualify_model.py (ADR 0010).

    uv run python scripts/release_report.py --out evals/reports/fixture-release.json

Each case also reports its reason code, and the report counts the cases by how they ended
(``ends``): a ``GROUNDED`` end (ADR 0033 §3) is its own category, never ``verified``
(PR-19). Each case also reports its repairs and token use, and, with ``--context-assembler shadow``,
the context columns from the run's ``context.compared`` events (ADR 0032 §7, Task 3d.3), and,
with ``--kernel-repeat shadow``, the repeat columns and disagreement count from its
``repeat.compared`` events (ADR 0031 §5, Task 3d.6), and, with ``--grounded-answers shadow``,
the grounding columns from its ``grounding.compared`` events: citation and rationale counts
(ADR 0033 §5, Task 3e.4). A case run with ``context_assembler: on`` (the context ablation,
``scripts/context_ablation.py``, Task 3f.2) has the ``context.assembled`` columns instead.
The Phase 3 ``off`` baseline is this report recorded with the
toggles ``off``:

    uv run python scripts/release_report.py --out evals/reports/phase3-baseline.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import Counter
from dataclasses import dataclass
from typing import Any

from e_agent.contracts.approval import ApprovalDecision
from e_agent.contracts.events import RunEvent, RunEventType
from e_agent.contracts.features import FeatureMode
from e_agent.contracts.run import ReasonCode, RunState
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
    "repairs.rate is repairs / attempts: numerator is the kernel's repair counter; "
    "denominator is accepted + repaired + terminally refused attempts, so the rate is at most"
    " 1. repairs is cont.repairs read from the run's stored continuation at run end, the "
    "refusals the kernel returned to the driver within its repair budget, never derived from "
    "the events ('unknown' when the run stored none). accepted counts the kernel's success "
    "records: a first-step driver proposal its validation left VALIDATED and no verification "
    "failed, an answer that verified, and a GROUNDED end. terminal_refusals is 1 for a run "
    "that FAILED validation_failed or verification_failed; policy_denied is 1 for a run that "
    "FAILED policy_denied, and it is neither a repair nor a terminal refusal (D3-31, review "
    "3f.2 R2). model_tokens is what the run's events record of the driver's token use "
    "('unknown' when they record none, never 0). context is null when context_assembler is "
    "off. In shadow it holds the context.compared columns: pack_tokens and unbounded_tokens "
    "are the kernel estimator's sums over the run's driver turns, not model-reported tokens. "
    "In on it holds the context.assembled columns: the packs built (one per driver call, "
    "acknowledgement turns included), their estimated tokens and drops, and the calls that "
    "fell back to the driver's history. repeat is null unless kernel_repeat is shadow; a "
    "disagreement is a write proposal the repeat rule would have short-circuited whose "
    "validation then gave other findings. grounding is null unless grounded_answers is "
    "shadow; it sums the citation and rationale-ref counts of the run's grounding.compared "
    "events, and grounding_unresolved is every unresolved or mismatched citation and "
    "unresolved rationale ref."
)


def fixture_profile(
    context_assembler: FeatureMode = FeatureMode.OFF,
    kernel_repeat: FeatureMode = FeatureMode.OFF,
    grounded_answers: FeatureMode = FeatureMode.OFF,
) -> Any:
    profile = load_profile(fixture_profile_path())
    features = profile.features.model_copy(
        update={
            "context_assembler": context_assembler,
            "kernel_repeat": kernel_repeat,
            "grounded_answers": grounded_answers,
        }
    )
    return profile.model_copy(update={"features": features})


TERMINAL_CODES = frozenset({ReasonCode.VALIDATION_FAILED, ReasonCode.VERIFICATION_FAILED})
"""A run that FAILED with one of these codes ended at a refusal the kernel did not return:
one terminal refusal. ``policy_denied`` is reported apart, never a repair or a terminal
refusal."""


async def kernel_repairs(store: Any, tenant_id: str, run_id: str) -> int | None:
    """The kernel's own repair counter, ``cont.repairs``, from the run's stored continuation
    (``RunStore.load_continuation``); None when the run stored none. The terminal transition
    stores the continuation in its own write (``kernel/transitions.py``), so the value is
    current at run end."""
    stored = await store.load_continuation(tenant_id, run_id)
    if stored is None:
        return None
    return int(stored[0]["data"]["repairs"])


def repair_metrics(events: list[RunEvent], repairs: int | None) -> dict[str, Any]:
    """Attempts, repairs and the repair rate (METRICS_NOTE, D3-31).

    The numerator is the kernel's repair counter (``repairs``, from `kernel_repairs`); it is
    not derived from the events. The denominator is accepted + repaired + terminally refused
    attempts, so the rate is at most 1. ``accepted`` counts the kernel's success records:
    a first-step driver proposal whose validation left its action ``VALIDATED`` (the
    ``action_state`` key, ADR 0031 §3) and whose write no verification failed (a later plan
    step is kernel-made, and a dispatch STALE or policy denial leaves the action
    ``BLOCKED``), an answer that verified, and a ``GROUNDED`` end. ``terminal_refusals`` is
    one when the run FAILED with a code in `TERMINAL_CODES`; ``policy_denied`` is one when
    it FAILED ``policy_denied``."""
    created = [e for e in events if e.type is RunEventType.PROPOSAL_CREATED]
    answers = {e.action_id for e in created if e.payload.get("kind") == "answer"}
    validated: dict[str | None, Any] = {}
    failed_writes: set[str | None] = set()
    verified_answers = 0
    for e in events:
        if e.type is RunEventType.VALIDATION_COMPLETED and e.action_id is not None:
            validated[e.action_id] = e.payload.get("action_state")  # the latest one wins
        elif e.type is RunEventType.OUTCOME_REPORTED and e.action_id in answers:
            verified_answers += e.payload.get("status") == "VERIFIED"
        elif e.type is RunEventType.OUTCOME_REPORTED and e.payload.get("status") == "FAILED":
            failed_writes.add(e.action_id)
    accepted_writes = sum(
        e.action_id not in answers
        and (e.payload.get("step_index") or 0) == 0
        and validated.get(e.action_id) == "VALIDATED"
        and e.action_id not in failed_writes
        for e in created
    )
    ends = [e.payload for e in events if e.type is RunEventType.RUN_STATE_CHANGED]
    final = ends[-1] if ends else {}
    code = final.get("reason_code")
    failed = final.get("to") == RunState.FAILED
    grounded = int(code == ReasonCode.GROUNDED)
    terminal = int(failed and code in TERMINAL_CODES)
    accepted = accepted_writes + verified_answers + grounded
    attempts = None if repairs is None else repairs + accepted + terminal
    return {
        "attempts": "unknown" if attempts is None else attempts,
        "repairs": "unknown" if repairs is None else repairs,
        "accepted": accepted,
        "terminal_refusals": terminal,
        "policy_denied": int(failed and code == ReasonCode.POLICY_DENIED),
        "rate": round(repairs / attempts, 4) if repairs is not None and attempts else None,
    }


def end_class(result: dict[str, Any]) -> str:
    """How a case ended, for the ``ends`` counts. ``grounded`` for a ``GROUNDED`` end, whose
    citations resolved against the run's own evidence and which no verifier read back (ADR
    0033 §3), so it is never ``verified`` (PR-19); ``verified`` for a success with a VERIFIED
    outcome report; otherwise the final state."""
    if result.get("reason_code") == ReasonCode.GROUNDED:
        return "grounded"
    if result.get("final_state") == "SUCCEEDED" and "VERIFIED" in result.get("outcomes", ()):
        return "verified"
    return str(result.get("final_state", "unknown")).lower()


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


def assembled_columns(events: list[RunEvent]) -> dict[str, Any] | None:
    """The ``context.assembled`` columns of a ``context_assembler: on`` run (ADR 0032 §7,
    Task 3d.5); None when the run recorded none. ``on`` builds one pack per turn, so there is
    no unbounded pack and no driver token delta to compare: only the packs built (one per
    driver call, acknowledgement turns included), their estimates and drops, and the calls
    that fell back to the driver's history. Counts only (PR-26)."""
    assembled = [e.payload for e in events if e.type is RunEventType.CONTEXT_ASSEMBLED]
    failed = [e for e in events if e.type is RunEventType.CONTEXT_FAILED]
    if not assembled and not failed:
        return None
    packs = [p for p in assembled if p.get("fallback") is not True]
    return {
        "packs": len(packs),  # one per driver call, the post-write acknowledgement's included
        "fallbacks": len(assembled) - len(packs),
        "failures": len(failed),
        "pack_tokens": sum(sum(p["pack_tokens"].values()) for p in packs),
        "dropped": sum(sum(p["dropped"].values()) for p in packs),
        "masked": sum(p["drop_reasons"]["class_route"] for p in packs),
        "omitted_observations": sum(len(p["omitted_evidence"]) for p in packs),
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


def _summed(counts: list[dict[str, Any]], keys: tuple[str, ...]) -> dict[str, int]:
    return {key: sum(int(c.get(key, 0)) for c in counts) for key in keys}


def grounding_columns(events: list[RunEvent]) -> dict[str, Any] | None:
    """The ``grounding.compared`` columns of a ``grounded_answers: shadow`` run; None when the
    run recorded none. Counts only, never a value or model text (PR-26)."""
    compared = [e.payload for e in events if e.type is RunEventType.GROUNDING_COMPARED]
    failed = [e for e in events if e.type is RunEventType.GROUNDING_SHADOW_FAILED]
    if not compared and not failed:
        return None
    refs = ("cited", "resolved", "unresolved")
    return {
        "compared": len(compared),
        "shadow_failures": len(failed),
        "citations": _summed([p["citations"] for p in compared], (*refs, "mismatched")),
        "rationale_evidence": _summed([p["rationale"]["evidence"] for p in compared], refs),
        "rationale_rules": _summed([p["rationale"]["rules"] for p in compared], refs),
    }


def unresolved_refs(grounding: dict[str, Any]) -> int:
    """A case's unresolved or mismatched citations and unresolved rationale refs."""
    citations = grounding["citations"]
    return (
        citations["unresolved"]
        + citations["mismatched"]
        + grounding["rationale_evidence"]["unresolved"]
        + grounding["rationale_rules"]["unresolved"]
    )


async def run_case(
    case: Case,
    context_assembler: FeatureMode = FeatureMode.OFF,
    kernel_repeat: FeatureMode = FeatureMode.OFF,
    grounded_answers: FeatureMode = FeatureMode.OFF,
) -> dict[str, Any]:
    rt = await build_runtime(
        fixture_profile(context_assembler, kernel_repeat, grounded_answers),
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
        "reason_code": run.reason_code.value if run.reason_code else None,
        "outcomes": list(outcomes),
        "first_blocked_rules": sorted(blocked[0]) if blocked else [],
        "provider_write_calls": writes,
        "repairs": repair_metrics(
            events, await kernel_repairs(rt.store, rt.operator.tenant_id, run.run_id)
        ),
        "model_tokens": project_progress(events, []).budgets_used.model_tokens,
        "context": context_columns(events) or assembled_columns(events),
        "repeat": repeat_columns(events),
        "grounding": grounding_columns(events),
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


def overall_rate(results: list[dict[str, Any]]) -> float | None:
    """repairs / attempts summed over the cases; None when there are none, or when a case's
    counter is 'unknown' (it stored no continuation): an unknown is never read as 0."""
    counted = [r["repairs"] for r in results if "repairs" in r]
    if any(c["repairs"] == "unknown" for c in counted):
        return None
    attempts = sum(c["attempts"] for c in counted)
    return round(sum(c["repairs"] for c in counted) / attempts, 4) if attempts else None


def build_report(
    rt: Any,
    results: list[dict[str, Any]],
    context_assembler: FeatureMode = FeatureMode.OFF,
    kernel_repeat: FeatureMode = FeatureMode.OFF,
    grounded_answers: FeatureMode = FeatureMode.OFF,
) -> dict[str, Any]:
    """The release report: the case results, the runtime's versions, and the write effects
    its admission accepted on their defaults, which release evidence lists (ADR 0029
    Operations)."""
    repeats = [r["repeat"] for r in results if r.get("repeat") is not None]
    grounding = [r["grounding"] for r in results if r.get("grounding") is not None]
    return {
        "report": "e-agent-release-matrix-v1",
        "environment": "fixture",
        "note": (
            "Deterministic host-path evidence (scripted driver, fake ERP). "
            "Not live model or live ERP evidence."
        ),
        "context_assembler": context_assembler.value,
        "kernel_repeat": kernel_repeat.value,
        "grounded_answers": grounded_answers.value,
        "metrics_note": METRICS_NOTE,
        "repair_rate": overall_rate(results),
        "repeat_disagreements": sum(r["disagreements"] for r in repeats) if repeats else None,
        "grounding_unresolved": sum(map(unresolved_refs, grounding)) if grounding else None,
        "ends": dict(sorted(Counter(end_class(r) for r in results).items())),
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
    parser.add_argument(
        "--grounded-answers",
        choices=[FeatureMode.OFF.value, FeatureMode.SHADOW.value],
        default=FeatureMode.OFF.value,
        help="the grounded_answers mode the cases run with (shadow adds the grounding columns)",
    )
    args = parser.parse_args()
    mode, repeat = FeatureMode(args.context_assembler), FeatureMode(args.kernel_repeat)
    grounded = FeatureMode(args.grounded_answers)
    results = [await run_case(c, mode, repeat, grounded) for c in CASES]
    rt = await build_runtime(fixture_profile(mode, repeat, grounded))
    report = build_report(rt, results, mode, repeat, grounded)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    code, text = summarize(results, args.out)
    sys.stdout.write(text)
    return code


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
