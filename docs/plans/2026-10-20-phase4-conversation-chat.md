# Phase 4: Conversation and Chat UX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. UI tasks also follow the `ag-*` skills named in each task, and stop at their owner gates.

**Status:** Draft, awaiting owner approval. Nothing in this plan is approved or implemented. The owner reviews the decisions table (D1–D16) and names the plan approved; a general instruction to continue is not approval (eng-phase-plan stop gate).

**Goal:** a user talks to e-agent in one thread. A message answers the run that waits for input, or starts a new run in the same thread. A new run gets a small, kernel-built summary of the earlier runs through the ContextAssembler, never raw model text. The open chat defects are fixed, and citations and the explanation are visible in the UI as "grounded, not verified". Everything new sits behind `features.conversations`, which falls back to today's per-run task view.

**Architecture:** the plan has six parts.
- **4a (design entry gate, no runtime code):** ADR 0023 (the conversation model, amending ADR 0022 and refining ADR 0032) and ADR 0034 (conversation-first workspace and the citation, rationale and explanation UI, settling EA-10). The owner accepts both at gate G-A.
- **4b (chat defects):** the four core plan Phase 0 defects, as small UI fixes inside the approved design, with no toggle. They do not wait for G-A (D14).
- **4c (contracts, stores, toggle):** the `features.conversations` toggle and its startup rule; the `Conversation` contract and `RunRecord.conversation_id`; the `ConversationStore` port on both stores, with Postgres migration `0007`.
- **4d (routing and carried context):** the message router; carried context built at admission and rendered only in the pack's `recent_turns` layer; the `shadow` comparison; the API routes, each with an authorization dependency; a fixture thread end to end.
- **4e (UI, through the `ag-*` stages):** brief (gate G-B), mockup (gate G-C), the thread view, the D10 citation and explanation UI, the rationale on the approval card (cut line), and the UI review (gate G-D).
- **4f (verification):** end-of-phase levels 1–3, the phase review, the handoff, and the live check on the owner's instruction only.

**Tech Stack:** Python 3.12+, Pydantic v2 records (`e_agent.contracts`), FastAPI (`e_agent.server`), memory and Postgres stores, pytest; the TypeScript UI workspace (`ui/`, pnpm, Vitest, Playwright, React); the development harness (`uv run e-agent-harness`).

**Spec:**
- [Roadmap](../roadmap.md) row 4 ("Conversation and chat UX") and its rules.
- [Core plan](2026-10-12-core-conversation-cognition.md) Phases 0 and 1, with their exit evidence.
- [Phase 3 handoff](../handoffs/2026-10-20-phase3-cognition-context.md): D10 (no UI for citations, rationale or explanation), the live-write gap, FB-1, FB-2, and pending item 14 (the "grounded, not verified" wording had no `ag-*` review).
- ADRs 0022, 0027, 0030, 0032 and 0033 (accepted); 0023 and 0034 (new in 4a).
- [UI architecture](../design/ui-architecture.md) §4.2, §10, §11; [target architecture](../design/target-architecture.md) §5.1, §7.2, §7.4.
- [Principles](../design/principles.md) PR-13, PR-14, PR-15, PR-19, PR-22, PR-23, PR-24, PR-26, PR-27, PR-30, PR-34.
- `ag-ux-foundations` requirements EA-1, EA-3, EA-5, EA-6, EA-9, EA-10 and EA-16.

## Owner decisions

Each row has a recommended default. "Approve" accepts every default; name a row to change it.

| ID | Decision | Recommended default |
|---|---|---|
| D1 | Conversation shape and ADR numbers | A thread of runs (core plan option A, the roadmap default). A `Conversation` owns many runs; each run keeps one task, one budget, one approval and one outcome. ADR 0023 fills the reserved gap for the conversation model; ADR 0034, the next free number, holds the UI decisions |
| D2 | Message routing | One active run per conversation. The router looks only at the conversation's latest run:<br>– `WAITING_INPUT`: the message answers it, through the existing input path and its `expected_revision`;<br>– terminal (`SUCCEEDED`, `FAILED`, `CANCELLED`) or no run: the message starts a new run in the conversation;<br>– `CREATED`, `RUNNING`, `VERIFYING`, `WAITING_APPROVAL`, `NEEDS_RECONCILIATION`: the message is refused with `CONFLICT` and a fixed hint ("wait, decide the approval, or stop the run"). No queue and no auto-cancel.<br>Alternative: allow a new run beside a `WAITING_APPROVAL` run. Not chosen: its write would be refused by ADR 0020 anyway, and two live cards in one thread is a state the mockup would then have to cover |
| D3 | Greetings | No model call outside a run. A greeting stays an ADR 0022 reply run that waits for input, and the next message answers it. A run-less turn would bypass mode pinning, the per-call route check in `_with_tools` (T23), evidence and reconstruction. ADR 0023 amends ADR 0022 only to say that a reply run belongs to a conversation; the "reply" label shows once per thread (4b.2) |
| D4 | What is stored | A `conversations` row holds ids, the owner, a revision and timestamps, never text (record kind `conversations`, class audit skeleton). User text stays where it is today: `runs.task` and `input.received`. The thread is a projection of the conversation's runs and their events. The title is derived at read time from the first run's task, cut to 80 characters. No archive or delete route in Phase 4; retention and deletion follow ADR 0030's Phase 7 parts |
| D5 | Carried context content | Built by the kernel, deterministic, once at admission, from up to 5 earlier runs of the conversation, newest first. Per run: run id, task id and version, end state and reason code, the user's own messages in that run (class `personal`, fenced as data), the values a verifier confirmed (class-walked against the contract's declared `data_classes`; unmarked counts as `personal`), and the record refs it read (contract id, source ref, revision, observed time). Never `message.final` text, reply or question text, observation values, rationale text or a grounded summary.<br>"Values a verifier confirmed" means `OutcomeReport.verified_values` of a `VERIFIED` outcome, plus the arguments of a typed answer whose outcome is `VERIFIED`. Today only the procurement write verifier sets `verified_values` (`plugins/erp/domain/procurement/verifier.py`), and `kernel/ir_on.py` drops it when `execution_ir` is not `on`. So Task 4a.1 reads the ERP answer verifiers and the stored outcome reports, and fixes this row to what they actually keep. If a verified answer leaves nothing to carry, run 2 inherits only refs and user text, and the core plan exit ("uses the first run's findings") needs the answer's verified fields |
| D6 | Carried facts are not evidence | A carried ref is a hint, not a fact of the new run. Citation lookup stays scoped to this run (ADR 0033, Phase 3 Review Focus 5): a citation that names an earlier run's evidence is `KERNEL-CITATION`. Validation and approval use only this run's reads; the model must re-read (PR-15, PR-19) |
| D7 | Carried context needs the pack | Carried items reach the model only as the pack's `recent_turns` layer (ADR 0032 §1, empty in Phase 3). No new `DriverInput` field, so `sdk_api` stays 1.2. Startup refuses `conversations: on` unless `context_assembler` is `on`, like the 3b.1 startup rule. Note: the Phase 3 ruling gates `context_assembler: on` in a live profile on a first live write with the pack; the Phase 4 live check is where that write is tried |
| D8 | Toggle modes | `off`: today, per-run task view, conversation routes refuse, no run is linked. `shadow`: the UI keeps the per-run task view but sends messages through the conversation route. `answer` and `start` are what today's client does anyway, so those runs are linked. A message the router would refuse (D2) is not refused: the route records `conversation.compared` with `route: refuse` and starts an unlinked run (`conversation_id = None`), exactly as today, so the store's one-active-run check never fires. The kernel builds the carried layer, records `conversation.compared` and gives the driver nothing. `on`: the thread view, the router refuses, and carried context reaches the model. What `shadow` withholds is the refusal and the carried context |
| D9 | Mode pinning | `RunModes` gains `conversations`, pinned at admission and written only when not `off`, so an `off` continuation is byte-identical. The carried items are stored in the run's continuation (class business payload) and fixed for the run's life; a later message never changes them |
| D10 | How the UI learns the mode | A member-readable projection `GET /v1/me/features` returning `{conversations}` (the ADR 0017 pattern, with a session dependency). The UI reads nothing from `/health/ready`, which has no session. Alternative: a `features` field on `SessionResponse`; not chosen because `/v1/local/session` is loopback-only and never production auth |
| D11 | Sidebar source | In `on`, the sidebar lists the server's conversations (`GET /v1/conversations`, paged). Runs with `conversation_id = None` stay in today's session-local per-run history; no thread is synthesised for them |
| D12 | Stream | No conversation event stream. The thread view uses the active run's existing stream and re-reads the conversation snapshot after a posted message and after a run reaches a terminal or waiting state. ADR 0007 is unchanged |
| D13 | EA-10 | ADR 0034 ratifies EA-10 ("conversation first, closable artifact workspace", research 16) at G-A, before the brief. The brief extends the v4/v5 work (research 16, research 17) rather than restarting it |
| D14 | Chat defects first | Tasks 4b.1–4b.4 land before G-A, each in its own commit, with no toggle. They are inside the approved design (core plan Phase 0). One `ag-ux-review` covers the four diffs (4b.4) |
| D15 | D10 UI scope | In Phase 4: citations and the explanation in the outcome and the timeline, read from the existing `/v1/runs/{id}/evidence` `explanation` key (no contract change), with "grounded, not verified" wording (PR-19). The rationale on the approval card changes `ApprovalPresentation` (UI architecture §4.2, server-owned), so it ships only if ADR 0034's rationale section is accepted at G-A (Task 4e.6); otherwise it moves to a named follow-up |
| D16 | Phase size and cut line | Must-have: 4a–4d, 4e.1–4e.5, 4e.7 and 4f. The cut line is 4e.6 (rationale on the approval card). If the phase runs long, 4e.6 moves to a Phase 4′ with its own plan rather than being skipped |

## Global Constraints

- **Branch** `phase4/conversation-chat` from `main` at `b52f979` (Phase 3 merged, PR #7).
  - Stage explicit paths. Every commit ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
  - `main` is protected (strict, five required checks): changes reach it only through a PR whose checks pass.
  - Merge, push and rebase only on the owner's instruction.
- **Harness phase `4`.**
  - Features live in `harness/state/4/features.json` (`F-4a-1` … `F-4f-2`, one per task).
  - Each task has one contract (`uv run e-agent-harness new-task 4 <id> --feature <F-id> --gate <set> --paths ...`).
  - Run `check-scope` before each commit, `gate <set>` after the commit on a clean tree, and `close-check` before a task closes (ENG-WORK-1, ENG-EVID-1).
  - `harness/context.toml` `active_plan` points at this plan from the planning commit. Phase 3 switched it at 3a.2; here it switches now so that every Phase 4 contract pins this plan's digest.
  - UI tasks that write a brief or a mockup add `research/**` to their contract's paths; `research/**` is create-only, so they create new files and never edit an earlier study (ENG-BOUND-2).
- **Gate commands** (from `harness/context.toml`):
  - `full`: `uv sync --locked`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy`, `uv run lint-imports`, `uv run python scripts/export_openapi.py --check`, `uv run pytest -q`, `pnpm --dir ui gen:check`, `pnpm --dir ui check`, `uv run python scripts/check_core_only.py`.
  - `ui`: `pnpm --dir ui check`.
  - `pg`: `E_AGENT_TEST_STORE=postgres uv run pytest -q tests/unit/kernel tests/conformance tests/unit/adapters/postgres`, with `E_AGENT_TEST_PG_DSN` set to the `e_agent_test` database, never the live ledger's database (HP-13).
  - `e2e`: `make e2e` (builds the UI and runs `pnpm --dir ui conformance`).
  - `live`: `scripts/env_check.py` and `scripts/odoo_sandbox.py info`.
- **Design before code.** ADRs 0023 and 0034 are accepted at G-A before 4c starts. 4b does not wait (D14). If an accepted ADR changes a shape below, the accepting commit amends this plan (ENG-PLAN-3).
- **Authoritative files mid-task.** A task that edits a digest input (the target architecture, the ADR index, the roadmap, this plan) runs `uv run e-agent-harness refresh-task` before `close-check`.
- **Toggle default `off`.** Every committed profile keeps `conversations` `off`, and the Phase 2 and 3 toggles keep their committed values. The committed profiles are `src/e_agent/plugins/erp/simulator/fixture_profile.json`, `profiles/dev-ollama.json` and `profiles/live.example.json`.
- **`off` is today.** With `conversations` `off`, every existing test is unchanged in:
  - the event stream: `run.created` gains `conversation_id` only when it is set, so `tests/unit/kernel/golden/off_mode_events_v3.json` and `tests/unit/plugins/erp/simulator/golden/off_mode_events_erp_v3.json` do not move;
  - the continuation and the driver snapshot;
  - the model requests: `tests/unit/adapters/pydantic_ai/golden/off_model_request.json` and `tests/unit/plugins/erp/simulator/golden/off_model_request_erp.json`;
  - the UI: the per-run task view and its conformance specs.
- **Reservation boundary (ADR 0027).** Carried context is built once, at admission, before the run can reserve anything. A failure there records `feature.fallback` with `CONVERSATION_CONTEXT_FAILED` and the run starts without carried context. After admission the carried layer is part of the pack, so a later failure follows ADR 0032's `CONTEXT_UNAVAILABLE` path. A fallback never sends unmasked data to a route that is not `local` and has no `data_processing` declaration (T23).
- **Trust anchor (PR-13, PR-14, PR-15).** A message is never a decision: no code path leads from the message route to `approval_flow`, and approval goes only through `/v1/runs/{id}/approvals`. Carried context is a proposal input only; it grants nothing, is never evidence of the new run (D6), and never enters an approval digest.
- **Data rules (PR-26, ADR 0030).** Carried items are minimised (D5) and class-walked through the same class-per-route rule as observations (`kernel/context_walk.py`). New event payloads carry ids, counts, digests and reason codes, never user text or values. The new record kind `conversations` declares its class.
- **Authorization (PR-27).** Every new route has a session dependency. Conversations are scoped by tenant and owner; a foreign conversation looks absent (`NOT_FOUND`, PR-24). Task 4d.4 adds the route enumeration test that PR-27's row lacks.
- **API changes regenerate types.** A task that adds or changes a route regenerates `ui/packages/client/openapi.json` (`uv run python scripts/export_openapi.py`) and `ui/packages/client/src/schema.ts` (`pnpm --dir ui gen`) in the same commit; `full` checks both.
- **Stores (ENG-STORE-1, PR-30).** Both stores change together under `tests/conformance`. The migration is forward-only.
- **Driver changes.** No driver or prompt change is planned. If one becomes necessary, run `uv run pytest -q tests/unit/server/test_recorded_model_replays.py tests/unit/adapters/pydantic_ai/test_prompt_golden.py` (PR-32).
- **Hygiene.** No `os.environ`, `os.getenv` or `asyncio.create_task` under `src/e_agent` (ENG-ARCH-6, ENG-ARCH-7). Import contracts, exemptions and allow-lists are never widened (PR-06). Kernel modules stay under `MAX_KERNEL_MODULE_LINES = 500` (`tests/unit/kernel/test_structure.py`), so routing and carrying are new modules.
- **UI rules.** Every UI task goes through its `ag-*` stage. State the server owns is rendered, never derived (EA-1). Approved, committed, verified and grounded are separate labels (EA-3, PR-19). No provider identifiers in UI packages (PR-11, EA-6). Announcements are polite (EA-16).
- **Review.** Each task's close review runs in a fresh context (`eng-review`). Kernel and trust-anchor tasks (4c.3, 4d.1, 4d.2, 4d.3, 4e.6) get a second reviewer: Codex when it has quota, else a second fresh-context Claude reviewer adjudicated by the advisor, as the owner ruled for Phase 3 on 2026-10-20.
- **Boundaries.**
  - Containers: only `e-agent-ledger` (test database `e_agent_test`) for `pg`, and `odoo19-learning` plus `e-agent-ledger` in the live check (Task 4f.2). Never `odoo-bench` (ENG-BOUND-1).
  - `archive/**` and existing `research/**` files are read-only.
  - No change under `addons/**` is planned (ENG-BOUND-2).
  - Never read or grep `profiles/*.local.json` or `~/.config/e-agent/**`; every grep passes `--exclude='*.local.json'`.

## Review Focus

These are failure modes the tests below do not fully exercise. Each item names the task that adds its test; the reviewer of that task checks it by reading.

1. **A message read as a decision** (PR-13, PR-15). "Yes, approve it" typed while a run waits for approval must not touch the action. Task 4d.1 adds `test_message_while_waiting_approval_never_touches_the_action` and `test_message_text_is_never_a_decision`. The reviewer checks that nothing reachable from the message route calls `approval_flow` or writes an `approval.decided` event.
2. **Instructions inside carried text** (T1, PR-34). A user's earlier message, or a record ref, that reads like an instruction must reach the model fenced as data. Task 4d.2 adds `test_carried_user_text_is_fenced` and `test_injected_carried_text_does_not_change_the_proposal`. The reviewer checks that the fence cannot be closed from inside the carried text.
3. **Carried facts used as current facts** (PR-15, PR-19, PR-24). An earlier run's values may be stale. Task 4d.2 adds `test_citation_to_carried_evidence_is_kernel_citation` and `test_validation_ignores_carried_values`. The reviewer checks that the citation lookup and the validator read only this run's evidence.
4. **Personal data in the carried layer** (T23, PR-26). Task 4d.2 adds `test_carried_personal_value_masked_on_hosted_route`. The reviewer checks that every carried field, user text included, goes through the class walk, and that `conversation.compared` holds no value.
5. **A foreign conversation** (PR-24, PR-27). Tasks 4c.3 and 4d.4 test another owner and another tenant on both stores and through the API. The reviewer checks that every store query filters by tenant and owner, not only by id.
6. **Two runs from one thread** (PR-17). Two concurrent messages, or one retried message, must start at most one run. Task 4c.3 tests the revision check and the one-active-run rule on both stores; Task 4d.1 tests the idempotency key. The reviewer checks the Postgres path under concurrency (the check runs inside the run-creating transaction).
7. **`shadow` that acts** (ADR 0027, PR-23). `shadow` must add no model call, read or budget use, refuse no message, and give the driver no carried item. Task 4d.3 asserts it, including the would-refuse case. The reviewer checks every `DriverInput` and pack built for a run pinned `shadow`.
8. **The UI claiming more than the server says** (EA-1, EA-3, PR-19). A carried summary or a grounded answer must never read as verified. Task 4e.5 tests the labels. The reviewer checks that every status label comes from a server field.

## Design refs

| Area | Section | Task |
|---|---|---|
| Conversational reply runs | ADR 0022 Decision 3 | 4a.1, 4b.2 |
| Event log is the source; rows are projections | target §5.1 item 2 | 4a.1, 4c.2, 4d.4 |
| `recent_turns` layer, budgets, drop order, fencing | target §7.2; ADR 0032 §1, §2, §4 | 4a.1, 4d.2 |
| Rendering | target §7.4; ADR 0032 §6 | 4d.2 |
| Data classes and class-per-route rule | target §13.3; ADR 0030; ADR 0032 §5 | 4c.2, 4d.2 |
| Feature toggles | ADR 0027; target §6.4.8 | 4c.1, 4d.3 |
| Citations, explanation, rationale | ADR 0033 §1, §4, §6 | 4d.2, 4e.5, 4e.6 |
| `ApprovalPresentation` | UI architecture §4.2 | 4a.1, 4e.6 |
| Task workspace and surfaces | UI architecture §10, §11; ADRs 0015, 0016 | 4a.1, 4e.4 |
| Member-readable projections | ADR 0017; UI architecture §11 | 4d.4 |
| Conversation model (not yet in the design) | new target §5.7, written in 4a.1 | 4a.1 |

## ADRs

| ADR | Status | Decides | Needed by |
|---|---|---|---|
| 0023 Conversation model (new) | To write in 4a.1; Proposed until G-A | D1–D9 and D11–D12: the `Conversation` record, `RunRecord.conversation_id`, the `ConversationStore` port and the one-active-run rule, routing, carried context and its non-evidence rule, the toggle, pinning, fallback and startup rule, routes and their authorization, events and reason code; amends ADR 0022 (D3) and refines ADR 0032 (`recent_turns` filled) | 4c, 4d |
| 0034 Conversation-first workspace and explanation UI (new) | To write in 4a.1; Proposed until G-A | D10, D13, D15: EA-10, the thread view's surfaces, the citation and explanation display, the "grounded, not verified" wording, and the `ApprovalPresentation.rationale` section (shown second, never an approval input, never in the digest) | 4e |
| 0022 Conversational turns | Accepted; amended by 0023 at G-A | reply runs | 4b.2, 4d.1 |
| 0027 Feature toggles | Accepted | the toggle and reservation rules | 4c.1, 4d.3 |
| 0030 Data governance | Phase 3 parts accepted | record classes, class-per-route; retention stays Phase 7 | 4c.2, 4d.2 |
| 0032 ContextAssembler | Accepted; refined by 0023 at G-A | the pack and its `recent_turns` layer | 4d.2, 4d.3 |
| 0033 Explanation and grounded answers | Accepted | run-scoped citations, the explanation projection | 4d.2, 4e.5, 4e.6 |
| 0007, 0011, 0015, 0016, 0017, 0018, 0020 | Accepted | event stream, layered UI, workspace, surfaces, member projections, reason codes, connection-level write admission | throughout |

A Proposed ADR blocks the merge. 4c to 4e wait for G-A; 4b does not.

## Toggles and fallback

One new toggle, `features.conversations`, pinned per run at admission (D9). The chat defects in 4b have no toggle: they are fixes inside the approved design (D14). The route enumeration test in 4d.4 has no toggle: it is a check, not a runtime path.

| Mode | Behaviour |
|---|---|
| `off` | Today. The UI shows the per-run task view. `GET /v1/me/features` reports `off`. The conversation routes exist in every mode, so the OpenAPI document is the same, but in `off` they refuse with `NOT_FOUND` and the fixed message "conversations are off". No run is linked, no pin is written, and no new event appears. |
| `shadow` | The UI keeps the per-run task view, and its controller posts messages through `POST /v1/conversations/{id}/messages`, one conversation per "New task". `answer` and `start` routes are linked as in `on`, because today's client does the same. A message the router would refuse is not refused: it starts an unlinked run (`conversation_id = None`) as today, and the run records `conversation.compared` with `route: refuse`. At admission of a run with earlier runs in its conversation, the kernel builds the carried items and the `recent_turns` layer they would render, records `conversation.compared` (carried run ids, item counts, the layer digest, the kernel's token estimate, masked and dropped counts), and gives the driver nothing. No model call, read or budget use is added. A shadow error records `conversation.shadow_failed` with a stage and a fixed message and changes nothing else.<br>Real consumers: `test_shadow_layer_digest_equals_on_layer_digest` over the fixture thread corpus (Task 4d.3), which asserts its case count; and the evidence bundle's `conversation` key. |
| `on` | The UI shows the thread view. Messages route as in `shadow`. At admission the kernel builds the carried items, stores them in the continuation, records `conversation.context_carried` (conversation id, carried run ids, carried digest; no text), and every pack of the run renders them in `recent_turns`, fenced and class-walked. Startup refuses `on` unless `context_assembler` is `on` (D7). |

| Toggle | Fallback code (`feature.fallback`, before the first reservation only, never ends a run) | Terminal code |
|---|---|---|
| `conversations` | `CONVERSATION_CONTEXT_FAILED`: building the carried items failed at admission; the run starts without them, as in `off` | none of its own: after admission the carried layer is part of the pack, so a failure ends with ADR 0032's `CONTEXT_UNAVAILABLE`, or goes to reconciliation when a reservation is unresolved |

UI fallback: when `GET /v1/me/features` or a conversation route fails, the UI shows the per-run task view for the active run and keeps the composer draft. This changes presentation only; no write path depends on it.

**Observability** (ENG-TOGGLE-3): `/health/ready` and the evidence bundle report `features.conversations` with the other four toggles. The evidence bundle also reports the run's pinned `conversations` mode, its `conversation_id` and its carried run ids.

## Gate

| Task | Gate set |
|---|---|
| 4a.1, 4a.2 | `full` (docs only) |
| 4b.1–4b.4 | `ui`, plus `make e2e` through `eng-verify` |
| 4c.1, 4c.2 | `full` |
| 4c.3, 4c.4 | `full` and `pg` |
| 4d.1, 4d.2, 4d.3 | `full` and `pg` |
| 4d.4, 4d.5 | `full`, `pg` and `e2e` |
| 4e.1, 4e.2 | `full` (docs only), plus the mockup's own `verify.mjs` in 4e.2 |
| 4e.3, 4e.4, 4e.5 | `full` and `e2e` |
| 4e.6 | `full`, `pg` and `e2e` |
| 4e.7 | `full` (docs only), with the `pnpm --dir ui check` and `pnpm --dir ui conformance` output quoted in the review |
| 4f.1 | end-of-phase levels 1–3 |
| 4f.2 | level 4 (live) |

A contract carries one gate set (HP-6). Where a task names more, the contract's set is the first one named, and the others run through `eng-verify` and are named in the handoff.

**End-of-phase levels** (`eng-verify`, in order, on a clean tree): (1) the `full` gate; (2) the Postgres run (the `pg` gate); (3) `make e2e`; (4) the live check on `odoo19-learning`.

## Live check

Run in Task 4f.2 only on the owner's instruction, through the `live-sandbox` skill, with the identity flags on every sandbox mutation. It uses temporary `profiles/*.local.json` copies that set `conversations: on` and `context_assembler: on` (and `shadow` for the second item), deleted after the check; the agent never reads them.
- `/health/ready` and `GET /v1/me/features` report `conversations` in each mode.
- In `on`, in one thread in the UI: "hi" → "which products are short?" → "draft a PO for it" (core plan exit).
  - Expected: two runs in one conversation. Run 1 is the greeting's reply run, answered by the question. Run 2 starts after run 1 ends.
  - Run 2's evidence bundle shows `conversation.context_carried` naming run 1, and each pack's `recent_turns` layer.
  - Run 2 does not ask again which products are short.
  - If the model proposes the draft PO, the owner approves it in the UI, never `--approve` (that would be the agent's self-approval under the live profile). That is the first live write with `context_assembler: on` and closes the Phase 3 live-write gap. If the model proposes no PO, report it as model behaviour (ADR 0010), as in Phase 3.
- While run 2 waits for approval, typing "approve it" is refused with the fixed hint, and the action is unchanged.
- The sidebar shows one thread.
- In `shadow`: the per-run view is unchanged, no message is refused, and the second run of a thread records `conversation.compared` with no carried item in its model request.

The live check must not touch:
- `odoo-bench`, or any container outside `odoo19-learning-*` and `e-agent-ledger`;
- live business data;
- a hosted model route;
- any write beyond one draft PO in the `e-agent-demo` namespace.

Results are reported separately from fixture results (ENG-EVID-2).

---

## Part 4a: design entry gate

No runtime code. The ADRs are written, reconciled with this plan and the checkout, and accepted by the owner at G-A.

### Task 4a.1: ADRs 0023 and 0034, the ADR 0022 and 0032 notes, target §5.7

**Files:**
- New: `docs/adr/0023-conversation-model.md`, `docs/adr/0034-conversation-workspace-and-explanation-ui.md`.
- `docs/adr/0022-conversational-turns-read-feedback-discovery.md` and `docs/adr/0032-context-assembler.md`: a dated "Amended by ADR 0023 (Proposed)" line each.
- `docs/adr/README.md`: rows 0023 and 0034.
- `docs/design/target-architecture.md`: a new §5.7 "Conversations" tagged `[P]` with ADR 0023, and the §17 coverage note.
- `docs/roadmap.md`: the design coverage row "Conversation model" points at ADR 0023 and target §5.7.
- This plan, if an ADR changes a shape.

**Interfaces:** produces the record shapes, codes and events every later task uses:
- records: `Conversation`, `CarriedRun`, `CarriedRef`, `MessageRoute`, `RouteKind`, `ConversationSummary`, `ConversationSnapshot`;
- the reason code `CONVERSATION_CONTEXT_FAILED`;
- the events `conversation.context_carried`, `conversation.compared` and `conversation.shadow_failed`;
- the routes of Task 4d.4;
- for ADR 0034: the thread view's surfaces, the citation and explanation display rules, and `ApprovalPresentation.rationale`.

- [ ] Read what a verified run leaves behind (D5): the ERP answer verifiers in `src/e_agent/plugins/erp/domain/*/`, `OutcomeReport.verified_values` (`contracts/outcome.py`), where the kernel drops it (`kernel/ir_on.py`, `kernel/verification.py`), and what the `outcome_reports` rows keep. Fix D5's wording in this plan to what they actually produce, before the ADR states it.
- [ ] Write ADR 0023 from D1–D9, D11 and D12, and the core plan Phase 1 option table. Read `kernel/coordinator.py`, `kernel/context.py`, `sdk/store.py` and `server/api.py` first, and cite current `file:line`. State the ADR 0022 amendment (D3) and the ADR 0032 refinement (`recent_turns` holds carried items; drop order unchanged).
- [ ] Write ADR 0034 from D10, D13 and D15: EA-10 with its research 16 source; the citation, explanation and "grounded, not verified" rules; a separate section for `ApprovalPresentation.rationale`, so the owner can accept or defer it on its own (D16).
- [ ] Add target §5.7 (a summary that cites ADR 0023, no restated rules) and the index rows.
- [ ] Run `uv run python scripts/repo_move.py check`; expected: no broken links. Run `uv run e-agent-harness refresh-task`.
- [ ] Commit `docs(adr): ADRs 0023 and 0034 for review`.

### Task 4a.2: owner acceptance (gate G-A)

**Files:** the ADRs above, `docs/adr/README.md`, this plan (status line and decisions).

**Interfaces:** consumes the ADRs of 4a.1; produces their accepted status, which 4c–4e cite.

- [ ] The owner accepts or amends ADRs 0023 and 0034, and confirms D1–D16. Record each answer in the decisions table and the ADR status lines, with the owner's words.
- [ ] If ADR 0034's rationale section is deferred, mark Task 4e.6 deferred in this plan and in `harness/state/4/features.json`.
- [ ] Run `uv run e-agent-harness validate-context`; expected: `ok: manifest valid for ...`.
- [ ] Commit `docs: Phase 4 ADRs 0023 and 0034 accepted (G-A)`.

## Part 4b: chat defects (no toggle, D14)

Each task uses `ag-ui-implement` for a change inside the approved design (core plan Phase 0). Task 4b.4 ends with one `ag-ux-review` over the four diffs.

### Task 4b.1: legacy `run.state_changed` rows render without `undefined`

The server already emits `from` and `to` (`kernel/run_loop.py`, ADR 0031). Old rows carry only `state`, and `selectTimeline` prints `String(p["from"])`.

**Files:** `ui/packages/ui-core/src/store.ts` (`selectTimeline`), `ui/packages/ui-core/src/i18n.ts` (`status.unknown` in EN and VI, if absent), `ui/packages/ui-core/test/selectors.test.ts`, `ui/packages/ui-conformance/src/mock-api.ts` (one legacy row), `ui/packages/ui-conformance/tests/contract.spec.ts`.

**Interfaces:** consumes `RunEvent`; produces `TimelineItem.transition` with `to` from `to` or `state`, and `from` as `"unknown"` when absent.

- [ ] Failing tests: `selectors.test.ts` "renders a legacy state row as unknown → RUNNING", and "never prints undefined in a transition"; `contract.spec.ts` "legacy state row shows no undefined".
- [ ] Run `pnpm --dir ui exec vitest run packages/ui-core/test/selectors.test.ts`; expected: fails with `expected 'undefined → undefined' to be 'unknown → RUNNING'`.
- [ ] Implement: `to = p.to ?? p.state`; `from` is the unknown label when absent.
- [ ] Run the same command and `pnpm --dir ui check`; expected: pass.
- [ ] Commit `fix(ui): legacy state rows render without undefined (core plan 0.1)`.

### Task 4b.2: the reply label shows once per thread

**Files:** `ui/packages/ui-core/src/store.ts` (`selectConversation` marks `firstReply`), `ui/packages/components/src/features/conversation/Messages.tsx`, `ui/packages/ui-core/test/selectors.test.ts`, `ui/packages/ui-conformance/tests/composer.spec.ts`.

**Interfaces:** `ConversationItem.firstReply: boolean`. In the per-run view a thread is one run; Task 4e.3 extends it to a conversation.

- [ ] Failing tests: `selectors.test.ts` "marks only the first reply of a thread"; `composer.spec.ts` "reply label shows once after hi, hi"; and "a later reply keeps a quiet not-verified hint" (the truthful-state rule stays, ADR 0022).
- [ ] Run `pnpm --dir ui exec vitest run packages/ui-core/test/selectors.test.ts`; expected: fails with `firstReply` undefined.
- [ ] Implement: the visible label on the first reply; later replies carry the same text as an accessible description, not a visible badge.
- [ ] Run the same command; then `make ui-build && pnpm --dir ui exec playwright test --config packages/ui-conformance/playwright.config.ts -g "reply label"`; expected: pass.
- [ ] Commit `fix(ui): reply label once per thread (core plan 0.2)`.

### Task 4b.3: Context chip says what the agent uses

**Files:** `ui/packages/ui-core/src/i18n.ts` (`context.noHost`, EN and VI), `ui/packages/components/src/features/composer/ContextPreview.tsx` (only if the key changes), `ui/apps/web/test/routes.test.ts`.

**Interfaces:** none new. The EN text is "Uses this conversation and your connected systems; this page sends no extra details." It names no provider (PR-11). The VI text is the owner's to confirm at review.

- [ ] Failing test: `routes.test.ts` "context chip says what the agent uses", in EN and VI.
- [ ] Run `pnpm --dir ui exec vitest run apps/web/test/routes.test.ts`; expected: fails on the old text "Nothing else: this workspace sends no page context."
- [ ] Implement the copy; run `pnpm --dir ui lint:neutral`; expected: pass.
- [ ] Run the test command and `pnpm --dir ui check`; expected: pass.
- [ ] Commit `fix(ui): Context chip copy (core plan 0.3)`.

### Task 4b.4: the sidebar says "Your turn" after a reply, and the 4b review

`TaskNavigation.tsx` renders `resultStatusKey(h.state, h.reasonCode)`, and `TaskHistoryEntry` has no `replyPending`, so the sidebar says "Your answer is needed".

**Files:** `ui/packages/ui-core/src/controller.ts` (`TaskHistoryEntry.replyPending?: boolean`, set from `selectPendingReply`), `ui/packages/ui-core/src/presentation.ts`, `ui/packages/components/src/features/task-navigation/TaskNavigation.tsx`, `ui/packages/ui-core/test/controller.test.ts`, `ui/packages/ui-conformance/tests/composer.spec.ts`, `docs/reviews/2026-10-<dd>-chat-defects-ux-review.md` and its `-RESOLUTION.md`.

**Interfaces:** consumes `selectPendingReply` and `runStatusKey(state, events, replyPending)`.

- [ ] Failing tests: `controller.test.ts` "history entry records a pending reply", and "a stored entry without replyPending still loads"; `composer.spec.ts` "sidebar says Your turn after a reply".
- [ ] Run `pnpm --dir ui exec vitest run packages/ui-core/test/controller.test.ts`; expected: fails with `replyPending` undefined.
- [ ] Implement; run the same command and `pnpm --dir ui check`; expected: pass.
- [ ] Run `make e2e`; expected: exit 0, with its pass and skip counts quoted.
- [ ] Run `ag-ux-review` in review mode over the diffs of 4b.1–4b.4 and the running UI; answer every finding in the resolution file.
- [ ] Commit `fix(ui): sidebar Your turn after a reply (core plan 0.4); chat defects review`.

## Part 4c: contracts, stores and the toggle

### Task 4c.1: `features.conversations`, the pin, the reason code and the startup rule

**Files:**
- `src/e_agent/contracts/features.py`: `Features.conversations` and `RunModes.conversations`, both `FeatureMode.OFF`.
- `src/e_agent/contracts/run.py`: `ReasonCode.CONVERSATION_CONTEXT_FAILED`.
- `src/e_agent/kernel/features.py`: the fixed message for the code.
- `src/e_agent/kernel/continuation.py`: the pin, written only when a mode is not `off`.
- `src/e_agent/server/bootstrap.py`: the startup rule.
- The three committed profiles (explicit `off`).
- Tests: `tests/unit/contracts/test_features.py`, `tests/unit/server/test_committed_profiles.py`, `tests/unit/kernel/test_mode_pinning.py`, `tests/unit/server/test_conversation_startup.py` (new).

**Interfaces:** produces `RunModes.conversations`, read by 4d.2 and 4d.3, and the startup refusal.

- [ ] Failing tests:
  - `test_conversations_default_off`;
  - `test_committed_profiles_keep_conversations_off`;
  - `test_readiness_reports_five_toggles` (replaces `test_readiness_reports_four_toggles`);
  - `test_conversation_code_has_a_fixed_message`;
  - `test_conversations_pinned_only_when_not_off`;
  - the existing `test_off_run_writes_no_pin` and `test_absent_pin_means_off` keep passing with the new field;
  - `test_conversations_on_requires_context_assembler_on`: startup fails with `STARTUP_REJECTED`, and the message names the setting, never a value;
  - `test_conversations_shadow_allowed_with_any_context_assembler_mode`.
- [ ] Run `uv run pytest -q tests/unit/contracts/test_features.py tests/unit/server/test_committed_profiles.py tests/unit/kernel/test_mode_pinning.py tests/unit/server/test_conversation_startup.py`; expected: fails on the unknown field `conversations`.
- [ ] Implement. Nothing reads the mode yet except readiness, evidence, the pin and the startup rule.
- [ ] Run the same command, `tests/unit/kernel/test_off_baseline.py`, `tests/unit/plugins/erp/simulator/test_off_baseline_erp.py` and both `off` model-request goldens; expected: pass, goldens unchanged.
- [ ] Commit `feat(contracts): features.conversations, default off, pinned per run (ADR 0023)`.

### Task 4c.2: the `Conversation` contract and `RunRecord.conversation_id`

**Files:**
- `src/e_agent/contracts/conversation.py` (new): `Conversation(tenant_id, conversation_id, owner_id, revision, created_at, updated_at)`; `CarriedRef(contract_id, source_ref, revision, observed_at)`; `CarriedRun(run_id, task_id, task_version, state, reason_code, user_messages, verified_values, refs)`; `RouteKind` (`answer`, `start`, `refuse`); `MessageRoute(kind, run_id, expected_revision, hint)`; `ConversationSummary` and `ConversationSnapshot` (read models).
- `src/e_agent/contracts/run.py`: `RunRecord.conversation_id: str | None = None`.
- `src/e_agent/contracts/data_classes.py`: `RECORD_KINDS` gains `conversations` (audit skeleton, "a conversation's ids, owner and revision").
- `src/e_agent/kernel/reconstruct.py`: `run_created_keys` adds `conversation_id` only when set.
- Tests: `tests/unit/contracts/test_conversation.py` (new), `tests/conformance/test_record_classes.py`, `tests/unit/kernel/test_off_projection.py`.

**Interfaces:** produces the records above, consumed by 4c.3–4e.

- [ ] Failing tests:
  - `test_conversation_record_holds_no_text`: the field set is ids, owner, revision and timestamps;
  - `test_carried_run_has_no_model_text_field`;
  - `test_message_route_answer_needs_run_and_revision`;
  - `test_run_record_conversation_id_defaults_none`;
  - `test_run_created_has_no_conversation_key_when_unset`;
  - `test_every_store_record_kind_declares_a_class` (existing; now lists `conversations`).
- [ ] Run `uv run pytest -q tests/unit/contracts/test_conversation.py`; expected: `ModuleNotFoundError: e_agent.contracts.conversation`.
- [ ] Implement.
- [ ] Run the same command, `tests/conformance/test_record_classes.py`, `tests/unit/kernel/test_off_projection.py` and the `off` baselines; expected: pass, the v3 goldens unchanged. Run `uv run python scripts/export_openapi.py --check`; expected: no change (no route exposes the records yet).
- [ ] Commit `feat(contracts): Conversation record and RunRecord.conversation_id (ADR 0023)`.

### Task 4c.3: the `ConversationStore` port and the memory store, under conformance

**Files:**
- `src/e_agent/sdk/store.py`: `ConversationStore` protocol; `RunStore.create_run_idempotent` gains `conversation_revision: int | None = None`.
- `src/e_agent/kernel/memory_store.py`: implements both, and fixes FB-2 (`update_run` and `wait_for_approval` keep an empty driver state `{}`).
- `tests/conformance/test_conversation_store.py` (new); `tests/conformance/test_run_store.py`.

**Interfaces:**
- `create_conversation(conversation) -> None`;
- `get_conversation(tenant_id, owner_id, conversation_id) -> Conversation`: `NotFound` for another owner or tenant;
- `list_conversations(tenant_id, owner_id, *, after: str | None, limit: int) -> ConversationPage`: newest first, `limit` at most 100;
- `list_conversation_runs(tenant_id, owner_id, conversation_id) -> tuple[RunRecord, ...]`: oldest first;
- `create_run_idempotent(..., conversation_revision=n)`: when `run.conversation_id` is set, in the same transaction it checks the conversation's revision equals `n`, refuses when the conversation has a run in a non-terminal state, and bumps the revision and `updated_at`. Both refusals raise `ConcurrencyConflict`. An idempotent replay returns the first run and changes nothing.

- [ ] Failing tests, each parametrised over both stores, each printing its case count and failing on zero:
  - `test_create_and_get_conversation`;
  - `test_foreign_owner_conversation_looks_absent`;
  - `test_foreign_tenant_conversation_looks_absent`;
  - `test_list_conversations_is_paged_and_bounded`;
  - `test_run_creation_bumps_conversation_revision`;
  - `test_stale_conversation_revision_is_refused`;
  - `test_second_active_run_in_conversation_is_refused`;
  - `test_new_run_allowed_after_terminal_run`;
  - `test_idempotent_replay_starts_one_run`;
  - `test_empty_driver_state_round_trips` (FB-2, in `test_run_store.py`).
- [ ] Run `uv run pytest -q tests/conformance/test_conversation_store.py tests/conformance/test_run_store.py`; expected: fails with `ImportError` on `ConversationStore`.
- [ ] Implement in the memory store. Postgres tests are skipped until 4c.4, and the skip is named in the handoff.
- [ ] Run the same command; expected: pass on the memory store.
- [ ] Commit `feat(store): ConversationStore port and memory store; FB-2 parity (ADR 0023)`.

### Task 4c.4: Postgres migration `0007` and the Postgres store; CI runs the conformance suites on Postgres

**Files:**
- `src/e_agent/adapters/postgres/migrations/0007_conversations.sql` (new): table `conversations (tenant_id, conversation_id, owner_id, revision, created_at, updated_at)` with primary key `(tenant_id, conversation_id)`; `runs.conversation_id` nullable, with a composite foreign key `(tenant_id, conversation_id)`; index `(tenant_id, conversation_id, created_at)`. Forward-only, no data rewrite.
- `src/e_agent/adapters/postgres/store.py`: implements `ConversationStore` and the revision check inside `create_run_idempotent`'s transaction, with the conversation row locked `FOR UPDATE`.
- `tests/unit/adapters/postgres/test_migrations.py`.
- `.github/workflows/ci.yml`: the Postgres job runs `tests/unit/kernel tests/conformance tests/unit/adapters/postgres`, the `pg` gate's set (FB-1).

**Interfaces:** consumes the port of 4c.3.

- [ ] Failing tests: `test_migration_0007_applies_after_0006` (new, in `test_migrations.py`); the existing `test_migrations_apply_once_and_are_idempotent` and `test_modified_applied_migration_is_rejected` keep passing; the 4c.3 suite with `E_AGENT_TEST_STORE=postgres`; `test_concurrent_messages_start_one_run` (in `test_conversation_store.py`), two tasks against one conversation.
- [ ] Run `E_AGENT_TEST_STORE=postgres uv run pytest -q tests/unit/adapters/postgres tests/conformance/test_conversation_store.py`; expected: fails on the missing `conversations` table.
- [ ] Implement; never hold a transaction across a model or ERP call (PR-17).
- [ ] Run the same command, then the `pg` gate; expected: pass.
- [ ] Commit `feat(postgres): conversations table and store, migration 0007; CI runs conformance on Postgres (FB-1)`.

## Part 4d: routing and carried context

### Task 4d.1: message routing in the kernel facade

**Files:**
- `src/e_agent/kernel/conversation.py` (new): `route_message(latest: RunRecord | None) -> MessageRoute`, pure (D2); `ConversationFlow`, which the coordinator delegates to.
- `src/e_agent/kernel/coordinator.py`: `create_conversation(principal) -> Conversation` and `post_message(principal, conversation_id, text, *, expected_revision, idempotency_key, request_digest) -> tuple[MessageRoute, str]` (the route and the run id).
- `tests/unit/kernel/test_conversation_routing.py` (new).

**Interfaces:**
- `answer` calls the existing `accept_input` with the run's revision.
- `start` calls `admit_run` with `conversation_id` and `conversation_revision`.
- `refuse` raises `KernelError(CONFLICT, <fixed hint>)`.
- Only the conversation's owner may post (`FORBIDDEN` for any other requester).

- [ ] Failing tests:
  - `test_waiting_input_message_answers_the_run`;
  - `test_terminal_run_message_starts_a_new_run`;
  - `test_empty_conversation_message_starts_a_run`;
  - `test_running_run_message_is_refused`;
  - `test_message_while_waiting_approval_never_touches_the_action` (Review Focus 1): the action's revision, the approval rows and the event list are unchanged;
  - `test_message_text_is_never_a_decision`: "approve", "yes" and "reject" each give the same route as any other text;
  - `test_retried_message_starts_one_run` (same idempotency key);
  - `test_reused_key_with_other_text_conflicts`;
  - `test_other_requester_is_forbidden`;
  - `test_new_run_cannot_reuse_an_earlier_approval`: run 2 proposes the same action as run 1; it gets a new digest and a new pending approval.
- [ ] Run `uv run pytest -q tests/unit/kernel/test_conversation_routing.py`; expected: `ModuleNotFoundError: e_agent.kernel.conversation`.
- [ ] Implement. `route_message` reads no clock and no store.
- [ ] Run the same command on both stores; expected: pass.
- [ ] Commit `feat(kernel): conversation message routing (ADR 0023)`.

### Task 4d.2: carried context at admission, rendered in `recent_turns`

**Files:**
- `src/e_agent/kernel/carried.py` (new): `carry(runs, events_by_run, outcomes, classes) -> tuple[CarriedRun, ...]`, pure (D5); `render_carried(carried, rules, index) -> tuple[str, tuple[Dropped, ...]]`.
- `src/e_agent/kernel/context.py`: `assemble(..., carried: Sequence[CarriedRun] = ())` renders the `recent_turns` layer, fenced; carried items drop first after knowledge (ADR 0032 §2).
- `src/e_agent/kernel/context_on.py`: passes the run's carried items from the continuation.
- `src/e_agent/kernel/coordinator.py`: at admission of a run pinned `on`, builds the carried items, stores them in the continuation, and records `conversation.context_carried`; on failure, `feature.fallback` with `CONVERSATION_CONTEXT_FAILED`.
- `src/e_agent/contracts/events.py`: `conversation.context_carried`.
- `tests/unit/kernel/test_carried_context.py` (new); `tests/unit/kernel/test_context.py`.

**Interfaces:** consumes `RunModes.conversations`, `OutcomeReport.verified_values`, the `read.recorded` events and `Registry.data_class`; produces the carried layer, which 4d.3 compares.

- [ ] Failing tests:
  - `test_carry_is_deterministic`;
  - `test_carry_holds_no_model_text`: no `message.final`, reply, question or rationale text, over a corpus that has all four;
  - `test_carry_takes_values_only_from_verified_outcomes`: values come only from a `VERIFIED` outcome, as D5 states after 4a.1; a `GROUNDED` or failed run carries refs only;
  - `test_carry_takes_at_most_five_runs_newest_first`;
  - `test_carried_user_text_is_fenced` (Review Focus 2);
  - `test_injected_carried_text_does_not_change_the_proposal`: the scripted driver proposes the same action with clean and injected carried text;
  - `test_carried_personal_value_masked_on_hosted_route` (Review Focus 4);
  - `test_carried_layer_dropped_first_over_budget`: each drop is a `Dropped` entry;
  - `test_citation_to_carried_evidence_is_kernel_citation` (Review Focus 3);
  - `test_validation_ignores_carried_values`;
  - `test_carried_set_fixed_at_admission`: a run added to the conversation later does not change the pack;
  - `test_carry_failure_falls_back_before_reservation`;
  - `test_pack_without_carried_items_is_unchanged`: the Phase 3 pack digests stay the same.
- [ ] Run `uv run pytest -q tests/unit/kernel/test_carried_context.py`; expected: `ModuleNotFoundError: e_agent.kernel.carried`.
- [ ] Implement. `carry` reads only records and events, never a model.
- [ ] Run the same command, `tests/unit/kernel/test_context.py`, the `off` goldens and the replay suite on both stores; expected: pass, goldens unchanged.
- [ ] Commit `feat(kernel): carried context in the recent_turns layer (ADR 0023, ADR 0032)`.

### Task 4d.3: `conversations: shadow` and its comparison

**Files:** `src/e_agent/kernel/carried.py` (shadow entry point), `src/e_agent/kernel/coordinator.py`, `src/e_agent/contracts/events.py` (`conversation.compared`, `conversation.shadow_failed`), `tests/unit/kernel/test_conversation_shadow.py` (new), `tests/unit/kernel/fixtures/conversation_threads.json` (new: the fixture thread corpus: hi → hi, hi → question, question → PO, a message during approval, a thread over five runs).

**Interfaces:** consumes `carry` and `render_carried`; produces `conversation.compared {conversation_id, carried_run_ids, items, layer_digest, layer_tokens, masked, dropped}`.

- [ ] Failing tests:
  - the consumer `test_shadow_layer_digest_equals_on_layer_digest`: over the corpus, the layer `shadow` records equals the `recent_turns` layer of the `on` pack; prints the case count and fails on zero;
  - `test_shadow_gives_the_driver_no_carried_item` (Review Focus 7);
  - `test_shadow_adds_no_model_call_read_or_budget`;
  - `test_shadow_failure_changes_nothing`;
  - `test_shadow_would_refuse_starts_an_unlinked_run_and_records_it`: a message while the latest run waits for approval starts a run with `conversation_id = None`, as today, and records `route: refuse`;
  - `test_compared_event_holds_no_value_or_text`.
- [ ] Run `uv run pytest -q tests/unit/kernel/test_conversation_shadow.py`; expected: fails on the unknown event type `conversation.compared`.
- [ ] Implement.
- [ ] Run the same command on both stores; expected: pass, with the case count printed.
- [ ] Commit `feat(kernel): conversations shadow comparison (ADR 0023, ADR 0027)`.

### Task 4d.4: the API routes, member features and the route authorization test

**Files:**
- `src/e_agent/server/conversations.py` (new router, included by `api.py`):
  - `POST /v1/conversations` → `{conversation_id}`;
  - `GET /v1/conversations?after=&limit=` → `ConversationList` of `ConversationSummary(conversation_id, title, updated_at, latest_state, reply_pending)`;
  - `GET /v1/conversations/{id}` → `ConversationSnapshot(conversation, runs)`, each run with id, task, state, reason code and created time;
  - `POST /v1/conversations/{id}/messages` with the `Idempotency-Key` header and body `{text, expected_revision}` → `{route, run_id}`.
- `src/e_agent/server/api.py`: `GET /v1/me/features` → `MemberFeatures{conversations}`; the evidence bundle's `conversation` key (id, pinned mode, carried run ids, `conversation.compared` counts).
- `ui/packages/client/openapi.json` and `ui/packages/client/src/schema.ts` (regenerated).
- `docs/design/principles.md`: PR-27's check.
- Tests: `tests/unit/server/test_conversation_api.py` (new), `tests/unit/server/test_route_authorization.py` (new), `tests/unit/server/test_api.py`.

**Interfaces:** consumes `ConversationFlow`; produces the routes Task 4e.3 calls. Every route has `Depends(session)`. In `off`, the conversation routes refuse with `NOT_FOUND` "conversations are off"; `/v1/me/features` answers in every mode.

- [ ] Failing tests:
  - `test_conversation_routes_refuse_when_off`;
  - `test_create_list_get_and_post_message`;
  - `test_foreign_conversation_is_not_found` (Review Focus 5), for another owner and another tenant;
  - `test_post_message_requires_idempotency_key`;
  - `test_refusal_carries_the_fixed_hint`;
  - `test_list_is_paged`;
  - `test_member_features_reports_the_mode`;
  - `test_evidence_bundle_reports_conversation`;
  - `test_every_v1_route_has_an_authorization_dependency`: enumerates `app.routes`, prints the count and fails on zero (PR-27). Its allow-list holds exactly `POST /v1/local/session` (it creates the session), `GET /health/live` and `GET /health/ready`, and the test asserts the allow-list has three entries, so it cannot be widened quietly (PR-06).
- [ ] Run `uv run pytest -q tests/unit/server/test_conversation_api.py tests/unit/server/test_route_authorization.py`; expected: `ModuleNotFoundError: e_agent.server.conversations`.
- [ ] Implement; HTTP handlers delegate to the kernel facade and hold no routing logic (PR-03).
- [ ] Run `uv run python scripts/export_openapi.py` and `pnpm --dir ui gen`; then the test command, `export_openapi.py --check` and `pnpm --dir ui gen:check`; expected: pass. Add the check to PR-27's row in principles.
- [ ] Commit `feat(server): conversation routes and member features, each with a session dependency (ADR 0023)`.

### Task 4d.5: a fixture thread end to end

**Files:** `tests/unit/server/test_conversation_e2e.py` (new); `src/e_agent/plugins/erp/domain/testing/scripted_driver.py`, only if the scripted driver needs a branch for a carried shortage. A change there changes the `domain-erp` artifact digest; name it in the handoff.

**Interfaces:** consumes the routes of 4d.4 with the ERP fixture profile and `conversations` and `context_assembler` set `on` in a test profile.

- [ ] Failing tests:
  - `test_two_run_thread_carries_first_run_findings`: "hi" → "which products are short?" → "draft a PO for it". Expected: two runs; run 2's pack has run 1 in `recent_turns`; run 2 reads before it proposes; the approval is decided through the approvals route only;
  - `test_thread_in_shadow_matches_per_run_behaviour`: the same thread in `shadow`, plus a message sent while run 2 waits for approval, gives the same run outcomes as the per-run tasks, plus `conversation.compared`; the approval-time message starts an unlinked run and changes nothing in run 2.
- [ ] Run `uv run pytest -q tests/unit/server/test_conversation_e2e.py`; expected: fails (the scripted thread is not wired).
- [ ] Implement only test wiring and, if needed, the scripted branch.
- [ ] Run the same command, the `pg` gate and `make e2e`; expected: pass.
- [ ] Commit `test(server): fixture conversation thread end to end`.

## Part 4e: UI through the `ag-*` stages

Every task here reads `ag-ux-foundations` first and cites AG and EA criteria by ID. A stage never starts before the previous gate is recorded.

### Task 4e.1: design brief (gate G-B)

**Files:** `research/<NN>-conversation-thread-brief.md` (new; NN is the next free research number: 20 on 2026-10-20, re-checked against `research/README.md` and every worktree in `git worktree list` before writing).

**Interfaces:** consumes ADRs 0023 and 0034 and the current UI; produces the approved brief that 4e.2 builds from.

- [ ] Run `ag-ux-review` in gap-audit mode over the current chat surface after 4b, to `docs/reviews/2026-10-<dd>-chat-surface-gap-audit.md`.
- [ ] Write the brief with `ag-ux-brief`:
  - roles and the normative states: thread empty; reply pending; clarification; running; waiting approval with a refused message; verified; grounded; failed; per-run fallback; legacy runs;
  - the AG criteria and EA-1, EA-3, EA-5, EA-6, EA-9, EA-10 and EA-16;
  - 2–3 directions; how they will be judged;
  - the D15 surfaces (citations, explanation, rationale second on the card);
  - the "grounded, not verified" wording (handoff item 14);
  - open questions, among them: where legacy runs appear (D11), and the VI copy of 4b.3.
- [ ] The owner approves the brief and names a direction. Record the approval verbatim in the brief's Approval section (G-B).
- [ ] Commit `docs(research): conversation thread design brief (G-B)`.

### Task 4e.2: mockup (gate G-C)

**Files:** `research/mockups/conversation-thread-v<N>/` (new; the next free version), with `verify.mjs`, the QA file and screenshots.

**Interfaces:** consumes the approved brief; produces the owner-selected direction.

- [ ] Build the mockup with `ag-ux-mockup`: every normative state of the brief with labelled samples, 2–3 comparable directions on the same scenario, a stop control in every state (AG-CTRL-1), and the closable artifact workspace (EA-10).
- [ ] Run `node research/mockups/conversation-thread-v<N>/verify.mjs`; expected: every state checked, with the output in the QA file.
- [ ] Self-review the screenshots with the `ag-ux-review` rubric; open findings go in the QA file.
- [ ] The owner selects a direction (G-C). Record it in the QA file.
- [ ] Commit `docs(research): conversation thread mockup (G-C)`.

### Task 4e.3: ui-core conversation state

**Files:** `ui/packages/client/src/index.ts` (conversation and features calls), `ui/packages/ui-core/src/controller.ts` (mode, active conversation, message post, fallback), `ui/packages/ui-core/src/store.ts` (`selectThread`), `ui/packages/ui-core/test/conversation.test.ts` (new), `ui/packages/ui-conformance/src/mock-api.ts` (conversation routes and `/v1/me/features`).

**Interfaces:** consumes the routes of 4d.4; produces the controller state 4e.4 renders. The thread is built only from server snapshots and run events (AG-FE-2, EA-1).

- [ ] Failing tests in `conversation.test.ts`:
  - "reads the mode from /v1/me/features";
  - "off and shadow keep the per-run view";
  - "shadow posts through the conversation route";
  - "on lists server threads, newest first";
  - "a refused message keeps the draft and shows the server's hint";
  - "falls back to the per-run view when a conversation route fails";
  - "the thread comes from server snapshots only";
  - "the reply label shows on the first reply of a conversation" (extends 4b.2).
- [ ] Run `pnpm --dir ui exec vitest run packages/ui-core/test/conversation.test.ts`; expected: fails with the missing client method `listConversations`.
- [ ] Implement.
- [ ] Run the same command and `pnpm --dir ui check`; expected: pass.
- [ ] Commit `feat(ui-core): conversation state behind features.conversations (ADR 0023)`.

### Task 4e.4: the thread view, the sidebar and the closable workspace

**Files:** `ui/packages/components/src/features/conversation/` (thread and run cards), `ui/packages/components/src/features/task-navigation/TaskNavigation.tsx` (threads in `on`), `ui/packages/layouts/` (the closable artifact workspace, per the selected mockup), `ui/packages/ui-core/src/i18n.ts` (EN and VI), `ui/packages/ui-conformance/tests/conversation.spec.ts` (new), `docs/design/ui-architecture.md` (new §12 "Conversation threads").

**Interfaces:** consumes the 4e.3 controller; produces the selected design in the four surfaces of ADR 0016.

- [ ] Failing specs in `conversation.spec.ts`:
  - "two runs show in one thread";
  - "the sidebar lists one thread";
  - "the workspace closes and reopens, and the conversation stays" (EA-10);
  - "a message during approval shows the hint, and the card is unchanged";
  - "a new run is announced politely" (EA-16);
  - "the off profile shows today's per-run view";
  - an axe check per state.
- [ ] Run `make ui-build && pnpm --dir ui exec playwright test --config packages/ui-conformance/playwright.config.ts -g "thread|sidebar|workspace"`; expected: fails with no thread element.
- [ ] Implement the selected direction only.
- [ ] Run the same command, `pnpm --dir ui check` and `make e2e`; expected: pass. Update UI architecture §12 in the same change.
- [ ] Commit `feat(ui): conversation thread view and closable workspace (ADR 0034)`.

### Task 4e.5: citations and the explanation, "grounded, not verified"

**Files:** `ui/packages/ui-core/src/store.ts` (`selectExplanation`, from the evidence bundle's `explanation` key), `ui/packages/components/src/features/outcome/` and `ui/packages/components/src/features/timeline/` (citation and explanation display), `ui/packages/ui-core/src/i18n.ts`, `ui/packages/components/test/citations.test.tsx` (new), `ui/packages/ui-conformance/tests/explanation.spec.ts` (new), `ui/packages/ui-conformance/src/mock-api.ts`.

**Interfaces:** consumes `/v1/runs/{id}/evidence` (`explanation`, citations as evidence id, pointer and value digest). The value shown beside a citation is read from that run's recorded evidence, never from model text. No contract change.

- [ ] Failing tests:
  - `citations.test.tsx` "a citation shows its record and field from the server";
  - "a grounded run says grounded, not verified" (EN and VI);
  - "free text outside citations is labelled unverified";
  - "the explanation lists facts before any rationale";
  - "an unresolved citation is never shown as a fact";
  - `explanation.spec.ts` "explanation opens from the outcome" (Review Focus 8).
- [ ] Run `pnpm --dir ui exec vitest run packages/components/test/citations.test.tsx`; expected: fails with the missing component.
- [ ] Implement.
- [ ] Run the same command, `pnpm --dir ui check` and `make e2e`; expected: pass.
- [ ] Commit `feat(ui): citations and explanation, grounded not verified (ADR 0033, ADR 0034)`.

### Task 4e.6: rationale on the approval card (cut line, D16; only if ADR 0034's rationale section is accepted)

**Files:** `src/e_agent/kernel/approval.py` (`ApprovalPresentation.rationale`: summary, cited evidence ids, rule ids, from the continuation; never a digest input), `src/e_agent/kernel/approval_flow.py`, `tests/unit/kernel/test_approval_rationale.py` (new), the regenerated client types, `ui/packages/components/src/features/approval/`, `ui/packages/ui-core/test/approval.test.ts`.

**Interfaces:** consumes the rationale text that ADR 0033 keeps in the continuation; produces the card's second section.

- [ ] Failing tests:
  - `test_presentation_carries_rationale_after_facts`;
  - `test_rationale_never_changes_the_approval_digest` (existing; must still pass);
  - `test_presentation_without_rationale_is_unchanged`;
  - `test_rationale_is_not_in_any_event_payload`;
  - `approval.test.ts` "rationale renders after the facts, labelled as the agent's reason".
- [ ] Run `uv run pytest -q tests/unit/kernel/test_approval_rationale.py`; expected: fails on the missing field `rationale`.
- [ ] Implement; regenerate OpenAPI and TS types.
- [ ] Run the same command on both stores, `pnpm --dir ui check` and `make e2e`; expected: pass, digest vectors unchanged.
- [ ] Commit `feat(approval): rationale second on the approval card (ADR 0034)`.

### Task 4e.7: UI review (gate G-D)

**Files:** `docs/reviews/2026-10-<dd>-conversation-thread-ux-review.md` and `-RESOLUTION.md`.

**Interfaces:** consumes the diffs of 4e.3–4e.6 and the running UI.

- [ ] Run `ag-ux-review` in review mode. Quote the real output of `pnpm --dir ui check` and `pnpm --dir ui conformance` on the reviewed revision.
- [ ] Fix the findings as `4.U<n>` tasks; answer each one in the resolution file. No Blocker or High stays open.
- [ ] The owner reviews the UI change (G-D, the `ag-ui-implement` stop gate).
- [ ] Commit `docs(reviews): conversation thread UX review and resolution (G-D)`.

## Part 4f: verification

### Task 4f.1: end-of-phase verification and handoff

**Files:** `README.md` (toggle and commands), `docs/roadmap.md` (Phase 4 status), `docs/handoffs/<date>-phase4-conversation-chat.md`, `harness/state/4/`.

**Interfaces:** consumes every task's evidence.

- [ ] Run `eng-verify` levels 1–3 on a clean tree; record each result with its counts.
- [ ] Phase review with `eng-review` in a fresh context, then the final check across the kernel tasks (Codex, or two fresh-context Claude reviewers adjudicated by the advisor); fix findings as `4.R<n>` tasks.
- [ ] Write the handoff with `eng-handoff`. State plainly that:
  - carried context is a hint and never evidence of the new run;
  - a `GROUNDED` end is not verified;
  - the thread corpus is authored fixture input, not model evidence (PR-29);
  - whether 4e.6 shipped or moved to Phase 4′.
- [ ] Commit `docs: Phase 4 handoff and roadmap status`.

### Task 4f.2: live check

**Interfaces:** consumes the Live check section above.

- [ ] On the owner's instruction only, run the live check through `live-sandbox`. Record the results in the handoff, labelled live and separate from fixture results.
- [ ] Commit `docs: Phase 4 live check results`.

## Self-review

- **Spec coverage.**
  - Roadmap row 4:
    - conversation model (ADR 0023, thread of runs with carried context) → 4a.1, 4c.2–4c.4, 4d.1–4d.5;
    - chat defects: `status.undefined` → 4b.1; label noise → 4b.2; Context chip copy → 4b.3; sidebar → 4b.4;
    - UI through `ag-*` with owner gates → 4e.1 (G-B), 4e.2 (G-C), 4e.7 (G-D);
    - toggle `features.conversations` with fallback to the per-run task view → 4c.1, 4d.3, 4e.3.
  - Core plan Phase 1 interfaces:
    - `Conversation` → 4c.2. `ConversationTurn` is not a stored record: the thread is a projection (D4);
    - `RunRecord.conversation_id` → 4c.2;
    - `ConversationStore` on both stores → 4c.3, 4c.4, with migration `0007`, not the stale `0005`;
    - routes → 4d.4;
    - the conversation SSE stream is replaced by the run stream plus snapshots (D12).
  - Core plan Phase 1 tasks:
    - task 4 (carried context) uses the Phase 3 ContextAssembler, not a precursor → 4d.2;
    - task 3's run-less turn is replaced by D3.
  - Core plan exit evidence: the two-run thread → 4d.5 (fixture) and 4f.2 (live); the sidebar shows one thread → 4e.4; conformance on both stores → 4c.3, 4c.4.
  - Phase 3 handoff items: D10 → 4e.5, 4e.6; the live-write gap → 4f.2; FB-1 → 4c.4; FB-2 → 4c.3; item 14 (grounded wording review) → 4e.1, 4e.7.
  - EA-10 → 4a.1 (ADR 0034), 4e.4.
  - PR-27's missing check → 4d.4.
- **Placeholder scan.** The research number (20) and the mockup version are re-checked at task time because the `ag-*` skills require it; `<dd>` in review file names is the date the review runs. No step says "add tests" without naming them.
- **Type consistency.**
  - `Conversation`, `CarriedRun`, `CarriedRef`, `MessageRoute`, `RouteKind`, `ConversationSummary` and `ConversationSnapshot` live in `contracts/conversation.py` (4c.2).
  - `route_message` and `ConversationFlow` live in `kernel/conversation.py` (4d.1); `carry` and `render_carried` in `kernel/carried.py` (4d.2, 4d.3).
  - `RunModes.conversations` (4c.1) is read by 4d.2 and 4d.3.
  - `create_run_idempotent(..., conversation_revision=)` (4c.3) is called by `post_message` (4d.1).
  - `CONVERSATION_CONTEXT_FAILED` (4c.1) is used in 4d.2. The events `conversation.context_carried` (4d.2), `conversation.compared` and `conversation.shadow_failed` (4d.3) are in `contracts/events.py`.
- **Review Focus coverage.**
  - Item 1 → 4d.1.
  - Items 2, 3 and 4 → 4d.2.
  - Item 5 → 4c.3, 4d.4.
  - Item 6 → 4c.3, 4c.4, 4d.1.
  - Item 7 → 4d.3.
  - Item 8 → 4e.5.
- **Toggles.** One runtime feature, one toggle. Its fallback code is used only at admission, before any reservation, and never ends a run. After admission the carried layer follows ADR 0032's terminal path. `shadow` has a real consumer (4d.3). The chat defects and the route test state why they have no toggle.
