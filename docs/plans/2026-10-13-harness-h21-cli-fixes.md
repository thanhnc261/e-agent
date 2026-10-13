# Harness H2.1: CLI fixes from the Phase 1 pilot

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** fix the harness defects the Phase 1 pilot recorded, so that the next phase runs the session loop without workarounds: no ledger-wiping `pg` gate, evidence that survives a clone, a UI gate, a closed state, and commands for the scope and feature edits that needed `--replace` or hand-written JSON.

**Architecture:** changes stay inside `tools/harness/` (CLI, manifest, schemas), `harness/context.toml`, `tests/harness/`, `tests/conformance/test_harness_context.py`, and the `eng-*` skill text that documents the workarounds. Behaviour changes are additive where old state exists: old `evidence/…` references keep validating, old contracts without the new optional fields keep loading.

**Tech Stack:** Python 3.12 stdlib, `jsonschema` (already a dependency), pytest scratch-repository fixture from H2.

**Spec:** [harness plan](2026-10-12-dev-harness.md) H2 and the session loop; the Phase 1 [pilot log](../../harness/state/1/harness-pilot-log.md) rows HP-1 to HP-14; [H3 handoff](../handoffs/2026-10-13-harness-h3.md) deferred list.

## Global Constraints

- **Branch** `harness/h21-cli-fixes`, stacked on `refactor/phase1-structure` (Phase 1 complete) with the H3 commits cherry-picked; trailer `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- **No product code changes.** The product helper `truncate_for_tests` is not touched; HP-13 is guarded in the harness, and a product-side guard is an open item.
- **Test first** for every behaviour change; `set -o pipefail` on every gate chain.
- **Gate after every task:** `uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run lint-imports && uv run pytest -q tests/harness tests/conformance && uv run python scripts/check_agent_skills.py`.
- **No container is touched**; the `pg` guard is tested with fake DSNs.
- H2.1 changes the harness itself, so it runs outside the harness task loop (the tool would judge its own changes mid-flight); the full gate and a final review stand in.

## Review Focus

1. **A test DSN and the live DSN that name the same database in different spellings** (URL versus keyword form, default port omitted). The guard must compare host, port and database name, not strings. Test: Task 1, `test_pg_guard_compares_parsed_databases`.
2. **A gate run while an earlier gate's evidence file is still uncommitted.** The second run must still record `clean_tree: true` when no code changed. Test: Task 2, `test_second_gate_ignores_uncommitted_evidence`.
3. **A fresh clone closes a task** whose evidence was recorded elsewhere. Test: Task 2, `test_close_check_passes_in_a_fresh_clone`.
4. **Old state:** a feature citing `evidence/gates/…` and a contract without the new optional fields still validate and load. Tests: Task 2 and Task 5.
5. **`new-task` after a task closed** must not need `--replace`, and must still refuse while the active task is not closed. Test: Task 3.

---

### Task 1: `pg` gate guard (HP-13, high)

**Files:** `manifest.py` (new `[gate_guards.<set>]` table), `gate.py` (`check_guards`), `harness/context.toml`, `tests/harness/test_gate.py`, `tests/conformance/test_harness_context.py`.

**Interfaces:** `manifest.GateGuard(require_env: tuple[str, ...], distinct_databases: tuple[tuple[str, str], ...])`; `Manifest.gate_guards: dict[str, GateGuard]`; `gate.database_identity(dsn: str) -> tuple[str, int, str]` (host, port, database; URL or keyword form; default host `localhost`, port `5432`); `gate.check_guards(m, set_name, env) -> list[str]`; `run_gate` raises `ValueError("gate <set> refused: …")` before running any command.

- [ ] Failing tests: `test_pg_guard_refuses_missing_test_dsn`, `test_pg_guard_refuses_same_database`, `test_pg_guard_compares_parsed_databases` (URL vs `host=… dbname=…`, omitted port), `test_pg_guard_allows_distinct_databases` (runs and writes evidence), `test_real_manifest_pg_gate_is_guarded` (conformance: the `pg` set does not mention `E_AGENT_PG_DSN`, and its guard requires `E_AGENT_TEST_PG_DSN` distinct from `E_AGENT_PG_DSN`).
- [ ] Implement; manifest `pg = ["E_AGENT_TEST_STORE=postgres uv run pytest -q tests/unit/kernel"]` plus `[gate_guards.pg] require_env = ["E_AGENT_TEST_PG_DSN"]`, `distinct_databases = [["E_AGENT_TEST_PG_DSN", "E_AGENT_PG_DSN"]]`.
- [ ] Gate, commit `fix(harness): pg gate refuses a test DSN that names the live ledger (HP-13)`.

### Task 2: committed evidence (HP-4, high)

**Files:** `state.py` (`Paths.evidence`, `Paths.live_evidence` under `harness/state/evidence/`), `gate.py` (clean tree ignores bookkeeping), `closecheck.py` (`BOOKKEEPING` single source, imported by `tasks.IMPLICIT_PATHS`), `schemas/features.schema.json` and `schemas/handoff.schema.json` (evidence pattern accepts `evidence/` and `harness/state/evidence/`), tests.

- [ ] Failing tests: `test_gate_writes_committable_evidence` (path under `harness/state/evidence/gates/<task>/`), `test_second_gate_ignores_uncommitted_evidence`, `test_close_check_passes_in_a_fresh_clone` (`git clone` the scratch repo after the bookkeeping commit; `close-check` in the clone prints ok), `test_old_evidence_paths_still_validate` (conformance).
- [ ] Implement. `clean_tree` in evidence means "no non-bookkeeping change"; `close-check` keeps requiring a fully clean tree.
- [ ] Gate, commit `fix(harness): gate evidence lives under harness/state and survives a clone (HP-4)`.

### Task 3: UI in the full gate (HP-12, high)

**Files:** `harness/context.toml` (`full` gains `pnpm --dir ui check`; new set `ui = ["pnpm --dir ui check"]`), `schemas/task.schema.json` (gate enum gains `ui`), `cli.py` (`--gate` choices from the manifest, not a literal list), conformance test.

- [ ] Failing tests: `test_full_gate_covers_ui` (conformance), `test_new_task_accepts_manifest_gate_sets` (scratch manifest with an extra set).
- [ ] Implement; install UI dependencies in the worktree and run `pnpm --dir ui check` once to confirm the command passes.
- [ ] Gate, commit `fix(harness): full gate runs the UI checks (HP-12)`.

### Task 4: closed state and clearer next actions (HP-3, HP-9, HP-2, HP-7)

**Files:** `status.py`, `cli.py`, tests.

- [ ] Failing tests: `test_status_reports_closed_task` (after a passing close-check the next action is "clear the context, then new-task …"), `test_new_task_after_close_needs_no_replace`, `test_new_task_still_refuses_open_task`, `test_status_after_new_task_asks_to_commit_bookkeeping` (only `harness/state/**` dirty), `test_check_scope_prints_ok_count`.
- [ ] Implement: `status.collect` computes `closed = closecheck.problems(...) == []`; `new-task` accepts replacing a closed task; `check-scope` prints `ok: N changed paths inside scope`.
- [ ] Gate, commit `feat(harness): closed state; status and check-scope say what happened (HP-2, HP-3, HP-7, HP-9)`.

### Task 5: contract maintenance commands (HP-8, HP-10, HP-11, HP-1)

**Files:** `tasks.py`, `cli.py`, `schemas/task.schema.json` (optional `features_digest`, `scope_changes[] {glob, reason, at}`), `status.py`, `closecheck.py`, tests.

- [ ] Failing tests: `test_contract_pins_features_digest`, `test_status_and_close_check_flag_changed_acceptance`, `test_refresh_task_keeps_base_and_paths`, `test_refresh_task_from_features_rederives_acceptance`, `test_amend_scope_adds_glob_with_reason`, `test_new_task_dedupes_paths`, `test_old_contract_without_new_fields_loads`.
- [ ] Implement `refresh-task [--from-features]` (new context and features digests; base, created_at, paths kept) and `amend-scope --add GLOB --reason TEXT`; dedupe `allowed_paths`.
- [ ] Gate, commit `feat(harness): refresh-task, amend-scope and acceptance drift detection (HP-1, HP-8, HP-10, HP-11)`.

### Task 6: schema tools (HP-5, HP-14, date-time)

**Files:** `contracts.py` (format checker for `date-time` via `datetime.fromisoformat`, no new dependency), `cli.py` (`validate <schema> <file>`, `add-feature <phase> <id> --category … --description … --step …`), tests.

- [ ] Failing tests: `test_validate_command_reports_problems`, `test_add_feature_appends_valid_entry`, `test_add_feature_refuses_duplicate_id`, `test_date_time_format_is_enforced`.
- [ ] Implement.
- [ ] Gate, commit `feat(harness): validate and add-feature commands; date-time enforced (HP-5, HP-14)`.

### Task 7: skills, docs, pilot log, handoff

- [ ] `eng-session`: close ritual uses "the contract's gate set, never the smoke set"; Known harness limits keeps only HP-6; mention `refresh-task`, `amend-scope`, `add-feature`, `validate`. `eng-verify`: `pg` level needs `E_AGENT_TEST_PG_DSN` naming a separate test database; evidence paths. `eng-foundations` gotchas: G-6 updated, new G-11 for HP-13. `eng-handoff`, `eng-review` template, `live-sandbox`: evidence paths.
- [ ] Pilot log: a "Resolution (H2.1)" section mapping each HP id to its commit or deferral.
- [ ] README harness commands; harness plan H2.1 line; H3 handoff merge note superseded; `docs/handoffs/2026-10-13-harness-h21.md`.
- [ ] Full gate (`uv run pytest -q` whole suite) and the skill check; commit `docs(harness): H2.1 skills, pilot-log resolution, handoff`.

## Deferred by design

- HP-6 (several gate sets per contract): the contract keeps one set; `eng-verify` orders the other levels. Revisit when a phase needs a contract-level list.

## Self-review

Every pilot row HP-1 to HP-14 maps to a task or to the deferral above; each Review Focus line names its test; the new schema fields are optional so H2 state stays valid.
