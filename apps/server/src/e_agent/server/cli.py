"""Command-line interface. Calls the same application services the API will use."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any

from e_agent.contracts.approval import ApprovalDecision
from e_agent.contracts.run import RunState
from e_agent.kernel.errors import KernelError
from e_agent.sdk.discovery import discover

from .bootstrap import build_runtime
from .profile import load_profile

DEMO_TASK = "Restock product widget-a for demand d-001 by creating a draft purchase order."


def _print(text: str = "") -> None:
    sys.stdout.write(text + "\n")


async def _demo(args: argparse.Namespace) -> int:
    profile = load_profile(args.profile)
    rt = build_runtime(
        profile,
        scenario=args.scenario,
        driver_mode=args.driver_mode,
        lose_response_after_commit=args.fault == "lost-response",
    )
    run = await rt.coordinator.start_run(rt.operator, DEMO_TASK, rt.scope)

    say = (lambda _text="": None) if args.json else _print
    presentation: dict[str, Any] | None = None
    if run.state is RunState.WAITING_APPROVAL:
        pres = await rt.coordinator.pending_approval(rt.operator.tenant_id, run.run_id)
        presentation = pres.model_dump(mode="json")
        say("== Approval required " + "=" * 50)
        say(f"action      {pres.action_id}")
        say(f"capability  {pres.contract_id}  (binding {pres.binding_id})")
        say(f"executes as {pres.credential_subject}")
        for item in pres.material_fields:
            say(f"  {item.path:<16} {item.value}")
        say(f"digest      {pres.digest}")
        decision = _decision(args)
        if decision is None:
            say("No decision given; run left WAITING_APPROVAL (use --approve or --reject).")
        else:
            run = await rt.coordinator.decide(
                actor=rt.operator,
                run_id=run.run_id,
                action_id=pres.action_id,
                action_digest=pres.digest,
                expected_run_revision=pres.run_revision,
                decision=decision,
            )
            if run.state is RunState.WAITING_APPROVAL:  # re-proposed after stale facts
                say("Facts changed; a new proposal needs approval. Re-run the demo.")

    if run.state is RunState.NEEDS_RECONCILIATION and args.reconcile:
        say("== Reconciling (read-only; no write is re-sent) " + "=" * 22)
        run = await rt.coordinator.reconcile(rt.operator, run.run_id)

    events = await rt.store.list_events(rt.operator.tenant_id, run.run_id)
    if args.json:
        payload: dict[str, Any] = {
            "environment": profile.environment,
            "run": run.model_dump(mode="json"),
            "approval_presentation": presentation,
            "events": [e.model_dump(mode="json") for e in events],
            "fixture_erp_create_calls": rt.fake_erp.create_calls if rt.fake_erp else None,
        }
        _print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        _print("== Timeline " + "=" * 59)
        for e in events:
            detail = e.payload.get("to") or e.payload.get("status") or e.payload.get("text") or ""
            _print(f"{e.sequence:>3} {e.type:<26} {detail}")
        _print(f"Final state: {run.state} ({run.reason or ''}) [environment={profile.environment}]")
    return 0


def _decision(args: argparse.Namespace) -> ApprovalDecision | None:
    if args.approve:
        return ApprovalDecision.APPROVED
    if args.reject:
        return ApprovalDecision.REJECTED
    if not args.json and sys.stdin.isatty():
        answer = input("Approve this exact action? [y/N] ").strip().lower()
        return ApprovalDecision.APPROVED if answer == "y" else ApprovalDecision.REJECTED
    return None


def _plugins(args: argparse.Namespace) -> int:
    profile = load_profile(args.profile)
    for plugin in discover():
        m = plugin.manifest
        state = "enabled" if m.plugin_id in profile.enabled_plugins else "disabled (not imported)"
        _print(f"{m.plugin_id} {m.version} [{m.kind}] from {plugin.distribution}: {state}")
        for cap in m.provides_capabilities:
            _print(f"    {cap.effect:<5} {cap.contract_id}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="e-agent", description="e-agent CLI")
    parser.add_argument("--profile", help="profile JSON (default: packaged fixture profile)")
    sub = parser.add_subparsers(dest="command", required=True)
    demo = sub.add_parser("demo", help="run the fixture procurement walking skeleton")
    demo.add_argument("--scenario", choices=["valid", "zero-shortage", "over-budget"])
    demo.add_argument("--driver-mode", choices=["valid", "invalid-then-repair", "always-invalid"])
    demo.add_argument("--fault", choices=["lost-response"])
    group = demo.add_mutually_exclusive_group()
    group.add_argument("--approve", action="store_true", help="operator approves the action")
    group.add_argument("--reject", action="store_true", help="operator rejects the action")
    demo.add_argument("--reconcile", action="store_true", help="run read-only reconciliation")
    demo.add_argument("--json", action="store_true")
    sub.add_parser("plugins", help="list discovered plugins (metadata only)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "demo":
            return asyncio.run(_demo(args))
        return _plugins(args)
    except KernelError as exc:
        sys.stderr.write(f"error {exc.code}: {exc.safe_message}\n")
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
