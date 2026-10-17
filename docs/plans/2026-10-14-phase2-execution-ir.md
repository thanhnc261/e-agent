# Phase 2: Core Runtime with Execution IR Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Status:** Draft 2026-10-14, amended 2026-10-17 after a staleness review against the checkout at the Hygiene phase's close (findings P2R-1 to P2R-19, folded in below). Awaiting owner review. Not approved; no `new-task` until the owner names it approved. Part 2a's documents were drafted on 2026-10-14 from the approved [adoption review](../reviews/2026-10-14-x-agent-adoption-review.md) (target §6.4, ADRs 0024, 0025, 0027–0029, threats T20–T22, all Proposed); owner gate G1 still applies.

**Goal:** the kernel executes a typed execution IR (TaskDefinition → ActionPlan → StepRecord) behind `features.execution_ir: off | shadow | on`, falling back to today's single-action loop before any write is reserved.

**Architecture:** the plan has four parts.
- **2a (design entry gate, no runtime code):** the target architecture's "Execution IR" section (§6.4), threats T20–T22 and ADRs 0024, 0025, 0027–0029 already exist (commit `6aaab54`). 2a reconciles them with this plan and the current checkout, and the owner accepts them (gate G1). The [design-principles review](../reviews/2026-10-14-design-principles-review.md) DR-01 found that Phase 2 had no design section; roadmap rule 2 makes that section and its ADRs the entry gate.
- **2b (toggle infrastructure):** `Profile.features`, the `feature.fallback` event, toggles in `/health/ready` and in the evidence bundle. This is the roadmap's first runtime task, and every later feature uses it.
- **2c (execution IR):** portable contracts, task definitions for the eight ERP tasks, store support, the IR compiler and validator, shadow mode, single-step `on`, multi-step plans with one approval digest and serial per-step dispatch, failure semantics, and a driver that emits IR.
- **2d (verification):** end-of-phase gate, Postgres run, `make e2e`, phase review, handoff and the live check.

The trust anchor does not move: the kernel compiles, validates, approves, reserves, dispatches and verifies; the driver's IR is a proposal (ENG-TRUST-1, ENG-TRUST-2).

**Tech Stack:** Python 3.12, pydantic records (`e_agent.contracts.common.Record`, `extra="forbid"`), RFC 8785 JCS digests (ADR 0006), PostgreSQL migrations under `src/e_agent/adapters/postgres/migrations/`, pydantic-ai `FunctionModel` for driver tests, pytest, the e-agent harness (`uv run e-agent-harness`), pnpm for the UI client regeneration.

**Spec:**
- [Roadmap](../roadmap.md) Phase 2 row and rules 1–5.
- [Target architecture](../design/target-architecture.md) §1.3 (task definition), §5.1 principle 3, §5.4 (step record sketch), §6.3 (loop), §7.2 rule 1 (tool schemas fixed at admission), §15 (`contracts/task.py`, `kernel/step.py`), §17 C8 and C11.
- [MVP design](../design/mvp-detailed-design.md) §7 (action states), §9 (persistence, `operation_reservations`), §10 (budgets), and the approval digest (lines 113–117).
- [Core conversation plan](2026-10-12-core-conversation-cognition.md) Phase 2 (TaskDefinition interface, line 107) and Phase 3 (StepRecord transaction rule).
- [Odoo tools plan](2026-10-12-odoo-tools-from-erp-bench.md) tasks 0.1 (ADR 0024) and 0.3 (ActionPlan sketch, ADR 0025).
- ADRs 0003, 0004, 0006, 0014, 0018, 0020 (see ADRs).
- [Design-principles review](../reviews/2026-10-14-design-principles-review.md) DR-01 (entry gate) and DR-08 (notes fixture as the genericity check).

## Global Constraints

- **Branch** `phase2/execution-ir` from `main` after the owner merges the Hygiene phase ([PR #4](https://github.com/thanhnc261/e-agent/pull/4)); `new-task` waits for that merge. `main` without Hygiene lacks `server/environment.py`, `sdk/tasks.py`, the TID251 bans and the prompt golden this plan relies on. Stage explicit paths. Every commit ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Merge, push and rebase only on the owner's instruction.
- **Runs after Phase 1d** ([plugin boundary plan](2026-10-14-phase1d-plugin-boundary.md)). Amended at Phase 1d's close (2026-10-16, ENG-PLAN-3): the ERP domain pack is now `src/e_agent/plugins/erp/domain/` (tests `tests/unit/plugins/erp/domain/`), the Odoo adapter `src/e_agent/plugins/erp/odoo/` and the simulator `src/e_agent/plugins/erp/simulator/`, and the paths below use that layout. Phase 1d added task presets (`TaskPreset` in `src/e_agent/sdk/ports.py`, contributed by the domain pack's `plugin.py`; Task 1d.3), and Task 2c.2 extends those presets into task definitions rather than starting a second catalogue.
- **Harness phase `2`.** Features in `harness/state/2/features.json` (`F-2a-1` … `F-2d-2`, one per task, as in Phase 1), one task contract per task (`uv run e-agent-harness new-task`), `check-scope` before each commit, `gate <set>` after the commit on a clean tree, `close-check` before a task closes (ENG-WORK-1, ENG-EVID-1).
- **Gate commands** (from `harness/context.toml`):
  - `full`: `uv sync --locked`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy`, `uv run lint-imports`, `uv run python scripts/export_openapi.py --check`, `uv run pytest -q`, `pnpm --dir ui gen:check`, `pnpm --dir ui check`, `uv run python scripts/check_core_only.py`.
  - `core`: `uv run python scripts/check_core_only.py` (core wheels and a non-ERP test pack install and start without any ERP wheel).
  - `pg`: `E_AGENT_TEST_STORE=postgres uv run pytest -q tests/unit/kernel`, with `E_AGENT_TEST_PG_DSN` set to the `e_agent_test` database and never the live ledger's database (G-11).
  - `e2e`: `make e2e`.
- **Design before code.** Part 2a's documents and ADRs are accepted by the owner before 2b starts. 2c's contract shapes below come from the existing sketches (core plan line 107, Odoo plan 0.3, target §5.4). If an accepted ADR changes a shape, the commit that accepts it also amends this plan (ENG-PLAN-3, G-7: re-materialise the active task with `--replace`).
- **Authoritative files mid-task (G-7).** Tasks that edit a digest input (2a.1 and 2a.2 the target architecture and the ADR index, 2d.1 the roadmap) run `uv run e-agent-harness refresh-task` before `close-check`.
- **Toggle default `off`.** Every committed profile (`src/e_agent/plugins/erp/simulator/fixture_profile.json`, `profiles/dev-ollama.json`, `profiles/live.example.json`) keeps `execution_ir` `off`. A profile without `features` means all `off`.
- **`off` is today.** With `execution_ir: off` the event stream, action records, digests and outcomes of every existing test are unchanged. The `max_admitted_writes` check in `_handle_proposal` (`kernel/proposals.py`) keeps its meaning.
- **Hygiene rules** (Phase 1h). No `os.environ`, `os.getenv` or `asyncio.create_task` under `src/e_agent` (ENG-ARCH-6, ENG-ARCH-7): environment reads go through `server/environment.py`, background work through `supervised_task` (`sdk/tasks.py`), and the allow-list pinned by `tests/conformance/test_banned_api.py` stays unchanged. A task that changes the driver, its prompt or the tool schemas runs `uv run pytest -q tests/unit/server/test_recorded_model_replays.py tests/unit/adapters/pydantic_ai/test_prompt_golden.py`, and an intended prompt change updates `tests/unit/adapters/pydantic_ai/golden/base_instructions.txt` in the same commit (ENG-EVID-5). A golden-file test fails on an empty golden and asserts its case count (ENG-EVID-4).
- **Phase 3 boundary.** Phase 2 delivers StepRecord. ProgressLedger, KERNEL-REPEAT, ContextAssembler, the explanation contract and run reconstruction stay in Phase 3.
- **Live multi-step writes are out of scope.** Multi-step plans run in fixture profiles and through the CLI and API only. A bootstrap guard refuses `max_admitted_writes > 1` with `environment: live` (Task 2c.7) until a UI plan-approval thread lands (owner decision D3).
- **Boundaries.** Containers: only `e-agent-ledger` (test database `e_agent_test`) for `pg`, and `odoo19-learning` plus `e-agent-ledger` in the live check (Task 2d.2). Never `odoo-bench` (ENG-BOUND-1). `archive/**` and existing `research/**` reports are read-only. No change under `addons/**` is planned; one would bump the bridge version (ENG-BOUND-2).

## Review Focus

Failure modes the happy-path tests do not exercise; each is pinned to the task that adds its test.

1. **Shadow costs something.** Shadow must not add a driver call, a provider read or a budget decrement. Test: Task 2c.5 `test_shadow_adds_no_driver_calls_reads_or_budget`.
2. **`off` drifts from today.** Any new code path reached with the toggle `off` changes the event stream. Test: Task 2c.5 `test_off_mode_event_stream_matches_baseline` against a golden stream recorded in Task 2b.1 before any 2c change. Generated ids (`new_id`, uuid4) enter the digest input through `logical_operation_id`, so the baseline records digests under a deterministic id source and normalises ids in the stream; otherwise it would differ on every run.
3. **Fallback after a reservation.** A failure after `reserve_operation` must fail closed or go to reconciliation, never back to the single-action loop. Test: Task 2c.8 `test_no_fallback_after_first_reservation`.
4. **A lineage value the approval did not bind.** The plan digest binds the placeholder `(step, path)`; lineage has one rule (target §6.4.3, ADR 0025): the value is copied from the earlier step's verified outcome and must match the schema type. A value from anywhere else, or of the wrong type, stops the plan before that step reserves. Test: Task 2c.8 `test_lineage_value_outside_verified_outcome_stops_plan`.
5. **Step N blocks step N+1 on the same connection.** An `UNKNOWN` or `CONNECTION_BUSY` step stops the remainder; the run goes to reconciliation and reports the unstarted steps. Test: Task 2c.8 `test_unknown_step_blocks_remaining_steps`.
6. **A multi-step plan approved through a UI that shows one action.** Test: Task 2c.7 `test_live_profile_refuses_multi_write_budget`.
7. **Profile schema edges.** A profile without `features` loads as all `off`; an unknown feature name is rejected (`extra="forbid"`). Test: Task 2b.1 `test_profile_features_default_off` and `test_profile_rejects_unknown_feature`.
8. **New event types break the UI.** `ui-core` selectors and i18n switch on `RunEventType`. Test: Task 2b.2 `pnpm --dir ui check` with a ui-core test that renders `feature.fallback` and every `ir.*` event (`ir.plan_compiled`, `ir.shadow_failed`, `ir.lineage_resolved`, `ir.step_verified`).

## Design refs

| Document | Section | Used by |
|---|---|---|
| `docs/design/target-architecture.md` | §1.3 task definition; §7.2 rule 1 | 2a.1, 2c.2, 2c.6 |
| `docs/design/target-architecture.md` | §5.1 principle 3; §5.4 step record | 2a.1, 2c.1, 2c.3 |
| `docs/design/target-architecture.md` | §6.4 Execution IR (proposed, `6aaab54`; reconciled in 2a.1) | all of 2c |
| `docs/design/target-architecture.md` | §15 module map (`contracts/task.py`, `kernel/step.py`); §17 C8, C11 | 2c.1, 2c.4 |
| `docs/design/mvp-detailed-design.md` | §7 action states; §9 reservations; §10 budgets; approval digest | 2c.4, 2c.7, 2c.8 |
| `docs/design/threat-model.md` | T20, T21, T22 (proposed, `6aaab54`); T22's test belongs to Phase 5 (benchmark auto-approve) | 2c.7, 2c.8 |

## ADRs

All five Phase 2 ADRs were written in `6aaab54` and are Proposed; 2a.1 reconciles them with this plan and 2a.2 records the owner's acceptance (0023 stays reserved for conversations; 0026 is the Phase 1d plugin-layout ADR).

| ADR | Decision | Status | Effect on this phase |
|---|---|---|---|
| [0027](../adr/0027-feature-toggles.md) | Feature toggles: `Profile.features`, modes, shadow comparison, `feature.fallback` with reason codes, readiness and evidence reporting | Written, Proposed | Blocks 2b |
| [0024](../adr/0024-plan-approval-model.md) | Approval model for multi-step plans: the approver approves the whole plan's digest once; deviation stops the plan; benchmark-only auto-approve for `read`/`write_low` (owner D-3); nothing modified after approval (owner D-4) | Written, Proposed | Blocks 2c.7 |
| [0025](../adr/0025-execution-ir.md) | Execution IR: ActionPlan, PlannedStep, lineage placeholders and their digest binding, per-step reservation and verification, partial failure, StepRecord (C8 part 1), `execution_ir` mode semantics; widens the ADR 0018 table (`VERIFYING → RUNNING`, `RUNNING → VERIFYING`) | Written, Proposed | Blocks 2c |
| [0028](../adr/0028-task-definitions.md) | Task definitions (C11): portable `TaskDefinition` and `AcceptanceSpec`, owned by domain packs, tool set fixed at admission; `TaskTemplate` becomes a projection; per-task approval TTL | Written, Proposed | Blocks 2c.2 |
| [0029](../adr/0029-capability-effect-declarations.md) | Capability effect declarations: `risk`, `reversibility` on contracts, `idempotency` on bindings; conservative defaults refused in live profiles (adoption review XA-01) | Written, Proposed | Blocks 2c.1, 2c.2, 2c.7, 2c.8 |
| 0006 | Approval digest canonicalization | Accepted | Plan digest uses `jcs-sha256-v1`; a 1-step plan's approval digest equals today's action digest |
| 0003, 0014 | Durability; approval binds versions and facts | Accepted | Per-step evidence before writes; revalidation before each step |
| 0004 | Agent driver integration | Accepted | `DriverStep` gains `ProposePlan` (SDK port change, covered by 0025) |
| 0018 | Run transition table and reason codes | Accepted 2026-10-14 | 2c.8 adds reason codes; new transitions come through ADR 0025 |
| 0020 | Connection-level write admission (`CONNECTION_BUSY`) | Accepted 2026-10-14 | Serial step dispatch relies on it |

**Owner decisions** (default applies if no answer):

| Id | Decision | Default |
|---|---|---|
| D0 | DR-01 asks for the design section and ADR before the detailed plan. This plan puts them inside the phase as Part 2a with gate G1 and writes 2c from the existing sketches, amended when the ADRs differ. The alternative is 2a as a separate pre-phase, with 2c rewritten after acceptance | 2a inside this plan, gate G1 |
| D1 | ADR numbers 0027 (toggles) and 0028 (task definitions); or fold both into 0025 | Separate ADRs, as numbered |
| D2 | ADR 0024 approval model | **Decided 2026-10-14:** approve the plan once; benchmark-only auto-approve allowed for `read`/`write_low` (adoption review D-3), implemented with Phase 5, not in Phase 2 |
| D3 | Approval surface for multi-step plans | Phase 2: fixtures, CLI and API only, with the live guard; UI plan approval is an `ag-*` thread with Phase 5 writes |
| D4 | ADRs 0018 and 0020 (DR-06) | **Done:** accepted 2026-10-14 with 0019, 0021, 0022 |
| D5 | Evidence bundle | Additive keys (`features`, `plan`, `steps`) under `e-agent-evidence-v1`; existing keys unchanged |

## Toggles and fallback

One toggle, `features.execution_ir`, covers task definitions, action plans and step records.

| Mode | Behaviour |
|---|---|
| `off` | Today's single-action loop. No IR is compiled, no step record is written, no new event appears. |
| `shadow` | The run acts on the existing path. After the existing proposal handling validates a proposal, the kernel compiles it into a 1-step ActionPlan, resolves the task definition, computes the plan digest and records `ir.plan_compiled` (plan digest, step count, task definition id and version, whether the step digest equals the action digest) and the step records. A compile or validation error records `ir.shadow_failed` and nothing else. No extra driver call, provider read or budget use. |
| `on` | The run executes the IR. The tool set comes from the task definition at admission. A single `ProposeAction` becomes a 1-step plan; a `ProposePlan` becomes an N-step plan. The plan is validated as a whole, approved once and dispatched step by step. |

The mode table and fallback rule are decided in target §6.4.8 (ADR 0027); this section restates them for the tasks.

**Fallback boundary** (ENG-TOGGLE-2): the first `reserve_operation` call (`src/e_agent/kernel/dispatch.py`, the `reserve_operation` call in `_dispatch`).
- Before it, with `on`: a task-definition, compile or validation failure records `feature.fallback` with a reason code (`IR_TASK_UNRESOLVED`, `IR_COMPILE_FAILED`, `IR_VALIDATION_FAILED`) and continues on the existing path. A single proposal goes to today's `_handle_proposal`. A multi-step `ProposePlan` cannot run on the old path, so it returns to the driver as a repair finding within `max_validation_repairs`, which is today's handling of an invalid proposal.
- After it: no fallback. A failed, `UNKNOWN` or busy step stops the plan; the run fails closed or goes to reconciliation, and the outcome reports committed, verified and unstarted steps.
- Fallback never bypasses approval, admission, verification or the transition table.

**Observability** (ENG-TOGGLE-3): `/health/ready` returns `features: {"execution_ir": "<mode>"}`; the evidence bundle records the same object.

## Gate

| Task | Gate set |
|---|---|
| 2a.1, 2a.2 | `full` (docs only; confirms nothing else moved) |
| 2b.1, 2b.2 | `full` and `pg` |
| 2b.3 | `full` and `e2e` |
| 2c.1, 2c.2, 2c.4, 2c.9 | `full` (2c.1, 2c.4 and 2c.9 also run `pg`, as ADR 0025 asks) |
| 2c.3, 2c.5, 2c.6, 2c.7, 2c.8 | `full` and `pg` |
| 2d.1 | end-of-phase levels 1–3 |
| 2d.2 | level 4 (live) |

**End-of-phase levels** (`eng-verify`, in order, on a clean tree): (1) the `full` gate; (2) the Postgres run (`pg` gate and `tests/conformance/test_run_store.py` with `E_AGENT_TEST_STORE=postgres`); (3) `make e2e`; (4) the live check on `odoo19-learning` (below).

## Live check

Run by the owner through the `live-sandbox` skill at the end of the phase. It exercises:
- `/health/ready` reports `features.execution_ir` for each mode used.
- Task 3 ("Draft a purchase order for any shortage from the approved supplier") three times: once with `off`, once with `shadow`, once with `on`. Expected: `off` matches the pre-phase behaviour; `shadow` records `ir.plan_compiled` with the step digest equal to the action digest and the same outcome as `off`; `on` runs a 1-step plan through approval, reservation, dispatch and read-back verification with step records for each stage.
- Task 1 (read-only shortage question) with `on`: the tool set equals the task definition's capabilities, and the answer passes the acceptance check.
- The evidence bundle of each run contains `features`; the `on` run also contains `plan` and `steps`.

It may not touch: `odoo-bench` or any container outside `odoo19-learning-*` and `e-agent-ledger`; live business data; multi-step writes (the live guard refuses them). Live keys expire 2026-10-19; a later check needs renewed keys. Results are reported separately from fixture results (ENG-EVID-2).

---

## Part 2a: design entry gate

The documents exist (commit `6aaab54`): target §6.4, threats T20–T22, ADRs 0024, 0025, 0027, 0028 and 0029 with their index rows, and the roadmap coverage row. 2a does not rewrite them; it makes them agree with this plan and the checkout, and records the owner's acceptance.

### Task 2a.1: reconcile the ADRs and §6.4 with this plan

**Files:** `docs/adr/0024-plan-approval-model.md`, `docs/adr/0025-execution-ir.md`, `docs/adr/0027-feature-toggles.md`, `docs/adr/0028-task-definitions.md`, `docs/adr/0029-capability-effect-declarations.md`, `docs/adr/README.md`, `docs/design/target-architecture.md` (§6.4), this plan if a shape changes.

**Interfaces:** consumes the five ADRs and §6.4; produces the shapes 2b and 2c implement.

- [ ] Compare each ADR's contract shapes with Tasks 2b.1–2c.9 and amend this plan or the ADR in the same commit where they differ (ENG-PLAN-3). Known differences to settle:
  - ADR 0028 names the run's tool set but not how it reaches a driver built once per runtime. Record this plan's mechanism (Task 2c.6): `DriverInput.allowed_capabilities`, set by the run loop from the admitted definition, with the kernel refusing any read or proposal outside it. It is an additive SDK port change, in the same `sdk_api` minor bump as `ProposePlan` (ADR 0025).
  - Lineage: `LineageRef(step_id, path)` with the one copy-from-verified-outcome rule (§6.4.3), and no `PlannedStep.lineage` field; the plan's tasks use that shape.
  - ADR 0025's gate line and this plan's Gate table name the same sets.
- [ ] Fix the stale code references (ENG-DOC-1): ADR 0027 `server/profile.py:70-81` (the `Profile` record is now further down), ADR 0028 `bootstrap.py:106-133` (now `tool_specs`, 100-127), and ADR 0029 `adapters/odoo/executor.py:340-347` (now `plugins/erp/odoo/executor.py`). Cite functions rather than line numbers where they can be.
- [ ] Run `uv run python scripts/repo_move.py check`; expected: no broken links.
- [ ] Commit `docs(adr): reconcile Phase 2 ADRs with the plan`.

### Task 2a.2: owner acceptance (gate G1)

**Files:** the five ADRs (status lines), `docs/adr/README.md` (status column), `docs/design/target-architecture.md` (§6.4 tag once accepted), this plan's status line.

- [ ] The owner accepts or amends ADRs 0024, 0025, 0027, 0028, 0029 and §6.4. Record each status as Accepted with the date, or record the amendment and repeat 2a.1 for it.
- [ ] Run `uv run python scripts/repo_move.py check`; expected: no broken links.
- [ ] Commit `docs(adr): accept Phase 2 ADRs 0024, 0025, 0027-0029`.

**Owner gate G1:** 2b starts after 0027 is accepted; 2c starts after 0024, 0025, 0028 and 0029 are accepted.

---

## Part 2b: toggle infrastructure

### Task 2b.1: `Profile.features`

**Files:** `src/e_agent/contracts/features.py` (new: `FeatureMode` StrEnum, `Features` record with `execution_ir: FeatureMode = FeatureMode.OFF`), `src/e_agent/server/profile.py` (`Profile.features: Features = Features()`), `src/e_agent/kernel/coordinator.py` (accepts `features`), `src/e_agent/server/bootstrap.py` (passes it), `tests/unit/contracts/test_features.py`, `tests/unit/server/test_profile_features.py`, `tests/unit/kernel/golden/off_mode_events.json` (new baseline), `tests/unit/kernel/record_off_baseline.py` (recording script), `tests/unit/kernel/test_off_baseline.py`, `tests/unit/server/test_committed_profiles.py` (covers all three committed profiles).

**Interfaces:** produces `Features` and `FeatureMode` for every later task; the coordinator exposes `self._features`. Toggles come only from the typed profile, never from an environment variable (ADR 0027; ENG-ARCH-6).

- [ ] Record the golden baseline first, on the unchanged kernel: `uv run python tests/unit/kernel/record_off_baseline.py` writes the event types, action states and digests of the notes-domain write run and the ERP draft-po fixture run into `off_mode_events.json`, with a deterministic id source injected for `new_id` and generated ids normalised in the stream; `test_off_baseline.py` only asserts against it and fails on an empty golden (`test_off_baseline_fails_on_empty_golden`, ENG-EVID-4). Commit the baseline before any other change.
- [ ] Failing tests: `test_profile_features_default_off` (fixture profile without `features` → `execution_ir == "off"`), `test_profile_rejects_unknown_feature` (`{"features": {"nope": "on"}}` raises `ValidationError`), `test_feature_mode_values` (exactly `off`, `shadow`, `on`), `test_coordinator_receives_profile_features`.
- [ ] Run `uv run pytest -q tests/unit/contracts/test_features.py tests/unit/server/test_profile_features.py`; expected: fails with `ModuleNotFoundError: No module named 'e_agent.contracts.features'`.
- [ ] Implement. Add `"features": {"execution_ir": "off"}` to the three committed profiles.
- [ ] Run the same command; expected: all pass. Run `uv run pytest -q tests/unit/server/test_committed_profiles.py`; expected: pass, with `test_committed_profiles_keep_execution_ir_off` loading all three committed profiles, including the simulator's `fixture_profile.json`.
- [ ] Commit `feat(contracts): profile feature toggles, default off`.

### Task 2b.2: `feature.fallback` event

**Files:** `src/e_agent/contracts/events.py` (`RunEventType.FEATURE_FALLBACK = "feature.fallback"`, `IR_PLAN_COMPILED = "ir.plan_compiled"`, `IR_SHADOW_FAILED = "ir.shadow_failed"`, `IR_LINEAGE_RESOLVED = "ir.lineage_resolved"`, `IR_STEP_VERIFIED = "ir.step_verified"`; target §6.4.5, §6.4.6), `src/e_agent/contracts/run.py` (`ReasonCode` members `IR_TASK_UNRESOLVED`, `IR_COMPILE_FAILED`, `IR_VALIDATION_FAILED`), `src/e_agent/kernel/features.py` (new: `record_fallback(feature, reason, detail)` mixin method), `tests/unit/kernel/test_feature_fallback.py`, `ui/packages/ui-core/src/i18n.ts`, `ui/packages/ui-core/src/store.ts` (only if the switch is exhaustive), `ui/packages/ui-core/test/feature-events.test.ts`.

**Interfaces:** consumes `Features`; produces `record_fallback` for 2c.6 and 2c.8.

- [ ] Failing tests: `test_record_fallback_appends_event_with_reason` (payload carries `feature`, `reason_code`, `detail`), parametrised over both stores in `tests/unit/kernel/` so the `pg` gate runs it (ENG-STORE-1); ui-core test `renders feature and IR events without crashing and with a label`.
- [ ] Run `uv run pytest -q tests/unit/kernel/test_feature_fallback.py`; expected: fails with `AttributeError: FEATURE_FALLBACK`. Run `pnpm --dir ui test`; expected: the new `feature-events.test.ts` test fails.
- [ ] Implement. UI labels follow `ag-ui-implement` (event labels are user-visible text; no provider identifiers).
- [ ] Run both commands; expected: pass. Run the `pg` gate; expected: pass.
- [ ] Commit `feat(kernel): feature.fallback and IR event types`.

### Task 2b.3: toggles in readiness and evidence

**Files:** `src/e_agent/server/api.py` (`/health/ready` adds `features`; the evidence route passes `features` to `build_evidence`), `src/e_agent/kernel/evidence.py` (`build_evidence(..., features=...)` adds `features`), `src/e_agent/server/cli.py` (evidence command passes features), `ui/packages/client/openapi.json`, `ui/packages/client/src/schema.ts` (regenerated), `tests/unit/server/test_api.py`, `tests/unit/kernel/test_evidence.py`.

- [ ] Failing tests: `test_ready_reports_features` (`{"execution_ir": "off"}` for the fixture profile, `"shadow"` when the profile says so), `test_evidence_records_features`, `test_evidence_v1_keys_unchanged` (D5: all existing keys still present with the same schema id).
- [ ] Run `uv run pytest -q tests/unit/server/test_api.py -k ready tests/unit/kernel/test_evidence.py`; expected: the three new tests fail with `KeyError: 'features'`.
- [ ] Implement; regenerate with `uv run python scripts/export_openapi.py` and `pnpm --dir ui gen`.
- [ ] Run the same tests, `uv run python scripts/export_openapi.py --check` and `pnpm --dir ui gen:check`; expected: pass. `/health/ready` returns an untyped mapping, so readiness alone causes no OpenAPI drift; regenerate only if the evidence response model changes. Run `make e2e`; expected: pass.
- [ ] Commit `feat(server): report feature toggles in readiness and evidence`.

---

## Part 2c: execution IR

### Task 2c.1: IR contracts

**Files:** `src/e_agent/contracts/task.py` (`TaskDefinition`, `AcceptanceSpec`), `src/e_agent/contracts/plan.py` (adds `ActionPlan`, `PlannedStep`, `LineageRef`; `ActionProposal` unchanged), `src/e_agent/contracts/step.py` (`StepRecord`, `StepKind`, `StepStatus`, `StepUsage`, `schema_version = "step.v1"`), `src/e_agent/contracts/action.py` (nullable `plan_id`, `step_index` on `ActionRecord`), `src/e_agent/contracts/run.py` (`RunRecord` gains nullable `task_id`, `task_version`; C11), `src/e_agent/contracts/capability.py` (`Risk`, `Reversibility` on `CapabilityDescriptor`; `Idempotency` on `CapabilityBinding`, ADR 0029), `src/e_agent/sdk/manifest.py` (`BindingTemplate.idempotency`), `tests/unit/contracts/test_capability_effects.py`, `tests/unit/contracts/test_task.py`, `tests/unit/contracts/test_action_plan.py`, `tests/unit/contracts/test_step.py`.

**Interfaces:** produces the records every 2c task uses; portable records only (ENG-ARCH-2).

- [ ] Failing tests: `test_task_definition_requires_capabilities_and_acceptance`; `test_action_plan_rejects_duplicate_step_ids`; `test_action_plan_rejects_unknown_dependency`; `test_action_plan_rejects_cycle`; `test_lineage_ref_must_point_to_an_earlier_dependency`; `test_step_record_fields_match_target_5_4`; `test_contract_records_are_frozen`; `test_read_risk_only_on_read_or_answer_effects`; `test_effect_declaration_defaults` (write → `write_high`, `irreversible`; binding → `none`); `test_lineage_key_literal_refused`; `test_lineage_ref_has_step_and_path_only`; `test_action_record_plan_fields_default_null`; `test_run_record_task_fields_default_null`.
- [ ] Run `uv run pytest -q tests/unit/contracts -k "task or plan or step"`; expected: `ModuleNotFoundError: No module named 'e_agent.contracts.task'`.
- [ ] Implement; structural validation lives in the records, policy validation stays in the kernel.
- [ ] Run the same command; expected: pass. Run `uv run lint-imports`; expected: every contract kept.
- [ ] Commit `feat(contracts): task definition, action plan and step record`.

### Task 2c.2: task definitions for the ERP pack

Builds on the Phase 1d task presets (Task 1d.3): each of the eight task definitions extends the `TaskPreset` the domain pack already contributes for its task kind, so the preset and the definition do not become two catalogues.

**Files:** `src/e_agent/plugins/erp/domain/tasks/` (one resource file per task kind, eight), `src/e_agent/plugins/erp/domain/e_agent_plugin.json` (declares the task definitions), `src/e_agent/plugins/erp/domain/plugin.py` (exposes them), `src/e_agent/sdk/` (plugin API to provide task definitions, if the ADR places it there), `src/e_agent/kernel/registry.py` (admits task definitions: every capability must be an admitted binding, duplicate `task_id` refused; refuses a defaulted write effect declaration with `environment: live`, ADR 0029), the ERP pack and Odoo manifests (effect declarations), `tests/unit/plugins/erp/domain/test_task_definitions.py`, `tests/unit/kernel/test_registry.py`, `tests/unit/kernel/conftest.py` (notes-domain task definition), `tests/unit/plugins/erp/domain/golden/task_capabilities.json` (new).

**Interfaces:** today every run gets one tool set: each agent-visible capability with exactly one binding (`tool_specs` in `server/bootstrap.py`). There is no per-task set to copy. This task decides each definition's narrowed capability set from the task's goal and records it.

- [ ] Failing tests: `test_eight_task_definitions_load_from_resources`; `test_task_capabilities_match_golden` (the golden file records today's single tool set and each definition's chosen subset; every subset is inside today's set; non-zero case count); `test_assistant_definition_is_read_only` (the general `assistant` definition, ADR 0028); `test_definition_budgets_only_narrow` (a definition budget above the profile's is refused at admission); `test_registry_refuses_task_with_unadmitted_capability`; `test_registry_refuses_duplicate_task_id`; `test_notes_domain_task_definition_admitted` (genericity, DR-08); `test_live_profile_refuses_defaulted_write_declaration`; `test_fixture_profile_reports_defaulted_declarations`; `test_erp_write_capabilities_declare_effects`; `test_pack_without_task_definitions_admitted` (a pack that declares none, such as the `check_core_only.py` test pack, still loads).
- [ ] Run `uv run pytest -q tests/unit/plugins/erp/domain/test_task_definitions.py tests/unit/kernel/test_registry.py`; expected: the new tests fail (`FileNotFoundError` for the resources, then registry assertions).
- [ ] Implement; manifests and resources change, so re-pin digests with `scripts/plugin_inventory.py` in the same commit.
- [ ] Run the same command, `uv run python scripts/check_wheels.py` and `uv run python scripts/check_core_only.py`; expected: pass; the domain-erp wheel contains `e_agent/plugins/erp/domain/tasks/*`, and the core-only check passes with a pack that declares no task definitions.
- [ ] Commit `feat(erp): task definitions for the eight ERP tasks`.

### Task 2c.3: store support for plans and steps

**Files:** `src/e_agent/adapters/postgres/migrations/0005_action_plans_and_steps.sql` (tables `action_plans`, `run_steps`; nullable `plan_id`, `step_index` on actions), `src/e_agent/sdk/store.py` (`put_plan`, `get_plan`, `list_steps`; `EventSpec` batches may carry step records so steps commit in the same transaction as run events), `src/e_agent/kernel/memory_store.py`, `src/e_agent/adapters/postgres/store.py`, `tests/conformance/test_run_store.py`.

- [ ] Failing conformance tests: `test_put_and_get_plan`; `test_steps_commit_with_events_atomically` (a failing append leaves neither); `test_step_sequence_is_monotonic_per_run`; `test_tenant_scope_on_plans_and_steps`; `test_existing_rows_have_null_plan_id`.
- [ ] Run `uv run pytest -q tests/conformance/test_run_store.py`; expected: `AttributeError: put_plan`.
- [ ] Implement both stores and the migration.
- [ ] Run the same command; expected: pass. Run the `pg` gate and `E_AGENT_TEST_STORE=postgres uv run pytest -q tests/conformance/test_run_store.py`; expected: pass (ENG-STORE-1).
- [ ] Commit `feat(store): action plans and step records in both stores`.

### Task 2c.4: IR compiler, validator and plan digest

**Files:** `src/e_agent/kernel/ir.py` (new: `compile_proposal(proposal, task) -> ActionPlan`, `validate_plan(plan, task, ctx) -> tuple[Finding, ...]`, `plan_digest_input(plan, ...)`), `src/e_agent/kernel/approval.py` (plan digest using the existing `compute_digest`), `src/e_agent/kernel/step.py` (new: step-record builders), `tests/unit/kernel/test_ir.py`, `tests/unit/contracts/test_digest.py` (plan golden vectors), `ui/packages/ui-core/test/digest.test.ts` (1-step plan vector).

- [ ] Failing tests: `test_single_proposal_compiles_to_one_step_plan`; `test_one_step_plan_digest_equals_action_digest`; `test_plan_digest_golden_vectors` (two- and three-step plans with a lineage placeholder; asserts a non-zero vector count); `test_plan_digest_changes_when_dependency_or_path_changes`; ui-core `1-step plan digest equals the action digest` (same vector in TypeScript, so `ui-core/src/digest.ts` stays valid); `test_validate_rejects_capability_outside_task_definition`; `test_validate_rejects_write_count_over_budget`; `test_validate_is_pure` (no store or driver access).
- [ ] Run `uv run pytest -q tests/unit/kernel/test_ir.py tests/unit/contracts/test_digest.py`; expected: `ModuleNotFoundError: No module named 'e_agent.kernel.ir'`.
- [ ] Implement.
- [ ] Run the same command and `pnpm --dir ui test`; expected: pass. Run the `pg` gate; expected: pass.
- [ ] Commit `feat(kernel): IR compiler, plan validation and plan digest`.

### Task 2c.5: shadow mode

**Files:** `src/e_agent/kernel/proposals.py` (after today's validation, shadow compiles and records), `src/e_agent/kernel/features.py`, `tests/unit/kernel/test_execution_ir_shadow.py`, `tests/unit/kernel/test_off_baseline.py`.

- [ ] Failing tests: `test_shadow_records_plan_compiled_with_matching_digest`; `test_shadow_writes_step_records`; `test_shadow_compile_error_records_shadow_failed_and_run_unchanged`; `test_shadow_adds_no_driver_calls_reads_or_budget` (counting driver and executor fakes; budget counters equal to `off`); `test_shadow_outcome_equals_off`; `test_off_mode_event_stream_matches_baseline` (against the 2b.1 golden file).
- [ ] Run `uv run pytest -q tests/unit/kernel/test_execution_ir_shadow.py tests/unit/kernel/test_off_baseline.py`; expected: the shadow tests fail (no `ir.plan_compiled` event); the baseline test passes.
- [ ] Implement.
- [ ] Run the same command; expected: pass. Run the `pg` gate; expected: pass.
- [ ] Commit `feat(kernel): execution IR shadow mode`.

### Task 2c.6: `on` mode, single step

**Files:** `src/e_agent/sdk/ports.py` (`DriverInput.allowed_capabilities: tuple[str, ...] | None = None`; `None` keeps today's set), `src/e_agent/kernel/run_loop.py` (resolves the run's task definition at admission, records `task_id` and `task_version`, sets `allowed_capabilities` on every turn), `src/e_agent/kernel/gateway.py` (refuses a read outside the set), `src/e_agent/kernel/proposals.py` (`on` path: compile, validate, approve the 1-step plan; a proposal outside the set is a finding), `src/e_agent/kernel/approval_flow.py` (the definition's `approval_ttl` replaces the global TTL for its runs), `src/e_agent/kernel/dispatch.py` (step records around reserve, dispatch, verify), `src/e_agent/kernel/verification.py` (acceptance check at run end), `src/e_agent/contracts/run.py` (`ReasonCode.ACCEPTANCE_UNMET`, classified failed), `src/e_agent/adapters/pydantic_ai/driver.py` (offers only the allowed tools on a turn), `tests/unit/kernel/test_execution_ir_on.py`, `tests/unit/adapters/pydantic_ai/test_driver_tool_filter.py`.

**Interfaces:** the API builds one runtime, and one driver, for every task kind (`build_runtime(profile)` in `server/api.py`), so the tool set is narrowed per run through `DriverInput`, not per driver. The kernel's refusal is the boundary; the driver's filter is what the model sees.

- [ ] Failing tests: `test_on_tool_set_equals_task_definition`; `test_on_read_outside_task_definition_refused`; `test_on_run_records_task_id_and_version`; `test_on_task_approval_ttl_replaces_global`; `test_on_definition_budgets_narrow_profile_budgets`; `test_driver_offers_only_allowed_tools` (FunctionModel; `None` offers today's set); `test_on_single_step_run_records_steps_for_each_stage`; `test_on_single_step_approval_presentation_unchanged` (same `ApprovalPresentation` and digest as `off`); `test_on_acceptance_unmet_fails_run_with_reason` (`ACCEPTANCE_UNMET`, ADR 0028); `test_on_unresolved_task_falls_back_with_reason` (`IR_TASK_UNRESOLVED`, run completes on the old path); `test_on_validation_error_before_reservation_falls_back`; `test_model_cannot_mark_plan_verified` (ENG-TRUST-1).
- [ ] Run `uv run pytest -q tests/unit/kernel/test_execution_ir_on.py tests/unit/adapters/pydantic_ai/test_driver_tool_filter.py`; expected: fails (`allowed_capabilities` unknown; tool set is today's list; no step records).
- [ ] Implement.
- [ ] Run the same command; expected: pass. Run the replay suite and the prompt golden (Global Constraints, ENG-EVID-5); expected: pass with `off`, every recording replayed. Run the `pg` gate; expected: pass.
- [ ] Commit `feat(kernel): execution IR on, single-step plans`.

### Task 2c.7: multi-step plans, approval and dispatch

**Files:** `src/e_agent/kernel/approval.py` (`ApprovalPresentation` gains optional `plan_steps`, the plan's highest `risk` and its irreversible steps; a 1-step plan leaves `plan_steps` empty), `src/e_agent/kernel/approval_flow.py` (one approval for the plan digest), `src/e_agent/kernel/dispatch.py` (serial dependency-order dispatch; step N+1 reserves after step N is verified; facts and policy revalidated before each reservation), `src/e_agent/contracts/run.py` (run pairs `VERIFYING → RUNNING` and `RUNNING → VERIFYING`, ADR 0025), `src/e_agent/kernel/transitions.py`, `src/e_agent/server/bootstrap.py` (live guard), `src/e_agent/server/cli.py` (prints plan steps before `--approve`), `src/e_agent/plugins/erp/domain/testing/scripted_tasks.py` (a two-step fixture scenario), `tests/unit/kernel/conftest.py` (two-step notes scenario), `tests/unit/kernel/test_action_plan_dispatch.py`, `tests/unit/server/test_bootstrap_guards.py`, OpenAPI and `schema.ts` regenerated.

- [ ] Failing tests: `test_plan_approved_once_dispatches_steps_in_order`; `test_each_step_reserves_after_previous_verified`; `test_lineage_value_resolved_and_recorded_before_reservation`; `test_stale_fact_before_step_two_stops_plan` (ENG-TRUST-3); `test_approval_for_other_digest_rejected`; `test_presentation_shows_highest_risk_and_irreversible_steps` (ADR 0029); `test_live_profile_refuses_multi_write_budget`; `test_erp_two_step_fixture_scenario` (scripted); `test_notes_two_step_plan` (genericity); `test_verifying_to_running_allowed_only_between_plan_steps`. Steps run serially inside the run loop; no task is started outside `supervised_task` (ENG-ARCH-7).
- [ ] Run `uv run pytest -q tests/unit/kernel/test_action_plan_dispatch.py tests/unit/server/test_bootstrap_guards.py`; expected: fails (only one write admitted; no guard).
- [ ] Implement; regenerate the OpenAPI document and the UI client.
- [ ] Run the same command, `uv run python scripts/export_openapi.py --check` and `pnpm --dir ui gen:check`; expected: pass. Run the `pg` gate; expected: pass.
- [ ] Commit `feat(kernel): multi-step action plans with one approval`.

### Task 2c.8: plan failure semantics

**Files:** `src/e_agent/contracts/run.py` (reason code `PLAN_LINEAGE_REJECTED`; step outcomes keep today's codes, ADR 0025; the run pairs arrive in 2c.7), `src/e_agent/kernel/transitions.py`, `src/e_agent/kernel/dispatch.py`, `src/e_agent/kernel/recovery.py`, `src/e_agent/kernel/evidence.py` (`plan` and `steps` sections), `tests/unit/kernel/test_action_plan_failures.py`, `tests/unit/kernel/test_recovery.py`.

- [ ] Failing tests: `test_no_fallback_after_first_reservation`; `test_step_failure_keeps_verified_steps_and_reports_remainder`; `test_unknown_step_blocks_remaining_steps` (run goes to reconciliation; no replay, ENG-TRUST-5); `test_connection_busy_on_step_two_stops_plan`; `test_lineage_value_outside_verified_outcome_stops_plan`; `test_recovery_resumes_plan_without_replaying_committed_steps`; `test_evidence_lists_plan_and_steps`; `test_unknown_step_not_resent_even_with_provider_key` (re-send stays off in Phase 2, ADR 0029); `test_step_reason_codes_independent_of_plan_length` (a provider error on step 2 classifies like one on a 1-step run).
- [ ] Run `uv run pytest -q tests/unit/kernel/test_action_plan_failures.py tests/unit/kernel/test_recovery.py`; expected: the new tests fail. Recovery reuses the existing supervised sweeper; no new background task or TID251 exemption (ENG-ARCH-7).
- [ ] Implement.
- [ ] Run the same command; expected: pass. Run the `pg` gate; expected: pass.
- [ ] Commit `feat(kernel): action plan partial failure and reconciliation`.

### Task 2c.9: driver emits IR

**Files:** `src/e_agent/sdk/ports.py` (`ProposePlan(plan: ActionPlan)` added to `DriverStep`; `sdk_api` minor bump), plugin manifests' `sdk_api` ranges, `src/e_agent/adapters/pydantic_ai/driver.py` (with `on`, offers plan output when the task definition allows more than one write), `src/e_agent/plugins/erp/domain/testing/scripted_tasks.py` (scripted driver emits `ProposePlan`), `tests/unit/adapters/pydantic_ai/test_driver_plan.py`, `tests/unit/sdk/test_ports.py`, `tests/unit/adapters/pydantic_ai/golden/base_instructions.txt` (if the base prompt changes; today it says to call exactly one write tool), a new recording under the replay suite's recordings for a plan output.

- [ ] Failing tests: `test_function_model_plan_output_becomes_propose_plan` (pydantic-ai `FunctionModel`, no live model); `test_driver_offers_plan_output_only_when_task_allows_multiple_writes`; `test_driver_off_mode_outputs_unchanged`; `test_plan_with_model_chosen_connection_is_rejected` (model output never selects connections); `test_sdk_api_range_admits_existing_plugins`.
- [ ] Run `uv run pytest -q tests/unit/adapters/pydantic_ai/test_driver_plan.py tests/unit/sdk/test_ports.py`; expected: `ImportError: cannot import name 'ProposePlan'`.
- [ ] Implement.
- [ ] Run the same command and `uv run lint-imports`; expected: pass, every contract kept. Run the replay suite and the prompt golden (ENG-EVID-5); expected: pass, the new plan recording replayed, and `off` recordings unchanged.
- [ ] Commit `feat(driver): drivers emit action plans`.

---

## Part 2d: verification

### Task 2d.1: end-of-phase verification and handoff

**Files:** `README.md` (toggle and plan commands), `docs/roadmap.md` (Phase 2 status), `docs/handoffs/<date>-phase2-execution-ir.md`, `harness/state/2/`.

- [ ] Run `eng-verify` levels 1–3 on a clean tree; expected: `full` pass, `pg` and Postgres store conformance pass, `make e2e` pass. Record each result.
- [ ] Phase review with `eng-review` (reviewer subagent) against this plan and the ENG rules; fix findings as `2.R<n>` tasks.
- [ ] Write the handoff with `eng-handoff`: what changed, each verification level with its output, rulings, changes outside the repository, what remains (UI plan approval, live multi-step writes, Phase 3 items) (ENG-DOC-2).
- [ ] Commit `docs: Phase 2 handoff and roadmap status`.

### Task 2d.2: live check

- [ ] The owner runs the live check above through `live-sandbox`; the results go into the handoff, labelled live and separate from fixture results.
- [ ] Commit `docs: Phase 2 live check results`.

## Self-review

- **Spec coverage.** Roadmap row: toggle infrastructure → 2b.1–2b.3; TaskDefinition (C11) → 2a.1, 2c.1, 2c.2, 2c.6; ActionPlan with dependencies, lineage and one approval digest → 2c.1, 2c.4, 2c.7, 2c.8; StepRecord (C8) → 2c.1, 2c.3, 2c.5, 2c.6; driver emits IR → 2c.9; kernel validates, approves, dispatches step by step and verifies → 2c.4, 2c.6, 2c.7; toggle with fallback → 2b.2, 2c.5, 2c.6, 2c.8; ADRs C8, C11 and the action-plan IR → 2a.1, 2a.2. DR-01 → §6.4 (exists), accepted in 2a.2. Roadmap rule 1 end-of-phase levels → 2d.1, 2d.2.
- **Placeholder scan.** No TBD. The open shapes are settled by the ADRs; 2a.1 amends this plan or the ADR where they differ.
- **Name consistency.** `Features`, `FeatureMode`, `execution_ir`, `feature.fallback`, `ir.plan_compiled`, `ir.shadow_failed`, `ir.lineage_resolved`, `ir.step_verified`, `ActionPlan`, `PlannedStep`, `LineageRef`, `StepRecord`, `ProposePlan`, `compile_proposal`, `validate_plan`, `Risk`, `Reversibility`, `Idempotency`, the `$lineage` digest key, `allowed_capabilities`, `PLAN_LINEAGE_REJECTED` and `ACCEPTANCE_UNMET` are used with the same spelling in every task.
- **Review Focus coverage.** Items 1–8 each name a task and a test.
