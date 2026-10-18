# Phase 2: execution IR (2026-10-18)

## Summary

- **Plan:** [Phase 2 plan](../plans/2026-10-14-phase2-execution-ir.md), Parts 2a to 2d; [roadmap](../roadmap.md) row 2; [ADR 0024](../adr/0024-plan-approval-model.md), [ADR 0025](../adr/0025-execution-ir.md), [ADR 0027](../adr/0027-feature-toggles.md), [ADR 0028](../adr/0028-task-definitions.md) and [ADR 0029](../adr/0029-capability-effect-declarations.md); [target architecture §6.4](../design/target-architecture.md#64-execution-ir-p).
- **Branch:** `phase2/execution-ir`, cut from `main` at `6f7ec70`. Pushed to draft PR #6 on the owner's instruction; not merged.
- **Execution:** the development harness ran every task, 2a.1 to 2c.9 (with the inserted 2c.5a and 2c.8a to 2c.8c) and 2d.1, through contract, `check-scope`, gate evidence on a clean commit, feature flip, handoff and `close-check`. Every task has committed review records in `harness/state/2/reviews/`: Codex for 2b.1 to 2b.3, 2c.1, 2c.5a, 2c.6, 2c.8 (re-check), 2c.8b (partial), 2c.9 and the final check of 2c.8b and 2c.8c (accept, below); Claude reviewers for the others and for the scoped re-reviews after fixes. The whole-phase review ran in a fresh Claude context (`2d.1-phase.json`, eight findings, below).
- **Result:** behind the profile toggle `features.execution_ir` (`off` by default), a run's tools come from the admitted task definition, a validated proposal runs as a 1-step plan with the same approval digest as today, and a multi-step plan is approved once and dispatched step by step. Each step is re-validated, its arguments re-checked against the approved digest and its outcome independently verified before the next step starts. `off` is byte-identical to the pre-phase behaviour on the recorded goldens (event types, transitions, states, digests and payload key sets). All of it is fixture evidence. The live check 2d.2 is the owner's.

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
| 2d.1 | `35ff36a`, `7531592`, `f390d98` | Docs: README toggle and demo, roadmap, target §6.4 (P-2), ADR 0025 store port note (P-6), wider `pg` gate (P-4), regenerated fixture release report |

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
  (E_AGENT_TEST_PG_DSN on database e_agent_test in e-agent-ledger; E_AGENT_PG_DSN unset)

# e2e  harness/state/evidence/gates/2d.1/2026-10-18T15-36-01.274698+00-00-e2e.json  (commit f390d98, clean_tree=True)
make e2e -> 150 passed, 4 skipped (1.3m)

# core  harness/state/evidence/gates/2d.1/2026-10-18T15-37-23.573787+00-00-core.json  (commit f390d98, clean_tree=True)
uv run python scripts/check_core_only.py -> core-only check passed in 7.4s
```

The `pg` set now includes `tests/conformance` and `tests/unit/adapters/postgres` (P-4); during the phase they ran by hand outside the gate (HP-6), as each task handoff records.

`scripts/check_wheels.py` has no gate set (HP-6). It passed by hand on `f390d98`: every wheel installs and imports from its own dependency closure, installed plugin bytes match the trusted wheel inventories before activation, and the installed demo and the ERP-04 to 08 demos complete outside the repository.

Also on the fixture:
- `scripts/release_report.py`: 21/21 cases passed; `evals/reports/fixture-release.json` now carries `defaulted_declarations` (four `fixture-erp` bindings with a defaulted `idempotency`). It is labelled `environment: fixture` and is not live qualification.
- The README two-step demo, run verbatim: `demo --driver-mode two-step-plan` stops at WAITING_APPROVAL with both steps shown (step 2's `requested_date` from step 1, and the plan digest); with `--approve` one approval dispatches both steps and the run ends `SUCCEEDED (outcome verified)`, "Created and verified draft purchase order PO/FIXTURE/0002."
- The recorded-model replay suite (`tests/unit/server/test_recorded_model_replays.py`, part of the full gate's pytest): 13 passed, none skipped (PR-32).

### Level 4: live check

Not run. It is Task 2d.2, the owner's, through `live-sandbox` (open items below).

## Phase review

The whole-phase review ran in a fresh Claude context on the branch head after 2c.8b (`harness/state/2/reviews/2d.1-phase.json`): **rework**, eight findings.

| Id | Severity | Finding | Handled |
|---|---|---|---|
| P-1 | Medium | An answer proposal or read on an unusable connection, or an answer with no verifier, raised out of `start_run`; the run was left non-terminal or classified INTERRUPTED | Fixed in 2c.8c (`8d76782`, `a87f63e`) |
| P-2 | Low | Target §6.4.6 lacked the fenced resume work and the VERIFYING-until-startup window | Fixed in 2d.1 (`7531592`). The `[P]` tag stays in the heading, since the ADR index links that anchor; the status line says what is implemented |
| P-3 | Low | A step's integrity check compared with snapshot inputs that nothing tied to `approval.action_digest` | Fixed in 2c.8c (`81c20ac`, `e9610b2`) |
| P-4 | Low | No end-of-phase Postgres evidence for `tests/conformance` and `tests/unit/adapters/postgres` | The `pg` gate set now covers them (`harness/context.toml`, `7531592`); evidence below |
| P-5 | Low | Comments still said "a plan resume is attempted at most once" | Fixed in 2c.8c (`f9b2d8d`) |
| P-6 | Low | The RunStore port gained `put_plan`, `get_plan`, `list_steps` and a wider `EventBatch`; the ADR did not name it | ADR 0025 names it (`7531592`) |
| P-7 | Low | One test was renamed: `test_on_refuses_startup_for_capability_bound_on_two_connections` (`tests/unit/server/test_execution_ir_on_erp.py:145`) | Noted here |
| P-8 | Low | Coverage note: some areas were unverified in the reviewer's frozen copy | Covered by the gate runs below |

**Codex final check of 2c.8b, 2c.8c and the 2d.1 docs** (`harness/state/2/reviews/2d.1-codex-final.json`; Codex session `01a14fc9-dbbc-74c3-9b58-eb9f216b73e3`, on `5d39921..ad54b43`): `{"task": "2d.1", "verdict": "accept", "findings": [], "reviewer": {"provider": "codex", "fresh_context": true}}`. Codex re-checked its earlier findings and reported each fixed:

- C-1: concurrent reconciliation sends no later write; the fenced resume claim completes the plan.
- C-2: resume queuing writes no continuation, and completion is read from durable actions.
- C-3: mutation by a validator or after validation, tampered plan inputs and missing plan state all fail STALE before reservation.
- C2-1: STOP authority is call-scoped and does not disable a concurrent fenced resume.
- C2-2: a pending verification is re-queued at startup by action and run revision. An added reproduction with two UNKNOWN writes ended SUCCEEDED with exactly three provider writes for three steps.
- 2c.8c: refusals on an unusable connection or of an unknown capability fail closed, and the worker strands no work.
- `off`: unchanged on the tested success paths (notes and ERP event-stream goldens, approval digests, recovery tests, recorded-model replays).

Limits of that check, as Codex stated them: it ran the memory store only (34 focused tests, 563 kernel, worker and memory-store conformance tests, 17 ERP golden and replay tests); seven `test_registry.py` cases could not set up in its sandbox, which forbids temporary files, and are not evidence either way; it ran no Postgres or live checks. The Postgres and full-suite results above cover those levels.

## Rulings

- **Approval expiry between steps ends STALE**, as on the single-action path (2c.8, `1ea7ffb`). Cost if wrong: a resumed plan would need a fresh approval flow instead of a stale end.
- **Plan resume runs only under fenced `resume` work** keyed by step and run revision; recovery and reconciliation never send a write and write no plan state (C-2 option b). A step still COMMITTED after a claim is re-driven at the next startup (owner ruling 2026-10-18, replacing "at most once"). A takeover at a fence above 1 fails a resumable plan even if the first owner never started (fail-closed, in the ADR amendment). Cost if wrong: a stranded plan waits for the next startup recovery rather than resuming sooner.
- **Authority to start a later step is call-scoped** (`NextStep` START/QUEUE/STOP); only the approval call and the fenced resume claim pass START (Codex C2-1). Cost if wrong: none found; another caller cannot start a step.
- **Argument integrity before every `reserve_operation`**: `KERNEL-ARGUMENTS-CHANGED` for a single action, `KERNEL-PLAN-DIGEST-MISMATCH` for a plan digest recomputed from inputs, failing closed when the plan state is missing; both end STALE. Cost if wrong: one extra `get_plan` read per plan step dispatch in `on`.
- **Refused reads return fixed refusals to the driver** (`CONNECTION_NOT_AVAILABLE`, `READ_NOT_PERMITTED`, `UNKNOWN_CAPABILITY`, `NOT_A_READ_CAPABILITY`); a proposal on an unusable connection or of an unknown kind is a repair finding (`KERNEL-CONNECTION`, `KERNEL-PROPOSAL-KIND`); a missing verifier ends the run VERIFICATION_FAILED (`KERNEL-VERIFIER`). Cost if wrong: a driver sees a refusal code where it saw an exception before.
- **`verified_values` only in `on`**; real versions in the digest; a sentinel version is refused (`KERNEL-PLAN-STEP-UNVALIDATABLE`); a changed stored step ends STALE (`KERNEL-PLAN-STEP-CHANGED`) (2c.7). Cost if wrong: a plan with an unvalidatable step is refused rather than run.
- **The §6.4 heading keeps `[P]`** because `docs/adr/README.md` links `#64-execution-ir-p`; the status line carries the state (2d.1). Cost if wrong: a reader skimming headings sees "proposal"; the anchor is renamed at merge.

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

Wheels built twice at `ad54b43`, with the same result, version 0.1.0 (`scripts/plugin_inventory.py`). `f390d98` changed only `README.md`, which is in no plugin wheel. The pins change only if a later commit touches `src/e_agent/plugins/erp/**`.

| Plugin | `artifact_sha256` |
|---|---|
| `domain-erp` | `c4e89bfb124105487861d86d454c04eff5384711e472239dc70a0a7a8e89050e` |
| `odoo19` | `5976460ec47f273d9136c526c1e51dcc1af06988bc4331778ef62cd5d76c09e0` |
| `fixture-erp` | `3ad0cc7c03979179afdd9eb3f560c084ce492a4424d0851532e66ad31a16b50c` |

The live profile does not enable `fixture-erp`, so only the first two go into `profiles/live-odoo19-learning.local.json`.

## Open items for the owner

1. Re-pin `domain-erp` and `odoo19` in `profiles/live-odoo19-learning.local.json` with the pins above (`draft-po.json` and the ERP capability declarations changed).
2. Run the live check 2d.2 on `odoo19-learning` through the `live-sandbox` skill, as the plan's "Live check" section states: `/health/ready` reports `features.execution_ir` for each mode used; Task 3 ("Draft a purchase order for any shortage from the approved supplier") once each with `off`, `shadow` and `on`, through the CLI (`--task <kind>`), since API and UI runs resolve no task definition in Phase 2 (D8); Task 1 with `on`; each evidence bundle contains `features`, and the `on` runs also `plan` and `steps`. Before the `on` legs, check one possible surprise: `on` refuses startup when a capability is bound on two connections (2c.6), and the agent could not read the live profile to check its bindings.
3. Branch protection on `main` (PR-39).
4. Merge PR #6 when 2d.2 passes. At merge, §6.4 of the target architecture becomes merged and its `[P]` tag and the ADR index anchor change together.
5. What remains after Phase 2: plan approval in the UI (the API and UI show the plan's presentation fields but resolve no task definition, D8), live multi-step writes (Phase 5) and the Phase 3 items in the roadmap.
6. `golden/off_model_request.json` serialises pydantic-ai's `ToolDefinition`; a pydantic-ai upgrade needs it regenerated at a baseline commit (2c.9).

## Changes outside the repository

| Change | Undo |
|---|---|
| The `pg` runs truncated only the `e_agent_test` database in `e-agent-ledger` | none needed |
| Draft PR #6 opened and `phase2/execution-ir` pushed on the owner's instruction | close the PR, delete the remote branch |
