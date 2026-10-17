# Phase 1d: plugin boundary and reusable core (2026-10-16)

## Summary

- **Plan:** [Phase 1d plan](../plans/2026-10-14-phase1d-plugin-boundary.md), tasks 1d.1 to 1d.12 and the phase-review fix 1d.R1; [roadmap](../roadmap.md) row 1d; [ADR 0026](../adr/0026-plugin-layout-and-reusable-core.md).
- **Branch:** `refactor/phase1d-plugin-boundary`, cut from `main` at `30005a6`. Not merged, not pushed.
- **Execution:** the development harness ran tasks 1d.1 to 1d.11 and 1d.R1 through contract, `check-scope`, gate evidence on a clean commit, feature flip, handoff and `close-check`. Task 1d.12 has its contract and its functional live checks (below), but not yet its `live` gate evidence, feature flip, task handoff or `close-check`; F-1d-12 stays `passes: false` until then. Tasks 1d.3 to 1d.10 have committed review records in `harness/state/1/reviews/` (Codex for 1d.3, 1d.4, 1d.5 and 1d.7b; Claude for 1d.6 to 1d.10, with scoped re-reviews after fixes); 1d.2 records its review R-1 fix in its handoff (`0d895fb`) but has no review file. 1d.10, 1d.R1 and 1d.11 ran in the main context. The phase review ran on Codex and found one Blocker, fixed in 1d.R1 and accepted by Codex (below).
- **Result:** the core (contracts, plugin SDK, kernel, server and the infrastructure adapters) installs and starts without any ERP distribution, and ERP is the first plugin area under `src/e_agent/plugins/erp/{domain,odoo,simulator}`. Run behaviour is unchanged: the OpenAPI check, the golden demo prompts, the recorded-model replays and `make e2e` (150 passed, 4 skipped, as in Phase 1) all hold. The live check (1d.12, 2026-10-17) passes on `odoo19-learning`: readiness admits `domain-erp` and `odoo19` with the new pins and no `fixture-erp`, task 1 is answered and verified as at the 2026-10-13 baseline, and stale or wrong pins are refused at startup. Its harness `live` gate set is still to run by the owner, so 1d.12 is not closed.

## What changed

| Commit | Content |
|---|---|
| `e347b20`, `0ffd71c`, `8362afa` | ADR 0026 written, aligned with the plan and accepted with the common plugin SDK amendment (1d.1) |
| `7d6188e`, `84bf45d` | Auth placement and the sandbox probe come from the adapter manifests' `connection` section; an undeclared placement is refused, never defaulted (1d.2) |
| `49abd0b`, `38cd4d2`, `1f83eb6`, `5b793e8`, `93184fb`, `08e0a6d` | Task presets come from the domain pack; the demo prompts match the recorded golden file (1d.3) |
| `23d37fd` | The scripted driver comes from the domain pack through a driver factory; `demand_ref` and `product_ref` fold into `refs` (1d.4) |
| `beec2fe`, `5d402aa` | The ERP simulator becomes the discovered provider plugin `fixture-erp`; startup errors carry no setting value (1d.5) |
| `17d725f`, `83c37ce`, `71ae31a` | The server ships no profile; `--profile` or `E_AGENT_PROFILE` is required, and the fixture profile ships with the simulator (1d.6) |
| `79978a1`, `83f3912` | Import contracts "Core never imports plugins" and "Plugins are guests"; the registry enforces `required_features` (1d.7) |
| `5234025`, `e6ace64`, `96a6825` | `e_agent.sdk.http`, the authenticated HTTP helper behind the `[http]` extra; the Odoo client uses it (1d.7b) |
| `7b43a74`, `6fbef41`, `d848946` | `e-agent-server` drops its ERP dependencies; the code-less `e-agent-erp` bundle; `check_core_only.py` joins the full gate and CI (1d.8) |
| `43036dc`, `612c017` | `repo_move.py` gains the `plugins` move set (1d.9) |
| `2daed08`, `d3bed9c`, `1b89e9a` | The domain pack and the Odoo adapter move under `plugins/erp/` (47 renames); docs, import contracts and ENG-ARCH-1/5 follow (1d.10) |
| `bbdf8fe` | Phase 2 and Odoo tools plans amended; principles PR-01, PR-03, PR-08, PR-10; Phase 1 follow-up note; pilot log; roadmap; gotcha G-15 (1d.11) |
| `cf346db` | In a live profile, a binding routes only to its own provider's connections, and the sandbox guard probes every provider an admitted binding reaches (phase review R-1, 1d.R1) |
| `fdc3c8d` | Plan: 1d.11 steps done, 1d.R1 recorded (1d.11) |

Task-level detail, rulings and evidence: `harness/state/1/handoffs/1d.*.json` and `harness/state/1/reviews/1d.*.json`.

## What was verified

Levels 1 to 3 ran on the clean tree at `fdc3c8d`, the final head after the 1d.R1 fix:

```text
# full  harness/state/evidence/gates/1d.11/2026-10-16T11-34-11.086089+00-00-full.json  (commit fdc3c8d, clean_tree=True)
uv sync --locked                                -> Checked 82 packages in 1ms
uv run ruff check .                             -> All checks passed!
uv run ruff format --check .                    -> 267 files already formatted
uv run mypy                                     -> Success: no issues found in 121 source files
uv run lint-imports                             -> Contracts: 12 kept, 0 broken.
uv run python scripts/export_openapi.py --check -> (no output, exit 0)
uv run pytest -q                                -> 972 passed, 30 skipped in 50.47s
pnpm --dir ui gen:check                         -> packages/client/openapi.json → packages/client/src/schema.ts [36.6ms]
pnpm --dir ui check                             -> ✓ built in 26ms
uv run python scripts/check_core_only.py        -> core-only check passed in 7.2s

# pg  harness/state/evidence/gates/1d.11/2026-10-16T11-35-17.654503+00-00-pg.json  (commit fdc3c8d, clean_tree=True)
E_AGENT_TEST_STORE=postgres uv run pytest -q tests/unit/kernel -> 167 passed in 7.24s
  (E_AGENT_TEST_PG_DSN on database e_agent_test in e-agent-ledger; E_AGENT_PG_DSN unset)

# e2e  harness/state/evidence/gates/1d.11/2026-10-16T11-35-25.267333+00-00-e2e.json  (commit fdc3c8d, clean_tree=True)
make e2e -> 4 skipped, 150 passed (1.3m)

# core  harness/state/evidence/gates/1d.11/2026-10-16T11-36-47.719174+00-00-core.json  (commit fdc3c8d, clean_tree=True)
uv run python scripts/check_core_only.py -> core-only check passed in 7.6s
```

The same four levels also passed at `bbdf8fe`, before the phase review (`harness/state/evidence/gates/1d.11/2026-10-16T11-1*`; pytest 966 passed, 30 skipped).

`scripts/check_wheels.py` has no gate set (pilot log HP-6). It passed by hand on `2daed08`, again on the committed tree after it, and on `fdc3c8d` after the 1d.R1 server change: 12 wheels install and import from their own dependency closure, installed plugin bytes match the trusted wheel inventories, and the installed demos complete outside the repository. The 12 wheel file lists before and after the move are equal through the prefix map.

`repo_move.py check --set plugins --docs`: 0 broken links, 0 old-path references in code and config, 0 in current docs (4 broken links in read-only history, ruled to stay; D5).

### Level 4: live check (1d.12, 2026-10-17), labelled live

Live results against the `odoo19-learning` sandbox (bridge 19.0.0.4.0, Postgres ledger `e-agent-ledger`, Ollama driver), on `4de0de3`. They are not fixture results (ENG-EVID-2). Redacted evidence: `harness/state/evidence/live/1d.12-startup.json` and `harness/state/evidence/live/1d.12-flow1.json`.

- **Pins.** The three plugin wheels rebuilt at `4de0de3` give the same `artifact_sha256` as the table below. The agent re-pinned `domain-erp` and `odoo19` in the git-ignored live profile on the owner's instruction (ruling below); `fixture-erp` is not enabled there.
- **Stale pins refused.** Before the re-pin, `serve` with the previous pins exits 3: `STARTUP_REJECTED: domain-erp: artifact bytes differ from the approved build inventory`.
- **Readiness.** With the new pins, `/health/ready` returns `{"status": "ready", "environment": "live", "plugins": ["domain-erp", "odoo19"], "store": "postgres", "self_approval_allowed": true}`. `fixture-erp` is not loaded. Startup passed the sandbox guard, which probes the marker through the `odoo19` manifest's sandbox probe and refuses startup on a mismatch.
- **Task 1** (API, flow 1 of the Phase 1 live check: "hi", then "Which products are short for open demand?"): run `run_6409317e94f84bccbb72718410fc9849`, CREATED → RUNNING → WAITING_INPUT → RUNNING → SUCCEEDED, reason `answered`, 31.6 s. `procurement.shortage.answer.v1` VERIFIED (demand 12, available 4, inbound 10, shortage 0 for "E-Agent Widget A"). The event counts equal the 2026-10-13 baseline (5 reads, 1 proposal, 1 outcome, no approval). Sandbox data was only read.
- **Wrong pin refused.** A temporary git-ignored profile with the `odoo19` pin's last hex digit flipped exits 3: `STARTUP_REJECTED: odoo19: artifact bytes differ from the approved build inventory`. The file was deleted afterwards.
- **Not run: the harness `live` gate set**, that is, neither `scripts/env_check.py` nor `scripts/odoo_sandbox.py info` as a gate. `info` needs the Odoo admin key in the environment (`odoo_sandbox.py:56`), and `env_check.py` skips its authenticated Odoo checks without `E_AGENT_ODOO_API_KEY` (`env_check.py:55-68`); both keys live only in the owner's key file, the agent was refused access to it and did not work around that. A manual `env_check.py` run without those variables reported only the local Ollama models, Postgres configuration and Python, and is not counted. The owner runs `uv run e-agent-harness gate live` with `E_AGENT_ODOO_URL`, `E_AGENT_ODOO_DB`, `E_AGENT_ODOO_ADMIN_KEY` and `E_AGENT_ODOO_API_KEY` set; its evidence closes the task.

## Plugin pins for the owner's re-pin

Wheels built at `2daed08` and again at `9a7a88b`, version 0.1.0; 1d.R1 changed only `src/e_agent/server/bootstrap.py`, which is in no plugin wheel (`scripts/plugin_inventory.py`):

| Plugin | `artifact_sha256` |
|---|---|
| `domain-erp` | `93fa9a4d84d4f7529def4f532532b82aee7c537b709ec0201a898c5d9220e3b4` |
| `odoo19` | `5f2296c3064b3a94e3a053d617a3abae1b9cce8f2097125430f9b91abef70ac7` |
| `fixture-erp` | `3342fa23df5f8051e2b0408e6045df3d6d6d17111f425e599e97631cebce8a48` |

The live profile does not enable `fixture-erp`, so only the first two go into `profiles/live-odoo19-learning.local.json`.

## Phase review

Codex ran the end-of-phase review on `bbdf8fe` (`harness/state/1/reviews/1d-phase.json`): **rework**, one finding.

- **R-1, Blocker, correctness.** The live sandbox guard chose its live providers by `connection.integration_id`, and admission never checked that a binding's connection belongs to the binding's provider. A pinned live profile that enabled `fixture-erp` and mapped its binding to a connection of an unconfigured integration passed the guard, and reads routed to the simulator (Codex reproduced it in memory with fixture reads only). Before Phase 1d the simulator was registered only for `environment: fixture`. It violated ADR 0026 and Review Focus 1.
- **Fix, Task 1d.R1 (`cf346db`).** In a live profile, `admit_plugins` refuses a connection whose integration is not an enabled plugin and a binding mapped to a connection of another integration; `_check_sandbox` counts as live every provider that a connection names or an admitted binding routes to. Four new tests reproduce the finding and were watched failing (`DID NOT RAISE KernelError`), then passing.
- **Codex review of the fix** (`harness/state/1/reviews/1d.R1.json`; Codex job `task-mvavyjlz-a5rktr`, session `01a14479-efcc-7581-830f-15dd0b14ffb8`, 3 min 30 s and 29 commands, among them `git show cf346db`, `lint-imports` and in-memory Python reproductions; the phase review was job `task-mvavjedn-ps9d8t`): `{"task": "1d.R1", "verdict": "accept", "findings": [], "reviewer": {"provider": "codex", "fresh_context": true}}`.
- **Second whole-phase pass on the final head `6deb3de`** (Codex, 2026-10-17; `harness/state/1/reviews/1d-phase-r2.json`; job `task-mvbqk74n-8duwdj`, session `01a1478a-3827-7702-bdc4-844b77557133`, 2 min 44 s, 34 commands including the phase diff and in-memory Python reproductions): `{"task": "1d-phase-r2", "verdict": "accept", "findings": [], "reviewer": {"provider": "codex", "fresh_context": true}}`. A first attempt on 2026-10-16 (`task-mvawbiyl-nq9xgj`) stopped on Codex's usage limit without a verdict.

## Rulings

- 1d.12: the plan reserved the live profile re-pin for the owner. The owner instructed the agent to implement F-1d-12 on 2026-10-17, so the agent re-pinned with a script that replaced only the two `artifact_sha256` values and printed no other profile value. Cost if wrong: restore the previous pins `domain-erp` `0f1c8f61a8a3bcd3d1b1e7803c3df233ddead29be235a9bf2d769673a7a23c4e` and `odoo19` `8df983a76276dd2191569b3c45725929c072b1259b237e52fc2dada1b708c66f` (they no longer start).
- D1 to D6 applied at their defaults (owner plan approval 2026-10-15). Cost if wrong: per decision in the plan.
- "Core never imports plugins" forbids `e_agent.plugins.**` from contracts, SDK, kernel and server; "Plugins are guests" keeps an explicit list, because `test_every_plugin_package_is_a_guest` matches source modules literally (1d.10). Cost if wrong: a new plugin package must be added to the list by hand; the guest test fails until it is.
- The infrastructure adapters are not sources of "Core never imports plugins"; the layers and adapter contracts forbid the existing ERP plugins to them, but no wildcard covers future plugins (1d.10 review R-3, R-5). Cost if wrong: a future plugin imported by an infrastructure adapter would pass the gate until the adapter contract is widened.
- The ownership check of 1d.R1 runs for live profiles only: live credentials are already looked up by the connection's integration id as a plugin id, and only live profiles are probed, while the non-ERP test packs name an integration apart from their plugin in fixture profiles. It sits in `bootstrap.admit_plugins`, not in `PluginRegistry`. Cost if wrong: a fixture profile may route a binding through another integration's connection (no live system is reached); a caller that admits plugins without `admit_plugins` skips the check, though the guard's union still refuses an unprobed provider that a binding reaches.
- The Odoo tools plan named no "manifest `connection` consumed" item, so 1d.11 adds a dated amendment instead of removing one. Cost if wrong: none; the section is consumed since 1d.2.
- `docs/design/principles.md` also updates PR-01 (12 contracts) and PR-03 (its check exists since 1d.7) next to PR-08 and PR-10, and AGENTS.md's PR-10 line (scope amended). Cost if wrong: none; each row names a check that runs in the full gate.

## Deferred minors

- `AuthContext.apply` still carries `Authorization`/`Bearer ` defaults, unreachable from the host (1d.2).
- The sandbox target comparison in bootstrap is still Odoo-shaped (1d.2).
- A plugin-contributed driver factory named `pydantic-ai` is never consulted (1d.4).
- `load_profile` reads `E_AGENT_PROFILE` from `os.environ` directly (PR-37; hygiene plan) (1d.6).
- `task_kind` default `draft-po` in `server/profile.py` is a domain literal; it goes with the Phase 2 task definitions (1d.7).
- Review lows left as is: 1d.7 R-2 to R-4, 1d.9 R-8 and R-9.
- `scripts/` is outside mypy's configured packages (1d.9).

## Open items for the owner

1. Task 1d.12 is done except for the identity gate: run `uv run e-agent-harness gate live` with the Odoo admin and integration keys in the environment (above), so its evidence can close the task. The Odoo API keys expire 2026-10-19.
2. By the H0 rule, a Codex re-review of the 1d.5 fixes and a Codex review of 1d.7 (kernel admission change) were still owed; decide whether the two whole-phase Codex passes (the second one accepted the final head) cover them.
3. The review schema accepts only `fresh_context: true`; `harness/state/1/reviews/1d.7b-r2.json` records `false` truthfully and does not validate.
4. Harness backlog (H5): HP-6 (one gate set per contract); `amend-scope` with two `--add` flags keeps only the last; the scope hook refuses edits under `.superpowers/sdd/`.
5. Merge and push of `refactor/phase1d-plugin-boundary`; CI has not run `check_core_only.py` on Python 3.13.
6. No import contract yet forbids the infrastructure adapters from importing future plugins.
7. Whether the binding-ownership rule should move into `PluginRegistry` (a kernel API change, through an ADR) or stay in the composition root.
8. The roadmap 1d row now mentions 1d.R1 (1d.12).

## Changes outside the repository

| Change | Undo |
|---|---|
| Started the stopped `e-agent-ledger` container for the `pg` runs against its `e_agent_test` database (1d.10, 1d.11); it was left running. The runs truncated only `e_agent_test` | `docker stop e-agent-ledger` |
| `profiles/live-odoo19-learning.local.json` re-pinned: `domain-erp` and `odoo19` `artifact_sha256` (1d.12) | restore the previous pins from the 1d.12 ruling |
| A temporary `profiles/live-odoo19-learning-wrongpin.local.json` (mode 0600) created for the wrong-pin start and deleted (1d.12) | none needed |
| Live server started on 127.0.0.1:8795 for the check and stopped (1d.12) | none needed |
| One live run, `run_6409317e94f84bccbb72718410fc9849`, added to the live ledger (1d.12) | none needed; normal run history |
