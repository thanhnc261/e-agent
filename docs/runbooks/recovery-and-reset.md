# Runbook: recovery, reconciliation and reset

## Process crash or restart

`e-agent serve` runs `recover()` at startup; `uv run e-agent --profile <p> recover` runs it on demand. Recovery never sends a write:

| Found | Action |
|---|---|
| Action `DISPATCHING` | Marked `UNKNOWN`; the run waits in `NEEDS_RECONCILIATION` |
| Action `APPROVED`/`RESERVED`, not dispatched | Blocked; the run fails ("approve a new run") because the approval may be stale |
| Action `COMMITTED`, run `VERIFYING` | Independent read-back verification is re-run |
| Run `RUNNING`/`CREATED` with no pending effect | Failed ("interrupted during driver turn") |

An unexpected error in API background work applies the same rules to that one run.

## Unknown outcome (`NEEDS_RECONCILIATION`)

The provider may or may not have applied the write. Use **Reconcile** in the UI or `POST /v1/runs/{id}/reconcile`. It reads the bridge's operation ledger by operation key: if the write committed with the approved digest, the run is verified and succeeds; if nothing is found, the action stays unresolved and nothing is re-sent. Never retry the business action by hand. Inspect `e_agent.operation` in the sandbox if in doubt.

## Sandbox reset

```bash
uv run python scripts/odoo_sandbox.py reset --namespace <ns>
```

This removes or cancels only records created or seeded in that namespace (see the [I06 runbook](i06-odoo-bridge.md#4-reset)). It refuses when an e-agent-created order or quotation left draft state; resolve that manually in Odoo.

## Ledger database

- Migrations are forward-only and checksummed: `uv run e-agent --profile <p> migrate`. A changed migration file is refused.
- The ledger must be its own database; startup refuses a DSN that names a provider database.
- Back up the ledger before upgrades; evidence bundles can be re-exported from it at any time.

## Keys

- Rotate the Odoo integration key in Odoo (7-day expiry in the dev setup), then `uv run e-agent secret set secretref:local/odoo-integration`.
- Keep `E_AGENT_SECRET_KEY` (the local key-encryption key) outside the repository. Losing it makes stored secrets unreadable; re-enter them.
- A connection whose provider subject changes requires a new approval for pending actions; the credential subject is part of the digest.
