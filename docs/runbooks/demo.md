# Runbook: demo (fixture and live sandbox)

Never point any of this at `odoo-bench` (port 8071) or a non-sandbox database. Startup refuses a database whose `e_agent.sandbox_marker` does not match the profile.

## 1. Fixture demo (no Odoo, no model)

```bash
uv sync
uv run e-agent demo --approve                                   # ERP-03 draft PO
uv run e-agent demo --driver-mode invalid-then-repair --approve # blocked by PR-003, repaired
for t in shortage recommend amend-rfq quotation late-orders crm-lead overdue-invoices; do
  uv run e-agent demo --task $t --approve
done
uv run python scripts/release_report.py                         # 21-case matrix -> evals/reports/
```

Web UI on the fixture server:

```bash
(cd ui && pnpm install && pnpm build)
uv run e-agent serve --static ui/dist/web
# http://127.0.0.1:8787/           standalone app (?lang=vi, ?theme=dark, ?layout=sidebar)
# http://127.0.0.1:8787/host.html  overlay on a neutral host page
# http://127.0.0.1:8787/reference/ non-React reference UI
```

## 2. Live sandbox demo

Prerequisites: the [I06 runbook](i06-odoo-bridge.md) is done, the integration key is in the local secret store, and a PostgreSQL database for the ledger exists (not Odoo's).

1. Seed a namespace and note the printed refs:

   ```bash
   export E_AGENT_ODOO_URL=http://localhost:8069 E_AGENT_ODOO_DB=<sandbox db> E_AGENT_ODOO_ADMIN_KEY=<admin key>
   uv run python scripts/odoo_sandbox.py seed-tasks --namespace demo-1
   ```

2. Copy `profiles/live.example.json`, set `namespace`, `expected_sandbox_marker`, the bindings, and either `driver.kind: scripted` with `task_kind` and `refs` from step 1, or `driver.kind: pydantic-ai` with the qualified Ollama model.
3. Run `uv run e-agent --profile my-live.json migrate`, then `demo --task <kind> --approve` or `serve --static ui/dist/web`.
4. Export evidence with `--evidence-out run.json` or `uv run e-agent --profile my-live.json evidence <run_id>`. Bundles are redacted and labelled `environment=live`.
5. Reset when done: `uv run python scripts/odoo_sandbox.py reset --namespace demo-1`.
