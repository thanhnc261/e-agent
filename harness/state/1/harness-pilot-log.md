# Harness pilot log: roadmap Phase 1

Harness plan H5 pilots the session loop on a real phase. This log records every place where the harness got in the way, misled, or failed to catch something during Phase 1, so that the harness can be improved. One row per issue; the task column names where it was first seen.

Severity: **high** = can let a wrong result pass or block a correct one; **medium** = costs a rework round or a manual workaround; **low** = friction or noise.

| Id | Task | Severity | Issue | Workaround used | Proposed fix |
|---|---|---|---|---|---|
| HP-1 | 1a.1 | low | `new-task` writes duplicate globs into `allowed_paths` when an explicit `--paths` value is also implicit (`docs/handoffs/**` appeared twice). | none needed | dedupe in `tasks.materialise`: `list(dict.fromkeys([...]))`. |
| HP-2 | 1a.1 | medium | Right after `new-task`, `status` says "commit the work, then run gate full", because the only dirty files are the new contract and `active.json`. No work exists yet. | ignored the next action until the work was done | the next action should take into account that only harness bookkeeping is dirty, for example "commit the contract, then do the work". |
| HP-3 | 1a.1 | medium | After `close-check` prints "ok: task may close", `status` still says "run checkpoint, write the handoff, then close-check". There is no closed state and no command that deactivates the task. | ignored | add `close` (or let `close-check` mark the contract closed), and make `status` say "pick the next feature" for a closed task. |
| HP-4 | 1a.1 | high | `evidence/` is git-ignored, but feature `evidence` and handoff `evidence_refs` must point under it, and `close-check` tests that the files exist. In a fresh clone or another worktree (the context strategy's parallel tasks), every closed task fails `close-check`. The plan's "must be identical" reference would also exist on one machine only. | committed the key numbers and a diffable reference under `docs/handoffs/` | either commit gate evidence JSON (small, already redacted) or let `close-check` accept a committed digest of the evidence file in place of the file itself. |
| HP-5 | 1a.1 | low | No CLI command validates `features.json`. `handoff <id>` exists, but the feature list needs `python -c "...contracts.validate('features', ...)"`. | the python one-liner | add `validate <schema> <file>` or `features check <phase>`. |
| HP-6 | 1a.1 | medium | A contract has one `gate_set`, but the phase plan requires several per task (full, plus the Postgres run and `make e2e`). The plan's Postgres-after-every-task rule conflicts with its container boundary, and nothing flagged it. | ran `make e2e` by hand; ruled that the Postgres run is deferred to 1c.11 | let `gate_set` be a list, and let `validate-context` or `new-task` warn when a plan's required gate needs an environment the boundaries forbid. |
| HP-7 | 1a.1 | low | `check-scope` prints nothing on success, so a transcript cannot show it ran (the unattended `/goal` evaluator judges only the transcript). | none | print "ok: N changed paths inside scope". |
| HP-8 | 1a.2 | medium | A contract copies its feature's `steps` into `acceptance` when it is created. When the feature list changes later, nothing refreshes or flags the stale copy. | re-ran `new-task --replace` after editing the steps | pin a digest of the feature entry in the contract; have `status` and `close-check` report "acceptance changed since materialisation". |
| HP-9 | 1a.2 | medium | Confirms HP-3: after `close-check` printed ok for 1a.1, `new-task` refused with "task 1a.1 is active; finish it with close-check or pass --replace". `close-check` passing does not count as finished. | `--replace` | `new-task` should accept a task whose last `close-check` passed, or `close-check` should mark the contract closed. |
| HP-10 | 1a.2 | medium | The active plan is an implicit allowed path of every task, but it is also part of the context digest. Recording a plan deviation mid-task, which roadmap rule 2 asks for, marks the task's own contract stale and forces `new-task --replace`. That also resets `base_commit`. | committed, then re-materialised | exclude the active plan's own task section from the digest, or let `new-task --refresh` update the digest without moving `base_commit`. |
| HP-11 | 1a.3 | low | Adding one allowed path mid-task (`scripts/repo_move.py`, for a false positive in its own check) needs `new-task --replace` with every `--paths` repeated, which also resets `base_commit` while the move sits uncommitted. | `--replace` with the full path list | add `amend-scope --add <glob>`, recorded in the contract with a reason. |
| HP-12 | 1a.3 | high | The `full` gate set has no UI unit tests (`pnpm --dir ui test`, vitest) and no UI type check. During the move, `ui/packages/ui-core/test/digest.test.ts` reads the Python golden vectors by relative path. It would have broken while `gate full` stayed green; it was caught only by `repo_move.py check` and a manual vitest run. | ran `pnpm test` by hand | add `pnpm --dir ui test` (and the UI typecheck) to `[gates].full`, or add a `ui` gate set that contracts touching `ui/**` must include. |
| HP-13 | 1c.11 | high | The `pg` gate in `harness/context.toml` sets `E_AGENT_TEST_PG_DSN=$E_AGENT_PG_DSN`. The Postgres tests call `truncate_for_tests()`, which truncates runs, events, actions, reservations and approvals. With `~/.config/e-agent/live.env` sourced, as the README's live section instructs, `gate pg` would wipe the live ledger. | ran the Postgres suite against a separate `e_agent_test` database in the `e-agent-ledger` container | give the `pg` gate its own variable (`E_AGENT_TEST_PG_DSN`), and have the gate, or `truncate_for_tests`, refuse when the test DSN names the same database as `E_AGENT_PG_DSN`. |
| HP-14 | 1c.11 | low | The whole-branch review at the end of a phase has no place in the loop. Its fixes need a feature id, but the feature list holds only plan tasks, so a review-fix entry had to be added by hand (`F-1-R1`). | added the entry and a task `1.R1` | add a standard per-phase `review` feature, or a `new-task --review` mode that creates one. |

## Resolution (harness H2.1, 2026-10-13)

Fixed on branch `harness/h21-cli-fixes` ([plan](../../../docs/plans/2026-10-13-harness-h21-cli-fixes.md), [handoff](../../../docs/handoffs/2026-10-13-harness-h21.md)).

| Id | Resolution | Commit |
|---|---|---|
| HP-1 | `new-task` de-duplicates `allowed_paths`. | `02c4d96` |
| HP-2 | `status` asks to commit the harness bookkeeping when only the new contract is dirty, and names the first acceptance step. | `7ccc43c` |
| HP-3 | A task whose `close-check` passes is closed; `status` says so and names the next unfinished feature. | `a7665ef` |
| HP-4 | Gate and live evidence are written under `harness/state/evidence/` and committed with the bookkeeping; `close-check` passes in a fresh clone. Old `evidence/…` references still validate. | `7ccc43c` |
| HP-5 | `validate <schema> <file>`. | `b84fe8c` |
| HP-6 | Open: a contract keeps one gate set; `eng-verify` orders the other levels. | — |
| HP-7 | `check-scope` prints `ok: N changed paths inside scope`. | `a7665ef` |
| HP-8 | A contract pins a digest of its feature entries; `status` and `close-check` report drift; `refresh-task --from-features` re-derives acceptance. | `02c4d96` |
| HP-9 | `new-task` follows a closed task without `--replace`. | `a7665ef` |
| HP-10 | `refresh-task` renews the digests without moving the base commit, creation time or scope; it is the remedy `status` names for a stale digest. | `02c4d96` |
| HP-11 | `amend-scope --add <glob> --reason <why>` records the change in the contract's `scope_changes`. | `02c4d96` |
| HP-12 | `gate full` and a new `ui` set run `pnpm --dir ui check`. Running it found a provider identifier in a UI test that had been red on `main` since 89b2b1e; fixed in `8ae3413`. | `5145fb0` |
| HP-13 | The `pg` gate no longer aliases the live DSN; `[gate_guards.pg]` requires `E_AGENT_TEST_PG_DSN` and refuses when it names the same host, port and database as `E_AGENT_PG_DSN`. | `38ef5fb` |
| HP-14 | `add-feature` appends a validated entry, so a phase-review fix gets its feature id by command. | `b84fe8c` |

## Carried to harness plan H5 (Phase 1d, 2026-10-16)

| Id | State | Seen again |
|---|---|---|
| HP-6 | Open, carried to the H5 backlog ([Phase 1d plan](../../../docs/plans/2026-10-14-phase1d-plugin-boundary.md) D5; plugin boundary review R-8). A contract still holds one gate set, so a task whose plan asks for `full`, `pg`, `e2e` and `core` runs the extra sets as their own `gate` commands and cites their evidence in the handoff. | 1d.8 (`full` and `core`), 1d.10 (`full`, `core`, `pg`, `e2e` and `check_wheels.py` by hand) |
| HP-13 | Resolved by `[gate_guards.pg]` and `[gate_guards."*"]` in `harness/context.toml` (H2.1 `38ef5fb`); the 1d.10 `pg` run used `E_AGENT_TEST_PG_DSN` on `e_agent_test` with `E_AGENT_PG_DSN` unset. | — |

