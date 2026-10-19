# Phase 3: Cognition and Context Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Status:** Approved by the owner on 2026-10-19 ("Approved"), with every recommended default in the decisions table (D1–D10). Gate G2 passed on 2026-10-19 ("Accept"): the owner accepted ADRs 0031, 0032 and 0033 and ADR 0030's Phase 3 parts, with every recommended answer to the open questions, including digest-only rationale storage. This plan was amended in the same commit for the ADRs (G-7). Written after Phase 2 merged (PR #6, `3ec2d70`) and revised after a fresh-context plan review and a scoped re-review (findings P3-1 to P3-19 and P3-R1 to P3-R4 in `harness/state/3/reviews/3-plan.json`); the ADR reviews are in `harness/state/3/reviews/3a.1.json`.

**Goal:** the kernel decides what reaches the model: a budgeted, minimized, fenced context pack built from a progress ledger. Answers carry citations, which the kernel checks against this run's recorded evidence. Every proposal can carry a checked rationale. Any run can be reconstructed and explained from `run_events` alone. The new runtime paths sit behind toggles. Before a write is reserved, they fall back to today's driver history. After a reservation they fail closed (ADR 0027).

**Architecture:** the plan has seven parts.
- **3a (design entry gate, no runtime code):** three new ADRs and the target sections they decide, reconciled with this plan and accepted by the owner at gate G2:
  - 0031: progress ledger, repeat detection and run reconstruction;
  - 0032: ContextAssembler;
  - 0033: explanation and grounded answers.
  - The Phase 3 parts of ADR 0030 were accepted at the same gate; its Phase 5 and Phase 7 parts stay Proposed.
- **3b (data boundary and toggles):** in order:
  - the ADR 0030 hosted-route startup rule, which that ADR requires to land first;
  - the `features` fields, per-run mode pinning and the ERP `off` model-request golden;
  - data classes, declared beside capability schemas and on stored records.
- **3c (projections, read-only):** the progress ledger, run reconstruction (U3) and the deterministic explanation projection (Q5, G11). All three are computed from recorded events and change no run.
- **3d (context assembly):**
  - contracts;
  - the pure assembler: layers, budgets, drop log, bounded and masked observations, fencing;
  - shadow comparison;
  - driver rendering per target §7.4;
  - the kernel's `on` mode;
  - `KERNEL-REPEAT`.
- **3e (answers and rationale):** citations on typed answers, a generic grounded answer for read-only questions, `ProposalRationale`, and drivers that emit them.
- **3f (driver conformance and the context ablation):** one suite that every driver passes, and the first run of the research 03 §8 ablation.
- **3g (verification):** end-of-phase levels 1–3, the phase review, the handoff and the live check.

**Tech Stack:** Python 3.12+, Pydantic v2 records (`e_agent.contracts`), pydantic-ai driver (`adapters/pydantic_ai`), memory and Postgres stores, pytest, the development harness (`uv run e-agent-harness`).

**Spec:**
- [Roadmap](../roadmap.md) row 3 ("Cognition and context").
- [Core plan](2026-10-12-core-conversation-cognition.md) Phases 3–4 and their exit evidence. The core plan's Phase 2 shipped as roadmap Phase 2, and step records shipped in Phase 2 Task 2c.3.
- [Target architecture](../design/target-architecture.md) §5.1, §5.6, §6.2, §6.3, §7.2, §7.4, §13.3 and fitness rows U3, Q5, G11.
- ADRs 0004, 0007, 0018, 0022, 0027, 0028, 0031, 0032, 0033 (accepted) and 0030 (Phase 3 parts accepted at G2; the rest Proposed).
- [Threat model](../design/threat-model.md) T1, T6, T12, T13, T17, T23, T24.
- [Principles](../design/principles.md) PR-13, PR-15, PR-19, PR-21, PR-26, PR-28, PR-32, PR-34.
- The [Phase 2 handoff](../handoffs/2026-10-18-phase2-execution-ir.md).

## Owner decisions

Each row has a recommended default. "Approve" accepts every default; name a row to change it. D9 of the first draft (shortening `credential_version` in exports) is withdrawn: an auditor recomputes the approval digest from the exported action, and `credential_version` is one of its inputs (`kernel/approval.py`). The `.gitleaksignore` fingerprints stay. A scoped `.gitleaks.toml` rule stays a Phase 2 open item, outside row 3.

| ID | Decision | Recommended default |
|---|---|---|
| D1 | Toggle split | Three toggles, each with its own `off`-mode proof: `features.context_assembler` (assembler, minimization, bounded observations, §7.4 rendering), `features.kernel_repeat` (`KERNEL-REPEAT`) and `features.grounded_answers` (citation and rationale checks, the generic grounded answer). Projections (3c) get no toggle because they change no run |
| D2 | Route boundary (ADR 0030) | The declared `data_boundary` decides, as ADR 0030 says. One amendment: an undeclared `ollama` route whose base URL host is loopback (`localhost`, `127.0.0.0/8`, `::1`) is `local`. Any other undeclared route, `litellm` included, is `hosted:unknown`, never refused for that alone. Readiness reports the boundary and its basis: `verified` for loopback, `declared` for an operator assertion. The owner's live profile uses a loopback Ollama, so it needs no edit |
| D3 | Bounded results | Bounding happens in the context pack, not in the gateway. The continuation keeps the full observation. The pack carries at most the capability's bound and marks the rendered observation `PARTIAL` with `truncated` (PR-21) |
| D4 | Grounded answer shape | Citations travel in a kernel envelope beside the answer arguments: `ActionProposal.citations: tuple[Citation, ...] = ()`. Each `Citation(evidence_id, pointer, value)` has `pointer` as an RFC 6901 JSON pointer into the observation's data.<br>The domain answer models in `plugins/erp/domain/*/api.py` and the notes test answer stay unchanged, and their verifiers still decide.<br>The driver offers `citations` on answer tools only when `grounded_answers` is not `off`, so `off` tool schemas are byte-identical.<br>At rest, a citation is stored as `evidence_id`, `pointer` and a digest of the canonical value, never the value (PR-26) |
| D5 | Generic read-only question | A core answer `grounded.answer.v1` (`summary`, at least one citation), admitted only when the run is pinned `on`, its offered tools hold no typed answer contract, and the run is unbound or its task definition sets `AcceptanceSpec.grounded_answer` (ADR 0033 §3, refining ADR 0028). A call that is not admitted is the repair finding `KERNEL-GROUNDED-ANSWER`. It ends `SUCCEEDED` with reason code `GROUNDED`: every citation resolved against this run's recorded evidence; the release report counts it apart from verified runs. It is never `verified`, which needs a typed verifier's fresh read-back (PR-19). Text outside citations is labelled `unverified`. The core plan asked for `verified`; this default keeps the PR-19 distinction |
| D6 | Rationale finding | `ProposalRationale` is optional on `ActionProposal` and on `ActionPlan`. With `grounded_answers: on`, a rationale is the repair finding `KERNEL-RATIONALE`, within `max_validation_repairs`, when its evidence ref is not in this run or its rule is not in the inventory. Rationale is never an approval input and never enters the approval digest (target §5.6). At rest it is evidence ids, rule ids, codes and a digest of each model-authored text, never the text (owner, G2); the text lives only in the continuation |
| D7 | Event keys for reconstruction | Events gain the payload keys reconstruction needs, additively (Task 3c.2). ADR 0031 records this as a refinement of ADR 0027's `off` proof:<br>– The Phase 2 goldens stay frozen.<br>– A new golden is recorded beside them.<br>– A test proves the old golden is a projection of the new one: same order, same keys, same values, plus only ADR 0031's listed keys.<br>Events written before this change are reconstructed and marked `partial` |
| D8 | Per-run mode pinning and continuation | A run pins the three Phase 3 modes when it starts, in the kernel continuation. The pin is written only when a mode is not `off`; when it is absent, every mode is `off`. So a profile flip affects new runs only, and an in-flight `off` run keeps its history continuation.<br>The driver snapshot gains `rendering: "pack"` only for pinned-`on` runs, so `STATE_SCHEMA` is unchanged and `off` snapshots are byte-identical.<br>A restore whose `rendering` disagrees with the pin fails the run closed with `DRIVER_STATE_MISMATCH`, or sends it to reconciliation when a reservation is unresolved, through a handler in `_load_cont` and an allowed transition (today a restore `ValueError` propagates uncaught).<br>The route is not pinned, so the startup rule alone cannot protect a resumed run. Before every model call, the kernel checks the run's pinned `context_assembler` mode against the current route. A run not pinned `on`, on a route that is not `local` and has no `data_processing`, makes no model call and fails closed with `ROUTE_BOUNDARY_UNMET`, or goes to reconciliation when a reservation is unresolved (T23).<br>The driver learns the pinned `grounded_answers` mode only from `DriverInput.grounding`, never from the profile<br>`execution_ir` keeps reading the profile per call, as Phase 2 shipped |
| D9 | Phase size and cut line | Must-have: 3a–3c, 3d.1–3d.5 and 3e. The cut line is the core plan's Phase 4 items: 3d.6 (`KERNEL-REPEAT`), 3f.1 (driver conformance) and 3f.2 (ablation). If the phase runs long, they move to a Phase 3′ with their own plan rather than being skipped |
| D10 | UI | Citations, rationale and the explanation are exposed through the evidence bundle and the CLI only. Their UI (timeline, citation display, rationale second on the approval card) is a later UI plan |

## Global Constraints

- **Branch** `phase3/cognition-context` from `main` at `3ec2d70` (Phase 2 merged).
  - Stage explicit paths. Every commit ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
  - `main` is protected (strict, five required checks): changes reach it only through a PR whose checks pass.
  - Merge, push and rebase only on the owner's instruction.
- **Harness phase `3`.**
  - Features live in `harness/state/3/features.json` (`F-3a-1` … `F-3g-2`, one per task).
  - Each task has one contract (`uv run e-agent-harness new-task 3 <id> --feature <F-id> --gate <set> --paths ...`).
  - Run `check-scope` before each commit, `gate <set>` after the commit on a clean tree, and `close-check` before a task closes (ENG-WORK-1, ENG-EVID-1).
  - `harness/context.toml` `active_plan` switches to this plan in Task 3a.2. Until then, the 3a.1 contract's plan digest is the Phase 2 plan.
- **Gate commands** (from `harness/context.toml`):
  - `full`: `uv sync --locked`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy`, `uv run lint-imports`, `uv run python scripts/export_openapi.py --check`, `uv run pytest -q`, `pnpm --dir ui gen:check`, `pnpm --dir ui check`, `uv run python scripts/check_core_only.py`.
  - `pg`: `E_AGENT_TEST_STORE=postgres uv run pytest -q tests/unit/kernel tests/conformance tests/unit/adapters/postgres`, with `E_AGENT_TEST_PG_DSN` set to the `e_agent_test` database, never the live ledger's database (G-11).
  - `e2e`: `make e2e`.
  - `core`: `uv run python scripts/check_core_only.py`.
  - `live`: `scripts/env_check.py` and `scripts/odoo_sandbox.py info`.
- **Design before code.** Part 3a's ADRs are accepted by the owner before 3b starts. If an accepted ADR changes a shape below, the accepting commit amends this plan (ENG-PLAN-3, G-7).
- **Authoritative files mid-task (G-7).** A task that edits a digest input (the target architecture, the ADR index, the roadmap, this plan) runs `uv run e-agent-harness refresh-task` before `close-check`.
- **Toggle default `off`.** Every committed profile keeps `context_assembler`, `kernel_repeat` and `grounded_answers` `off`, and `execution_ir` stays `off`. The committed profiles are `src/e_agent/plugins/erp/simulator/fixture_profile.json`, `profiles/dev-ollama.json` and `profiles/live.example.json`.
- **`off` is today.** With the three new toggles `off`, every existing test is unchanged in:
  - the event stream, action records, digests and outcomes;
  - the driver snapshot;
  - the pinned model requests: `tests/unit/adapters/pydantic_ai/golden/off_model_request.json` (notes pack) and the ERP `off_model_request_erp.json` recorded in Task 3b.2 before anything changes.

  The one planned exception is D7 (additive event keys). Its proof is the frozen Phase 2 golden and the projection test, not a re-recorded golden.
- **Reservation boundary (ADR 0027).**
  - A fallback code is used only before the run's first write reservation. It is carried only by `feature.fallback` and never ends a run.
  - After a reservation, each toggle uses its own terminal code: the run fails closed through the transition table, or goes to reconciliation when a reservation is unresolved.
  - A fallback never sends unmasked data to a route that is not `local` and has no `data_processing` declaration (T23).
- **Driver changes** run `uv run pytest -q tests/unit/server/test_recorded_model_replays.py tests/unit/adapters/pydantic_ai/test_prompt_golden.py` (PR-32).
  - An intended prompt change updates `tests/unit/adapters/pydantic_ai/golden/base_instructions.txt` in the same commit (ENG-EVID-5).
  - A golden-file test fails on an empty golden and asserts its case count (ENG-EVID-4, PR-31).
- **Hygiene rules.**
  - No `os.environ`, `os.getenv` or `asyncio.create_task` under `src/e_agent` (ENG-ARCH-6, ENG-ARCH-7); the allow-list in `tests/conformance/test_banned_api.py` stays unchanged.
  - Import contracts, exemptions and allow-lists are never widened to make a change fit (PR-06): the assembler lives in the kernel and imports no plugin or adapter.
- **Model output stays a proposal** (PR-13). Citations and rationale are model-authored claims that the kernel checks. They never grant approval, change policy or mark a result verified. The verifier stays the authority for a typed answer (PR-19).
- **No hidden reasoning** (PR-28, ADR 0004). The context pack, the ledger and the explanation hold no chain-of-thought; the existing thinking-hygiene test keeps passing.
- **Nothing new reaches an export** (PR-26). New event payloads carry ids, pointers, counts, digests and reason codes, never observation values.
- **Review.** Each task's close review runs in a fresh context (`eng-review`).
  - Kernel and trust-anchor tasks are reviewed by Codex: 3b.2, 3b.3, 3c.1, 3c.2, 3c.3, 3d.2, 3d.3, 3d.5, 3d.6, 3e.1, 3e.2 and 3e.3.
  - The phase review in 3g.1 is a final check, not a substitute.
- **Boundaries.**
  - Containers: only `e-agent-ledger` (test database `e_agent_test`) for `pg`, and `odoo19-learning` plus `e-agent-ledger` in the live check (Task 3g.2). Never `odoo-bench` (ENG-BOUND-1).
  - `archive/**` and existing `research/**` reports are read-only.
  - No change under `addons/**` is planned (ENG-BOUND-2).
  - No committed profile uses a hosted model route.

## Review Focus

These are failure modes the tests below do not fully exercise. Each item names the task that adds its test; the reviewer of that task checks it by reading.

1. **Instructions inside tool results** (T1, PR-34). A partner name, product description or lead note that reads like an instruction must reach the model fenced as data. It must not change the tool set or the plan.
   - Task 3d.2 adds injection fixtures and the fence tests.
   - Task 3d.5 adds the outcome test: a run over injected fixtures proposes the same action as over clean ones.
   - The reviewer checks that the fence cannot be closed from inside the data (delimiter escaping).
2. **Clearing that breaks a tool call/return pair** (target §7.4). Clearing an old tool result must keep its call, its return id and its `EvidenceRef`, or the provider rejects the request. Nothing is cleared while a deferred call is pending (§7.4 rule 4). Task 3d.4 tests both on the replay corpus; the reviewer checks the parallel-tool-call case.
3. **Masking that reaches the approval card** (ADR 0030, ADR 0006, T9). Masking governs model context and exports only. Task 3d.2 tests that the approval presentation is built from the unmasked action; the reviewer checks that no code path builds the card from a pack.
4. **Personal data in the actual model request** (T23). In `on`, every path that sends observation data renders it from the masked pack: the deferred tool returns and the post-write acknowledgement turn. On a route that is neither local nor declared, an assembly failure fails closed instead of falling back. Task 3d.4 asserts that a seeded `personal` value is absent from the captured model request and listed in `ContextPack.dropped`. Task 3b.2 adds the per-call route check for runs not pinned `on`, in `_with_tools`, the single choke point both driver call sites use. The reviewer checks for any other path that passes `Observation.data` to the model, or calls the driver outside `_with_tools`.
5. **A citation that resolves to another run's evidence** (T6, PR-24). Task 3e.1 tests a citation naming an `evidence_id` from a second run of the same tenant; the reviewer checks that the lookup is scoped by run, not only by tenant.
6. **`KERNEL-REPEAT` after the facts changed** (PR-15). A repeated blocked digest is short-circuited only while every fact it depends on has the same revision. Task 3d.6 tests a changed revision; the reviewer checks that the compared revision set is the full one the original validation used.
7. **Fallback after a reservation** (ADR 0027). No toggle's fallback code appears after the run's first reservation. Tasks 3d.5, 3d.6 and 3e.1 test the post-reservation path of their toggle; the reviewer checks every model call and check site against the run's reservation state.
8. **Shadow cost** (ADR 0027). `shadow` adds no model call, provider read or budget use. Task 3d.3 asserts the counts; the reviewer checks that token estimation does not call the model.

## Design refs

| Area | Section | Task |
|---|---|---|
| Event log is the source; rows are projections; reconstruction (U3) | target §5.1 item 2 | 3a.1, 3c.2 |
| Explanation contract: `ProposalRationale`, projection (Q5, G11) | target §5.6 | 3a.1, 3c.3, 3e.3 |
| Progress ledger | target §6.2 | 3a.1, 3c.1 |
| Loop and repeat detection | target §6.3 | 3a.1, 3d.6 |
| Context layers, budgets, clearing, fencing | target §7.2 | 3a.1, 3d.1, 3d.2 |
| Rendering | target §7.4 | 3a.1, 3d.4, 3d.5 |
| Data governance: classes, route boundary, minimization, bounded results | target §13.3 | 3a.1, 3b.1, 3b.3, 3d.2 |
| Feature toggles | ADR 0027; target §6.4.8 | 3b.2 |

## ADRs

| ADR | Status | Decides | Needed by |
|---|---|---|---|
| 0030 Data classification, minimization, retention and deletion | Phase 3 parts (startup rule, classes, minimization, bounded results) accepted 2026-10-19 at G2; retention (Phase 7) and export authorization (Phase 5) stay Proposed | route boundary with D2's loopback amendment, `local_only`, `data_processing`, field classes declared beside the schema (amends the `x-data-class` wording, below), record classes, class-per-route rule, bounded results | 3b.1, 3b.3, 3d.2 |
| 0031 Progress ledger, repeat detection and run reconstruction (new, C8) | Accepted 2026-10-19 (G2) | `ProgressLedger` as a kernel projection; `KERNEL-REPEAT` and its revision check; the event payload keys reconstruction needs, and the D7 refinement of ADR 0027's `off` proof | 3c.1, 3c.2, 3d.6 |
| 0032 ContextAssembler (new, C9) | Accepted 2026-10-19 (G2) | `ContextPolicy`, `ContextPack`, layers, per-layer budgets, drop log, clearing, fencing, the class-per-route mechanism, §7.4 rendering, per-run mode pinning and `rendering` (D8), the context reason codes, `sdk_api` 1.2 | 3b.2, 3d.1–3d.5 |
| 0033 Explanation contract and grounded answers (new, C18) | Accepted 2026-10-19 (G2) | `ProposalRationale`, `Citation`, the citation envelope (D4), `grounded.answer.v1`, its admission and `AcceptanceSpec.grounded_answer` (refining ADR 0028) and `GROUNDED` (D5), `KERNEL-CITATION`, `KERNEL-RATIONALE`, `KERNEL-GROUNDED-ANSWER`, the grounding reason codes, the explanation projection and its competency questions | 3c.3, 3e.1–3e.4 |
| 0027 Feature toggles | Accepted | the toggle and reservation rules the three new toggles follow; refined by 0031 for D7 only | 3b.2 |
| 0028 Task definitions | Accepted | `AcceptanceSpec`, refined by 0033 with `grounded_answer` | 3e.2 |
| 0004, 0007, 0018, 0022 | Accepted | no persisted reasoning; durable events; reason codes and attribution; rejected reads as feedback | throughout |

**ADR 0030 amendment:** fields are classed by `data_classes: Mapping[<instance path>, DataClass]` on the capability declaration, not by `x-data-class` inside the JSON schema. This keeps model-facing schemas, and the `off` model request, unchanged. 3a.1 amended ADR 0030, and G2 accepted the amended Phase 3 parts.

Every ADR this phase needs was accepted at G2 on 2026-10-19, so no task waits on an ADR. Which ADR each task implements: 3b.1 and 3b.3 → 0030 (Phase 3 parts); 3b.2 → 0032 (pinning and codes); 3c.1, 3c.2 and 3d.6 → 0031; 3d.1–3d.5 → 0032; 3c.3 and 3e → 0033.

## Toggles and fallback

Three toggles (D1), each pinned per run at start (D8). The projections in 3c and the startup rule in 3b.1 have no toggle: the projections change no run, and the startup rule is a safety refusal that only applies to a route that is not `local`, which no committed profile uses.

Reason codes. ADR 0031 decides the `kernel_repeat` pair, ADR 0032 the others and the cross-reference table, ADR 0033 `GROUNDED`. Task 3b.2 adds the eight in this table; Task 3e.2 adds `GROUNDED`, which ends a `grounded.answer.v1` run (nine new codes in all):

| Toggle | Fallback code (`feature.fallback`, before the first reservation only, never ends a run) | Terminal code (ends the run, or marks a skipped turn) |
|---|---|---|
| `context_assembler` | `CONTEXT_ASSEMBLY_FAILED` | `CONTEXT_UNAVAILABLE` |
| `kernel_repeat` | `REPEAT_CHECK_FAILED` | `REPEAT_UNAVAILABLE` |
| `grounded_answers` | `GROUNDING_CHECK_FAILED` | `GROUNDING_UNAVAILABLE` |
| (restore, D8) | none | `DRIVER_STATE_MISMATCH` |
| (route, D8) | none | `ROUTE_BOUNDARY_UNMET` |

Each toggle's `shadow` path has its own failure event, as `ir.shadow_failed` does for `execution_ir`: `context.shadow_failed`, `repeat.shadow_failed` and `grounding.shadow_failed`. A shadow failure changes nothing else.

**`features.context_assembler`** (Tasks 3d.2–3d.5).

| Mode | Behaviour |
|---|---|
| `off` | Today: the driver builds its history from its own message list, and observations reach the model unchanged. No pack is built and no new event appears. |
| `shadow` | Before each driver turn, the kernel builds the context pack and records `context.compared`: per-layer token estimates of the pack and of the same inputs rendered unbounded (both from the kernel's estimator; the driver history is not read), the driver's per-turn `tokens_used` delta, dropped and masked counts, and the pack digest. The driver still uses its own history. No model call, read or budget use is added.<br>Real consumers: the release report's context columns (pack against unbounded estimate, repair rate, token cost) and `test_shadow_pack_keeps_referenced_observations` over the recorded replay corpus (Task 3d.3). |
| `on` | The driver renders the pack per target §7.4. The stable prefix becomes instructions. The dynamic suffix is rebuilt per turn and never persisted. Old tool results are cleared, keeping their call and `EvidenceRef`, and nothing is cleared while a deferred call is pending. Every observation that reaches the model, deferred tool returns and the acknowledgement turn included, comes from the pack, so minimization and bounding apply to all of it. |

Failure handling:
- Before the run's first reservation, on a route that is `local` or has `data_processing` declared: `feature.fallback` with `CONTEXT_ASSEMBLY_FAILED`, and that call uses today's history.
- Otherwise there is no fallback:
  - The optional post-write acknowledgement turn (`kernel/verification.py`) is skipped, `context.failed` with `CONTEXT_UNAVAILABLE` is recorded, and the run keeps its verified outcome.
  - Any other call fails the run closed with `CONTEXT_UNAVAILABLE`, or sends it to reconciliation when a reservation is unresolved.
- While `context_assembler` is not `on`, the ADR 0030 startup rule refuses a route that is not `local` and has no `data_processing` (Task 3b.1).

**`features.kernel_repeat`** (Task 3d.6).

| Mode | Behaviour |
|---|---|
| `off` | Today: a repeated blocked proposal is validated again. |
| `shadow` | Validation runs as today. The kernel records `repeat.compared`: whether the repeat rule would have short-circuited, and whether validation then gave the same findings. Real consumer: `test_repeat_shadow_agrees_with_validation` over the fixture corpus asserts zero disagreements and its case count, and the release report counts disagreements. |
| `on` | A proposal whose digest equals an earlier blocked one in this run, with every fact revision unchanged, gets `KERNEL-REPEAT` without re-validation, and the finding counts against `max_validation_repairs`. |

Failure handling: before the first reservation, `feature.fallback` with `REPEAT_CHECK_FAILED`, and the proposal is validated as today. After a reservation, the run fails closed with `REPEAT_UNAVAILABLE`, or goes to reconciliation when a reservation is unresolved.

**`features.grounded_answers`** (Tasks 3e.1–3e.4).

| Mode | Behaviour |
|---|---|
| `off` | Today. Answer tools offer no `citations` and `grounded.answer.v1` is not offered. Any citations or rationale a driver sends anyway are dropped and not stored. |
| `shadow` | Citations and rationale are offered (`DriverInput.grounding` is `cite`), and `grounded.answer.v1` is not. The kernel checks citations and rationale and records `grounding.compared` (resolved, unresolved and mismatched counts). The answer's verifier decides as today. Real consumer: `test_grounding_shadow_agrees_with_on` over the authored grounded replays (Task 3e.4) asserts that shadow's verdicts equal `on`'s, and the release report shows the counts. |
| `on` | An unresolved or mismatched citation is `KERNEL-CITATION`; an unresolved rationale ref or rule is `KERNEL-RATIONALE` (D6). Both are repair findings within `max_validation_repairs`. A generic answer that is not admitted is `KERNEL-GROUNDED-ANSWER`. The verifier still decides whether a typed answer is verified; an admitted `grounded.answer.v1` ends `GROUNDED` (D5). |

Failure handling: before the first reservation, `feature.fallback` with `GROUNDING_CHECK_FAILED`, and a typed answer goes to its verifier as today. A `grounded.answer.v1` has no verifier, so it fails closed with `GROUNDING_UNAVAILABLE`. After a reservation, every case fails closed with `GROUNDING_UNAVAILABLE`, or goes to reconciliation when a reservation is unresolved.

**Observability** (ENG-TOGGLE-3): `/health/ready` and the evidence bundle report all four toggles under `features`, plus the route's `data_boundary`, its basis (`verified`, `declared` or `default`) and whether `data_processing` is declared. The evidence bundle also reports the run's pinned modes.

## Gate

| Task | Gate set |
|---|---|
| 3a.1, 3a.2 | `full` (docs only) |
| 3b.1 | `full` |
| 3b.2, 3b.3, 3c.1, 3c.2, 3c.3 | `full` and `pg` |
| 3d.1, 3d.2, 3d.3, 3d.6 | `full` and `pg` |
| 3d.4, 3d.5, 3e.4 | `full`, `pg` and `e2e` (driver and rendering change; replay suite inside `full`) |
| 3e.1, 3e.2, 3e.3, 3f.1, 3f.2 | `full` and `pg` |
| 3g.1 | end-of-phase levels 1–3 |
| 3g.2 | level 4 (live) |

A contract carries one gate set (HP-6). Where a task names more, the contract's set is `full`, and the other levels run through `eng-verify` and are named in the handoff.

**End-of-phase levels** (`eng-verify`, in order, on a clean tree): (1) the `full` gate; (2) the Postgres run (the `pg` gate); (3) `make e2e`; (4) the live check on `odoo19-learning`.

## Live check

Run in Task 3g.2 on the owner's instruction through the `live-sandbox` skill, with the identity flags on every sandbox mutation:
- `/health/ready` reports the four toggles, and for the Ollama route `data_boundary: local`, basis `verified`, no `data_processing`.
- Task 1 ("Which products are short for open demand?") with `context_assembler` set to `off`, `shadow` and `on`:
  - all three give the same verified answer;
  - `shadow` records `context.compared`;
  - `on` renders from the pack, and the evidence bundle shows the pack digest and drop log.
- "List the open demands and their shortage" (core plan exit) with `grounded_answers: on`: the answer carries citations that resolve to this run's `read.recorded` evidence, and the verifier verifies it.
- "List the open purchase orders" with `grounded_answers: on`, bound to the read-only ERP task definition `open-pos` (Task 3e.2, `grounded_answer: true`): `grounded.answer.v1` ends `SUCCEEDED` with reason code `GROUNDED`, with no bespoke answer contract.
- Task 3 (draft PO for a seeded shortage, after reset and seed) with `context_assembler: on`: the existing write path (validation, approval, reservation, dispatch, read-back) is unchanged, and the acknowledgement turn renders from the pack.
- The explanation projection of one live run answers the competency questions without a model call.

The live check must not touch:
- `odoo-bench`, or any container outside `odoo19-learning-*` and `e-agent-ledger`;
- live business data;
- a hosted model route;
- multi-step live writes.

Results are reported separately from fixture results (ENG-EVID-2).

---

## Part 3a: design entry gate

No runtime code. The ADRs are written, the target sections they decide are reconciled with this plan and the checkout, and the owner accepts them (gate G2).

### Task 3a.1: ADRs 0031–0033, ADR 0030's Phase 3 parts and the target sections

**Files:**
- New ADRs: `docs/adr/0031-progress-ledger-and-reconstruction.md`, `docs/adr/0032-context-assembler.md`, `docs/adr/0033-explanation-and-grounded-answers.md`.
- `docs/adr/0030-data-governance.md` and `docs/adr/README.md`.
- `docs/design/target-architecture.md`: §5.1, §5.6, §6.2, §6.3, §7.2, §7.4, §13.3, and §17 rows C8, C9, C18, C19.
- `docs/design/principles.md`: rows PR-21, PR-26 and PR-34, whose checks land in 3d.2, 3b.3 and 3d.2.
- `docs/design/threat-model.md`: T1, T6 and T23 test pointers.
- This plan.

**Interfaces:** produces the record shapes and codes every later task uses:
- records: `ProgressLedger`, `ContextPolicy`, `ContextPack`, `ContextLayer`, `Dropped`, `Citation`, `ProposalRationale`;
- the `grounded.answer.v1` contract and `AcceptanceSpec.grounded_answer`;
- the nine reason codes above (eight in the table plus `GROUNDED`);
- the findings `KERNEL-REPEAT`, `KERNEL-CITATION`, `KERNEL-RATIONALE` and `KERNEL-GROUNDED-ANSWER`;
- the event types `context.compared`, `context.failed`, `context.shadow_failed`, `repeat.compared`, `repeat.shadow_failed`, `grounding.compared` and `grounding.shadow_failed`.

- [ ] Write ADR 0031 from target §5.1 item 2, §6.2 and §6.3:
  - The ledger is a kernel projection over events and step records, never a source of truth.
  - `KERNEL-REPEAT` and its revision check (Review Focus 6).
  - The event payload keys reconstruction needs, listed by event type after reading the `kernel/` writers.
  - The D7 refinement of ADR 0027 (frozen golden plus projection test), and `partial` reconstruction of older events.
- [ ] Write ADR 0032 from §7.2 and §7.4:
  - layers, per-layer token budgets, the drop log, clearing rules (including rule 4) and fencing;
  - the class-per-route rule from ADR 0030;
  - the toggle table and reason codes above, D3 and D8;
  - the `sdk_api` 1.2 change: `data_classes` on the capability declaration (3b.3), `DriverInput.context` (3d.1) and `DriverInput.grounding` (3e.4), one unreleased version;
  - the per-call route check and `ROUTE_BOUNDARY_UNMET` (D8).
- [ ] Write ADR 0033 from §5.6:
  - `ProposalRationale` (`goal_ref`, `cited_evidence`, `rules_considered`, `alternatives`, `summary` ≤ 400 characters);
  - `Citation` and its envelope (D4), D5, D6;
  - the at-rest form (value digest, PR-26);
  - the projection and the research 03 competency questions it answers.
- [ ] ADR 0030: add D2's loopback rule and the `declared` or `verified` basis; replace the `x-data-class` mechanism with `data_classes` on the declaration; mark which parts G2 accepts. Its index row (class markers on new capabilities in Phase 5) stays.
- [ ] Target: tag each section with the ADR that decides it, and fix code references the Phase 2 merge moved (`kernel/proposals.py`, `kernel/run_loop.py`, `kernel/continuation.py`, the driver's line references).
- [ ] Run `uv run python scripts/repo_move.py check`; expected: no broken links. Run `uv run e-agent-harness refresh-task`.
- [ ] Commit `docs(adr): ADRs 0031-0033 and ADR 0030 Phase 3 parts for review`.

### Task 3a.2: owner acceptance (gate G2)

**Files:** the ADRs above, `docs/adr/README.md`, this plan (status line and decisions), `harness/context.toml` (`active_plan`).

**Interfaces:** consumes the ADRs of 3a.1; produces their accepted status, which every later task cites.

- [ ] The owner accepts or amends ADRs 0031–0033 and ADR 0030's Phase 3 parts, and confirms D1–D10. Record each answer in the decisions table and the ADR status lines.
- [ ] Switch `active_plan` to this plan; `uv run e-agent-harness validate-context` prints ok.
- [ ] Commit `docs: Phase 3 plan approved; ADRs 0030 (Phase 3 parts) and 0031-0033 accepted`.

## Part 3b: data boundary and toggles

### Task 3b.1: route data boundary and the startup rule

**Files:**
- `src/e_agent/server/profile.py`: `DriverConfig.data_boundary: str | None`, `Profile.local_only: bool = False`, `Profile.data_processing: DataProcessing | None`.
- `src/e_agent/contracts/data.py` (new): `DataProcessing(data_owner, legal_basis, region)` and the boundary literal `local | hosted:<region> | hosted:unknown`.
- `src/e_agent/server/bootstrap.py`: the rule.
- `src/e_agent/server/api.py`: readiness fields.
- `tests/unit/server/test_route_boundary.py`.

Until Task 3d.5 lands masking, the rule refuses a route that is not `local` and has no `data_processing` whatever `context_assembler` says, so `on` never covers an unbuilt path (ADR 0027). Task 3d.5 adds ADR 0030's `on` exemption with its masking test.

**Interfaces:** produces `effective_boundary(driver_config, base_url) -> (boundary, basis)` (D2) and the readiness keys `data_boundary`, `data_boundary_basis` and `data_processing_declared`.

- [ ] Failing tests:
  - `test_loopback_ollama_is_local_verified`;
  - `test_undeclared_remote_route_is_hosted_unknown`: basis `default`;
  - `test_litellm_defaults_to_hosted_unknown`: basis `default`, never `verified`;
  - `test_declared_boundary_is_reported_declared`;
  - `test_hosted_route_without_data_processing_fails_startup`, also with `context_assembler: on`;
  - `test_local_only_refuses_hosted_route`;
  - `test_readiness_reports_boundary_and_basis`;
  - `test_committed_profiles_are_local`: all three committed profiles start.
- [ ] Run `uv run pytest -q tests/unit/server/test_route_boundary.py`; expected: fails with `ModuleNotFoundError: e_agent.contracts.data`.
- [ ] Implement. The base URL comes from the typed driver settings, never `os.environ` (ENG-ARCH-6). The refusal message names the setting, never its value.
- [ ] Run the same command; expected: all pass. Run `uv run pytest -q tests/unit/server`; expected: pass.
- [ ] Commit `feat(server): model route data boundary and the hosted-route startup rule (ADR 0030)`.

### Task 3b.2: the three Phase 3 toggles, per-run pinning and the ERP `off` golden

**Files:**
- `src/e_agent/contracts/features.py`: `context_assembler`, `kernel_repeat`, `grounded_answers`, each `FeatureMode.OFF`.
- The three committed profiles.
- `src/e_agent/contracts/run.py`: the eight reason codes of the table.
- `src/e_agent/contracts/events.py`: `context.failed` (ADR 0032).
- `src/e_agent/kernel/features.py`: mode properties and fixed messages.
- `src/e_agent/kernel/continuation.py`: the pin, written only when a mode is not `off` (D8).
- `src/e_agent/kernel/ir_on.py`: the route check in `_with_tools`, which both driver call sites use (`kernel/run_loop.py` and the acknowledgement turn in `kernel/verification.py`) (D8, T23).
- `src/e_agent/kernel/verification.py`: an acknowledgement turn refused by the route check is skipped, recorded with `ROUTE_BOUNDARY_UNMET`, and the run keeps its verified outcome.
- `tests/conformance/test_driver_call_sites.py`: fails if a `_driver.advance` call bypasses `_with_tools`.
- New ERP `off` golden: `tests/unit/plugins/erp/simulator/golden/off_model_request_erp.json`, with its recording script, and `tests/unit/plugins/erp/simulator/test_off_model_request_erp.py`.
- Tests: `tests/unit/contracts/test_features.py`, `tests/unit/server/test_committed_profiles.py`, `tests/unit/kernel/test_feature_fallback.py`, `tests/unit/kernel/test_mode_pinning.py`.

**Interfaces:** produces `RunModes` (the pinned modes) read by every later toggle site, the reason codes, and the ERP model-request golden that 3b.3 and 3e.4 must leave unchanged.

- [ ] First, record `off_model_request_erp.json` from the ERP fixture profile on today's code. Commit it alone as `test(erp): pin the ERP off model request`, so the golden predates every Phase 3 change.
- [ ] Failing tests:
  - `test_phase3_toggles_default_off`;
  - `test_committed_profiles_keep_phase3_toggles_off`;
  - `test_readiness_reports_four_toggles`;
  - `test_phase3_codes_have_fixed_messages`;
  - `test_fallback_codes_never_end_a_run` (ADR 0027);
  - `test_modes_are_pinned_at_start`: a profile flip after start does not change the run's modes;
  - `test_off_run_writes_no_pin`: the continuation is byte-identical to today's;
  - `test_absent_pin_means_off`;
  - `test_hosted_route_refused_at_startup_even_with_context_assembler_on` (moved from 3b.1, review B1-2: the field lands here; ADR 0030's `on` exemption waits for 3d.5);
  - `test_pinned_off_run_on_undeclared_hosted_route_fails_closed`: a run started on a local route resumes after a restart onto an undeclared hosted route with `context_assembler: on`; it makes no model call and ends `ROUTE_BOUNDARY_UNMET` (T23, Review Focus 4);
  - `test_route_check_with_unresolved_reservation_goes_to_reconciliation`;
  - `test_route_check_skips_ack_turn_and_keeps_verified`: the acknowledgement turn of a verified write on an undeclared hosted route makes no model call;
  - `test_every_driver_call_goes_through_with_tools`: prints how many call sites it checked and fails on zero.
- [ ] Run `uv run pytest -q tests/unit/contracts/test_features.py tests/unit/server/test_committed_profiles.py tests/unit/kernel/test_feature_fallback.py tests/unit/kernel/test_mode_pinning.py`; expected: fails on the unknown field `context_assembler`.
- [ ] Implement; nothing reads the new modes yet except readiness, evidence and the pin.
- [ ] Run the same command, the `off` baselines (`tests/unit/kernel/test_off_baseline.py`, `tests/unit/plugins/erp/simulator/test_off_baseline_erp.py`) and both `off` model-request goldens; expected: all pass, goldens unchanged. Run the first command with `E_AGENT_TEST_STORE=postgres`; expected: pass.
- [ ] Commit `feat(contracts): Phase 3 feature toggles, default off, pinned per run (ADR 0032)`.

### Task 3b.3: data classes on capability declarations and stored records

**Files:**
- `src/e_agent/contracts/data_classes.py` (new): `DataClass`, `RecordClass`, `RetentionClass`, and the store-neutral registry of stored record kinds.
- `src/e_agent/contracts/capability.py`: `CapabilityDescriptor.data_classes: Mapping[str, DataClass]`, keyed by an instance path under `/input` or `/output` (`items` for any array index; owner decision 2026-10-19).
- `src/e_agent/sdk/__init__.py`: `SDK_API_VERSION = "1.2"`.
- `src/e_agent/kernel/registry.py`: resolves classes and counts unmarked properties per capability.
- Declarations: the ERP pack's capability declarations (`src/e_agent/plugins/erp/domain/*/`) and the notes test pack (`tests/unit/kernel/conftest.py`).
- `src/e_agent/server/api.py`: readiness `unmarked_properties`.
- Tests: `tests/unit/contracts/test_data_classes.py`, `tests/conformance/test_record_classes.py`, `tests/unit/kernel/test_registry_data_classes.py`, `tests/unit/plugins/erp/domain/test_data_classes_erp.py`, `tests/unit/sdk/test_ports.py`.

**Interfaces:** produces `Registry.data_class(contract_id, instance_path) -> DataClass`: the most restrictive class declared on the path or an ancestor, `personal` when none; the assembler (3d.2) passes the observation's own value paths, with array indices written as `items`.

- [ ] Failing tests:
  - `test_unmarked_property_counts_as_personal`;
  - `test_every_store_record_kind_declares_a_class`: fails on a missing declaration, runs on both stores, prints how many kinds it checked and fails on zero;
  - `test_readiness_reports_unmarked_counts`;
  - `test_erp_read_outputs_are_marked`: partner names and emails `personal`, quantities and refs `internal`;
  - `test_data_class_pointer_must_exist_in_schema`;
  - `test_sdk_api_is_1_2`.
- [ ] Run `uv run pytest -q tests/unit/contracts/test_data_classes.py tests/conformance/test_record_classes.py tests/unit/kernel/test_registry_data_classes.py tests/unit/plugins/erp/domain/test_data_classes_erp.py tests/unit/sdk/test_ports.py`; expected: fails with `ModuleNotFoundError: e_agent.contracts.data_classes`.
- [ ] Implement. Classes sit beside the schema, never inside it, so no model-facing schema and no digest changes.
- [ ] Run the same command with `E_AGENT_TEST_STORE=postgres` too; expected: pass on both stores. Run both `off` model-request goldens and the `off` baselines; expected: unchanged. Add the PR-26 check to its principles row.
- [ ] Commit `feat(contracts): data classes on capability declarations and stored records (ADR 0030)`.

## Part 3c: projections (read-only, no toggle)

### Task 3c.1: progress ledger projection

**Files:**
- `src/e_agent/contracts/progress.py` (new): `ProgressLedger` with the goal, the task definition ref, facts as `EvidenceRef` ids with revisions, done and pending steps, open findings, plain-text repair turns (as event ids, never text), and budgets used.
- `src/e_agent/kernel/progress.py` (new): `project_progress(events, steps) -> ProgressLedger`, pure.
- `tests/unit/kernel/test_progress.py`.

**Interfaces:** produces `ProgressLedger`, consumed by `explain` (3c.3) and `assemble` (3d.2).

- [ ] Failing tests:
  - `test_progress_of_a_verified_answer_run`;
  - `test_progress_of_a_blocked_then_repaired_run`;
  - `test_progress_of_a_two_step_plan`;
  - `test_progress_shows_plain_text_repair_turns` (core plan Phase 4);
  - `test_progress_is_pure`: the same input gives the same record, with no store write;
  - `test_progress_holds_no_model_text`: no `message.final` text, no thinking.
- [ ] Run `uv run pytest -q tests/unit/kernel/test_progress.py`; expected: `ModuleNotFoundError: e_agent.kernel.progress`.
- [ ] Implement over `RunStore.list_events` and `list_steps`; the fixtures are recorded fixture runs on both stores.
- [ ] Run the same command, then with `E_AGENT_TEST_STORE=postgres`; expected: pass.
- [ ] Commit `feat(kernel): progress ledger projection (ADR 0031)`.

### Task 3c.2: run reconstruction from `run_events` (U3)

**Files:**
- `src/e_agent/kernel/reconstruct.py` (new): `reconstruct(events) -> Reconstructed`, with the run, actions, approvals and receipts, each field `known`, `partial` or `unknown`.
- The event writers that gain keys (the ADR 0031 list).
- The recorders and comparers of the frozen goldens, which compare the projection onto the Phase 2 keys: `tests/unit/kernel/record_off_baseline.py`, `tests/unit/kernel/test_off_baseline.py`, and their ERP counterparts under `tests/unit/plugins/erp/simulator/`.
- New goldens beside the frozen Phase 2 ones: `tests/unit/kernel/golden/off_mode_events_v3.json` and `tests/unit/plugins/erp/simulator/golden/off_mode_events_erp_v3.json`.
- `tests/unit/kernel/test_off_projection.py`.
- `tests/conformance/test_reconstruction.py`.

**Interfaces:** consumes the ADR 0031 key list; produces `Reconstructed`, which 3c.3 and the evidence bundle use.

- [ ] Failing tests:
  - `test_reconstruction_equals_stored_rows` over every recorded fixture scenario (single write, blocked and repaired, reconciliation, two-step plan, answer), on both stores; prints the scenario count and fails on zero.
  - `test_pre_key_events_reconstruct_as_partial`: events without the new keys give `partial` or `unknown`, never a guessed value (PR-24).
  - `test_phase2_golden_is_a_projection_of_v3` (D7): same order, keys and values, plus only ADR 0031's listed keys.
- [ ] Run `uv run pytest -q tests/conformance/test_reconstruction.py tests/unit/kernel/test_off_projection.py`; expected: `ModuleNotFoundError: e_agent.kernel.reconstruct`.
- [ ] Add exactly the ADR 0031 keys, additively, with no observation values (PR-26).
- [ ] Record the `v3` goldens with their scripts. Leave the Phase 2 golden files untouched; their tests now compare the projection onto the Phase 2 keys.
- [ ] Run `uv run pytest -q tests/conformance/test_reconstruction.py tests/unit/kernel/test_off_projection.py tests/unit/kernel/test_off_baseline.py tests/unit/plugins/erp/simulator/test_off_baseline_erp.py`, and the first with `E_AGENT_TEST_STORE=postgres`; expected: pass.
- [ ] Commit `feat(kernel): reconstruct run rows from run_events (U3, ADR 0031)`.

### Task 3c.3: explanation projection (Q5, G11)

**Files:**
- `src/e_agent/kernel/explain.py` (new): `explain(ledger, reconstructed) -> Explanation`, covering goal → source facts (evidence ids and revisions) → validation findings by rule id → proposal (digest, plus the rationale's evidence ids, rule ids and text digests once 3e.3 lands) → approval (actor, policy version) → receipt → verified or grounded outcome.
- `src/e_agent/kernel/evidence.py`: additive bundle key `explanation`.
- `src/e_agent/server/cli.py`: `e-agent explain <run_id>`.
- `tests/unit/kernel/test_explain.py` and `tests/unit/kernel/test_evidence.py`.

**Interfaces:** consumes `ProgressLedger` (3c.1) and `Reconstructed` (3c.2); produces `Explanation`.

- [ ] Failing tests:
  - `test_explanation_answers_competency_questions`: one case per research 03 question that the ADR lists; asserts the case count;
  - `test_explanation_makes_no_model_call`;
  - `test_explanation_is_deterministic`;
  - `test_explanation_holds_no_observation_values` (PR-26);
  - `test_evidence_bundle_has_explanation`;
  - `test_explanation_of_old_run_marks_partial`.
- [ ] Run `uv run pytest -q tests/unit/kernel/test_explain.py tests/unit/kernel/test_evidence.py`; expected: `ModuleNotFoundError: e_agent.kernel.explain`.
- [ ] Implement.
- [ ] Run the same command on both stores; expected: pass.
- [ ] Commit `feat(kernel): deterministic explanation projection (Q5, ADR 0033)`.
- Rulings from review (2026-10-19), recorded so code and design agree (PR-35):
  - CQ06: findings' `expected` and `observed` stay out of the explanation; `observed` is read data and ADR 0033 §6 holds no observation values (PR-26). The bundle's events keep them. Explained findings carry rule id, version and status, without the validator message (C3-28, C3-29).
  - CQ07: the driver id comes from `run.created` through the reconstruction, and the evaluated rule refs (PASS included) from the ledger (C3-26, C3-27). `rule_bundle_version` is in no event payload, only inside the approval digest, so the explanation does not name it; recording it needs an ADR 0031 §3 key, which is the owner's decision (C3-27).

## Part 3d: context assembly

### Task 3d.1: context contracts and `DriverInput.context`

**Files:**
- `src/e_agent/contracts/context_pack.py` (new):
  - `ContextPolicy`, with per-layer token budgets and class-per-route rules;
  - `ContextLayer`;
  - `RenderedObservation(evidence, data, partial, truncated, masked)`, with `partial` true exactly when the observation is truncated, masked or its evidence is not COMPLETE (ADR 0032);
  - `ContextPack`, with `stable_prefix`, `dynamic_suffix`, `observations: tuple[RenderedObservation, ...]`, `dropped: tuple[Dropped, ...]` and `digest`;
  - `Dropped(kind, ref, reason)`.
- `src/e_agent/sdk/ports.py`: `DriverInput.context: ContextPack | None = None`, part of `sdk_api` 1.2 (3b.3).
- `tests/unit/contracts/test_context_pack.py` and `tests/unit/sdk/test_ports.py`.

**Interfaces:** produces the only types `DriverInput.context` carries; consumed by 3d.2–3d.5 and 3f.1.

- [ ] Failing tests: `test_pack_digest_is_stable`, `test_pack_rejects_unknown_layer`, `test_dropped_requires_reason`, `test_driver_input_context_defaults_none`, `test_rendered_observation_partial_requires_marker`.
- [ ] Run `uv run pytest -q tests/unit/contracts/test_context_pack.py tests/unit/sdk/test_ports.py`; expected: `ModuleNotFoundError: e_agent.contracts.context_pack`.
- [ ] Implement. A driver built for `sdk_api` 1.1 keeps working, because `context` is optional.
- [ ] Run the same command; expected: pass.
- [ ] Commit `feat(contracts): context policy and pack (ADR 0032)`.

### Task 3d.2: the assembler

**Files:**
- `src/e_agent/kernel/context.py` (new): `assemble(policy, ledger, observations, read_errors, findings, classes, boundary) -> ContextPack`, pure. `classes` is the registry lookup of 3b.3; `boundary` comes from 3b.1.
- `tests/unit/kernel/test_context_assembler.py`.
- `tests/unit/kernel/fixtures/injection/`: partner, product and lead values that read as instructions.
- `docs/design/principles.md`: the PR-21 and PR-34 checks.

**Interfaces:** consumes `ProgressLedger`, the registry classes and the boundary; produces `ContextPack`.

- [ ] Failing tests:
  - `test_stable_prefix_has_no_per_turn_state`;
  - `test_layer_over_budget_drops_oldest_and_logs_it`;
  - `test_bounded_observation_is_partial_with_truncated_marker` (PR-21, D3);
  - `test_error_is_never_rendered_as_empty_result` (PR-21);
  - `test_personal_value_masked_on_hosted_route_and_logged` (ADR 0030, T23);
  - `test_finding_and_read_error_text_masked_on_hosted_route` and `test_finding_message_rendered_from_inventory_on_hosted_route` (ADR 0032 §5, T23);
  - `test_local_route_keeps_personal_values`;
  - `test_untrusted_values_are_fenced` and `test_fence_cannot_be_closed_from_inside` (T1, PR-34; Review Focus 1);
  - `test_cleared_result_keeps_evidence_ref`;
  - `test_approval_presentation_ignores_the_pack` (Review Focus 3).
- [ ] Run `uv run pytest -q tests/unit/kernel/test_context_assembler.py`; expected: `ModuleNotFoundError: e_agent.kernel.context`.
- [ ] Implement. The assembler imports no plugin or adapter.
- [ ] Run the same command on both stores; expected: pass.
- [ ] Commit `feat(kernel): context assembler with budgets, drop log, minimization and fencing (ADR 0032)`.

### Task 3d.3: `context_assembler: shadow` and the baseline

**Files:**
- `src/e_agent/contracts/events.py`: `context.compared` and `context.shadow_failed`.
- `src/e_agent/kernel/run_loop.py`: build the pack before each driver turn in `shadow`.
- `src/e_agent/kernel/features.py`.
- `scripts/release_report.py`: context columns, repair rate and token cost per scenario.
- `evals/reports/phase3-baseline.json` (new; fixture evidence, recorded from `off` before 3d.4).
- `tests/unit/kernel/test_context_shadow.py` and `tests/unit/server/test_context_shadow_replays.py`.

**Interfaces:** consumes `assemble` (3d.2); produces `context.compared`, which the release report and the ablation (3f.2) read.

- [ ] Failing tests:
  - `test_shadow_records_context_compared_per_turn`;
  - `test_shadow_adds_no_model_call_read_or_budget` (Review Focus 8);
  - `test_shadow_failure_records_context_shadow_failed_and_changes_nothing`;
  - `test_off_records_no_context_event`;
  - the consumer `test_shadow_pack_keeps_referenced_observations`: over the recorded replay corpus, no observation whose resource ref the run's proposal or answer arguments use is dropped; asserts the case count.
- [ ] Run `uv run pytest -q tests/unit/kernel/test_context_shadow.py tests/unit/server/test_context_shadow_replays.py`; expected: fails, no `context.compared` event.
- [ ] Implement. Record `evals/reports/phase3-baseline.json` (repair rate and token cost under `off`, labelled fixture) with the release report.
- [ ] Run the same command, the `off` goldens and the replay suite; expected: pass, goldens unchanged.
- [ ] Commit `feat(kernel): context assembler shadow comparison and the off baseline (ADR 0032)`.

### Task 3d.4: the driver renders the pack (§7.4)

**Files:**
- `src/e_agent/adapters/pydantic_ai/driver.py`:
  - render from `DriverInput.context`: the stable prefix as instructions, and the dynamic suffix per turn, never persisted;
  - deferred tool returns built from `ContextPack.observations`, not `Observation.data`;
  - clearing that keeps tool call and return pairs, and skips clearing while a deferred call is pending;
  - `rendering: "pack"` in the snapshot of a pack-rendered run only (D8).
- `src/e_agent/plugins/erp/domain/testing/scripted_driver.py`: the scripted driver accepts a pack.
- `tests/unit/adapters/pydantic_ai/test_driver_context.py`.
- `tests/unit/adapters/pydantic_ai/golden/on_model_request.json` (new).

**Interfaces:** consumes `ContextPack` (3d.1); produces a driver that renders it whenever `DriverInput.context` is set and is unchanged when it is `None`.

- [ ] Failing tests:
  - `test_driver_renders_pack`;
  - `test_dynamic_suffix_is_not_persisted`;
  - `test_clearing_keeps_call_return_pairs`, including parallel tool calls (Review Focus 2);
  - `test_no_clearing_with_pending_deferred_call` (§7.4 rule 4);
  - `test_masked_value_absent_from_model_request`: hosted-route fixture; the captured request lacks the seeded `personal` value, which is listed in `dropped` (T23, Review Focus 4);
  - `test_snapshot_without_context_is_unchanged`;
  - `test_on_model_request_golden`: fails on an empty golden.
- [ ] Run `uv run pytest -q tests/unit/adapters/pydantic_ai/test_driver_context.py`; expected: fails, the driver ignores `context`.
- [ ] Implement. Record `on_model_request.json` with the script beside `off_model_request.json`.
- [ ] Run the same command, `uv run pytest -q tests/unit/server/test_recorded_model_replays.py tests/unit/adapters/pydantic_ai/test_prompt_golden.py`, both `off` model-request goldens and `make e2e`; expected: pass, `off` goldens unchanged.
- [ ] Commit `feat(driver): render the context pack per target 7.4 (ADR 0032)`.

### Task 3d.5: `context_assembler: on` in the kernel

**Files:**
- `src/e_agent/kernel/run_loop.py`: pass the pack on every driver call of a pinned-`on` run.
- `src/e_agent/kernel/verification.py`: the acknowledgement turn passes the pack; on failure the turn is skipped.
- `src/e_agent/kernel/continuation.py`: a `_load_cont` handler for a typed restore refusal → `DRIVER_STATE_MISMATCH` through an allowed transition (D8).
- `src/e_agent/kernel/features.py`: fallback or terminal, by reservation state and boundary.
- `src/e_agent/server/bootstrap.py`: the startup rule's `on` exemption (ADR 0030).
- `tests/unit/kernel/test_context_on.py`.
- `tests/unit/kernel/test_context_budget_turns.py`.

**Interfaces:** consumes the pinned modes (3b.2), `assemble` (3d.2) and the rendering driver (3d.4).

- [ ] Failing tests:
  - `test_on_passes_pack_on_every_call`, including the acknowledgement turn;
  - `test_assembly_failure_before_reservation_falls_back_on_local_route`;
  - `test_assembly_failure_on_undeclared_hosted_route_fails_closed` (T23);
  - `test_assembly_failure_after_reservation_has_no_fallback` (Review Focus 7);
  - `test_ack_turn_assembly_failure_skips_turn_and_keeps_verified`;
  - `test_off_to_on_flip_keeps_inflight_run_on_history` (D8);
  - `test_restore_rendering_mismatch_fails_closed` (D8): through the handler, not an uncaught `ValueError`; with an unresolved reservation it goes to reconciliation;
  - `test_injected_fixture_run_proposes_the_same_action` (T1, Review Focus 1);
  - `test_on_exempts_undeclared_hosted_route_at_startup`: ADR 0030's exemption, added here with masking;
  - `test_twelve_turn_conversation_respects_budget` and `test_twenty_turn_conversation_stays_under_budget`: scripted driver; core plan exit evidence.
- [ ] Run `uv run pytest -q tests/unit/kernel/test_context_on.py tests/unit/kernel/test_context_budget_turns.py`; expected: fails, no pack reaches the driver.
- [ ] Implement.
- [ ] Run the same command on both stores, the replay suite, the `off` goldens and `make e2e`; expected: pass, `off` goldens unchanged.
- [ ] Commit `feat(kernel): context_assembler on, with reservation-aware failure handling (ADR 0032)`.

### Task 3d.6: `KERNEL-REPEAT` (cut line, D9)

**Files:**
- `src/e_agent/kernel/proposals.py`: the repeat rule before validation.
- `src/e_agent/contracts/events.py`: `repeat.compared` and `repeat.shadow_failed`.
- `scripts/release_report.py`: the disagreement count.
- `tests/unit/kernel/test_kernel_repeat.py`.

**Interfaces:** consumes the pinned `kernel_repeat` mode and the run's validation history; produces the `KERNEL-REPEAT` finding.

- [ ] Failing tests:
  - `test_repeat_of_blocked_digest_short_circuits`;
  - `test_repeat_counts_against_repairs`;
  - `test_changed_fact_revision_revalidates` (Review Focus 6);
  - `test_repeat_shadow_records_comparison`;
  - the consumer `test_repeat_shadow_agrees_with_validation`: fixture corpus; zero disagreements; asserts the case count;
  - `test_repeat_off_unchanged`;
  - `test_repeat_check_failure_falls_back_before_reservation`;
  - `test_repeat_check_failure_after_reservation_fails_closed` (Review Focus 7).
- [ ] Run `uv run pytest -q tests/unit/kernel/test_kernel_repeat.py`; expected: fails, no `KERNEL-REPEAT` finding.
- [ ] Implement.
- [ ] Run the same command on both stores and the `off` goldens; expected: pass.
- [ ] Commit `feat(kernel): KERNEL-REPEAT for a repeated blocked proposal (ADR 0031)`.

## Part 3e: answers and rationale

### Task 3e.1: citations on typed answers

**Files:**
- `src/e_agent/contracts/grounding.py` (new): `Citation(evidence_id, pointer, value)`.
- `src/e_agent/contracts/plan.py`: `ActionProposal.citations: tuple[Citation, ...] = ()`, left out of serialization when empty and outside the approval digest.
- `src/e_agent/kernel/grounding.py` (new): resolves each citation against this run's continuation observations by evidence id, and compares the canonical value at the pointer. The answer arguments go to the domain model without `citations`.
- `src/e_agent/kernel/proposals.py`: the answer path, per pinned mode.
- `src/e_agent/contracts/events.py`: `grounding.compared` and `grounding.shadow_failed`; at rest, each citation is evidence id, pointer and value digest (PR-26).
- `tests/unit/kernel/test_grounding.py`.

**Interfaces:** produces `check_citations(observations, citations) -> GroundingResult`, used by 3e.2 and 3e.4.

- [ ] Failing tests:
  - `test_citation_resolves_to_this_run_evidence`;
  - `test_citation_to_another_run_is_unresolved` (Review Focus 5);
  - `test_mismatched_value_is_kernel_citation`;
  - `test_bad_pointer_is_kernel_citation`;
  - `test_citation_value_is_not_stored`: only the digest is stored (PR-26);
  - `test_grounded_off_drops_citations_and_action_record_unchanged`;
  - `test_grounded_shadow_records_comparison`;
  - `test_grounding_failure_falls_back_before_reservation`;
  - `test_grounding_failure_after_reservation_fails_closed` (Review Focus 7);
  - `test_verifier_still_decides`.
- [ ] Run `uv run pytest -q tests/unit/kernel/test_grounding.py`; expected: `ModuleNotFoundError: e_agent.contracts.grounding`.
- [ ] Implement.
- [ ] Run the same command on both stores and the `off` goldens; expected: pass, unchanged.
- [ ] Commit `feat(kernel): checked citations on typed answers (ADR 0033)`.

### Task 3e.2: the generic grounded answer

**Files:**
- `src/e_agent/kernel/grounded_answer.py` (new): the core `grounded.answer.v1` (`summary`, at least one citation). It is not a registry capability: the kernel branches on it before `_outside_task_set` and the capability lookup, and admits it per ADR 0033 §3 from the run's pinned mode, so an in-flight run's tool set does not change on a profile flip. It creates no `ActionRecord`; `message.final` gains `contract_id` and the at-rest citations.
- `src/e_agent/contracts/run.py`: `ReasonCode.GROUNDED`.
- `src/e_agent/contracts/task.py`: `AcceptanceSpec.grounded_answer: bool = False`, valid only when `required_effects` and `required_answer` are empty (refines ADR 0028).
- `src/e_agent/kernel/ir_on.py`: the acceptance gate accepts a `GROUNDED` end only with the flag set, from the kernel's own `message.final` record.
- `scripts/release_report.py`: counts `GROUNDED` apart from `VERIFIED`.
- `src/e_agent/plugins/erp/domain/tasks/` and `e_agent_plugin.json`: the read-only task definition `open-pos` (read capabilities only, `grounded_answer: true`) for the live check.
- `src/e_agent/kernel/evidence.py`: free text outside citations marked `unverified`.
- `tests/unit/kernel/test_grounded_answer.py`.

**Interfaces:** consumes `check_citations` (3e.1); produces the `GROUNDED` end and the `KERNEL-GROUNDED-ANSWER` finding.

- [ ] Failing tests:
  - `test_read_only_question_ends_grounded_without_bespoke_contract`;
  - `test_grounded_is_never_reported_as_verified` (PR-19);
  - `test_grounded_answer_not_offered_beside_a_typed_answer`;
  - `test_grounded_answer_refused_on_bound_run_without_admission`;
  - `test_acceptance_spec_grounded_answer_requires_no_effects_or_answer`;
  - `test_release_report_counts_grounded_separately`;
  - `tests/unit/plugins/erp/domain/test_open_pos_task.py::test_open_pos_is_read_only_and_admits_grounded_answer`: `open-pos` loads, offers only read capabilities, sets `grounded_answer` and admits `grounded.answer.v1` (owner G2 answer 5; the live check depends on it);
  - `test_free_text_answer_is_labelled_unverified`;
  - `test_grounded_answer_not_offered_unless_pinned_on`, including after a profile flip;
  - `test_grounded_answer_with_unresolved_citation_is_repaired`;
  - `test_grounding_failure_fails_closed_for_generic_answer`.
- [ ] Run `uv run pytest -q tests/unit/kernel/test_grounded_answer.py tests/unit/plugins/erp/domain/test_open_pos_task.py`; expected: `ModuleNotFoundError: e_agent.kernel.grounded_answer`.
- [ ] Implement.
- [ ] Run the same command on both stores and the `off` goldens; expected: pass, unchanged.
- [ ] Commit `feat(kernel): generic grounded answer for read-only questions (ADR 0033)`.

### Task 3e.3: `ProposalRationale`

**Files:**
- `src/e_agent/contracts/grounding.py`: `ProposalRationale`.
- `src/e_agent/contracts/plan.py`: `ActionProposal.rationale` and `ActionPlan.rationale`, both `ProposalRationale | None`, left out of serialization when `None` and outside the approval digest.
- `src/e_agent/kernel/grounding.py`: the rationale check.
- `src/e_agent/kernel/explain.py`: shows the rationale second, after the facts.
- `tests/unit/kernel/test_rationale.py`.

**Interfaces:** consumes the 3e.1 lookup and the rule inventory; produces the `KERNEL-RATIONALE` finding.

- [ ] Failing tests:
  - `test_rationale_with_unknown_evidence_is_kernel_rationale`;
  - `test_rationale_with_unknown_rule_is_kernel_rationale`;
  - `test_plan_rationale_is_checked`;
  - `test_rationale_summary_over_400_is_refused`;
  - `test_rationale_never_changes_the_approval_digest`;
  - `test_rationale_holds_no_hidden_reasoning`;
  - `test_rationale_off_action_record_unchanged`;
  - `test_rationale_text_is_stored_as_digest_only` (owner, G2; PR-26): no event payload holds the `summary` or alternative text; the text is kept only in the run's continuation, where the approval card reads it.
- [ ] Run `uv run pytest -q tests/unit/kernel/test_rationale.py`; expected: fails with `ImportError` on `ProposalRationale`.
- [ ] Implement. The approval digest covers arguments, not rationale (assert it).
- [ ] Run the same command on both stores and the `off` goldens; expected: pass.
- [ ] Commit `feat(kernel): checked proposal and plan rationale (ADR 0033)`.

### Task 3e.4: drivers emit citations and rationale

**Files:**
- `src/e_agent/sdk/ports.py`: `DriverInput.grounding: GroundingOffer = GroundingOffer.OFF` (`off`, `cite`, `cite_and_answer`), set by the kernel per call from the pinned mode and the ADR 0033 §3 admission (part of the unreleased `sdk_api` 1.2).
- `src/e_agent/kernel/run_loop.py`: sets `grounding` per call.
- `src/e_agent/adapters/pydantic_ai/driver.py`: answer tools gain a sibling `citations`, and write and plan tools gain `rationale`, unless `DriverInput.grounding` is `off`, and `grounded.answer.v1` only for `cite_and_answer`; the driver never reads the profile.
- `src/e_agent/plugins/erp/domain/testing/scripted_driver.py`: the scripted driver emits citations.
- `tests/replays/erp-authored-grounded-calls/`: an authored recording, provenance "authored".
- `tests/unit/server/test_recorded_model_replays.py`.
- `tests/unit/adapters/pydantic_ai/test_driver_grounding.py`.

**Interfaces:** consumes the envelope (3e.1), `grounded.answer.v1` (3e.2) and `ProposalRationale` (3e.3).

- [ ] Failing tests:
  - `test_off_tool_schemas_unchanged`: both `off` model-request goldens, notes and ERP;
  - `test_grounded_on_schema_offers_citations`;
  - `test_inflight_off_run_schema_unchanged_after_flip`: a run pinned `off` keeps the `off` tool schema after the profile flips `grounded_answers` on;
  - `test_authored_grounded_replay_verifies`;
  - the consumer `test_grounding_shadow_agrees_with_on`: authored grounded replays; asserts the case count.
- [ ] Run `uv run pytest -q tests/unit/adapters/pydantic_ai/test_driver_grounding.py tests/unit/server/test_recorded_model_replays.py`; expected: fails.
- [ ] Implement.
- [ ] Run the same command, the prompt golden and `make e2e`; expected: pass.
- [ ] Commit `feat(driver): drivers emit citations and rationale (ADR 0033)`.

## Part 3f: driver conformance and the context ablation (cut line, D9)

### Task 3f.1: driver conformance suite

**Files:** `tests/conformance/test_driver_conformance.py` (new) and `tests/conformance/driver_cases/`, the cases shared by the scripted driver and the pydantic-ai driver on recorded responses.

**Interfaces:** consumes the `AgentDriver` protocol, `ContextPack` and `Citation`; produces the suite a third-party driver must pass.

- [ ] Failing test `test_every_driver_passes_conformance`, parametrized over both drivers. It prints the case count and fails on zero. Cases (the core plan Phase 4 list, plus the protocol's own):
  - the offered tool set equals `allowed_capabilities`;
  - deferred reads and writes;
  - resume after restart (`snapshot` and `restore` round-trip, including `rendering`);
  - context pack rendering, with an unchanged stable prefix across turns;
  - clearing, with call/return pairing and no clearing while a call is pending;
  - findings in the dynamic suffix, never in the persisted history;
  - a repair finding gets a new proposal or a clarification, never silence;
  - grounded answers: citations, when sent, have the `Citation` shape and go in the envelope;
  - the token budget is respected;
  - no hidden reasoning is persisted.
- [ ] Run `uv run pytest -q tests/conformance/test_driver_conformance.py`; expected: fails on the first case not yet met.
- [ ] Fix what fails in the drivers, not in the cases.
- [ ] Run the same command and the `pg` gate; expected: pass.
- [ ] Commit `test(conformance): driver conformance suite`.

### Task 3f.2: context ablation, first run (research 03 §8)

**Files:** `evals/ablation/context-history-vs-typed.md` (new: design, hypotheses, metrics), `scripts/context_ablation.py` (new: runs the fixture corpus with `context_assembler` `off` and `on`), `evals/reports/phase3-context-ablation.json` (fixture evidence).

**Interfaces:** consumes `context.compared`, the release-report metrics (3d.3) and the baseline.

- [ ] Write the design from research 03 §8 (chat history against typed state): hypotheses, metrics (outcome, repair rate, token cost, dropped evidence) and the corpus.
- [ ] Failing test `tests/unit/scripts/test_context_ablation.py::test_ablation_runs_both_arms`; asserts the case count per arm and fails on zero.
- [ ] Run `uv run pytest -q tests/unit/scripts/test_context_ablation.py`; expected: `ModuleNotFoundError`.
- [ ] Implement and run it. Record the report labelled fixture, with no claim beyond the corpus.
- [ ] Commit `feat(evals): context ablation design and first fixture run`.

## Part 3g: verification

### Task 3g.1: end-of-phase verification and handoff

**Files:** `README.md` (toggles and commands), `docs/roadmap.md` (Phase 3 status), `docs/handoffs/<date>-phase3-cognition-context.md`, `harness/state/3/`, `evals/reports/fixture-release.json`.

**Interfaces:** consumes every task's evidence.

- [ ] Run `eng-verify` levels 1–3 on a clean tree; record each result.
- [ ] Phase review with `eng-review` in a fresh context, and a Codex final check across the kernel tasks; fix findings as `3.R<n>` tasks.
- [ ] Regenerate `evals/reports/fixture-release.json`, which stays labelled fixture evidence, and compare repair rate and token cost against `phase3-baseline.json`.
- [ ] Write the handoff with `eng-handoff`. State plainly that:
  - recordings are authored, not captured, unless a qualified model run exists (ADR 0010);
  - token counts in shadow are estimates;
  - a `GROUNDED` end is not `verified`;
  - the UI for citations and rationale is not built (D10).
- [ ] Commit `docs: Phase 3 handoff and roadmap status`.

### Task 3g.2: live check

**Interfaces:** consumes the Live check section above.

- [ ] On the owner's instruction, run the live check above through `live-sandbox`; record the results in the handoff, labelled live and separate from fixture results.
- [ ] Commit `docs: Phase 3 live check results`.

## Self-review

- **Spec coverage.**
  - Roadmap row 3:
    - progress ledger → 3c.1;
    - ContextAssembler (layers, budgets, clearing, rendering) → 3d.1–3d.5;
    - grounded answer contract → 3e.1, 3e.2, 3e.4;
    - driver conformance suite → 3f.1;
    - `KERNEL-REPEAT` → 3d.6;
    - explanation contract (`ProposalRationale`, projection) → 3c.3, 3e.3;
    - run reconstruction (U3) → 3c.2;
    - data minimization (class-per-route, bounded results, startup rule first) → 3b.1, 3b.3, 3d.2;
    - toggle `features.context_assembler` with fallback to the driver history → 3b.2, 3d.3, 3d.5.
  - Core plan exit evidence:
    - 12- and 20-turn budgets → 3d.5;
    - repair rate and token cost against a baseline → 3d.3, 3g.1;
    - "list the open demands" with citations → live check;
    - any read-only question without a bespoke contract → 3e.2 (ending `GROUNDED`, D5);
    - free text labelled unverified → 3e.2;
    - plain-text repair turns in the ledger → 3c.1;
    - research 03 §8 ablation → 3f.2.
  - Core plan Phase 3 task 2 (step records) shipped in Phase 2; its UI task is D10.
- **Placeholder scan.** ADR numbers 0031–0033 are the next free numbers (0023 is reserved). ADRs 0031 and 0033 fix the event payload keys (D7) and the competency questions (3c.3) in 3a.1, before the tasks that use them.
- **Type consistency.**
  - `ProgressLedger` (3c.1) feeds `explain` (3c.3) and `assemble` (3d.2).
  - `Reconstructed` (3c.2) feeds `explain`.
  - `Citation` and `ProposalRationale` live in `contracts/grounding.py` (3e.1, 3e.3).
  - `ContextPack` and `RenderedObservation` in `contracts/context_pack.py` (3d.1) are the only types `DriverInput.context` carries.
  - `sdk_api` 1.2 covers `data_classes` (3b.3), `DriverInput.context` (3d.1) and `DriverInput.grounding` (3e.4).
- **Review Focus coverage.**
  - Item 1 → 3d.2, 3d.5.
  - Item 2 → 3d.4.
  - Item 3 → 3d.2.
  - Item 4 → 3b.2, 3d.4, 3d.5.
  - Item 5 → 3e.1.
  - Item 6 → 3d.6.
  - Item 7 → 3d.5, 3d.6, 3e.1.
  - Item 8 → 3d.3.
- **Toggles.** Every runtime feature names its toggle, its fallback code (before the first reservation only, never ending a run) and its terminal code (after a reservation, or where the fallback would send unmasked data to an undeclared hosted route). Modes are pinned per run. The projections and the startup rule state why they have no toggle.
