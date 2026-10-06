# Runbook I06: install the bridge into the `odoo19-learning` sandbox

**Where:** the owner's machine. **Approved by:** plan §0 D4 (mount the addon path, create the integration user and API key). Never run against `odoo-bench` (port 8071) or any non-sandbox database.

The same flow is automated for a throwaway Odoo built from source in `scripts/dev/odoo_from_source.sh` (dev container and the nightly `odoo-live` CI job). The live tests in `tests/integration/test_odoo_live.py` (ERP-01..03) and `tests/integration/test_odoo_live_tasks.py` (ERP-04..08) passed against that Odoo 19 build on 2026-10-06.

## 1. Mount and install the addon

1. In `/Users/thanhnguyen/dev/study/erp/docker-compose.yml`, add a bind mount of this repository's `addons/` directory into the Odoo container (for example `- /path/to/e-agent/addons:/mnt/e-agent-addons:ro`) and append `/mnt/e-agent-addons` to the container's `addons_path`.
2. Restart the stack, update the apps list, and install **e-agent bridge** (`e_agent_bridge` 19.0.0.2.0; depends on Purchase + Inventory, Sales + Inventory (`sale_stock`) and CRM, which Odoo installs with it). Upgrading from 0.1 installs the new dependencies.

## 2. Sandbox marker, integration user, keys

As administrator in the sandbox database:

1. Settings → Technical → System Parameters: create `e_agent.sandbox_marker` with a value of your choice, for example `odoo19-learning`.
2. Create user **e-agent integration** with the groups *e-agent integration*, *Purchase / User*, *Inventory / User*, *Sales / User: All Documents* (sales orders and leads for ERP-05..07) and *Accounting / Read-only* (ERP-08) only. It never needs invoicing or posting rights. Under Preferences → Account Security, create an API key. Odoo 19 requires an expiry date.
3. To use the seed and reset tools, also add the administrator to the *e-agent integration* group, and create an admin API key for `scripts/odoo_sandbox.py`.

Store keys only in the local secret store or your password manager:

```bash
export E_AGENT_SECRET_KEY=$(uv run python -c "from e_agent.adapters.secretstore_local import generate_key; print(generate_key())")
# keep E_AGENT_SECRET_KEY outside the repository (e.g. password manager / shell profile)
uv run e-agent secret set secretref:local/odoo-integration   # paste the integration key, Enter
```

## 3. Seed and verify

```bash
export E_AGENT_ODOO_URL=http://localhost:8069 E_AGENT_ODOO_DB=<db> E_AGENT_ODOO_ADMIN_KEY=<admin key>
uv run python scripts/odoo_sandbox.py info
uv run python scripts/odoo_sandbox.py seed --namespace e-agent-demo     # prints demand/product refs
uv run python scripts/odoo_sandbox.py seed-tasks --namespace e-agent-demo  # ERP-04..08: RFQs, customers, orders, team, invoices
```

Use the printed refs in a live profile (see `profiles/live.example.json`). `e-agent` refuses to start if the database's marker does not match `expected_sandbox_marker`.

## 4. Reset

`uv run python scripts/odoo_sandbox.py reset --namespace e-agent-demo` cancels and removes only draft orders, draft quotations, leads and ledger rows created in that namespace, cancels the namespace's seeded RFQs and sales orders, and resets its seeded invoices to draft and cancels them. It refuses if any e-agent-created order or quotation in the namespace left draft state.

`seed-tasks` posts two synthetic customer invoices as sandbox setup by the administrator. No e-agent capability can post, pay or write off; the integration user has read-only accounting rights.
