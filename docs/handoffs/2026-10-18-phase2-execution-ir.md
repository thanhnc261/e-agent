# Phase 2: execution IR (2026-10-18)

## Summary

- **Plan:** [Phase 2 plan](../plans/2026-10-14-phase2-execution-ir.md), Parts 2a to 2d; [roadmap](../roadmap.md) row 2; [ADR 0024](../adr/0024-plan-approval-model.md), [ADR 0025](../adr/0025-execution-ir.md), [ADR 0027](../adr/0027-feature-toggles.md), [ADR 0028](../adr/0028-task-definitions.md) and [ADR 0029](../adr/0029-capability-effect-declarations.md); [target architecture §6.4](../design/target-architecture.md#64-execution-ir-i).
- **Branch:** `phase2/execution-ir`, cut from `main` at `6f7ec70`. Pushed to PR #6 on the owner's instruction and merged to `main` on the owner's instruction (2026-10-19).
- **Execution:** the development harness ran every task, 2a.1 to 2c.9 (with the inserted 2c.5a and 2c.8a to 2c.8c) and 2d.1, through contract, `check-scope`, gate evidence on a clean commit, feature flip, handoff and `close-check`. Every task has committed review records in `harness/state/2/reviews/`: Codex for 2b.1 to 2b.3, 2c.1, 2c.5a, 2c.6, 2c.8 (re-check), 2c.8b (partial), 2c.9 and the final check of 2c.8b and 2c.8c (accept, below); Claude reviewers for the others and for the scoped re-reviews after fixes. The whole-phase review ran in a fresh Claude context (`2d.1-phase.json`, eight findings, below).
- **Result:** behind the profile toggle `features.execution_ir` (`off` by default), a run's tools come from the admitted task definition, a validated proposal runs as a 1-step plan with the same approval digest as today, and a multi-step plan is approved once and dispatched step by step. Each step is re-validated, its arguments re-checked against the approved digest and its outcome independently verified before the next step starts. `off` is byte-identical to the pre-phase behaviour on the recorded goldens (event types, transitions, states, digests and payload key sets). All of it is fixture evidence. The live check 2d.2 passed on `odoo19-learning` on 2026-10-19 (Level 4 below).

## What changed

| Part, task | Commits | Content |
|---|---|---|
| 2a.1, 2a.2 | `55e09a2`, `beb9b3b`, `64ca921`, `56995e5` | ADRs 0024, 0025, 0027, 0028 and 0029 reconciled with the plan and accepted (gate G1, 2026-10-18) |
| 2b.1 | `5ec6cad`, `99b07e3`, `5cf44e6` | Off-mode golden baseline; `Profile.features` with every toggle `off` by default |
| 2b.2 | `c14f9c7`, `e31020e`, `5038b8f`, `fbc0466` | `feature.fallback` and the `ir.*` event types, with fixed messages and no caller text |
| 2b.3 | `2e5b56b` | `/health/ready` and the evidence bundle report the toggles |
| 2c.1 | `a320467`, `e037e60`, `770571b` | Contracts: `TaskDefinition`, `ActionPlan`, `StepRecord`, effect declarations, lineage references |
| 2c.2 | `a6ff19c`, `22ca83e` | Task definitions for the eight ERP tasks; risk and reversibility on the ERP capabilities |
| 2c.3 | `4ae3cc6`, `4bf2c0e`, `fa06d62`, `a732a12` | Action plans and step records in both stores; the `$lineage` wire form parsed only at the store boundary |
| 2c.4 | `3682ff7`, `a7e18dd`, `8aa0c3b`, `c7b3f4d`, `9c902ec` | IR compiler, plan validation and the lossless plan digest |
| 2c.5 | `764cfe0`, `dfc9748`, `423db64` | `shadow`: `ir.plan_compiled` recorded beside the old path, which still acts |
| 2c.5a | `118ecf8`, `aface8f`, `f19d057`, `61634d0` | Codex batch fixes: the wire form keeps the digest profile; draft-po acceptance needs a zero-shortage answer (ADR 0028 amendment, accepted); an action naming no plan of its run is refused |
| 2c.6 | `c527f69`, `bc5184a`, `e8c21f9`, `1542cf9`, `322205d` | `on` for single-step plans: the admitted definition sets the tools for the whole run; `ACCEPTANCE_UNMET` at run end and in recovery |
| 2c.7 | `adff12a`, `7243a3e`, `d976f33`, `ac22c9c`, `7c8cb1f` | `ProposePlan` (sdk_api 1.1); multi-step plans with one approval; plan guards before a later step reserves |
| 2c.8 | `e7cfcdc`, `fe40739`, `9f6a3ca`, `1ea7ffb`, `9143ecb`, `3d91705`, `40ba1a7`, `43cf231`, `de5ae80` | Partial failure and reconciliation; `PLAN_LINEAGE_REJECTED`; an approval expiring between steps ends STALE; plan resume under fenced `resume` work (migration 0006) |
| 2c.8a | `8ce2cd7`, `8286e89`, `3e55527`, `381eb3f` | Defaulted effect declarations in readiness, API and CLI evidence and the release report; parked step rows and acceptance transitions |
| 2c.9 | `57269ed`, `87f4407` | Drivers emit action plans; the authored recording `tests/replays/erp-authored-plan-calls/` |
| 2c.8b | `056c143`, `89beea7`, `8bc4a5b`, `4cef608`, `886a1fb`, `5af09cf`, `20c56af`, `dbd1689` | Codex C-1 to C-3 and C2-1, C2-2: call-scoped authority to start a later step; durable step state, and recovery writes no plan state; argument integrity before every reservation; resume items keyed by step and run revision; ADR 0025 resume amendment accepted by the owner |
| 2c.8c | `8d76782`, `81c20ac`, `f9b2d8d`, `5cb733f`, `a87f63e`, `e9610b2` | Reads and answers on an unusable connection, and proposals of an unknown kind, fail closed; a step's approved inputs are bound to the approval digest (P-1, P-3, P-5) |
| 2d.1 | `35ff36a`, `7531592`, `f390d98`, `1ea45e9` | The plan's 2d.1 checklist (`35ff36a`); README toggle and demo, roadmap status, target §6.4 (P-2), ADR 0025 store port note (P-6), wider `pg` gate (P-4), regenerated fixture release report (`7531592`); the README recipe runs under `uv` (`f390d98`); this handoff and the bookkeeping (`1ea45e9`) |

Task-level detail, rulings and evidence: `harness/state/2/handoffs/*.json` and `harness/state/2/reviews/*.json`. The plan and the SDD ledger carry every ruling with its cost if wrong.

## What was verified

Levels 1 to 3 ran on the clean tree at `f390d98`, the head after the 2d.1 docs. All results are fixture evidence (simulator, scripted and authored drivers, memory and test Postgres stores); none is live.

```text
# full  harness/state/evidence/gates/2d.1/2026-10-18T15-32-03.258128+00-00-full.json  (commit f390d98, clean_tree=True)
uv sync --locked                                -> Checked 82 packages in 1ms
uv run ruff check .                             -> All checks passed!
uv run ruff format --check .                    -> 320 files already formatted
uv run mypy                                     -> Success: no issues found in 132 source files
uv run lint-imports                             -> Contracts: 12 kept, 0 broken.
uv run python scripts/export_openapi.py --check -> (no output, exit 0)
uv run pytest -q                                -> 1525 passed, 30 skipped in 59.02s
pnpm --dir ui gen:check                         -> packages/client/openapi.json → packages/client/src/schema.ts [37.1ms]
pnpm --dir ui check                             -> 175 passed; ✓ built in 23ms
uv run python scripts/check_core_only.py        -> core-only check passed in 10.4s

# pg  harness/state/evidence/gates/2d.1/2026-10-18T15-33-22.012579+00-00-pg.json  (commit f390d98, clean_tree=True)
E_AGENT_TEST_STORE=postgres uv run pytest -q tests/unit/kernel tests/conformance tests/unit/adapters/postgres -> 813 passed in 59.66s
  (the harness requires E_AGENT_TEST_PG_DSN and refuses it when it names the same database as E_AGENT_PG_DSN,
   harness/context.toml distinct_databases; the run used database e_agent_test in e-agent-ledger)

# e2e  harness/state/evidence/gates/2d.1/2026-10-18T15-36-01.274698+00-00-e2e.json  (commit f390d98, clean_tree=True)
make e2e -> 150 passed, 4 skipped (1.3m)

# core  harness/state/evidence/gates/2d.1/2026-10-18T15-37-23.573787+00-00-core.json  (commit f390d98, clean_tree=True)
uv run python scripts/check_core_only.py -> core-only check passed in 7.4s
```

The `pg` set now includes `tests/conformance` and `tests/unit/adapters/postgres` (P-4); during the phase the controller ran them by hand outside the gate (HP-6), as the HP-6 notes in the task handoffs record.

`scripts/check_wheels.py` has no gate set (HP-6). It passed by hand on `f390d98` and again on the bookkeeping head, whose code is the same (`harness/state/evidence/manual/2d.1/check-wheels.txt`): every wheel installs and imports from its own dependency closure, installed plugin bytes match the trusted wheel inventories before activation, and the installed demo and the ERP-04 to 08 demos complete outside the repository.

Also on the fixture:
- `scripts/release_report.py`: 21/21 cases passed; `evals/reports/fixture-release.json` now carries `defaulted_declarations` (four `fixture-erp` bindings with a defaulted `idempotency`). It is labelled `environment: fixture` and is not live qualification.
- The README two-step demo, run verbatim: `demo --driver-mode two-step-plan` stops at WAITING_APPROVAL with both steps shown (step 2's `requested_date` from step 1, and the plan digest); with `--approve` one approval dispatches both steps and the run ends `SUCCEEDED (outcome verified)`, "Created and verified draft purchase order PO/FIXTURE/0002."
- The recorded-model replay suite (`tests/unit/server/test_recorded_model_replays.py`, part of the full gate's pytest): 13 passed, none skipped (PR-32).

### Level 4: live check (2d.2, 2026-10-19), labelled live

Live results against the `odoo19-learning` sandbox (bridge 19.0.0.4.0, Postgres ledger `e-agent-ledger`, Ollama driver), run 2026-10-18T23:11Z to 2026-10-19T00:09Z on code equal to `21a675d` (the commits after it touch no `src/`, `addons/` or profile files). They are not fixture results (ENG-EVID-2). Redacted evidence: `harness/state/evidence/live/2d.2-*.json`, `2d.2-sandbox.log` (identity, resets, seeds and the first three Task 3 runs; it stops at `on` try 1) and `2d.2-readiness.txt`.

- **Identity gate** (the harness `live` set): the owner ran it three times before the runs, recorded under task 2d.1 at `21a675d` (`harness/state/evidence/live/2026-10-18T23-*-live.json`), all passing; the 2d.2 contract's own `live` gate passed after the runs on the clean tree at `3aa0c3b` (`harness/state/evidence/gates/2d.2/2026-10-19T00-11-22.739575+00-00-live.json`). `info` reports marker `odoo19-learning`, database `training19_demo`, company 1 "My Company (San Francisco)", bridge `19.0.0.4.0`, server 19.0.1.3. The agent ran `info` again before the first reset, with the same identity.
- **Pins.** The owner re-pinned `domain-erp` and `odoo19` with the pins below; the three toggle profiles carry them (prefixes in `2d.2-readiness.txt`) and start with them.
- **Ledger.** `migrate` applied migration 0006 (resume work) to the live ledger; an idempotent re-run is recorded in `2d.2-readiness.txt`.
- **Readiness**, one `serve` per mode (the responses during the check; re-captured verbatim at 00:13Z in `2d.2-readiness.txt`): `{"status": "ready", "environment": "live", "plugins": ["domain-erp", "odoo19"], "store": "postgres", "self_approval_allowed": true, "features": {"execution_ir": "<mode>"}, "defaulted_declarations": []}` for `off`, `shadow` and `on`. `on` started, so no capability is bound on two connections.
- **Task 3 with a real shortage.** Before each mode the agent reset and seeded the `e-agent-demo` namespace with the identity flags (owner ruling below), which gives demand 12, available 5, inbound 0, shortage 7. Prompt: "Draft a purchase order for any shortage from the approved supplier", approved with `--approve`.

| Mode | Run | Result |
|---|---|---|
| `off` | `2d.2-task3-off-seeded.json` | Draft PO `P00033`, 7 units at 100: validation PASS (PR-001, PR-002), approval, reservation, dispatch COMMITTED, read-back VERIFIED; SUCCEEDED `verified`. The pre-phase path |
| `shadow` | `2d.2-task3-shadow-seeded.json` | `ir.plan_compiled` with `digest_matches: true`; the plan digest equals the approval digest (`jcs-sha256-v1:d59cad9f…`); draft PO `P00034` VERIFIED; SUCCEEDED `verified`, the same outcome as `off`; the bundle has `steps` (the shadow validate step) |
| `on`, try 1 | `2d.2-task3-on-seeded-try1.json` | The model proposed only an offer answer ("does not meet the requested delivery date") and no PO. The run-end acceptance check failed it: FAILED `acceptance_unmet` (KERNEL-ACCEPTANCE). No write |
| `on`, try 2 | `2d.2-task3-on-seeded.json` (not in the sandbox log) | Same seeded shortage (try 1 wrote nothing). A 1-step plan: `ir.plan_compiled`, plan digest equal to the approval digest (`jcs-sha256-v1:18963b7f…`), approval, reservation, dispatch COMMITTED, draft PO `P00035` VERIFIED; SUCCEEDED `verified`. The bundle has `plan` and `steps`: step-1 `validate`, `approval_wait`, `validate` (revalidation), `dispatch` and `verify`, each started and succeeded |

- **Task 1 with `on`** ("Which products are short for open demand?", `2d.2-task1-on.json`, before the reseed): SUCCEEDED `answered`. The model's first answer (shortage -2) failed independent verification; its second, after one more read, was VERIFIED (`procurement.shortage.answer.v1`: demand 12, available 4, inbound 10, shortage 0). Every read the model made is inside the `shortage` definition's capabilities; the evidence records the reads, not the offered tool list.
- **Evidence bundles** contain `features` in every run; the `on` write run also `plan` and `steps`. No credential string appears in them.

Also observed live, before the reseed (sandbox shortage 0; `*-preset.json` with the presets' fixture refs, which Odoo rejects as `E_AGENT_INVALID_REF`, and `2d.2-task3-{off,shadow,on}.json` with the plan's prompt):
- With the plan's prompt the model invented a shortage of 2 in `shadow` and `on` and proposed a 2-unit PO; PR-002 ("quantity must equal the derived shortage") blocked it before approval, and its later wrong answers failed independent verification (FAILED `verification_failed`). No write was sent. `off` ended SUCCEEDED: its first answer (shortage -2) failed independent verification and its second (shortage 0) was VERIFIED.
- These are the live model's behaviour (unqualified for plans; ADR 0010), not toggle effects: the kernel refused or failed each wrong proposal in every mode.

## Phase review

The whole-phase review ran in a fresh Claude context on the branch head after 2c.8b (`harness/state/2/reviews/2d.1-phase.json`): **rework**, eight findings.

| Id | Severity | Finding | Handled |
|---|---|---|---|
| P-1 | Medium | An answer proposal or read on an unusable connection, or an answer with no verifier, raised out of `start_run`; the run was left non-terminal or classified INTERRUPTED | Fixed in 2c.8c (`8d76782`, `a87f63e`) |
| P-2 | Low | Target §6.4.6 lacked the fenced resume work and the VERIFYING-until-startup window | Fixed in 2d.1 (`7531592`); the heading tag became `[I]` at the merge (2d.2) |
| P-3 | Low | A step's integrity check compared with snapshot inputs that nothing tied to `approval.action_digest` | Fixed in 2c.8c (`81c20ac`, `e9610b2`) |
| P-4 | Low | No end-of-phase Postgres evidence for `tests/conformance` and `tests/unit/adapters/postgres` | The `pg` gate set now covers them (`harness/context.toml`, `7531592`); evidence below |
| P-5 | Low | Comments still said "a plan resume is attempted at most once" | Fixed in 2c.8c (`f9b2d8d`) |
| P-6 | Low | The RunStore port gained `put_plan`, `get_plan`, `list_steps` and a wider `EventBatch`; the ADR did not name it | ADR 0025 names it (`7531592`) |
| P-7 | Low | One test was renamed: `test_on_refuses_startup_for_capability_bound_on_two_connections` (`tests/unit/server/test_execution_ir_on_erp.py:145`) | Noted here |
| P-8 | Low | Coverage note: some areas were unverified in the reviewer's frozen copy | Covered by the gate runs below |

**Codex final check of 2c.8b, 2c.8c and the 2d.1 docs** (`harness/state/2/reviews/2d.1-codex-final.json`; Codex session `01a14fc9-dbbc-74c3-9b58-eb9f216b73e3`, on `5d39921..ad54b43`): `{"task": "2d.1", "verdict": "accept", "findings": [], "reviewer": {"provider": "codex", "fresh_context": true}}`. Codex re-checked its earlier findings and reported each fixed. The details below are Codex's own report, recorded verbatim in `harness/state/evidence/manual/2d.1/codex-final-report.json`; they are model output, not gate evidence:

- C-1: concurrent reconciliation sends no later write; the fenced resume claim completes the plan.
- C-2: resume queuing writes no continuation, and completion is read from durable actions.
- C-3: mutation by a validator or after validation, tampered plan inputs and missing plan state all fail STALE before reservation.
- C2-1: STOP authority is call-scoped and does not disable a concurrent fenced resume.
- C2-2: a pending verification is re-queued at startup by action and run revision. An added reproduction with two UNKNOWN writes ended SUCCEEDED with exactly three provider writes for three steps.
- 2c.8c: refusals on an unusable connection or of an unknown capability fail closed, and the worker strands no work.
- `off`: unchanged on the tested success paths (notes and ERP event-stream goldens, approval digests, recovery tests, recorded-model replays).

Limits of that check, as Codex reported them: it ran the memory store only (34 focused tests, 563 kernel, worker and memory-store conformance tests, 17 ERP golden and replay tests); seven `test_registry.py` cases could not set up in its sandbox, which forbids temporary files, and are not evidence either way; it ran no Postgres or live checks. The Postgres and full-suite results above cover those levels.

## Rulings

- **Approval expiry between steps ends STALE**, as on the single-action path (2c.8, `1ea7ffb`). Cost if wrong: a resumed plan would need a fresh approval flow instead of a stale end.
- **Plan resume runs only under fenced `resume` work** keyed by step and run revision; recovery and reconciliation never send a write and write no plan state (C-2 option b). A step still COMMITTED after a claim is re-driven at the next startup (owner ruling 2026-10-18, replacing "at most once"). A takeover at a fence above 1 fails a resumable plan even if the first owner never started (fail-closed, in the ADR amendment). Cost if wrong: a stranded plan waits for the next startup recovery rather than resuming sooner.
- **Authority to start a later step is call-scoped** (`NextStep` START/QUEUE/STOP); only the approval call and the fenced resume claim pass START (Codex C2-1). Cost if wrong: none found; another caller cannot start a step.
- **Argument integrity before every `reserve_operation`**: `KERNEL-ARGUMENTS-CHANGED` for a single action, `KERNEL-PLAN-DIGEST-MISMATCH` for a plan digest recomputed from inputs, failing closed when the plan state is missing; both end STALE. Cost if wrong: one extra `get_plan` read per plan step dispatch in `on`.
- **Refused reads return fixed refusals to the driver** (`CONNECTION_NOT_AVAILABLE`, `READ_NOT_PERMITTED`, `UNKNOWN_CAPABILITY`, `NOT_A_READ_CAPABILITY`); a proposal on an unusable connection or of an unknown kind is a repair finding (`KERNEL-CONNECTION`, `KERNEL-PROPOSAL-KIND`); a missing verifier ends the run VERIFICATION_FAILED (`KERNEL-VERIFIER`). Cost if wrong: a driver sees a refusal code where it saw an exception before.
- **`verified_values` only in `on`**; real versions in the digest; a sentinel version is refused (`KERNEL-PLAN-STEP-UNVALIDATABLE`); a changed stored step ends STALE (`KERNEL-PLAN-STEP-CHANGED`) (2c.7). Cost if wrong: a plan with an unvalidatable step is refused rather than run.
- **§6.4 is tagged `[I]` at the merge** (2d.2): it is implemented and live-checked; its anchor changed to `#64-execution-ir-i` in the ADR index, README and this handoff in the same commit. It is not marked "merged" in that document's sense, because the HLD and MVP design do not restate it yet. Cost if wrong: a later doc pass moves the content into the MVP design.
- **Reset and seed before each Task 3 mode** (owner ruling 2026-10-19): the sandbox had no shortage, so no valid write existed; one mode's draft PO would cover the next mode's shortage. Cost if wrong: three namespace resets in the sandbox, undone by reset, seed and seed-tasks.
- **`on` was run a second time** on the same seeded shortage after try 1 proposed no PO and failed `acceptance_unmet`; both tries are recorded. Cost if wrong: one extra live run; the model's choice, not the kernel, decided try 1.

## Stated limits

- **Fixture evidence only.** Every result above runs on the fixture simulator, the scripted or authored driver and the test stores. No live model has been shown to produce a plan: the plan recording is authored, not captured (2c.9). A qualified model run (ADR 0010) is needed before any claim about model plans.
- **The ERP two-step scenario shows lineage only.** Step 2's lineage value equals the value step 1 proposed, because the simulator echoes it back: two draft POs for one demand, not a procurement scenario (2c.7).
- **Live profiles refuse `budgets.max_admitted_writes > 1`**, so multi-step writes cannot run live until Phase 5.
- **VERIFYING lasts until startup recovery.** A plan run left VERIFYING by an inconclusive verification waits for the next startup; there is no periodic re-drive, as for single actions (2c.8b).
- **Step statuses are only in the evidence bundle.** No API or CLI outcome view lists them yet (2c.8).
- **A provider read returning a mismatched observation still raises FORBIDDEN** out of `_driver_read`; the run is left until recovery, or ends INTERRUPTED in the worker. It is provider-caused and pre-existing (2c.8c R-1).
- **`on` refuses startup for a capability bound on two connections**: answers inherit every connection, and kernel routing for answers is later work (2c.6).
- **The end-to-end write-budget test after a verified write** stays unreachable until a driver turn may follow a write (2c.8a); the budget is tested at `_plan_findings`.
- **The evidence bundle lists the exporting runtime's current admission report**, not the one in force at the run's admission (2c.8a R-4).
- **The memory store's continuation save and load share nested data** (test store only; 2c.8b).

## Plugin pins for the owner's re-pin

Wheels built twice at `ad54b43` with the same result, version 0.1.0; each pin is `scripts/plugin_inventory.py` on the built wheel (`harness/state/evidence/manual/2d.1/plugin-pins.json`). Regenerating them before the re-pin is cheap: `uv build --package e-agent-domain-erp --wheel` (and `e-agent-adapter-odoo`), then `uv run python scripts/plugin_inventory.py <wheel>`. `f390d98` changed only `README.md`, which is in no plugin wheel. The pins change only if a later commit touches `src/e_agent/plugins/erp/**`.

| Plugin | `artifact_sha256` |
|---|---|
| `domain-erp` | `c4e89bfb124105487861d86d454c04eff5384711e472239dc70a0a7a8e89050e` |
| `odoo19` | `5976460ec47f273d9136c526c1e51dcc1af06988bc4331778ef62cd5d76c09e0` |
| `fixture-erp` | `3ad0cc7c03979179afdd9eb3f560c084ce492a4424d0851532e66ad31a16b50c` |

The live profile does not enable `fixture-erp`, so only the first two go into `profiles/live-odoo19-learning.local.json`.

## Open items for the owner

1. Branch protection on `main` (PR-39): the agent's GitHub call was refused by its permission classifier, so it is the owner's (command in the session).
2. The sandbox is left with the `on` run's draft PO `P00035` and without the task fixtures of `seed-tasks`, which the first reset removed. Undo: `odoo_sandbox.py reset`, `seed`, then `seed-tasks`, each with `--namespace e-agent-demo --expected-marker odoo19-learning --expected-company-id 1 --expected-bridge-version 19.0.0.4.0`. The reseed gives new record ids (demand `odoo/e_agent.demand/4` now); profile refs that name the old ids are stale.
3. What remains after Phase 2: plan approval in the UI (the API and UI show the plan's presentation fields but resolve no task definition, D8), live multi-step writes (Phase 5), a qualified model run for plans (ADR 0010), and the Phase 3 plan.
4. `golden/off_model_request.json` serialises pydantic-ai's `ToolDefinition`; a pydantic-ai upgrade needs it regenerated at a baseline commit (2c.9).
5. Delete the temporary toggle profiles `profiles/live-ir-{off,shadow,on}.local.json` when no longer needed (git-ignored, mode 0600).

## Changes outside the repository

| Change | Undo |
|---|---|
| The `pg` runs truncated only the `e_agent_test` database in `e-agent-ledger` | none needed |
| PR #6 pushed, updated with `main` and merged on the owner's instruction | revert the merge commit |
| `profiles/live-odoo19-learning.local.json` re-pinned by the owner; `profiles/live-ir-{off,shadow,on}.local.json` created (copies with the toggle set) | delete the three copies |
| Live ledger: migration 0006 applied; the 2d.2 runs added | none needed; forward-only migration, normal run history |
| Sandbox `e-agent-demo`: reset and seeded three times (identity-checked); draft POs `P00033` and `P00034` created and removed by the next reset; `P00035` left; task fixtures removed | reset, seed, seed-tasks (open item 2) |
