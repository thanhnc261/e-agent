"""Evidence bundle export (MVP design §11).

A redacted, self-describing JSON record of one run: environment class, versions,
events, proposals/findings, approvals, receipts and outcomes. It contains no
secrets (the ledger never stores them), no driver continuation and no model
reasoning; operators export it through an authorized command.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from e_agent.contracts.common import utc_now
from e_agent.contracts.run import TERMINAL_RUN_STATES
from e_agent.sdk.store import RunStore

EVIDENCE_SCHEMA = "e-agent-evidence-v1"


def classify(run_state: str, reason: str | None, environment: str) -> str:
    if run_state == "SUCCEEDED":
        return f"{environment}:succeeded"
    if run_state not in {str(s) for s in TERMINAL_RUN_STATES}:
        return f"{environment}:unresolved"
    text = (reason or "").lower()
    if "validation" in text or "rejected" in text or "policy" in text:
        return f"{environment}:blocked-by-design"
    if "budget" in text or "interrupted" in text or "provider" in text:
        return f"{environment}:infrastructure-or-budget"
    return f"{environment}:failed"


async def build_evidence(
    store: RunStore,
    tenant_id: str,
    run_id: str,
    *,
    environment: str,
    versions: Mapping[str, Any],
) -> dict[str, Any]:
    run = await store.get_run(tenant_id, run_id)
    events = await store.list_events(tenant_id, run_id)
    actions = await store.list_actions(tenant_id, run_id)
    approvals, receipts = [], []
    for action in actions:
        approvals += [
            a.model_dump(mode="json")
            for a in await store.list_approvals(tenant_id, action.action_id)
        ]
        receipts += [
            r.model_dump(mode="json")
            for r in await store.list_receipts(tenant_id, action.action_id)
        ]
    rule_bundles = sorted(
        {
            str(f.get("rule_id")) + "@" + str(f.get("rule_version"))
            for e in events
            if e.type == "validation.completed"
            for f in e.payload.get("findings", [])
        }
    )
    return {
        "schema": EVIDENCE_SCHEMA,
        "generated_at": utc_now().isoformat(),
        "environment": environment,
        "classification": classify(run.state, run.reason, environment),
        "versions": dict(versions),
        "rules_evaluated": rule_bundles,
        "run": run.model_dump(mode="json"),
        "actions": [a.model_dump(mode="json") for a in actions],
        "approvals": approvals,
        "receipts": receipts,
        "outcomes": [e.payload for e in events if e.type == "outcome.reported"],
        "events": [e.model_dump(mode="json") for e in events],
    }
