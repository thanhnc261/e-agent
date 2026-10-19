"""Context ablation, first run: chat history against typed state (research 03 §8, Task 3f.2).

Runs the release-report fixture corpus (``scripts/release_report.py`` ``CASES``) twice, with
``features.context_assembler`` ``off`` (arm A: the driver's own chat history) and ``on``
(arm B: the kernel's typed context pack, ADR 0032), and writes a paired report. It reuses
release_report's runner and metrics; nothing here measures a case on its own.

    uv run python scripts/context_ablation.py --out evals/reports/phase3-context-ablation.json

This is fixture evidence: the scripted driver and the fake ERP, no model and no live ERP
(PR-29). The scripted driver proposes the same thing whatever its context, so equal outcomes
show that the ``on`` path keeps the host safety path, not that typed state helps a model.
The design, the hypotheses and what this run cannot show are in
``evals/ablation/context-history-vs-typed.md``. The report holds counts and the kernel's
token estimates only: no run, action or evidence id, no pack digest and no timestamp, so two
runs give byte-identical output.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import sys
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from e_agent.contracts.features import FeatureMode
from e_agent.server.bootstrap import build_runtime

_RR_PATH = Path(__file__).resolve().parent / "release_report.py"
_spec = importlib.util.spec_from_file_location("release_report_for_ablation", _RR_PATH)
assert _spec is not None
assert _spec.loader is not None
rr = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = rr  # dataclasses resolve annotations through sys.modules
_spec.loader.exec_module(rr)

DESIGN = "evals/ablation/context-history-vs-typed.md"
ARMS = {"off": FeatureMode.OFF, "on": FeatureMode.ON}
"""Arm A (history) and arm B (typed state). The other Phase 3 toggles stay ``off``."""

NOTE = (
    "Fixture evidence (scripted driver, fake ERP): the release-report corpus run with "
    "context_assembler off and on. Not live model or live ERP evidence, and no qualified "
    "model took part. The scripted driver proposes the same thing whatever its context, so "
    "equal outcomes show the on path keeps the host safety path, not that typed state helps "
    "a model. The report makes no claim beyond this corpus."
)
COST_NOTE = (
    "pack_tokens_estimate is the kernel estimator's sum over a run's driver turns "
    "(estimate_tokens, ADR 0032), an estimate, not model-reported tokens. The off arm "
    "records no pack, so its estimate is 'unknown', never 0; model_tokens is 'unknown' in "
    "both arms because the scripted driver reports no token use. This run cannot compare "
    "token cost between the arms."
)
DROP_NOTE = (
    "dropped, masked and omitted_observations count the on arm's drop log "
    "(context.assembled). The off arm keeps no drop log, so they are 'unknown' there."
)
OUTCOME_KEYS = ("final_state", "reason_code", "outcomes", "provider_write_calls")


async def run_arms(cases: Sequence[Any]) -> dict[str, list[dict[str, Any]]]:
    """Each case once per arm, in corpus order, through release_report's `run_case`."""
    return {arm: [await rr.run_case(case, mode) for case in cases] for arm, mode in ARMS.items()}


def _sum(values: list[Any]) -> int | str:
    return "unknown" if not values or "unknown" in values else sum(values)


def arm_summary(arm: str, results: list[dict[str, Any]]) -> dict[str, Any]:
    """An arm's totals, from release_report's per-case metrics."""
    repairs = [r["repairs"] for r in results]
    proposals = sum(r["proposals"] for r in repairs)
    sent_back = sum(r["validation_repairs"] + r["answer_repairs"] for r in repairs)
    contexts = [r["context"] for r in results if r["context"] is not None]
    on = ARMS[arm] is FeatureMode.ON

    def context(key: str) -> int | str:
        return _sum([c[key] for c in contexts]) if on else "unknown"

    return {
        "context_assembler": ARMS[arm].value,
        "rendering": "pack" if on else "history",
        "cases": len(results),
        "passed": sum(r["passed"] for r in results),
        "ends": dict(sorted(Counter(rr.end_class(r) for r in results).items())),
        "proposals": proposals,
        "validation_repairs": sum(r["validation_repairs"] for r in repairs),
        "answer_repairs": sum(r["answer_repairs"] for r in repairs),
        "terminal_refusals": sum(r["terminal_refusals"] for r in repairs),
        "repair_rate": round(sent_back / proposals, 4) if proposals else None,
        "provider_write_calls": sum(r["provider_write_calls"] for r in results),
        "model_tokens": _sum([r["model_tokens"] for r in results]),
        "context_turns": context("turns"),
        "fallbacks": context("fallbacks"),
        "context_failures": context("failures"),
        "pack_tokens_estimate": context("pack_tokens"),
        "dropped": context("dropped"),
        "masked": context("masked"),
        "omitted_observations": context("omitted_observations"),
    }


def paired_case(off: dict[str, Any], on: dict[str, Any]) -> dict[str, Any]:
    """One corpus case in both arms: its outcome, repairs and the on arm's context columns."""

    def arm(result: dict[str, Any]) -> dict[str, Any]:
        return {
            **{key: result[key] for key in OUTCOME_KEYS},
            "end": rr.end_class(result),
            "passed": result["passed"],
            "repairs": result["repairs"],
            "context": result["context"],
        }

    same = all(off[key] == on[key] for key in OUTCOME_KEYS) and off["repairs"] == on["repairs"]
    return {
        "task": off["task"],
        "case": off["case"],
        "driver_mode": off["driver_mode"],
        "scenario": off["scenario"],
        "same_outcome_and_repairs": same,
        "off": arm(off),
        "on": arm(on),
    }


async def build_ablation(arms: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    """The ablation report: both arms' totals, the paired cases and the runtime's versions."""
    off, on = arms["off"], arms["on"]
    if len(off) != len(on):
        raise ValueError("the arms ran different case counts")
    pairs = [paired_case(a, b) for a, b in zip(off, on, strict=True)]
    rt = await build_runtime(rr.fixture_profile(FeatureMode.ON))
    return {
        "report": "e-agent-context-ablation-v1",
        "environment": "fixture",
        "evidence": "fixture: scripted driver and fake ERP, no model",
        "note": NOTE,
        "design": DESIGN,
        "corpus": "scripts/release_report.py CASES",
        "metrics_note": rr.METRICS_NOTE,
        "token_note": COST_NOTE,
        "drop_note": DROP_NOTE,
        "other_toggles": {"kernel_repeat": "off", "grounded_answers": "off"},
        "arms": {name: arm_summary(name, results) for name, results in arms.items()},
        "paired": {
            "cases": len(pairs),
            "same_outcome_and_repairs": sum(p["same_outcome_and_repairs"] for p in pairs),
            "differing": [p["case"] for p in pairs if not p["same_outcome_and_repairs"]],
        },
        "versions": rt.versions,
        "cases": pairs,
    }


def exit_code(report: dict[str, Any]) -> int:
    """0 only when both arms ran at least one case and every case passed its checks; zero
    cases is a failure, not a pass (PR-31, ENG-EVID-4)."""
    arms = report["arms"].values()
    return 0 if all(a["cases"] > 0 and a["passed"] == a["cases"] for a in arms) else 1


def dumps(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, ensure_ascii=False) + "\n"


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="evals/reports/phase3-context-ablation.json")
    args = parser.parse_args()
    report = await build_ablation(await run_arms(rr.CASES))
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(dumps(report))
    for name, arm in report["arms"].items():
        sys.stdout.write(
            f"{name}: {arm['passed']}/{arm['cases']} cases passed, repair rate "
            f"{arm['repair_rate']}, pack tokens (estimate) {arm['pack_tokens_estimate']}\n"
        )
    paired = report["paired"]
    sys.stdout.write(
        f"{paired['same_outcome_and_repairs']}/{paired['cases']} cases with the same outcome "
        f"and repairs in both arms -> {args.out}\n"
    )
    return exit_code(report)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
