# Runbook I00: local environment qualification

**Where:** the developer machine that hosts `odoo19-learning` and Ollama. The cloud CI/agent containers cannot reach these services. **Status:** to be executed by the project owner; results are recorded below once run.

All steps are read-only except the ones explicitly approved in plan §0 D4 (integration user, API key, sandbox marker, addons path).

## 1. Prerequisites

- Docker with the `odoo19-learning` stack running (`odoo:19.0` on port 8069). **Never** use `odoo-bench` (port 8071).
- uv, Python 3.12+, Node 24 LTS + pnpm (UI work from I08).
- Ollama with candidate models pulled.
- A separate PostgreSQL instance or database/role for e-agent (not Odoo's database or user).

## 2. One-time sandbox preparation (approved under D4)

1. In Odoo (Settings → Users), create a dedicated user `e-agent-integration` with only Purchase, Inventory, Sales, CRM and (read-only) Invoicing rights and the sandbox company.
2. As that user, create an API key (Preferences → Account Security → New API Key). Store it outside the repository (password manager or a local `.env` that is git-ignored).
3. As an administrator, add a system parameter `e_agent.sandbox_marker` = `odoo19-learning` (Settings → Technical → System Parameters). Live tooling refuses databases without this marker.
4. Mount `addons/e_agent_bridge` into the compose file's addons path in I06, when the addon exists. This is a change outside this repository.

## 3. Run the read-only check

```bash
export E_AGENT_ODOO_URL=http://localhost:8069
export E_AGENT_ODOO_DB=<database>
export E_AGENT_ODOO_API_KEY=<integration user key>   # never commit, never paste into issues
export E_AGENT_PG_DSN=postgresql://e_agent@localhost:5433/e_agent   # optional
uv run python scripts/env_check.py > environment-manifest.local.json
```

The script never prints the API key. It reports the Odoo version and installed relevant modules, whether JSON-2 works for the integration user, whether the sandbox marker is present, and the Ollama version plus model digests.

## 4. Record results

Commit a **redacted** summary (no keys, no business data) in this file:

| Item | Value |
|---|---|
| Odoo server version | _pending_ |
| JSON-2 works for integration user | _pending_ |
| Relevant modules installed | _pending_ |
| Sandbox marker present | _pending_ |
| e-agent PostgreSQL separate from Odoo | _pending_ |
| Ollama version | _pending_ |
| Candidate model digests | _pending_ |

I00 is done when every row is filled and the plan's I00 definition of done holds.
