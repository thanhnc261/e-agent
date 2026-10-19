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
from e_agent.contracts.context import Budgets
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
    "repairs.rate is repairs / attempts. A repair is exactly what the kernel's cont.repairs "
    "counts: a refusal it returned to the driver within max_validation_repairs, that is a "
    "failed proposal validation, a first-step dispatch STALE it returned, a plain-text "
    "KERNEL-VERIFICATION turn, a KERNEL-* refusal of an attempt that made no action, or a "
    "failed answer verification (repairs.kinds). A refusal that ended the run is in "
    "terminal_refusals, never in the rate: one under a FAILED record with reason code "
    "validation_failed, verification_failed or policy_denied, as the kernel's budget test or "
    "policy denial decides it. A finish check (KERNEL-ACCEPTANCE) and a later plan step are "
    "not refusals of an attempt. attempts is one per driver proposal.created plus one per "
    "counted refusal with no action id, so the rate is at most 1 (D3-31, review 3f.2 R1). "
    "model_tokens is what the run's events record of the driver's token use ('unknown' when "
    "they record none, never 0). context is null when context_assembler is off. In shadow it "
    "holds the context.compared columns: pack_tokens and unbounded_tokens are the kernel "
    "estimator's sums over the run's driver turns, not model-reported tokens. In on it holds "
    "the context.assembled columns: the packs built (one per driver call, acknowledgement "
    "turns included), their estimated tokens and drops, and the calls that fell back to the "
    "driver's history. repeat is null unless kernel_repeat is shadow; a disagreement is a "
    "write proposal the repeat rule would have short-circuited whose validation then gave "
    "other findings. grounding is null unless grounded_answers is shadow; it sums the "
    "citation and rationale-ref counts of the run's grounding.compared events, and "
    "grounding_unresolved is every unresolved or mismatched citation and unresolved rationale"
    " ref."
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


NOT_REFUSALS = frozenset(
    {
        "KERNEL-PLAN-STEP-CHANGED",  # a later plan step stopped before its action exists
        "KERNEL-PLAN-LINEAGE",
        "KERNEL-ACCEPTANCE",  # the ACCEPTANCE_UNMET ending, never returned to the driver
    }
)
"""Kernel findings whose no-action-id ``validation.completed`` is no refusal of an attempt."""

PLAIN_TEXT = "KERNEL-VERIFICATION"
"""A plain-text turn's repair (``kernel/run_loop.py``). Past the budget the kernel fails the
run without writing it, so every one that is written went back to the driver."""
NO_VERIFIER = "KERNEL-VERIFIER"
"""An answer without a verifier: written with the run's FAILED record, never returned."""

TERMINAL_CODES = {
    "validation": frozenset({ReasonCode.VALIDATION_FAILED, ReasonCode.POLICY_DENIED}),
    "no_action": frozenset({ReasonCode.VALIDATION_FAILED, ReasonCode.POLICY_DENIED}),
    "answer": frozenset({ReasonCode.VERIFICATION_FAILED}),
    "no_verifier": frozenset({ReasonCode.VERIFICATION_FAILED}),
}
"""The FAILED reason codes that can end the run at a refusal of each kind. A refusal is
terminal only when the run's FAILED record carries one of them (review R1-1): any other
ending (``budget_exhausted``, a timeout, a refused route) came after a returned refusal."""

REPAIR_KINDS = ("validation", "no_action", "plain_text", "stale", "answer")


def _refusal_kind(event: RunEvent, later_steps: set[str], answers: set[str]) -> str | None:
    """The kind of kernel refusal ``event`` records, or None when it records none.

    - ``validation``: a failed validation of a driver proposal (``kernel/proposals.py``);
    - ``stale``: a first-step dispatch revalidation that found the facts stale
      (``kernel/dispatch.py``); a later plan step's is no refusal of a driver attempt;
    - ``no_action``: a kernel finding on an attempt that made no action (``KERNEL-ARGS``,
      ``KERNEL-CONNECTION``, ``KERNEL-GROUNDED-ANSWER`` …, ``_repair_finding``), or a plan
      the policy denied;
    - ``plain_text``: the ``KERNEL-VERIFICATION`` turn; ``no_verifier``: ``KERNEL-VERIFIER``;
    - ``answer``: a failed verification of a driver answer (``kernel/grounding.py``).
    """
    if event.type is RunEventType.OUTCOME_REPORTED:
        failed = event.payload.get("status") == "FAILED"
        return "answer" if failed and event.action_id in answers else None
    if event.type is not RunEventType.VALIDATION_COMPLETED:
        return None
    status = event.payload.get("status")
    if status in (None, "PASS") or event.action_id in later_steps:
        return None
    if status == "STALE":
        return "stale" if event.action_id is not None else None
    if event.action_id is not None:
        return "validation"
    findings = event.payload.get("findings")
    rule_ids = {f.get("rule_id") for f in findings if isinstance(f, dict)} if findings else set()
    if rule_ids & NOT_REFUSALS:
        return None
    if PLAIN_TEXT in rule_ids:
        return "plain_text"
    return "no_verifier" if NO_VERIFIER in rule_ids else "no_action"


def _returned_stale(events: list[RunEvent], index: int) -> bool:
    """Whether the STALE refusal at ``index`` went back to the driver: the kernel's next run
    state change is to RUNNING with reason code ``stale`` (``kernel/dispatch.py``). A STALE
    past the budget, or one that ends a plan, fails the run instead."""
    changes = (e for e in events[index + 1 :] if e.type is RunEventType.RUN_STATE_CHANGED)
    change = next(changes, None)
    return (
        change is not None
        and change.payload.get("to") == RunState.RUNNING
        and change.payload.get("reason_code") == ReasonCode.STALE
    )


def _failed_code(events: list[RunEvent]) -> str | None:
    """The reason code of the run's FAILED record, or None when the run did not fail."""
    failed = [
        e
        for e in events
        if e.type is RunEventType.RUN_STATE_CHANGED and e.payload.get("to") == RunState.FAILED
    ]
    return failed[-1].payload.get("reason_code") if failed else None


def repair_metrics(
    events: list[RunEvent], max_repairs: int = Budgets().max_validation_repairs
) -> dict[str, Any]:
    """Attempts, the kernel's repairs of them, and the repair rate (METRICS_NOTE, D3-31).

    A repair is exactly what the kernel's ``cont.repairs`` counts: a refusal returned to
    the driver within ``max_validation_repairs`` (``max_repairs``, the run's budget). That is
    a ``validation``, ``no_action``, ``plain_text``, ``answer`` or returned ``stale`` refusal
    (`_refusal_kind`). A refusal is terminal, counted in ``terminal_refusals`` and never as a
    repair, when the run's FAILED record has a code `TERMINAL_CODES` allows for its kind and
    either the policy denied it (the run's last ``validation.completed`` under
    ``policy_denied``, ``kernel/proposals.py``), it is ``KERNEL-VERIFIER``, or the repairs
    before it had used the budget, which is the kernel's own test.

    The denominator counts one attempt per driver ``proposal.created`` (a later plan step is
    kernel-made, so it is none) and one per counted refusal with no action id (``no_action``,
    ``plain_text``, ``no_verifier``). Every repair maps to its own attempt: a validation,
    answer or STALE refusal to its proposal, a no-action refusal to itself. A STALE refusal
    follows a passing validation, which no other refusal of that proposal can, and blocks
    the action, so it can repeat for none. The rate is therefore at most 1."""
    created = [e for e in events if e.type is RunEventType.PROPOSAL_CREATED]
    later_steps = {
        e.action_id
        for e in created
        if e.action_id is not None and (e.payload.get("step_index") or 0) > 0
    }
    answers = {e.action_id for e in created if e.payload.get("kind") == "answer"}
    proposals = sum(e.action_id not in later_steps for e in created)
    code = _failed_code(events)
    validations = [i for i, e in enumerate(events) if e.type is RunEventType.VALIDATION_COMPLETED]
    denied_at = validations[-1] if validations and code == ReasonCode.POLICY_DENIED else None
    kinds = dict.fromkeys(REPAIR_KINDS, 0)
    no_action = terminal = 0
    for index, e in enumerate(events):
        if index == denied_at:  # a policy denial is terminal, whatever its status
            terminal += 1
            no_action += e.action_id is None
            continue
        kind = _refusal_kind(e, later_steps, answers)
        if kind is None or (kind == "stale" and not _returned_stale(events, index)):
            continue
        no_action += kind in ("no_action", "plain_text", "no_verifier")
        allowed = code in TERMINAL_CODES.get(kind, frozenset())
        if allowed and (kind == "no_verifier" or sum(kinds.values()) >= max_repairs):
            terminal += 1
        elif kind != "no_verifier":
            kinds[kind] += 1
    repairs = sum(kinds.values())
    attempts = proposals + no_action
    return {
        "attempts": attempts,
        "repairs": repairs,
        "terminal_refusals": terminal,
        "rate": round(repairs / attempts, 4) if attempts else None,
        "kinds": kinds,
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
    profile = fixture_profile(context_assembler, kernel_repeat, grounded_answers)
    rt = await build_runtime(
        profile,
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
        # the profile's budget: execution_ir `on` may narrow it per task; the corpus runs `off`
        "repairs": repair_metrics(events, profile.budgets.max_validation_repairs),
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
    attempts = sum(r.get("repairs", {}).get("attempts", 0) for r in results)
    repairs = sum(r["repairs"]["repairs"] for r in results if "repairs" in r)
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
        "repair_rate": round(repairs / attempts, 4) if attempts else None,
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
