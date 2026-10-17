# Hygiene: Gates, Typed Configuration, Supervised Tasks and CI Scans Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Status:** Draft 2026-10-15. **Approved by the owner on 2026-10-15.** Runs after Phase 1d closes.

**Goal:** close five small silent-pass and robustness holes from the [X-agent adoption review](../reviews/2026-10-14-x-agent-adoption-review.md) (approved 2026-10-14), so that each of principles PR-31, PR-32, PR-37, PR-38 and PR-39 in [principles](../design/principles.md) gets a machine check. PR-25's repository secret scan comes with PR-39.

**Architecture:** no runtime feature and no contract change. Each task adds one check and fixes what the check finds:

| Task | Review item | Principle | Check added |
|---|---|---|---|
| H.1 | XA-04 | PR-31 | `release_report.py` fails on zero cases; a finite list of known silent-pass paths in the ENG rules |
| H.2 | XA-14 | PR-37 | Ruff TID251 bans `os.environ` and `os.getenv` in product code, with a two-file allowlist |
| H.3 | XA-15 | PR-38 | A `supervised_task` helper; Ruff bans bare `asyncio.create_task` in product code outside it |
| H.4 | XA-17 | PR-32 | A golden file for the driver's base instructions; every recorded replay is replayed |
| H.5 | XA-16 | PR-25, PR-39 | CI secret scan and dependency vulnerability audit |

**Ordering:** after Phase 1d closes and before Phase 2 starts. Phase 1d edits `server/bootstrap.py` and moves plugin packages, so running this first would make both plans churn the same files. It is one harness phase with one task per row (features `F-HY-1` … `F-HY-5`, added to the harness when the owner approves this plan).

**Tech Stack:** ruff (`flake8-tidy-imports` banned-api), pytest, GitHub Actions, gitleaks (pinned release), `uvx pip-audit`, `pnpm audit`.

**Spec:**
- Adoption review: XA-04 ("Gates fail on empty input") and the "Cheap hygiene" table rows XA-14 to XA-17.
- Principles PR-25, PR-31, PR-32, PR-37, PR-38 and PR-39, and AGENTS.md "Development and verification".
- Evidence (checked 2026-10-15 on `main` at `8bc7b1f`):
  - `scripts/release_report.py:243` returns 0 when `passed == total`, so `0/0` passes.
  - `os.environ` reads in product code: `server/bootstrap.py:83,150,155` (environment variable names that the profile declares) and `adapters/secretstore_local/store.py:50-56` (the key-encryption key and the secrets path).
  - Bare `asyncio.create_task`: `server/worker.py:71` (heartbeat), `server/api.py:215,217` (worker and sweeper), `kernel/continuation.py:251`.
  - Ruff `select` has no `TID` (`pyproject.toml:57`).
  - CI (`.github/workflows/ci.yml`) has lint, types, imports, OpenAPI, tests, the release matrix, the Postgres suite, wheels and UI; it has no secret or vulnerability scan.
  - The driver's `BASE_INSTRUCTIONS` constant (`adapters/pydantic_ai/driver.py:65`) has no golden test. The replay test lists its tasks in a constant `TASKS` (`tests/unit/server/test_recorded_model_replays.py:17`), so a new recording that is not added to `TASKS` is never replayed.

## Global Constraints

- **Run behaviour unchanged.** The OpenAPI document, the event streams and the CLI output stay the same. Only startup error messages may change, where a missing environment variable is now reported by the settings helper.
- **Scope of the bans.** The Ruff bans apply to `src/e_agent/**`. Scripts, `tools/harness` and tests are command-line entry points and stay out of scope; the per-file ignores say so explicitly.
- **No new eval system** (adoption review XA-17). The live model lane stays with ADR 0010 qualification.
- **No blanket suppression.** A scanner finding is fixed or recorded with its reason in an allowlist entry; never disable a rule wholesale (PR-06).
- **Harness.** One contract per task, `check-scope` before each commit, gate evidence after the commit, `close-check` before a task closes.
- **Branch:** `chore/hygiene-gates` from `main` after Phase 1d merges. Stage explicit paths; every commit ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`; merge, push and rebase only on the owner's instruction.
- **Boundaries.** No container is needed. `archive/**` and `research/**` stay unchanged.

## Review Focus

1. **A ban that bans nothing.** A misspelt banned-api entry passes silently. Each ban task commits a probe that proves the rule fires: H.2 and H.3 run `ruff check` on a scratch file that uses the banned call and expect `TID251`.
2. **An allowlist that grows into a hole.** The allowlist is two files in H.2 and one helper module in H.3, and a test pins it: `test_banned_api_allowlist_is_pinned`.
3. **A supervised task that swallows errors.** The helper must log and surface a failure, never drop it. Test: H.3 `test_supervised_task_failure_is_logged_and_reraised_on_await`.
4. **A scan that scans nothing.** The secret scan and the audit print what they scanned, and CI fails if the count is zero (H.5).
5. **A recording that is never replayed.** Test: H.4 `test_every_recording_is_replayed`.

## Design refs

| Document | Section | Change |
|---|---|---|
| `docs/design/principles.md` | PR-25, PR-31, PR-32, PR-37, PR-38, PR-39; backlog table | Check column names the new check; status [I]; backlog rows removed (each task) |
| `.agents/skills/eng-foundations/references/rules.md` | new ENG rules | Zero-input gates and the silent-pass list (H.1); typed settings (H.2); supervised tasks (H.3); prompt and replay rule (H.4). Each cites AGENTS.md "Development and verification" |
| `README.md` | Development commands | The audit and scan commands (H.5) |

## ADRs

None. No contract or boundary changes; each task applies an existing AGENTS.md rule.

## Toggles and fallback

No runtime feature is added, so roadmap rule 3 does not apply.

## Gate

| Task | Gate set |
|---|---|
| H.1–H.4 | `full` |
| H.5 | `full`, plus the new CI jobs green on a pushed branch (the owner pushes) |

---

### Task H.1: gates fail on empty input (XA-04, PR-31)

**Files:**
- `scripts/release_report.py`: return 1 when `total == 0`, and print the count in every case.
- `tests/conformance/test_release_report.py` (scripts are tested under `tests/conformance`, like `test_repo_move.py`)
- `.agents/skills/eng-foundations/references/rules.md`: a new rule "Gates fail on empty input" with a finite **Known silent-pass paths** list. Its first entries are `release_report.py` (fixed here) and the replay `TASKS` constant (fixed in H.4).

**Steps:**
- [x] Write the failing test `test_release_report_fails_on_zero_cases`: call the report's summary function with an empty result list and expect exit code 1 and the text `0/0`.
- [x] Run `uv run pytest -q tests/conformance/test_release_report.py`. Expected: fails (returns 0). If the summary is not a separate function yet, extract it first without changing output.
- [x] Implement.
- [x] Run the test and `uv run python scripts/check_agent_skills.py`. Expected: pass.
- [x] Commit `fix(scripts): release report fails on zero cases; silent-pass list`.

### Task H.2: typed settings for environment reads (XA-14, PR-37)

**Files:**
- `src/e_agent/server/environment.py`: one function that reads a named environment variable for the profile's `*_env` settings and raises a clear startup error when a required one is missing.
- `src/e_agent/server/bootstrap.py`: the three reads go through it. The call-site list above was taken at `8bc7b1f`; re-take it at task start, because Phase 1d adds an `E_AGENT_PROFILE` read in `server/profile.py` (Task 1d.6), which also goes through the helper.
- `.agents/skills/eng-foundations/references/rules.md`: a rule for typed environment reads, citing AGENTS.md "Development and verification".
- `pyproject.toml`: add `TID` to Ruff `select`; `[tool.ruff.lint.flake8-tidy-imports.banned-api]` bans `os.environ` and `os.getenv`; per-file ignores allow `src/e_agent/server/environment.py` and `src/e_agent/adapters/secretstore_local/store.py` (the key-encryption key is a legitimate secret source), and exempt `scripts/**`, `tools/**` and `tests/**`.
- `tests/conformance/test_banned_api.py`

**Steps:**
- [x] Write the failing tests:
  - `test_os_environ_banned_in_product_code`: runs `ruff check` on a scratch module under a temporary `src/e_agent` path that reads `os.environ` and expects `TID251`.
  - `test_banned_api_allowlist_is_pinned`: the per-file ignores for `TID251` under `src/` are exactly the two files above (H.3 adds its helper).
  - `test_missing_dsn_env_reports_variable_name`: a profile whose `dsn_env` is unset fails startup naming the variable.
- [x] Run `uv run pytest -q tests/conformance/test_banned_api.py tests/unit/server`. Expected: the ban test fails (no `TID`).
- [x] Implement. Run `uv run ruff check .` and fix every finding in `src/` through the helper.
- [x] Run the `full` gate. Expected: pass.
- [x] Commit `chore: typed environment reads; ban os.environ in product code`.

### Task H.3: supervised background tasks (XA-15, PR-38)

**Files:**
- `src/e_agent/sdk/tasks.py`: `supervised_task(coro, *, name)` creates the task, keeps a reference, and adds a done-callback that logs an exception with the task name. Awaiting the task still raises it. It uses only the standard library and lives in the SDK because every layer may import the SDK: the ban covers adapters and plugins too, and they may not import the kernel.
- `src/e_agent/server/worker.py:71`, `src/e_agent/server/api.py:215,217`, `src/e_agent/kernel/continuation.py:251`: use the helper.
- `pyproject.toml`: ban `asyncio.create_task` under `src/e_agent/**`; the helper module is the only allowed caller.
- `tests/unit/sdk/test_tasks.py`, `tests/conformance/test_banned_api.py`
- `.agents/skills/eng-foundations/references/rules.md`: a rule for supervised background tasks, citing AGENTS.md "Development and verification".

**Steps:**
- [x] Write the failing tests:
  - `test_supervised_task_failure_is_logged_and_reraised_on_await`
  - `test_supervised_task_cancel_is_not_logged_as_failure`
  - `test_create_task_banned_in_product_code` (the same probe as H.2)
  - extend `test_banned_api_allowlist_is_pinned` to three files.
- [x] Run `uv run pytest -q tests/unit/sdk/test_tasks.py tests/conformance/test_banned_api.py`. Expected: fails (no helper).
- [x] Implement and migrate the four call sites.
- [x] Run the `full` gate. Expected: pass; the worker and sweeper tests are unchanged.
- [x] Commit `chore: supervised background tasks; ban bare create_task`.

### Task H.4: prompts are code; every recording is replayed (XA-17, PR-32)

**Files:**
- `tests/unit/adapters/pydantic_ai/golden/base_instructions.txt`, written once from the unchanged constant.
- `tests/unit/adapters/pydantic_ai/test_prompt_golden.py`
- `tests/unit/server/test_recorded_model_replays.py`: `TASKS` is checked against the files in `tests/replays/erp-model-calls/`.
- `.agents/skills/eng-foundations/references/rules.md`: the "Known silent-pass paths" entry for `TASKS` is marked fixed; a rule says a change to the driver, prompts or tool schemas must keep the replay suite and the prompt golden file green, and an intended prompt change updates the golden file in the same commit.

**Steps:**
- [x] Record the golden file from the current constant and commit it before any other change.
- [x] Write the failing tests:
  - `test_base_instructions_match_golden`
  - `test_every_recording_is_replayed`: the stems of the `*.json` recordings (the directory also holds a `README.md`) equal `set(TASKS)`, and the set is not empty.
- [x] Run the two test files. Expected: the golden test passes on unchanged code; the recording test passes today (8 recordings, 8 tasks, checked 2026-10-15) and fails when a scratch recording is added; record that probe in the handoff.
- [x] Run `uv run python scripts/check_agent_skills.py` and the `full` gate. Expected: pass.
- [x] Commit `test: prompt golden file; every recorded replay runs`.

### Task H.5: secret scan and dependency audit in CI (XA-16, PR-25, PR-39)

**Files:**
- `.github/workflows/ci.yml`: a `security` job that:
  - runs gitleaks (a pinned release binary, with its version and checksum in the workflow, not a floating action tag) over the full git history, and prints the number of commits scanned;
  - runs `uvx pip-audit` against the exported lock (`uv export --format requirements-txt`) and `pnpm --dir ui audit --prod`;
  - fails on any finding not in the allowlist, and on a scan that reports zero files.
- `.gitleaks.toml`: the allowlist. An entry is allowed only for a test fixture string, and carries its reason.
- `README.md`: the same commands for a local run.

**Steps:**
- [x] Run the scanner and both audits locally first and record the baseline in the task contract. Triage each finding: fix it, or allowlist it with its reason. A real credential in history is reported to the owner at once and is not pushed anywhere.
- [x] Add the job.
- [ ] The owner pushes the branch; the `security` job is green. Record the run link in the handoff.
  - 2026-10-17: PR-25 and PR-39 stay [Pa] in principles.md until the owner's pushed run is green (a deviation from the Design refs' status [I]).
- [x] Commit `ci: secret scan and dependency audit`.

---

### Close

- [ ] Update principles.md: PR-25, PR-31, PR-32, PR-37, PR-38 and PR-39 name their checks; the backlog rows for them are removed.
- [ ] Write the handoff with `eng-handoff`: each task's check, its probe and the baseline findings from H.5.

## Self-review

- **Spec coverage.** XA-04 → H.1. XA-14 → H.2. XA-15 → H.3. XA-17 → H.4. XA-16 → H.5. Every principle in the goal names a task and a check.
- **Placeholder scan.** No TBD. The scanner is gitleaks; the owner may swap it at review if the same constraints hold (pinned version and checksum, full history, a printed count, an allowlist with reasons).
- **Name consistency.** `supervised_task`, `server/environment.py`, `test_banned_api_allowlist_is_pinned`, `test_every_recording_is_replayed`, `F-HY-1` … `F-HY-5`.
- **Review Focus coverage.** Items 1–5 each name a task and a test.
