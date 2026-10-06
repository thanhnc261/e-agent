"""Command-line interface. Calls the same application services the API will use."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any

from e_agent.contracts.approval import ApprovalDecision
from e_agent.contracts.run import RunState
from e_agent.erp.testing.scenarios import SCENARIOS
from e_agent.erp.testing.scripted_tasks import TASK_KINDS
from e_agent.kernel.errors import KernelError
from e_agent.kernel.evidence import build_evidence
from e_agent.sdk.discovery import discover

from .bootstrap import build_runtime, open_store
from .profile import load_profile

DEMO_TASK = "Restock product widget-a for demand d-001 by creating a draft purchase order."


def _print(text: str = "") -> None:
    sys.stdout.write(text + "\n")


async def _demo(args: argparse.Namespace) -> int:
    profile = load_profile(args.profile)
    rt = await build_runtime(
        profile,
        scenario=args.scenario,
        driver_mode=args.driver_mode,
        lose_response_after_commit=args.fault == "lost-response",
        task_kind=args.task,
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
    if args.evidence_out:
        bundle = await build_evidence(
            rt.store,
            rt.operator.tenant_id,
            run.run_id,
            environment=profile.environment,
            versions=rt.versions,
        )
        _write_private(args.evidence_out, json.dumps(bundle, ensure_ascii=False, indent=2))
    await _close(rt.store)
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


async def _migrate(args: argparse.Namespace) -> int:
    profile = load_profile(args.profile)
    if profile.store.kind != "postgres":
        _print("profile uses the in-memory store; nothing to migrate")
        return 0
    store = await open_store(profile)  # applies migrations
    await store.close()
    _print("migrations applied")
    return 0


async def _recover(args: argparse.Namespace) -> int:
    profile = load_profile(args.profile)
    rt = await build_runtime(profile)
    try:
        for run in await rt.coordinator.recover():
            _print(f"{run.run_id}: {run.state} ({run.reason or ''})")
    finally:
        await _close(rt.store)
    return 0


async def _secret(args: argparse.Namespace) -> int:
    """Write-only secret management: values come from stdin and are never echoed."""
    from e_agent.adapters.secretstore_local import LocalSecretStore
    from e_agent.sdk.auth import Secret

    store = LocalSecretStore.from_environment()
    if args.action == "delete":
        await store.delete(args.ref)
        _print(f"deleted {args.ref}")
        return 0
    value = sys.stdin.readline().rstrip("\n")
    if not value:
        sys.stderr.write("no value on stdin\n")
        return 2
    await store.put(args.ref, Secret(value))
    _print(f"stored {args.ref} (value not shown)")
    return 0


def _write_private(path: str, text: str) -> None:
    """Evidence is authorized data: write it with owner-only permissions."""
    import os

    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(text)


async def _evidence(args: argparse.Namespace) -> int:
    profile = load_profile(args.profile)
    rt = await build_runtime(profile)
    try:
        bundle = await build_evidence(
            rt.store,
            rt.operator.tenant_id,
            args.run_id,
            environment=profile.environment,
            versions=rt.versions,
        )
    finally:
        await _close(rt.store)
    text = json.dumps(bundle, ensure_ascii=False, indent=2)
    if args.out:
        _write_private(args.out, text)
    else:
        _print(text)
    return 0


async def _close(store: Any) -> None:
    close = getattr(store, "close", None)
    if close is not None:
        await close()


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
    demo.add_argument("--scenario", choices=sorted(SCENARIOS))
    demo.add_argument(
        "--driver-mode",
        choices=["valid", "invalid-then-repair", "always-invalid", "wrong-answer-then-correct"],
    )
    demo.add_argument("--fault", choices=["lost-response"])
    demo.add_argument(
        "--task",
        choices=sorted(TASK_KINDS),
        help="ERP-03 draft PO (default), ERP-01 shortage, ERP-02 recommendation",
    )
    group = demo.add_mutually_exclusive_group()
    group.add_argument("--approve", action="store_true", help="operator approves the action")
    group.add_argument("--reject", action="store_true", help="operator rejects the action")
    demo.add_argument("--reconcile", action="store_true", help="run read-only reconciliation")
    demo.add_argument("--json", action="store_true")
    demo.add_argument("--evidence-out", help="write the redacted evidence bundle to this file")
    ev = sub.add_parser("evidence", help="export the evidence bundle of a run (durable store)")
    ev.add_argument("run_id")
    ev.add_argument("--out", help="file to write (default: stdout)")
    sub.add_parser("plugins", help="list discovered plugins (metadata only)")
    sub.add_parser("migrate", help="apply ledger migrations for a postgres-store profile")
    secret = sub.add_parser("secret", help="manage local secrets (value read from stdin)")
    secret.add_argument("action", choices=["set", "delete"])
    secret.add_argument("ref", help="secretref:local/<name>")
    sub.add_parser("recover", help="run startup recovery on unfinished runs (never re-sends)")
    srv = sub.add_parser("serve", help="run the local HTTP API (loopback only)")
    srv.add_argument("--host", default="127.0.0.1")
    srv.add_argument("--port", type=int, default=8787)
    srv.add_argument("--static", help="directory of the built web UI to serve at /")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "demo":
            return asyncio.run(_demo(args))
        if args.command == "migrate":
            return asyncio.run(_migrate(args))
        if args.command == "recover":
            return asyncio.run(_recover(args))
        if args.command == "serve":
            from .api import serve

            serve(args.profile, args.host, args.port, args.static)
            return 0
        if args.command == "evidence":
            return asyncio.run(_evidence(args))
        if args.command == "secret":
            return asyncio.run(_secret(args))
        return _plugins(args)
    except KernelError as exc:
        sys.stderr.write(f"error {exc.code}: {exc.safe_message}\n")
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
