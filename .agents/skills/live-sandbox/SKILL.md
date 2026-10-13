---
name: live-sandbox
description: Operate the odoo19-learning sandbox (identity, seed, reset, bridge, stack); manual use only.
disable-model-invocation: true
---

# Live sandbox operations

Everything here touches the owner's `odoo19-learning` sandbox. The owner starts this skill by name; a live mutation needs the owner's instruction in the current session.

## Hard limits

- Read [eng-foundations](../eng-foundations/SKILL.md) first; cite rules by ID.
- Only `odoo19-learning-*`, `e-agent-ledger` and containers e-agent creates are touched (ENG-BOUND-1). Nothing here names any other stack, and the permission rules deny them regardless.
- Keys live outside the repository: the local secret store and `~/.config/e-agent/live.env`; a profile with secrets is `profiles/*.local.json` and never committed (ENG-BOUND-3).
- Identity before mutation: every seed or reset passes `--expected-marker`, `--expected-company-id` and `--expected-bridge-version`, and runs after `info` has confirmed them.
- Record outcomes as redacted evidence under `harness/state/evidence/live/` (ENG-EVID-3): run ids, states and reason codes, never payloads with key material.

## Operations

| Operation | Command | Notes |
|---|---|---|
| Identity and readiness | `uv run python scripts/odoo_sandbox.py info` then `uv run python scripts/env_check.py` | always first; confirms database, company, marker and bridge version |
| Seed demo data | `uv run python scripts/odoo_sandbox.py seed --namespace e-agent-demo --expected-marker <marker> --expected-company-id <id> --expected-bridge-version <version>` | prints the refs the live profile needs |
| Seed task fixtures | `uv run python scripts/odoo_sandbox.py seed-tasks --namespace e-agent-demo --expected-marker <marker> --expected-company-id <id> --expected-bridge-version <version>` | after `seed` |
| Reset the namespace | `uv run python scripts/odoo_sandbox.py reset --namespace <ns> --expected-marker <marker> --expected-company-id <id> --expected-bridge-version <version>` | only the named namespace; see the recovery runbook |
| Bridge upgrade after `addons/` changes | `docker compose -p odoo19-learning exec odoo-1 <odoo command from runbook I06> -u e_agent_bridge`, then `info` | the version bump in `addons/e_agent_bridge/__manifest__.py` lands first (ENG-BOUND-2) |
| Wheel re-pin after domain or adapter changes | `uv build --package <distribution> --wheel`, then `uv run python scripts/plugin_inventory.py <wheel> > <inventory.json>`; copy `artifact_sha256` into the local live profile | pins come from a trusted wheel, never from installed files |
| Start the live stack | `set -a; . ~/.config/e-agent/live.env; set +a` then `make dev PROFILE=profiles/live-odoo19-learning.local.json` | loopback only |
| Ledger migrate and recover | `uv run e-agent --profile <p> migrate`, `uv run e-agent --profile <p> recover` | migrations are forward-only and checksummed |
| Rotate the integration key | rotate in the sandbox (7-day expiry in the dev setup), then `uv run e-agent secret set secretref:local/odoo-integration` | never paste the key anywhere else |
| Harness live check | `uv run e-agent-harness live-check` | runs the manifest's `live` gate set, redacted, into `harness/state/evidence/live/` |

Detail and first-time setup: [runbook I06](../../../docs/runbooks/i06-odoo-bridge.md) and [recovery and reset](../../../docs/runbooks/recovery-and-reset.md).

## Before handing off

- [ ] `info` ran before any mutation and its identity matched the expected flags.
- [ ] Every mutation and its namespace are listed in the handoff's "Changes outside the repository" with the undo (a reset of the same namespace).
- [ ] Evidence under `harness/state/evidence/live/` is redacted.

## Stop gate

No seed, reset, upgrade or stack start without the owner's instruction in this session. When in doubt, run `info` and stop.
