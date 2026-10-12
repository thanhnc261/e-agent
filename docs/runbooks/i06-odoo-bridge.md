# Runbook I06: install the bridge into the `odoo19-learning` sandbox

**Where:** the owner's machine. **Approved by:** plan §0 D4 (mount the addon path, create the integration user and API key). Never run against `odoo-bench` (port 8071) or any non-sandbox database.

The historical 2026-10-06 results below used the previous bridge; they do not qualify the 19.0.0.3.0 remediation source or the owner installation.

The same flow is automated for a throwaway Odoo built from source in `scripts/dev/odoo_from_source.sh` (dev container and the nightly `odoo-live` CI job). The live tests in `tests/integration/test_odoo_live.py` (ERP-01..03) and `tests/integration/test_odoo_live_tasks.py` (ERP-04..08) passed against that Odoo 19 build on 2026-10-06.

## 1. Mount and install the addon

1. In `/Users/thanhnguyen/dev/study/erp/docker-compose.yml`, add a bind mount of this repository's `addons/` directory into the Odoo container (for example `- /path/to/e-agent/addons:/mnt/e-agent-addons:ro`) and append `/mnt/e-agent-addons` to the container's `addons_path`.
2. Restart the stack, update the apps list, and install **e-agent bridge** (`e_agent_bridge` 19.0.0.3.0; depends on Purchase + Inventory, Sales + Inventory (`sale_stock`) and CRM, which Odoo installs with it). Upgrading from 0.1 installs the new dependencies.

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
uv run python scripts/odoo_sandbox.py seed --namespace e-agent-demo \
  --expected-marker "$E_AGENT_EXPECTED_MARKER" --expected-company-id "$E_AGENT_EXPECTED_COMPANY_ID" \
  --expected-bridge-version 19.0.0.3.0
uv run python scripts/odoo_sandbox.py seed-tasks --namespace e-agent-demo \
  --expected-marker "$E_AGENT_EXPECTED_MARKER" --expected-company-id "$E_AGENT_EXPECTED_COMPANY_ID" \
  --expected-bridge-version 19.0.0.3.0
```

Set the two expected identity variables from the explicitly designated synthetic sandbox; never infer them from an arbitrary response and then authorize mutation. The host pins URL port 8069, database, company, marker and bridge version; the bridge repeats the identity check inside each write transaction.

Use the printed refs in a live profile (see `profiles/live.example.json`). `e-agent` checks database/company/marker/bridge identity. Live profiles also require a dedicated PostgreSQL ledger and `artifact_sha256` for both domain and provider plugins from an externally trusted wheel inventory. Generate that inventory with `uv run python scripts/plugin_inventory.py <trusted-wheel> > <inventory.json>`; use the inventory's artifact hash, rather than approving the installed files themselves.

## 4. Reset

Reset requires the same expected marker/company/version arguments as seed. Version 19.0.0.3.0 records exact synthetic record IDs in an administrator-only `e_agent.fixture` inventory. It refuses legacy namespaces with no inventory, duplicate matches and unowned records. Choose a fresh `e-agent-...` namespace for a legacy installation; no automatic adoption or broad legacy cleanup is provided.

Reset removes eligible draft agent effects, cancels owned seed business documents and clears stock quantities only for owned fixture quants. Archived synthetic sources and cancelled audit records may remain; inspect the returned `remaining` inventory rather than assuming complete deletion. It refuses agent-created documents that have left the allowed draft state. Exact Odoo ORM behavior, repeated seed/reset and race handling still require the live test gate for this bridge version.

`seed-tasks` posts two synthetic customer invoices as sandbox setup by the administrator. No e-agent capability can post, pay or write off; the integration user has read-only accounting rights.
