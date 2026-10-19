# Phase 3: Cognition and Context Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Status:** Draft 2026-10-19, written after Phase 2 merged (PR #6, `3ec2d70`). Awaiting owner review; no task starts before the owner approves it and accepts the ADRs at gate G2 (Task 3a.2). The decisions table below carries a recommended default for every open choice.

**Goal:** the kernel decides what reaches the model (a budgeted, minimized, fenced context pack built from a progress ledger), answers carry citations the kernel checks against this run's recorded evidence, every proposal can carry a checked rationale, and any run can be reconstructed and explained from `run_events` alone. The new runtime paths sit behind toggles that fall back to today's driver history.

**Architecture:** the plan has seven parts.
- **3a (design entry gate, no runtime code):** three new ADRs (0031 progress ledger, repeat detection and run reconstruction; 0032 ContextAssembler; 0033 explanation and grounded answers), the Phase 3 parts of ADR 0030 (Proposed), and the target sections they decide, reconciled with this plan and accepted by the owner (gate G2).
- **3b (data boundary and toggles):** the ADR 0030 hosted-route startup rule lands first, as that ADR requires, then the `features` fields, then data classes on schemas and stored records.
- **3c (projections, read-only):** the progress ledger, run reconstruction (U3) and the deterministic explanation projection (Q5, G11), computed from the ledger and changing no run.
- **3d (context assembly):** contracts, the pure assembler (layers, budgets, drop log, bounded and masked observations, fencing), shadow comparison, `on` rendering per target §7.4, and `KERNEL-REPEAT`.
- **3e (answers and rationale):** grounded answers with citations, `ProposalRationale`, and drivers that emit both.
- **3f (driver conformance):** one suite that every driver passes.
- **3g (verification):** end-of-phase levels 1–3, the phase review, the handoff and the live check.

**Tech Stack:** Python 3.12+, Pydantic v2 records (`e_agent.contracts`), pydantic-ai driver (`adapters/pydantic_ai`), memory and Postgres stores, pytest, the development harness (`uv run e-agent-harness`).

**Spec:** [roadmap](../roadmap.md) row 3 ("Cognition and context"); [core plan](2026-10-12-core-conversation-cognition.md) Phases 3–4 (its Phase 2 shipped as roadmap Phase 2; step records shipped in Phase 2 Task 2c.3); [target architecture](../design/target-architecture.md) §5.1, §5.6, §6.2, §6.3, §7.2, §7.4, §13.3 and fitness rows U3, Q5, G11; ADRs 0004, 0007, 0018, 0022, 0027 (accepted), 0030 (Proposed); [threat model](../design/threat-model.md) T1, T6, T12, T13, T17, T23, T24; [principles](../design/principles.md) PR-13, PR-15, PR-21, PR-26, PR-28, PR-32, PR-34; the [Phase 2 handoff](../handoffs/2026-10-18-phase2-execution-ir.md).

## Owner decisions

Each row has a recommended default. "Approve" accepts every default; name a row to change it.

| ID | Decision | Recommended default |
|---|---|---|
| D1 | Toggle split | Three toggles: `features.context_assembler` (assembler, minimization, bounded observations, §7.4 rendering), `features.kernel_repeat` (`KERNEL-REPEAT`) and `features.grounded_answers` (citation and rationale checks). Each changes behaviour on its own and gets its own `off`-mode proof. Projections (3c) get no toggle: they change no run |
| D2 | Ollama route boundary | An `ollama` route is `local` when its base URL host is loopback (`localhost`, `127.0.0.0/8`, `::1`); any other host must declare `data_boundary`. A `litellm` route is `hosted:unknown` unless declared. The owner's live profile uses a loopback Ollama, so it needs no edit |
| D3 | Bounded results | Bounding happens in the context pack, not in the gateway: the ledger keeps the full observation, the pack carries at most the capability's bound and marks the rendered observation `PARTIAL` with `truncated`. ADR 0030's Gates (Phase 3) win over its index row ("markers Phase 5"), which 3a.1 corrects |
| D4 | Grounded answer shape | Today's typed, per-domain answer contracts keep their verifiers and gain an optional `citations` list (`Citation(evidence_id, pointer, value)`, `pointer` an RFC 6901 JSON pointer into the observation's data). The kernel checks citations generically. No new generic `grounded.answer.v1` contract, which the core plan sketched before typed answers existed |
| D5 | Rationale finding | `ProposalRationale` is optional. With `grounded_answers: on`, a rationale whose evidence ref is not in this run, or whose rule is not in the inventory, is the repair finding `KERNEL-RATIONALE` within `max_validation_repairs`. Rationale is never an approval input (target §5.6) |
| D6 | Run reconstruction gaps | Events gain the payload keys reconstruction needs, additively, in Task 3c.2, and the Phase 2 `off` goldens are re-recorded in that one commit with the diff limited to the added keys. The alternative, reconstructing only what events carry today, leaves U3 partial |
| D7 | Rendering migration | `on` bumps the driver continuation `STATE_SCHEMA`. An in-flight `on` continuation of the old schema fails closed (`INTERRUPTED`, `CONTINUATION_SCHEMA`); `off` and `shadow` continuations are unchanged. No migration code, because no `on` run exists before this phase |
| D8 | Phase size and cut line | Must-have: 3a–3e. 3f (driver conformance) and 3c.3 (explanation projection) are the cut line: if the phase runs long, they move to a Phase 3′ with their own plan rather than being skipped |
| D9 | `credential_version` in evidence | The evidence export shows `credential_version` as its first 12 characters plus `…`, which still shows whether a credential changed and stops the secret-scan false positive pinned in `.gitleaksignore` (Phase 2 open item). The ledger keeps the full value |
| D10 | UI | Citations, rationale and the explanation are exposed through the evidence bundle and the CLI only. Their UI (timeline, citation display, rationale second on the approval card) is a later UI plan |

## Global Constraints

- **Branch** `phase3/cognition-context` from `main` at `3ec2d70` (Phase 2 merged). Stage explicit paths. Every commit ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. `main` is protected (strict, five required checks): changes reach it only through a PR whose checks pass. Merge, push and rebase only on the owner's instruction.
- **Harness phase `3`.** Features in `harness/state/3/features.json` (`F-3a-1` … `F-3g-2`, one per task), one task contract per task (`uv run e-agent-harness new-task 3 <id> --feature <F-id> --gate <set> --paths ...`), `check-scope` before each commit, `gate <set>` after the commit on a clean tree, `close-check` before a task closes (ENG-WORK-1, ENG-EVID-1). `harness/context.toml` `active_plan` switches to this plan in the commit that records the owner's approval.
- **Gate commands** (from `harness/context.toml`):
  - `full`: `uv sync --locked`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy`, `uv run lint-imports`, `uv run python scripts/export_openapi.py --check`, `uv run pytest -q`, `pnpm --dir ui gen:check`, `pnpm --dir ui check`, `uv run python scripts/check_core_only.py`.
  - `pg`: `E_AGENT_TEST_STORE=postgres uv run pytest -q tests/unit/kernel tests/conformance tests/unit/adapters/postgres`, with `E_AGENT_TEST_PG_DSN` set to the `e_agent_test` database and never the live ledger's database (G-11).
  - `e2e`: `make e2e`. `core`: `uv run python scripts/check_core_only.py`. `live`: `scripts/env_check.py` and `scripts/odoo_sandbox.py info`.
- **Design before code.** Part 3a's ADRs are accepted by the owner before 3b starts. If an accepted ADR changes a shape below, the accepting commit amends this plan (ENG-PLAN-3, G-7).
- **Authoritative files mid-task (G-7).** A task that edits a digest input (the target architecture, the ADR index, the roadmap, this plan) runs `uv run e-agent-harness refresh-task` before `close-check`.
- **Toggle default `off`.** Every committed profile (`src/e_agent/plugins/erp/simulator/fixture_profile.json`, `profiles/dev-ollama.json`, `profiles/live.example.json`) keeps `context_assembler`, `kernel_repeat` and `grounded_answers` `off`; `execution_ir` stays `off`.
- **`off` is today.** With the three new toggles `off`, the event stream, action records, digests, outcomes and the pinned model request (`tests/unit/adapters/pydantic_ai/golden/off_model_request.json`) of every existing test are unchanged. The one planned exception is D6: Task 3c.2 adds payload keys and re-records the `off` goldens in a single commit whose diff is limited to those keys.
- **Driver changes** run `uv run pytest -q tests/unit/server/test_recorded_model_replays.py tests/unit/adapters/pydantic_ai/test_prompt_golden.py` (PR-32). An intended prompt change updates `tests/unit/adapters/pydantic_ai/golden/base_instructions.txt` in the same commit (ENG-EVID-5). A golden-file test fails on an empty golden and asserts its case count (ENG-EVID-4, PR-31).
- **Hygiene rules.** No `os.environ`, `os.getenv` or `asyncio.create_task` under `src/e_agent` (ENG-ARCH-6, ENG-ARCH-7); the allow-list in `tests/conformance/test_banned_api.py` stays unchanged. Import contracts, exemptions and allow-lists are never widened to make a change fit (PR-06): the assembler lives in the kernel and imports no plugin or adapter.
- **Model output stays a proposal** (PR-13). Citations and rationale are model-authored claims the kernel checks; they never grant approval, change policy or mark a result verified. The verifier stays the authority for an answer (PR-19).
- **No hidden reasoning** (PR-28, ADR 0004). The context pack, the ledger and the explanation hold no chain-of-thought; the existing thinking-hygiene test keeps passing.
- **Boundaries.** Containers: only `e-agent-ledger` (test database `e_agent_test`) for `pg`, and `odoo19-learning` plus `e-agent-ledger` in the live check (Task 3g.2). Never `odoo-bench` (ENG-BOUND-1). `archive/**` and existing `research/**` reports are read-only. No change under `addons/**` is planned (ENG-BOUND-2). No committed profile uses a hosted model route.

## Review Focus

Failure modes the tests below do not fully exercise; each names the task that adds its test, and the reviewer of that task checks it by reading.

1. **Instructions inside tool results** (T1, PR-34). A partner name, product description or lead note that reads like an instruction must reach the model fenced as data, and must not change the tool set or the plan. Task 3d.2 adds injection fixtures in partner, product and lead fields; the reviewer checks the fence cannot be closed from inside the data (delimiter escaping).
2. **Clearing that breaks a tool call/return pair** (target §7.4). Clearing an old tool result must keep its call, its return id and its `EvidenceRef`, or the provider rejects the request. Task 3d.4 tests the pairing on the replay corpus; the reviewer checks the parallel-tool-call case.
3. **Masking that reaches the approval card** (ADR 0030, ADR 0006, T9). Masking governs model context and exports only. Task 3d.2 tests that the approval presentation is built from the unmasked action; the reviewer checks no code path builds the card from a pack.
4. **A citation that resolves to another run's evidence** (T6, PR-24). Task 3e.1 tests a citation naming an `evidence_id` from a second run of the same tenant; the reviewer checks the lookup is scoped by run, not only by tenant.
5. **`KERNEL-REPEAT` after the facts changed** (PR-15). A repeated blocked digest is short-circuited only while every fact it depends on has the same revision. Task 3d.5 tests a changed revision; the reviewer checks the revision set compared is the full one the original validation used.
6. **Shadow cost** (ADR 0027). `shadow` adds no model call, provider read or budget use. Task 3d.3 asserts the counts; the reviewer checks token estimation does not call the model.

## Design refs

| Area | Section | Task |
|---|---|---|
| Event log is the source; rows are projections; reconstruction (U3) | target §5.1 item 2 | 3a.1, 3c.2 |
| Explanation contract: `ProposalRationale`, projection (Q5, G11) | target §5.6 | 3a.1, 3c.3, 3e.2 |
| Progress ledger | target §6.2 | 3a.1, 3c.1 |
| Loop and repeat detection | target §6.3 | 3a.1, 3d.5 |
| Context layers, budgets, clearing, fencing | target §7.2 | 3a.1, 3d.1, 3d.2 |
| Rendering | target §7.4 | 3a.1, 3d.4 |
| Data governance: classes, route boundary, minimization, bounded results | target §13.3 | 3a.1, 3b.1, 3b.3, 3d.2 |
| Feature toggles | ADR 0027; target §6.4.8 | 3b.2 |

## ADRs

| ADR | Status | Decides | Needed by |
|---|---|---|---|
| 0030 Data classification, minimization, retention and deletion | Proposed; Phase 3 parts (startup rule, classes, minimization, bounded results) to be accepted at G2; retention (Phase 7) and export authorization (Phase 5) stay Proposed | route boundary, `local_only`, `data_processing`, `x-data-class`, record classes, class-per-route rule, bounded results | 3b.1, 3b.3, 3d.2 |
| 0031 Progress ledger, repeat detection and run reconstruction (new, C8) | to write in 3a.1 | `ProgressLedger` as a kernel projection; `KERNEL-REPEAT` rule and its revision check; the event payload keys reconstruction needs (D6) | 3c.1, 3c.2, 3d.5 |
| 0032 ContextAssembler (new, C9) | to write in 3a.1 | `ContextPolicy`, `ContextPack`, layers, per-layer budgets, drop log, clearing, fencing, the class-per-route rule's mechanism, §7.4 rendering, `STATE_SCHEMA` bump (D7), `sdk_api` 1.2 | 3d.1–3d.4 |
| 0033 Explanation contract and grounded answers (new, C18) | to write in 3a.1 | `ProposalRationale`, `Citation`, `KERNEL-CITATION`, `KERNEL-RATIONALE`, the explanation projection and its competency questions | 3c.3, 3e.1–3e.3 |
| 0027 Feature toggles | Accepted | the toggle rules the three new toggles follow | 3b.2 |
| 0004, 0007, 0018, 0022 | Accepted | no persisted reasoning; durable events; reason codes and attribution; rejected reads as feedback | throughout |

A Proposed ADR blocks the merge until accepted. 3b waits for 0030 (Phase 3 parts); 3c for 0031; 3d for 0031 and 0032; 3e for 0033.

## Toggles and fallback

Three toggles (D1). Projections in 3c and the startup rule in 3b.1 have no toggle: the projections change no run, and the startup rule is a safety refusal that only applies to a hosted route, which no committed profile uses.

**`features.context_assembler`** (Tasks 3d.2–3d.4).

| Mode | Behaviour |
|---|---|
| `off` | Today: the driver builds its history from its own message list; observations reach the model unchanged. No pack is built, no new event appears. |
| `shadow` | Before each driver turn the kernel builds the context pack and records `context.compared` (per-layer token estimates, the driver history's estimate, dropped and masked counts, pack digest). The driver still uses its own history. No model call, read or budget use is added. Real consumer: `test_shadow_pack_keeps_every_cited_evidence` over the recorded replay corpus and the release report's context column (Task 3d.3). |
| `on` | The driver renders the pack per target §7.4: the stable prefix as instructions, the dynamic suffix per turn and never persisted, old tool results cleared with their call and `EvidenceRef` kept. Minimization and bounded observations apply. |

Fallback boundary: **before each model call**. If building the pack fails, the kernel records `feature.fallback` with `CONTEXT_ASSEMBLY_FAILED` and its fixed message, and that call uses today's history. Context assembly sits before any reservation, so the ADR 0027 rule "no fallback after a reservation" is never reached by this toggle; fallback never bypasses approval, admission, verification or the transition table. While `context_assembler` is not `on`, the ADR 0030 startup rule refuses a non-local route without `data_processing` (Task 3b.1).

**`features.kernel_repeat`** (Task 3d.5).

| Mode | Behaviour |
|---|---|
| `off` | Today: a repeated blocked proposal is validated again. |
| `shadow` | Validation runs as today; the kernel records `repeat.compared` (whether the repeat rule would have short-circuited, and whether validation then gave the same findings). |
| `on` | A proposal whose digest equals an earlier blocked one in this run, with every fact revision unchanged, gets `KERNEL-REPEAT` without re-validation and counts against `max_validation_repairs`. |

Fallback: if the repeat check fails, `feature.fallback` with `REPEAT_CHECK_FAILED`, and the proposal is validated as today.

**`features.grounded_answers`** (Tasks 3e.1–3e.3).

| Mode | Behaviour |
|---|---|
| `off` | Today: citations and rationale, if a driver sends them, are ignored and not stored. |
| `shadow` | The kernel checks citations and rationale and records `grounding.compared` (resolved, unresolved, mismatched counts). The answer's verifier decides as today. |
| `on` | An unresolved or mismatched citation is `KERNEL-CITATION`; an unresolved rationale ref or rule is `KERNEL-RATIONALE` (D5). Both are repair findings within `max_validation_repairs`. The verifier still decides whether a correct answer is verified. |

Fallback: if the check itself fails, `feature.fallback` with `GROUNDING_CHECK_FAILED`, and the answer goes to its verifier as today; the verifier's independent read-back remains the gate (PR-19).

**Observability** (ENG-TOGGLE-3): `/health/ready` and the evidence bundle report all four toggles under `features`, plus the route's `data_boundary` and whether `data_processing` is declared.

## Gate

| Task | Gate set |
|---|---|
| 3a.1, 3a.2 | `full` (docs only) |
| 3b.1, 3b.2 | `full` |
| 3b.3, 3c.1, 3c.2, 3c.3 | `full` and `pg` |
| 3d.1, 3d.2, 3d.3, 3d.5 | `full` and `pg` |
| 3d.4, 3e.3 | `full`, `pg` and `e2e` (driver and rendering change; replay suite inside `full`) |
| 3e.1, 3e.2, 3f.1 | `full` and `pg` |
| 3g.1 | end-of-phase levels 1–3 |
| 3g.2 | level 4 (live) |

**End-of-phase levels** (`eng-verify`, in order, on a clean tree): (1) the `full` gate; (2) the Postgres run (the `pg` gate); (3) `make e2e`; (4) the live check on `odoo19-learning`.

## Live check

Run in Task 3g.2 on the owner's instruction through the `live-sandbox` skill, with the identity flags on every sandbox mutation:
- `/health/ready` reports the four toggles, `data_boundary: local` for the Ollama route and no `data_processing`.
- Task 1 ("Which products are short for open demand?") with `context_assembler` `off`, `shadow` and `on`: the same verified answer; `shadow` records `context.compared`; `on` renders from the pack, and the evidence bundle shows the pack digest and drop log.
- Task 1 with `grounded_answers: on`: the answer carries citations that resolve to this run's `read.recorded` evidence, and the verifier verifies it.
- Task 3 (draft PO for a seeded shortage, after reset and seed) with `context_assembler: on`: the existing write path (validation, approval, reservation, dispatch, read-back) is unchanged.
- The explanation projection of one live run answers the competency questions without a model call.

It may not touch `odoo-bench` or any container outside `odoo19-learning-*` and `e-agent-ledger`, live business data, a hosted model route, or multi-step live writes. Results are reported separately from fixture results (ENG-EVID-2).

---

## Part 3a: design entry gate

No runtime code. The ADRs are written, the target sections they decide are reconciled with this plan and the checkout, and the owner accepts them (gate G2).

### Task 3a.1: ADRs 0031–0033, ADR 0030's Phase 3 parts and the target sections

**Files:** `docs/adr/0031-progress-ledger-and-reconstruction.md`, `docs/adr/0032-context-assembler.md`, `docs/adr/0033-explanation-and-grounded-answers.md` (new), `docs/adr/0030-data-governance.md`, `docs/adr/README.md`, `docs/design/target-architecture.md` (§5.1, §5.6, §6.2, §6.3, §7.2, §7.4, §13.3, §17 rows C8, C9, C18, C19), `docs/design/principles.md` (rows PR-21, PR-26, PR-34: their checks land in 3d.2, 3b.3 and 3d.2), `docs/design/threat-model.md` (T1, T6, T23 test pointers), this plan.

**Interfaces:** produces the record shapes every later task uses: `ProgressLedger`, `ContextPolicy`, `ContextPack`, `ContextLayer`, `Dropped`, `Citation`, `ProposalRationale`, the reason codes `CONTEXT_ASSEMBLY_FAILED`, `REPEAT_CHECK_FAILED`, `GROUNDING_CHECK_FAILED`, `CONTINUATION_SCHEMA`, and the findings `KERNEL-REPEAT`, `KERNEL-CITATION`, `KERNEL-RATIONALE`.

- [ ] Write ADR 0031 from target §5.1 item 2, §6.2 and §6.3: the ledger is a kernel projection over events and step records, never a source of truth; `KERNEL-REPEAT` with its revision check (Review Focus 5); the event payload keys reconstruction needs (D6), listed by event type after reading `kernel/` writers.
- [ ] Write ADR 0032 from §7.2 and §7.4: layers, per-layer token budgets, the drop log, clearing rules, fencing, the class-per-route rule from ADR 0030, the toggle table above, D3, D7 and the `sdk_api` 1.2 change to `DriverInput`.
- [ ] Write ADR 0033 from §5.6: `ProposalRationale` (`goal_ref`, `cited_evidence`, `rules_considered`, `alternatives`, `summary` ≤ 400 characters), `Citation` (D4), D5, the projection and the research 03 competency questions it answers.
- [ ] ADR 0030: correct the index row ("markers Phase 5") to the ADR's own Gates (D3); add D2's loopback rule to the route-boundary decision; mark which parts G2 accepts.
- [ ] Target: tag each section with the ADR that decides it, and fix code references the Phase 2 merge moved (`kernel/proposals.py`, `kernel/run_loop.py`).
- [ ] Run `uv run python scripts/repo_move.py check`; expected: no broken links. Run `uv run e-agent-harness refresh-task`.
- [ ] Commit `docs(adr): ADRs 0031-0033 and ADR 0030 Phase 3 parts for review`.

### Task 3a.2: owner acceptance (gate G2)

**Files:** the ADRs above, `docs/adr/README.md`, this plan (status line and decisions), `harness/context.toml` (`active_plan`).

- [ ] The owner accepts or amends ADRs 0031–0033 and ADR 0030's Phase 3 parts, and confirms D1–D10. Record each answer in the decisions table and the ADR status lines.
- [ ] Switch `active_plan` to this plan; `uv run e-agent-harness validate-context` prints ok.
- [ ] Commit `docs: Phase 3 plan approved; ADRs 0030 (Phase 3 parts) and 0031-0033 accepted`.

## Part 3b: data boundary and toggles

### Task 3b.1: route data boundary and the startup rule

**Files:** `src/e_agent/server/profile.py` (`DriverConfig.data_boundary: str | None`, `Profile.local_only: bool = False`, `Profile.data_processing: DataProcessing | None`), `src/e_agent/contracts/data.py` (new: `DataProcessing(data_owner, legal_basis, region)` and the boundary literal `local | hosted:<region>`), `src/e_agent/server/bootstrap.py` (the rule), `src/e_agent/server/api.py` (readiness fields), `tests/unit/server/test_route_boundary.py`.

**Interfaces:** produces `effective_boundary(driver, base_url)` (D2) and the readiness keys `data_boundary` and `data_processing_declared`.

- [ ] Failing tests: `test_loopback_ollama_is_local`, `test_remote_ollama_without_boundary_is_refused`, `test_litellm_defaults_to_hosted_unknown`, `test_hosted_route_without_data_processing_fails_startup`, `test_local_only_refuses_hosted_route`, `test_readiness_reports_boundary`, and `test_committed_profiles_are_local` (all three committed profiles start).
- [ ] Run `uv run pytest -q tests/unit/server/test_route_boundary.py`; expected: fails with `ImportError` on `e_agent.contracts.data`.
- [ ] Implement. The base URL is read through `server/environment.py`, never `os.environ` (ENG-ARCH-6). The refusal message names the setting, never its value.
- [ ] Run the same command; expected: all pass. Run `uv run pytest -q tests/unit/server`; expected: pass.
- [ ] Commit `feat(server): model route data boundary and the hosted-route startup rule (ADR 0030)`.

### Task 3b.2: the three Phase 3 toggles

**Files:** `src/e_agent/contracts/features.py` (`context_assembler`, `kernel_repeat`, `grounded_answers`, each `FeatureMode.OFF`), the three committed profiles, `src/e_agent/contracts/run.py` (reason codes `CONTEXT_ASSEMBLY_FAILED`, `REPEAT_CHECK_FAILED`, `GROUNDING_CHECK_FAILED`, `CONTINUATION_SCHEMA`), `src/e_agent/kernel/features.py` (mode properties; fixed fallback messages), `tests/unit/contracts/test_features.py`, `tests/unit/server/test_committed_profiles.py`, `tests/unit/kernel/test_feature_fallback.py`.

- [ ] Failing tests: `test_phase3_toggles_default_off`, `test_committed_profiles_keep_phase3_toggles_off`, `test_readiness_reports_four_toggles`, `test_phase3_fallback_codes_have_fixed_messages`.
- [ ] Run `uv run pytest -q tests/unit/contracts/test_features.py tests/unit/server/test_committed_profiles.py tests/unit/kernel/test_feature_fallback.py`; expected: fails on the unknown field `context_assembler`.
- [ ] Implement; nothing reads the new modes yet except readiness and evidence.
- [ ] Run the same command and `uv run pytest -q tests/unit/kernel/test_off_baseline.py tests/unit/plugins/erp/simulator/test_off_baseline_erp.py`; expected: all pass, goldens unchanged.
- [ ] Commit `feat(contracts): Phase 3 feature toggles, default off`.

### Task 3b.3: data classes on schemas and stored records

**Files:** `src/e_agent/contracts/data_classes.py` (new: `DataClass`, `RecordClass`, `RetentionClass`, and the store-neutral registry of stored record kinds), `src/e_agent/sdk/ports.py` (`output_schemas` beside `input_schemas`), `src/e_agent/kernel/registry.py` (reads `x-data-class`, counts unmarked properties per capability), the ERP pack's schema models (`src/e_agent/plugins/erp/domain/*/`, `x-data-class` through `json_schema_extra`) and the notes test pack, `src/e_agent/server/api.py` (readiness `unmarked_properties`), `tests/unit/contracts/test_data_classes.py`, `tests/conformance/test_record_classes.py`, `tests/unit/kernel/test_registry_data_classes.py`.

- [ ] Failing tests: `test_unmarked_property_counts_as_personal`, `test_every_store_record_kind_declares_a_class` (fails on a missing declaration; runs on both stores; prints how many kinds it checked and fails on zero), `test_readiness_reports_unmarked_counts`, `test_erp_read_outputs_are_marked` (partner names and emails `personal`, quantities and refs `internal`).
- [ ] Run `uv run pytest -q tests/unit/contracts/test_data_classes.py tests/conformance/test_record_classes.py tests/unit/kernel/test_registry_data_classes.py`; expected: fails with `ModuleNotFoundError: e_agent.contracts.data_classes`.
- [ ] Implement. Annotating a schema changes no digest: digests cover arguments, not schemas (check `tests/unit/kernel/test_off_baseline.py` stays green).
- [ ] Run the same command with `E_AGENT_TEST_STORE=postgres` too; expected: pass on both stores. Add the PR-26 check to its principles row.
- [ ] Commit `feat(contracts): data classes on capability schemas and stored records (ADR 0030)`.

## Part 3c: projections (read-only, no toggle)

### Task 3c.1: progress ledger projection

**Files:** `src/e_agent/contracts/progress.py` (new: `ProgressLedger`: goal, task definition ref, facts as `EvidenceRef` ids with revisions, done and pending steps, open findings, budgets used), `src/e_agent/kernel/progress.py` (new: `project_progress(events, steps) -> ProgressLedger`, pure), `tests/unit/kernel/test_progress.py`.

- [ ] Failing tests: `test_progress_of_a_verified_answer_run`, `test_progress_of_a_blocked_then_repaired_run`, `test_progress_of_a_two_step_plan`, `test_progress_is_pure` (the same input gives the same record; no store write), `test_progress_holds_no_model_text` (no `message.final` text, no thinking).
- [ ] Run `uv run pytest -q tests/unit/kernel/test_progress.py`; expected: `ModuleNotFoundError: e_agent.kernel.progress`.
- [ ] Implement over `RunStore.list_events` and `list_steps`; the fixtures are recorded fixture runs on both stores.
- [ ] Run the same command, then with `E_AGENT_TEST_STORE=postgres`; expected: pass.
- [ ] Commit `feat(kernel): progress ledger projection (ADR 0031)`.

### Task 3c.2: run reconstruction from `run_events` (U3)

**Files:** `src/e_agent/kernel/reconstruct.py` (new: `reconstruct(events) -> Reconstructed` with run, actions, approvals, receipts), the event writers that gain keys (D6, the list from ADR 0031), the Phase 2 goldens (`tests/unit/kernel/golden/off_mode_events.json`, `tests/unit/plugins/erp/simulator/golden/off_mode_events_erp.json`) re-recorded, `tests/conformance/test_reconstruction.py`.

- [ ] Failing test: `test_reconstruction_equals_stored_rows` over every recorded fixture scenario (single write, blocked and repaired, reconciliation, two-step plan, answer), on both stores; it prints the scenario count and fails on zero.
- [ ] Run `uv run pytest -q tests/conformance/test_reconstruction.py`; expected: fails, listing the fields that events lack.
- [ ] Add exactly the ADR 0031 keys, additively. Re-record the two `off` goldens with their scripts and check the diff adds only those keys (`git diff --stat` and a key-set comparison in the commit message).
- [ ] Run `uv run pytest -q tests/conformance/test_reconstruction.py tests/unit/kernel/test_off_baseline.py tests/unit/plugins/erp/simulator/test_off_baseline_erp.py`, and the first with `E_AGENT_TEST_STORE=postgres`; expected: pass.
- [ ] Commit `feat(kernel): reconstruct run rows from run_events (U3, ADR 0031)`.

### Task 3c.3: explanation projection (Q5, G11)

**Files:** `src/e_agent/kernel/explain.py` (new: `explain(events, steps) -> Explanation`: goal → source facts → validation findings by rule id → proposal (digest, rationale if any) → approval (actor, policy version) → receipt → verified outcome), `src/e_agent/kernel/evidence.py` (additive bundle key `explanation`; D9 `credential_version` shortening in the export only), `src/e_agent/server/cli.py` (`e-agent explain <run_id>`), `tests/unit/kernel/test_explain.py`, `tests/unit/kernel/test_evidence.py`.

- [ ] Failing tests: `test_explanation_answers_competency_questions` (one case per research 03 question the ADR lists; asserts the case count), `test_explanation_makes_no_model_call`, `test_explanation_is_deterministic`, `test_evidence_bundle_has_explanation`, `test_export_shortens_credential_version` (D9; the stored action keeps the full value).
- [ ] Run `uv run pytest -q tests/unit/kernel/test_explain.py tests/unit/kernel/test_evidence.py`; expected: `ModuleNotFoundError: e_agent.kernel.explain`.
- [ ] Implement.
- [ ] Run the same command on both stores; expected: pass. Run `gitleaks git --redact -c .gitleaks.toml .` on a regenerated fixture bundle; expected: no new finding.
- [ ] Commit `feat(kernel): deterministic explanation projection (Q5, ADR 0033)`.

## Part 3d: context assembly

### Task 3d.1: context contracts and `sdk_api` 1.2

**Files:** `src/e_agent/contracts/context_pack.py` (new: `ContextPolicy` with per-layer token budgets and class-per-route rules; `ContextLayer`; `ContextPack` with `stable_prefix`, `dynamic_suffix`, `dropped: tuple[Dropped, ...]`, `digest`; `Dropped(kind, ref, reason)`), `src/e_agent/sdk/ports.py` (`DriverInput.context: ContextPack | None = None`), `src/e_agent/sdk/__init__.py` (`SDK_API_VERSION = "1.2"`), `tests/unit/contracts/test_context_pack.py`, `tests/unit/sdk/test_ports.py`.

- [ ] Failing tests: `test_pack_digest_is_stable`, `test_pack_rejects_unknown_layer`, `test_dropped_requires_reason`, `test_driver_input_context_defaults_none`, `test_sdk_api_is_1_2`.
- [ ] Run `uv run pytest -q tests/unit/contracts/test_context_pack.py tests/unit/sdk/test_ports.py`; expected: `ModuleNotFoundError`.
- [ ] Implement. A driver built for `sdk_api` 1.1 keeps working: `context` is optional.
- [ ] Run the same command; expected: pass.
- [ ] Commit `feat(contracts): context policy and pack; sdk_api 1.2 (ADR 0032)`.

### Task 3d.2: the assembler

**Files:** `src/e_agent/kernel/context.py` (new: `assemble(policy, ledger, observations, findings, route) -> ContextPack`, pure), `tests/unit/kernel/test_context_assembler.py`, `tests/unit/kernel/fixtures/injection/` (partner, product and lead values that read as instructions), `docs/design/principles.md` (PR-21, PR-34 checks).

- [ ] Failing tests:
  - `test_stable_prefix_has_no_per_turn_state`;
  - `test_layer_over_budget_drops_oldest_and_logs_it`;
  - `test_bounded_observation_is_partial_with_truncated_marker` (PR-21);
  - `test_error_is_never_rendered_as_empty_result` (PR-21);
  - `test_personal_value_masked_on_hosted_route_and_logged` (ADR 0030);
  - `test_local_route_keeps_personal_values`;
  - `test_untrusted_values_are_fenced` and `test_fence_cannot_be_closed_from_inside` (T1, PR-34; Review Focus 1);
  - `test_cleared_result_keeps_evidence_ref`;
  - `test_approval_presentation_ignores_the_pack` (Review Focus 3).
- [ ] Run `uv run pytest -q tests/unit/kernel/test_context_assembler.py`; expected: `ModuleNotFoundError: e_agent.kernel.context`.
- [ ] Implement. The assembler reads data classes from the registry (3b.3) and the route boundary (3b.1); it imports no plugin or adapter.
- [ ] Run the same command on both stores; expected: pass.
- [ ] Commit `feat(kernel): context assembler with budgets, drop log, minimization and fencing (ADR 0032)`.

### Task 3d.3: `context_assembler: shadow`

**Files:** `src/e_agent/contracts/events.py` (`context.compared`), `src/e_agent/kernel/run_loop.py` (build the pack before each driver turn in `shadow`), `src/e_agent/kernel/features.py`, `scripts/release_report.py` (context column), `tests/unit/kernel/test_context_shadow.py`, `tests/unit/server/test_context_shadow_replays.py`.

- [ ] Failing tests: `test_shadow_records_context_compared_per_turn`, `test_shadow_adds_no_model_call_read_or_budget` (Review Focus 6), `test_shadow_failure_changes_nothing`, `test_off_records_no_context_event`, and the consumer `test_shadow_pack_keeps_every_cited_evidence` (over the recorded replay corpus, no evidence the verified answer depends on is dropped; asserts the case count).
- [ ] Run `uv run pytest -q tests/unit/kernel/test_context_shadow.py tests/unit/server/test_context_shadow_replays.py`; expected: fails, no `context.compared` event.
- [ ] Implement.
- [ ] Run the same command, the `off` goldens and the replay suite; expected: pass, goldens unchanged.
- [ ] Commit `feat(kernel): context assembler shadow comparison (ADR 0032)`.

### Task 3d.4: `context_assembler: on` and §7.4 rendering

**Files:** `src/e_agent/kernel/run_loop.py` (pass the pack; fallback before the model call), `src/e_agent/adapters/pydantic_ai/driver.py` (render from `DriverInput.context`: stable prefix as instructions, dynamic suffix per turn not persisted, clearing that keeps tool call and return pairs; `STATE_SCHEMA` bump, D7), `src/e_agent/plugins/erp/domain/testing/scripted_driver.py` (the scripted driver accepts a pack), `tests/unit/adapters/pydantic_ai/test_driver_context.py`, `tests/unit/adapters/pydantic_ai/golden/on_model_request.json` (new), `tests/unit/kernel/test_context_on.py`.

- [ ] Failing tests: `test_on_driver_renders_pack`, `test_dynamic_suffix_is_not_persisted`, `test_clearing_keeps_call_return_pairs` (including parallel tool calls; Review Focus 2), `test_old_schema_on_continuation_fails_closed` (D7), `test_assembly_failure_falls_back_for_that_call`, `test_on_model_request_golden` (fails on an empty golden).
- [ ] Run `uv run pytest -q tests/unit/adapters/pydantic_ai/test_driver_context.py tests/unit/kernel/test_context_on.py`; expected: fails.
- [ ] Implement; record `on_model_request.json` with the script beside `off_model_request.json`.
- [ ] Run the same command, `uv run pytest -q tests/unit/server/test_recorded_model_replays.py tests/unit/adapters/pydantic_ai/test_prompt_golden.py` and `make e2e`; expected: pass, `off_model_request.json` unchanged.
- [ ] Commit `feat(driver): render the context pack per target 7.4 (ADR 0032)`.

### Task 3d.5: `KERNEL-REPEAT`

**Files:** `src/e_agent/kernel/proposals.py` (repeat rule before validation), `src/e_agent/contracts/events.py` (`repeat.compared`), `tests/unit/kernel/test_kernel_repeat.py`.

- [ ] Failing tests: `test_repeat_of_blocked_digest_short_circuits`, `test_repeat_counts_against_repairs`, `test_changed_fact_revision_revalidates` (Review Focus 5), `test_repeat_shadow_records_comparison`, `test_repeat_off_unchanged`, `test_repeat_check_failure_falls_back`.
- [ ] Run `uv run pytest -q tests/unit/kernel/test_kernel_repeat.py`; expected: fails, no `KERNEL-REPEAT` finding.
- [ ] Implement.
- [ ] Run the same command on both stores and the `off` goldens; expected: pass.
- [ ] Commit `feat(kernel): KERNEL-REPEAT for a repeated blocked proposal (ADR 0031)`.

## Part 3e: answers and rationale

### Task 3e.1: grounded answers

**Files:** `src/e_agent/contracts/grounding.py` (new: `Citation(evidence_id, pointer, value)`), the ERP answer contracts (`plugins/erp/domain/procurement/answers.py`, `sales/late_orders.py`, `receivables/overdue.py`: optional `citations`), `src/e_agent/kernel/grounding.py` (new: resolve each citation against this run's recorded observations by run and evidence id; compare the canonical value at the pointer), `src/e_agent/kernel/proposals.py` (answer path, per toggle), `src/e_agent/contracts/events.py` (`grounding.compared`), `tests/unit/kernel/test_grounding.py`.

- [ ] Failing tests: `test_citation_resolves_to_this_run_evidence`, `test_citation_to_another_run_is_unresolved` (Review Focus 4), `test_mismatched_value_is_kernel_citation`, `test_bad_pointer_is_kernel_citation`, `test_grounded_off_ignores_citations`, `test_grounded_shadow_records_comparison`, `test_verifier_still_decides`.
- [ ] Run `uv run pytest -q tests/unit/kernel/test_grounding.py`; expected: `ModuleNotFoundError`.
- [ ] Implement.
- [ ] Run the same command on both stores; expected: pass.
- [ ] Commit `feat(kernel): grounded answers with checked citations (ADR 0033)`.

### Task 3e.2: `ProposalRationale`

**Files:** `src/e_agent/contracts/grounding.py` (`ProposalRationale`), `src/e_agent/contracts/plan.py` (`ActionProposal.rationale: ProposalRationale | None`), `src/e_agent/kernel/grounding.py` (rationale check), `src/e_agent/kernel/explain.py` (shows the rationale second, after the facts), `tests/unit/kernel/test_rationale.py`.

- [ ] Failing tests: `test_rationale_with_unknown_evidence_is_kernel_rationale`, `test_rationale_with_unknown_rule_is_kernel_rationale`, `test_rationale_summary_over_400_is_refused`, `test_rationale_never_changes_the_approval_digest`, `test_rationale_holds_no_hidden_reasoning`.
- [ ] Run `uv run pytest -q tests/unit/kernel/test_rationale.py`; expected: fails.
- [ ] Implement. The approval digest covers arguments, not rationale (assert it).
- [ ] Run the same command on both stores; expected: pass.
- [ ] Commit `feat(kernel): checked proposal rationale (ADR 0033)`.

### Task 3e.3: drivers emit citations and rationale

**Files:** `src/e_agent/adapters/pydantic_ai/driver.py` (tool schemas gain optional `citations` and `rationale` only when `grounded_answers` is not `off`), `src/e_agent/plugins/erp/domain/testing/` (scripted driver emits citations), `tests/replays/erp-authored-grounded-calls/` (authored recording, provenance "authored"), `tests/unit/server/test_recorded_model_replays.py`, `tests/unit/adapters/pydantic_ai/test_driver_grounding.py`.

- [ ] Failing tests: `test_off_tool_schema_unchanged` (the `off_model_request.json` golden), `test_grounded_on_schema_offers_citations`, `test_authored_grounded_replay_verifies`.
- [ ] Run `uv run pytest -q tests/unit/adapters/pydantic_ai/test_driver_grounding.py tests/unit/server/test_recorded_model_replays.py`; expected: fails.
- [ ] Implement.
- [ ] Run the same command, the prompt golden and `make e2e`; expected: pass.
- [ ] Commit `feat(driver): drivers emit citations and rationale (ADR 0033)`.

## Part 3f: driver conformance (cut line, D8)

### Task 3f.1: driver conformance suite

**Files:** `tests/conformance/test_driver_conformance.py` (new), `tests/conformance/driver_cases/` (cases shared by the scripted driver and the pydantic-ai driver on recorded responses).

- [ ] Failing test `test_every_driver_passes_conformance`, parametrized over both drivers. Cases: the offered tool set equals `allowed_capabilities`; a repair finding gets a new proposal or a clarification, never silence; `snapshot` and `restore` round-trip; the token budget is respected; no hidden reasoning is persisted; with a pack, the stable prefix is unchanged across turns; citations, when sent, have the `Citation` shape. It prints the case count and fails on zero.
- [ ] Run `uv run pytest -q tests/conformance/test_driver_conformance.py`; expected: fails on the first case not yet met.
- [ ] Fix what fails in the drivers, not in the cases.
- [ ] Run the same command and the `pg` gate; expected: pass.
- [ ] Commit `test(conformance): driver conformance suite`.

## Part 3g: verification

### Task 3g.1: end-of-phase verification and handoff

**Files:** `README.md` (toggles and commands), `docs/roadmap.md` (Phase 3 status), `docs/handoffs/<date>-phase3-cognition-context.md`, `harness/state/3/`, `evals/reports/fixture-release.json`.

- [ ] Run `eng-verify` levels 1–3 on a clean tree; record each result.
- [ ] Phase review with `eng-review` in a fresh context, and a Codex final check of the kernel tasks (3c.2, 3d.2–3d.5, 3e.1, 3e.2); fix findings as `3.R<n>` tasks.
- [ ] Regenerate `evals/reports/fixture-release.json`; it stays labelled fixture evidence.
- [ ] Write the handoff with `eng-handoff`, stating plainly: recordings are authored, not captured, unless a qualified model run exists (ADR 0010); token counts in shadow are estimates; UI for citations and rationale is not built (D10).
- [ ] Commit `docs: Phase 3 handoff and roadmap status`.

### Task 3g.2: live check

- [ ] On the owner's instruction, run the live check above through `live-sandbox`; record the results in the handoff, labelled live and separate from fixture results.
- [ ] Commit `docs: Phase 3 live check results`.

## Self-review

- **Spec coverage.** Roadmap row 3: progress ledger → 3c.1; ContextAssembler (layers, budgets, clearing, rendering) → 3d.1–3d.4; grounded answer contract → 3e.1, 3e.3; driver conformance suite → 3f.1; `KERNEL-REPEAT` → 3d.5; explanation contract (`ProposalRationale`, projection) → 3c.3, 3e.2; run reconstruction (U3) → 3c.2; data minimization (class-per-route, bounded results, startup rule first) → 3b.1, 3b.3, 3d.2; toggle `features.context_assembler` with fallback to the driver history → 3b.2, 3d.3, 3d.4. Core plan Phase 3 task 2 (step records) shipped in Phase 2; its UI task is D10.
- **Placeholder scan.** ADR numbers 0031–0033 are the next free numbers (0023 is reserved). The event payload keys of D6 and the competency questions of 3c.3 are fixed by ADRs 0031 and 0033 in 3a.1, before the tasks that use them.
- **Type consistency.** `ProgressLedger` (3c.1) feeds `assemble` (3d.2) and `explain` (3c.3); `Citation` and `ProposalRationale` live in `contracts/grounding.py` (3e.1, 3e.2); `ContextPack` in `contracts/context_pack.py` (3d.1) is the only type `DriverInput.context` carries.
- **Review Focus coverage.** Items 1 and 3 → 3d.2; 2 → 3d.4; 4 → 3e.1; 5 → 3d.5; 6 → 3d.3.
- **Toggles.** Every runtime feature names its toggle and its fallback boundary (before the model call for `context_assembler`; before validation for `kernel_repeat`; before the verifier for `grounded_answers`); projections and the startup rule state why they have none.
