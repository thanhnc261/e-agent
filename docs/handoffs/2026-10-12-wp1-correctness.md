# WP1 correctness and truthfulness: results (2026-10-12)

## Summary

This handoff reports the result of the WP1 correctness plan.

- **Plan:** [2026-10-12 target architecture WP1](../superpowers/plans/2026-10-12-target-architecture-wp1-correctness.md). It covers defects D1–D8, plus an owner amendment (Task 10).
- **Spec:** [target architecture v2](../target-architecture.md).
- **Branch:** `feat/wp1-correctness`. It is not merged and not pushed.
- **ADRs 0018–0021 are Proposed.** Contract-changing work merges only after the owner accepts them (plan Global Constraints).

Owner choices for this run:
- subagent-driven execution
- end to end after every task
- Ollama as the default provider, with LiteLLM supported
- the advisor consulted for decisions and phase reviews

How the work was executed:
- Each task had a fresh implementer.
- Each task then had a spec and quality reviewer, with a fix round where the reviewer found something.
- An advisor checkpoint followed each phase: A = Tasks 1–3, B = 4–5, C = 6–8, D = 10 and 9.
- The whole branch had a final review on the most capable model, then one fix wave and a re-review.

## Branch baseline: read before touching the branch

Commit `d0d9e70` (`chore: snapshot working tree before WP1`) commits the whole uncommitted working tree as it stood at `af50c62`: 727 files, including unrelated UI/v4, research and docs work. This was necessary because the plan's evidence was verified against that tree, and files it builds on (`0003_run_work.sql`, `contracts/work.py`, the plan, the spec) were untracked. `.playwright-mcp/` was added to `.gitignore`.

Consequences:
- Merging `feat/wp1-correctness` as-is also brings that snapshot into `main`.
- `git checkout main` in this checkout removes those files from the working tree. They remain safe on the branch. To keep them separate, branch `chore/wip-snapshot` from `d0d9e70`, or restore paths with `git checkout feat/wp1-correctness -- <paths>`.
- WP1's own work is `73a6240..HEAD`.

## What changed

| Defect | Change | ADR | Main files |
|---|---|---|---|
| D1 | `ALLOWED_RUN_TRANSITIONS` contract table. `_check_run_transition` runs first in `_set_run_state` and before both direct run-state writes. Illegal pairs raise `CONFLICT`. | 0018 | `contracts/run.py`, `kernel/coordinator.py` |
| D2 | Self-approval refused with `FORBIDDEN` unless `operator.allow_self_approval`. The fixture profile sets it; `profiles/live.example.json` does not. `/health/ready` reports `self_approval_allowed`. | 0019 | `server/profile.py`, `bootstrap.py`, `api.py`, `profiles/fixture.json` |
| D3 | `RunEvent.actor` is stamped by both stores from the `current_actor` ContextVar (`actor_scope`). Labels: `principal:<id>` (API session, start/input/decide work), `system:worker:<owner>` (recovery, expire, failures), `system:worker:startup` (startup/CLI recovery), `system:kernel` (default). | 0018 | `sdk/store.py`, `contracts/events.py`, both stores, `api.py`, `cli.py` |
| D4 | `ReasonCode` (17 members) and `RunRecord.reason_code` appear on every failure or terminal transition and in event payloads. The evidence classifier reads the code first and falls back to text only for old rows (mapping in ADR 0018). | 0018 | `contracts/run.py`, `coordinator.py`, `kernel/evidence.py` |
| D5 | The approval expiry sweeper only enqueues fenced `expire` work, every 30 s. The worker runs `expire_approval` under the claim and re-checks everything. Migration 0004 widens `run_work.kind`. | 0019 | `coordinator.py`, `api.py`, `migrations/0004_run_work_expire.sql`, `contracts/work.py` |
| D6 | `list_events(..., limit)` in the port and both stores. `/events` defaults to 500, ceiling 1000. SSE, the run snapshot and evidence export page their reads. The UI client `listEvents` pages until it gets a short page. | 0018 | `sdk/store.py`, both stores, `api.py`, `evidence.py`, `ui/packages/client/src/index.ts` |
| D7 | `reserve_operation` raises `ConnectionBusy` while another action on the same tenant and connection is RESERVED, DISPATCHING or UNKNOWN. This is serialized by a transaction-scoped advisory lock. The coordinator blocks the action and fails the run with `CONNECTION_BUSY`. `DuplicateOperation` keeps precedence. | 0020 (amended) | both stores, `coordinator.py` |
| D8 | `target-architecture.md` status tags flipped only where code exists. ADR index table repaired. Runbook note for single-operator live trials. | — | `docs/target-architecture.md`, `docs/adr/README.md`, `docs/runbooks/i06-odoo-bridge.md` |
| Owner amendment | LiteLLM is an explicit opt-in provider (`driver.provider: "litellm"`). The proxy endpoint must be loopback only. The key comes only from the variable named by `api_key_env`. A fixed placeholder is used when no key is given, so `OPENAI_API_KEY` is never read. There is no provider fallback. Runtime metadata gains `model_provider`. Ollama was already the default, so that part of the request needed no code. | 0021 | `adapter-agent-pydantic/.../driver.py`, `profile.py`, `bootstrap.py`, `README.md` |

Hardening from the final review:
- `recover()` and the sweeper isolate per-run failures and log them with `exc_info`.
- Malformed loopback URLs (bad port, `%` in the netloc) are rejected as `STARTUP_REJECTED`.
- `VERIFICATION_FAILED` classifies as `failed`, not `blocked-by-design`.

## Changes to the Proposed ADRs during execution

The owner should review these before accepting.

- **0020:** the busy set was widened from DISPATCHING/UNKNOWN to **RESERVED, DISPATCHING and UNKNOWN**. Without RESERVED, two concurrent reservations both pass, because RESERVED→DISPATCHING happens outside the admission lock. The second write would then dispatch behind the first under the losable session lock. A crash-stranded RESERVED row blocks the connection until recovery marks it BLOCKED.
- **0018:**
  - added the classifier mapping
  - added the `system:worker:startup` label
- **0021:** new. Its guard wording was corrected to match the code.
- **0019:** unchanged.

## Verification at the final head

- `uv run ruff check .`: clean.
- `ruff format --check`: clean.
- `mypy`: clean.
- `lint-imports`: 7 contracts kept.
- `export_openapi.py --check`: OK.
- `pnpm gen:check`: OK.
- `uv run pytest -q` with `E_AGENT_TEST_PG_DSN` set: **493 passed, 19 skipped**. The baseline was 418/19.
- `E_AGENT_TEST_STORE=postgres uv run pytest -q packages/kernel tests/conformance`: **209 passed**. The baseline was 176.
- `make e2e`: **142 passed, 2 skipped**, the same as the baseline.
- UI unit tests (`pnpm test`): 157 passed.
- Migration 0004 was applied as an upgrade on a database that already had 0001–0003.

Not verified:
- live Odoo
- the live Ollama or LiteLLM model
- `tests/integration/test_odoo_live.py`, which is skipped without a sandbox. Its profile now sets `allow_self_approval: true` explicitly.

PostgreSQL ran in a throwaway container: `postgres:16-alpine` on `127.0.0.1:55432`.

## Rulings made during execution

Each ruling is listed with what it costs if it is wrong.

1. **Baseline snapshot commit `d0d9e70` on a new branch.** If wrong, the owner splits the unrelated work out. Nothing is lost.
2. **"End to end after each turn" means the full gate and the Postgres run after every task, plus `make e2e` when a task touches the server, OpenAPI or `ui/`.** If wrong, the cost was extra minutes per task.
3. **Ollama was already the default. LiteLLM is opt-in under ADR 0021 with a loopback guard.** If remote LiteLLM endpoints were wanted, relaxing the guard is one line plus an ADR edit.
4. **Execution order was 1–8, 10, 9,** so the doc pass and the final gate cover Task 10. If wrong, nothing material is lost.
5. **The Proposed ADRs gate the merge, not the execution.** If the owner rejects an ADR, that task's commits are reverted.
6. **Temporary transition recording went to the scratchpad, not `/tmp`.** If wrong: none.
7. **Commit trailer "Claude Opus 5.5" on all commits.** Commit `7428a64` says "Claude Sonnet 5.5"; it was left as-is, because rewriting history for a trailer has no functional value. If wrong, amend at squash.
8. **Advisor phase reviews at the end of phases A–D.** If wrong, there were fewer checkpoints than the owner wanted.
9. **Actor labels follow the plan.** Start and input work runs as the requester's principal, decide as the decider, and recovery and expire as `system:worker`. If wrong, worker-path events need a bulk relabel; the schema does not change.
10. **The plan-mandated actor assertion, which could never fail, was deferred to the final wave.** It was fixed there in `ad0230d`. If wrong, nothing further.
11. **The sweeper catches `Exception` per run, not only `KernelError` as the plan said.** If wrong, a systemic error is logged once per run instead of once per tick.
12. **RESERVED was added to the busy set, and ADR 0020 amended.** If wrong, WP2's slots > 1 must treat reservation as the per-connection serialization point. A stranded RESERVED row then holds the connection until the next recovery pass.
13. **The Task 9 doc truthfulness edits went beyond the brief's line list.** If wrong, the doc diff is larger.
14. **`VERIFICATION_FAILED` is `failed`, not `blocked-by-design`.** If wrong, it is a one-line set change.
15. **Startup and CLI recovery run as `system:worker:startup`.** If wrong, it is a label string.
16. **The UI client `listEvents` paging was fixed in this branch.** If wrong, a small `ui/` diff sits outside the plan's file list.
17. **`recover()` has a per-run guard.** If wrong, a systemic recovery bug is logged per run instead of crashing startup.
18. **Parked: `listEvents` could loop forever against a server that ignores `after_sequence`.** If wrong, a contract-breaking server hangs the UI refresh. Fix: `if (next <= cursor) throw`.
19. **Parked: `listEvents` detects a short page with the client constant 1000.** If wrong, a future server clamp below 1000 truncates silently.
20. **Parked: a systemic recovery failure is logged and startup proceeds.** If wrong, the operator must read warnings to notice it.

## Owner decisions still open

- **Accept or amend ADRs 0018–0021,** including the 0020 widening above.
- **`_recover_run`'s VERIFICATION_FAILED rule:** it fails a WAITING_INPUT run on restart, unlike the VERIFIED rule. Should it exclude WAITING_INPUT? If so, also drop WAITING_INPUT→FAILED from the table.
- **How to separate the `d0d9e70` snapshot** from WP1 before merging.

## Remaining, not implemented (triaged by the final review)

**For WP2:**
- a durable writer lease
- a correlation id on events and work
- a `latest_sequence` port method (the snapshot still pages every event to read the last sequence)
- a partial index for the connection busy query
- the cancel/RESERVED interaction on terminal runs (no path found)
- a concurrency test with two PostgreSQL sessions

**Later:**
- an `expire` row that ends DONE as a no-op is never re-enqueued; the decide path backstops it, and one sentence is due in ADR 0019
- `qualify_model.py` matches a reason by its text
- unbounded `list_events` reads remain in CLI, scripts and recovery, outside D6's scope
- `OPENAI_ORG_ID` and `OPENAI_PROJECT_ID` are read by the OpenAI client
- `api_key_env` is ignored on Ollama profiles
- the doc row "Decide racing cancel" still has its analysis as [P]

**Test gaps, deferred:**
- a non-terminal illegal pair
- RUN_TERMINAL payload codes
- `_peek_cont` with an empty cache
- SSE at an exact multiple of the page size
