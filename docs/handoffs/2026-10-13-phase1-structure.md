# Phase 1: structure refactor (2026-10-13)

## Summary

- **Plan:** [Phase 1 plan](../plans/2026-10-12-phase1-structure-refactor.md); [roadmap](../roadmap.md) Phase 1.
- **Branch:** `refactor/phase1-structure`, cut from `main` at `ebfcf70`. Not merged, not pushed.
- **Execution:** the development harness ran every one of the 19 tasks: task contract, `check-scope`, gate evidence, feature flip, handoff and `close-check`. Tasks with code had a subagent review. The feature list is `harness/state/1/features.json`, and all 19 entries pass with gate evidence. The per-task handoffs are in `harness/state/1/handoffs/`.
- **Result:** no behaviour change. The full gate passes on every task. The wheels hold the same files, entry points and dependencies as before. The plugin pins are byte-identical. The live flows match the 2026-10-12 baseline; Flow 3 varies on live model runs, and it varies the same way on `main`.

## What changed

| Part | Change |
|---|---|
| 1a | All Python code is one tree, `src/e_agent/{contracts,sdk,kernel,erp,adapters/*,server}`. The 135 code and test files moved as exact renames (R100). Each of the 10 distributions has `dists/<name>/pyproject.toml` (hatchling). A shared hook, `dists/_hooks/src_tree.py`, builds wheels from `src/`, keeps editable installs importing from `src/`, and refuses sdists. Tests are in `tests/unit/<part>/`. `scripts/repo_move.py` does the moves (`layout`, `links`, `check`). `.vscode/settings.json` hides caches. |
| 1b | The designs are in `docs/design/`, the plans in `docs/plans/` and the specs in `docs/specs/`; `docs/superpowers/` is gone. `AGENTS.md` gains "How work is done", "Repository map" and "Environment boundaries". `CLAUDE.md` is short and Claude-specific. README points to the roadmap. Target-architecture §15 and §16 and MVP design §3 describe the new layout. |
| 1c | `kernel/coordinator.py` shrinks from 1,827 lines to a 190-line `RunCoordinator` facade over nine mixin modules: `continuation`, `transitions`, `run_loop`, `gateway`, `proposals`, `approval_flow`, `dispatch`, `verification`, `recovery`. All 43 methods are byte-identical and each is defined once. `server/api.py` (764 → 545 lines) moves its work loop into `worker.py` (`WorkerMixin`) and its text bus into `streaming.py`. Fitness tests check that every method is defined once, that every kernel module is at most 500 lines, and that each type-checking stub matches one real method. A new import contract lets only the facade import `coordinator`. |

## What was verified

- **Gate per task (`gate full`):** passed on a clean tree for every task, including the review-fix task `1.R1`. Pytest went from 572 passed / 30 skipped at the baseline to 635 passed / 30 skipped at `1.R1`: 572 − 13 + 76 = 635.
  - **+76 new tests:** 13 for the mover, 13 for the layout, and 50 structure and fitness tests (27 at 1c.1, 22 at 1c.9, 1 at 1c.11).
  - **−13 from a fixed collision.** Before the move, `packages/kernel/tests` and `packages/plugin-sdk/tests` both imported as `tests.test_discovery`. The full suite ran kernel's 16 discovery tests twice and never ran the sdk's 3.
- **`make e2e`:** 150 passed / 4 skipped at the baseline, after 1a.3, and after 1c.10.
- **Wheels:**
  - `check_wheels.py` passes at the baseline, after 1a.3 and at 1c.11.
  - Against the [1a.1 wheel reference](2026-10-13-phase1-1a1-wheel-reference.txt), every wheel has the same files and entry points. Requires-Dist is identical as parsed requirements; hatchling writes the specifiers in canonical order.
  - `manifest_sha256` and `artifact_sha256` for `domain-erp` and `odoo19` are byte-identical, and they match the pins in the live profile, so no re-pin was needed.
- **Postgres:** 218 passed, 0 skipped. This covers the kernel suite on the Postgres store, run-store conformance, migrations and process recovery. They ran against a separate `e_agent_test` database in the `e-agent-ledger` container, never the live ledger (see HP-13).
- **Live, `odoo19-learning` (bridge 19.0.0.4.0, Postgres ledger, Ollama):**

| Flow | Baseline 2026-10-12 | Phase 1 branch | Pre-refactor `main` (control) |
|---|---|---|---|
| 1 (API): "hi" → "Which products are short for open demand?" | SUCCEEDED `answered` | SUCCEEDED `answered`: reply, WAITING_INPUT, follow-up, reads, verified answer | not rerun |
| 3: "Draft a purchase order for any shortage from the approved supplier" | SUCCEEDED; no write | 1 of 3 SUCCEEDED `answered`; 2 FAILED `verification_failed` | 2 of 3 SUCCEEDED; 1 FAILED `verification_failed` |
| 4: "Check demand demand-123" | SUCCEEDED `answered`; `read.rejected E_AGENT_INVALID_REF` | the same | not rerun |
| UI: "hi" → shortage question | Completed · verified, 8/8 checks | Completed · verified, 8/8 checks; reply shown once with its label; "E-Agent Widget A" | not rerun |

  Flow 3 failures are model variance, and the trust anchor holds in every run:
  - The two failing runs on the branch have the same event shape as the failing run on `main`: 9 reads, 4 proposals, 3 validations and 2 outcomes.
  - In every run, rule PR-002 blocked purchase-order proposals for 2 units, since the derived shortage is 0.
  - No write reached approval.
  - Where the model's final answer claimed a shortage of 2, independent read-back verification rejected it.

  The Odoo sandbox was only read; no approval was given. Evidence is in `evidence/1c/live/` (git-ignored).

## Rulings

Each task handoff states its rulings with cost-if-wrong. The ones that change the plan's text are recorded in the plan's execution notes:
- The layout move runs in 1a.3 together with the tooling.
- The plan's static `force-include` copied every package into site-packages and shadowed `src/`, so a shared build hook replaces it. `uv_build` cannot build outside its project directory.
- The build is wheel-only; sdists are refused.
- `[tool.ruff] src = ["."]` keeps imports byte-identical.
- `research/` stays read-only, so four of its links to moved designs stay broken.
- In the kernel split, `ContinuationMixin` is the base, with `TYPE_CHECKING` stubs for calls between mixins. The `LOG` names `e_agent.kernel.coordinator` and `e_agent.server.api` are kept.
- One annotation changed: `_GatewayReader` now names its coordinator argument as the base class.
- The SSE route stays in `create_app`, because it is a closure.
- The Postgres run was deferred to 1c.11, the only task in which the plan allows containers.

## Open items

- **Owner decisions:**
  - Merge `refactor/phase1-structure`.
  - Allow a link-only rewrite of `research/` (4 broken links to moved designs).
  - Review the reworded `AGENTS.md` and `CLAUDE.md`.
- **Harness:** the [pilot log](../../harness/state/1/harness-pilot-log.md) has 14 findings, HP-1 to HP-14. Three are high:
  - **HP-13** needs action before anyone runs `gate pg`. The `pg` gate points the truncating test suite at the live ledger DSN. Make it read `$E_AGENT_TEST_PG_DSN`, and refuse when that names the same database as `E_AGENT_PG_DSN`.
  - **HP-4:** evidence is git-ignored, but `close-check` requires the files.
  - **HP-12:** gate `full` lacks the UI unit tests. Most of the others are about task lifecycle: closed state, scope amendment, refreshing the digest when the plan changes, and multiple gate sets.
- **Branch review (after 1c.11, task `1.R1`):** fixed four findings:
  - `layout` drops the caches that `git mv` carried along; their compiled paths named the old tree.
  - The `api.py` and `coordinator.py` line citations in target-architecture are function references now.
  - A test keeps the mover's hook copy equal to `dists/_hooks/src_tree.py`.
  - A dead `docs/superpowers/` prefix is gone.

  Kept as rulings:
  - `dev-mode-dirs` exposes the whole `src/` tree in a lone editable install. Wheels and import contracts still enforce dependency closure.
  - The mixins-plus-stubs design; collaborators can replace it later (SR-06).
  - `[tool.ruff] src = ["."]`. Re-sorting imports into first-party groups is a style-only follow-up of about 48 files.
  - The preserved logger names.
- **Unchanged from before:** live release qualification is still NOT_READY. Phase 1 changed structure, not readiness.

## Changes outside the repository

| Change | Undo |
|---|---|
| Created database `e_agent_test` in the `e-agent-ledger` container, for the Postgres test suite | `docker exec e-agent-ledger psql -U <user> -d postgres -c "DROP DATABASE e_agent_test"` |
| Live runs from the check added run records to the live ledger (9 runs: 6 on the branch including the UI run, 3 on `main`) | none needed; they are normal run history |
| Started and stopped `e-agent-ledger` (found stopped, left stopped) | none |
