# Phase 4: Conversation and Chat UX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. UI tasks also follow the `ag-*` skills named in each task, and stop at their owner gates.

**Status:** Approved by the owner on 2026-10-20, with every recommended default in the decisions table (D17 ruled (a) earlier the same day). Not implemented. Reviewed four times by fresh-context reviewers: `harness/state/4/reviews/4-plan.json` (PL-1 to PL-14, rework), `4-plan-r2.json` (PL2-1 to PL2-8), `4-plan-r3.json` (PL3-1 to PL3-3) and `4-plan-r4.json` (accept; PL4-1 and PL4-2 folded in). Amended 2026-10-20 by Task 4a.1 (ENG-PLAN-3), where writing ADRs 0023 and 0034 showed a shape that could not hold: D15 and Task 4e.5 read citations from the bundle's `grounded_answer` key and `proposal.created` events, not the `explanation` key, and read a cited value from `actions[].approved_facts` (review R1-1, confirmed at G-A); D17, 4c.4, 4d.2 and the live check item 4 state the data-class ancestor rule, the verifier-read gap and the demand-ref locator. Gate G-A passed on 2026-10-20 with the owner's answers "1 accept 2 accept 3 defer 4 ok 5 ok 6 ok 7 yes": ADRs 0023 and 0034 accepted; ADR 0034 §5 (the rationale on the approval card) deferred, so Task 4e.6 is deferred to a named follow-up; the D15 amendment confirmed; the ADR 0027 refinement for `conversations: shadow` confirmed; the four never-carried ref paths accepted as a known limit; and a carried ref counts only from a read that found its record (completeness `complete`).

**Goal:** a user talks to e-agent in one thread. A message answers the run that waits for input, or starts a new run in the same thread. A new run gets a small, kernel-built summary of the earlier runs through the ContextAssembler, never raw model text. The open chat defects are fixed, and citations and the explanation are visible in the UI as "grounded, not verified". Everything new sits behind `features.conversations`, which falls back to today's per-run task view.

**Architecture:** the plan has six parts.
- **4a (design entry gate, no runtime code):** ADR 0023 (the conversation model, amending ADR 0022 and refining ADR 0032) and ADR 0034 (conversation-first workspace and the citation, rationale and explanation UI, settling EA-10). The owner accepted both at gate G-A on 2026-10-20 and deferred ADR 0034 §5, the rationale.
- **4b (chat defects):** the four core plan Phase 0 defects, as small UI fixes inside the approved design, with no toggle, then their UX review, the owner's review (gate G-0) and the fixes. They do not wait for G-A (D14).
- **4c (contracts, stores, toggle):** the `features.conversations` toggle and its startup rule; the `Conversation` contract and `RunRecord.conversation_id`; the `ConversationStore` port on both stores in one task, with Postgres migration `0007`; the host-side answer value formats in the plugin manifest (D17).
- **4d (routing and carried context):** the message router, which binds an answer to the question the user saw; carried context built at admission and rendered only in the pack's `recent_turns` layer; the `shadow` comparison; the API routes, each with an authorization dependency; a fixture thread end to end.
- **4e (UI, through the `ag-*` stages):** brief (gate G-B), mockup (gate G-C), the thread view, the D10 citation and explanation UI (second cut line), the rationale on the approval card (first cut line; deferred at G-A, so not built in Phase 4), and the UI review (gate G-D). Five owner gates in all: G-0, G-A, G-B, G-C, G-D.
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
| D1 | Conversation shape and ADR numbers | A thread of runs (core plan option A, the roadmap default). A `Conversation` owns many runs; each run keeps one task, one budget, one approval and one outcome. ADR 0023 fills the reserved gap for the conversation model; ADR 0034, the next free number, holds the UI decisions. Both accepted by the owner at gate G-A, 2026-10-20 ("1 accept", "2 accept") |
| D2 | Message routing | One active run per conversation. The router looks only at the conversation's latest run:<br>– `WAITING_INPUT`: the message answers it only when its `reply_to` names that run and the run revision the user saw with the pending question, through the existing input path. A message for an earlier question (Q1 while Q2 is pending), or with no `reply_to`, gets `CONFLICT` with the fixed hint "the question changed; read it again", in every mode, as `/v1/runs/{id}/inputs` does today. A retried answer is idempotent through today's input replay check, moved into the kernel;<br>– terminal (`SUCCEEDED`, `FAILED`, `CANCELLED`) or no run: the message starts a new run in the conversation;<br>– `CREATED`, `RUNNING`, `VERIFYING`, `WAITING_APPROVAL`, `NEEDS_RECONCILIATION`: the message is refused with `CONFLICT` and a fixed hint ("wait, decide the approval, or stop the run"). No queue and no auto-cancel.<br>Alternative: allow a new run beside a `WAITING_APPROVAL` run. Not chosen: its write would be refused by ADR 0020 anyway, and two live cards in one thread is a state the mockup would then have to cover |
| D3 | Greetings | No model call outside a run. A greeting stays an ADR 0022 reply run that waits for input, and the next message answers it. A run-less turn would bypass mode pinning, the per-call route check in `_with_tools` (T23), evidence and reconstruction. ADR 0023 amends ADR 0022 only to say that a reply run belongs to a conversation; the "reply" label shows once per thread (4b.2) |
| D4 | What is stored | A `conversations` row holds ids, the owner, a revision and timestamps, never text (record kind `conversations`, class audit skeleton). User text stays where it is today: `runs.task` and `input.received`. The thread is a projection of the conversation's runs and their events. The title is derived at read time from the first run's task, cut to 80 characters. No archive or delete route in Phase 4; retention and deletion follow ADR 0030's Phase 7 parts |
| D5 | Carried context content | Refs and checked typed values; no free text, even when classed. The one text carried is the user's own words, fenced as `personal` data; no answer or model text is carried. Built by the kernel, deterministic, once at admission, from up to 5 earlier runs of the conversation, newest first. Per run: run id, task id and version, end state and reason code, and three kinds of fact:<br>– the user's own messages in that run (the task text and `input.received`), class `personal`, fenced as data;<br>– checked typed values from the normalised arguments of each answer action in state `VERIFIED`. A path qualifies only if the answer contract declares a host-side value format for it (`answer_value_formats`, D17, Task 4c.4) and declares it in `data_classes` (then class-walked). Its value is carried only if it passes that format check, and a `ref`-format value only if it also equals a source ref the same run recorded. A path with no format is never carried, whatever class it declares, so `/input/explanation` and `/input/summary` are excluded;<br>– the record refs it read (contract id, source ref, revision, observed time). The source ref is the `EvidenceRef.locator` of each observation that a `read.recorded` event names (by `evidence_id`), read from the run's stored continuation; the `read.recorded` payload is unchanged.<br>Never model text (`message.final`, reply, question or rationale text, a grounded summary, a free-text answer field) and never a raw observation. `OutcomeReport.verified_values` is not a source: the answer verifiers do not set it, and `kernel/ir_on.py` drops it when `execution_ir` is not `on`. A `GROUNDED` answer carries refs only. Task 4a.1 lists, per answer contract, the declared paths and which `ref` paths can match a recorded source ref today |
| D6 | Carried facts are not evidence | A carried ref is a hint, not a fact of the new run. Citation lookup stays scoped to this run (ADR 0033, Phase 3 Review Focus 5): a citation that names an earlier run's evidence is `KERNEL-CITATION`. Validation and approval use only this run's reads; the model must re-read (PR-15, PR-19) |
| D7 | Carried context needs the pack | Carried items reach the model only as the pack's `recent_turns` layer (ADR 0032 §1, empty in Phase 3). No new `DriverInput` field, so `sdk_api` stays 1.2; the one SDK-visible addition, `CapabilityDescriptor.answer_value_formats` (D17), joins the unreleased 1.2 list (Task 4c.4). Startup refuses `conversations: on` unless `context_assembler` is `on`, like the 3b.1 startup rule. Note: the Phase 3 ruling gates `context_assembler: on` in a live profile on a first live write with the pack; the Phase 4 live check is where that write is tried |
| D8 | Toggle modes | `off`: today, per-run task view, conversation routes refuse, no run is linked. `shadow`: the UI keeps the per-run task view but sends messages through the conversation route. `answer` and `start` are what today's client does anyway, so those runs are linked. `shadow` never refuses what today's path accepts. A message the router would refuse (D2) starts an unlinked run (`conversation_id = None`), exactly as today, and records `conversation.compared` with `route: refuse`. A linked start or answer that hits `ConcurrencyConflict` or any other conversation-step error falls back, server-side, inside the same request and under the message's own idempotency record, to today's unlinked run or plain input, and records `conversation.shadow_failed`; no request fails, and the UI never re-posts. In `shadow`, an answer to the caller's own unlinked run (made by such a fallback) is a plain input, as `/inputs` would take it. The kernel builds the carried layer, records `conversation.compared` and gives the driver nothing. `on`: the thread view, the router refuses, and carried context reaches the model. What `shadow` withholds is the refusal and the carried context. ADR 0023 §9's refinement of ADR 0027 for this toggle confirmed by the owner at gate G-A, 2026-10-20 ("5 ok") |
| D9 | Mode pinning | `RunModes` gains `conversations`, pinned at admission and written only when not `off`, so an `off` continuation is byte-identical. The carried items are stored in the run's continuation (class business payload) and fixed for the run's life; a later message never changes them |
| D10 | How the UI learns the mode | A member-readable projection `GET /v1/me/features` returning `{conversations}` (the ADR 0017 pattern, with a session dependency). The UI reads nothing from `/health/ready`, which has no session. Alternative: a `features` field on `SessionResponse`; not chosen because `/v1/local/session` is loopback-only and never production auth |
| D11 | Sidebar source | In `on`, the sidebar lists the server's conversations (`GET /v1/conversations`, paged). Runs with `conversation_id = None` stay in today's session-local per-run history; no thread is synthesised for them |
| D12 | Stream | No conversation event stream. The thread view uses the active run's existing stream and re-reads the conversation snapshot after a posted message and after a run reaches a terminal or waiting state. ADR 0007 is unchanged |
| D13 | EA-10 | ADR 0034 ratifies EA-10 ("conversation first, closable artifact workspace", research 16) at G-A, before the brief. The brief extends the v4/v5 work (research 16, research 17) rather than restarting it |
| D14 | Chat defects first | Tasks 4b.1–4b.5 land before G-A, each in its own commit, with no toggle. They are inside the approved design (core plan Phase 0). One `ag-ux-review` covers the four diffs (4b.4) and stops at its gate; the owner reviews (G-0); the fixes are 4b.5, before 4e.1 |
| D15 | D10 UI scope | In Phase 4: citations and the explanation in the outcome and the timeline, read from the existing `/v1/runs/{id}/evidence` bundle (no contract change): the explanation from its `explanation` key, citations from its `grounded_answer` key and, in a run pinned `grounded_answers: on`, from its `proposal.created` events, with "grounded, not verified" wording (PR-19). The `explanation` key holds no citations; a citation stores only its value's digest (ADR 0034 §3, Task 4a.1). Amended by Task 4a.1 (review R1-1): the cited value comes from actions[].approved_facts; a `GROUNDED` run (`grounded.answer.v1`) shows none. Confirmed by the owner at gate G-A, 2026-10-20 ("4 ok"). An answer's own action records no approved facts (`kernel/grounding.py:406-421`), so a typed answer's value shows only when another action of the same run recorded that evidence; a verified write ends the run, so that action can only be a blocked or superseded write proposal, and in practice the value is rarely shown (review R2-1). The rationale on the approval card changes `ApprovalPresentation` (UI architecture §4.2, server-owned), so it ships only if ADR 0034's rationale section is accepted at G-A (Task 4e.6); otherwise it moves to a named follow-up |
| D16 | Phase size and cut lines | Must-have: 4a–4d, 4e.1–4e.4, 4e.7 and 4f. Two cut lines, in order: 4e.6 (rationale on the approval card) first, then 4e.5 (the citation and explanation UI, which comes from the Phase 3 handoff, not roadmap row 4). If the phase runs long, they move to a Phase 4′ with its own plan rather than being skipped. 4e.6 deferred by the owner at gate G-A, 2026-10-20 ("3 defer") |
| D17 | How ERP answer values qualify as typed | **(a), owner 2026-10-20.** The plugin manifest declares a host-side value format per answer path, beside `data_classes`: `CapabilityDescriptor.answer_value_formats`, keyed by the same RFC 6901 instance paths, each value from a closed set the kernel checks: `decimal`, `integer`, `date`, `date-time`, `enum:<v1>\|<v2>…`, `ref`. It is never in the model-facing schema, so the tool schemas and the `off` model-request goldens are unchanged. The kernel carries a value only when it passes its declared format; a `ref` value also has to equal a source ref the same run recorded (the round-3 reviewer's option (d), kept as a guard against fabricated refs). Free strings are never carried. Admission refuses an unknown format, a path the contract's schema does not have, a format whose schema type cannot hold it, a format on a path that no `data_classes` entry covers (on the path or an ancestor, as `ClassIndex.declared` reads it, so `/input/late_order_refs` covers `/input/late_order_refs/items`), and any format on a capability that is not an answer. The ERP domain pack declares the `ShortageAnswer` refs and decimals, the late-orders and overdue-invoices refs and dates, and the `offer.recommend` refs and decimal; explanation and summary text get no format (Task 4c.4). This is a plugin contract change, covered by ADR 0023. Not chosen: (b) adding `pattern` to the JSON schemas, which changes the tool schemas and the `off` goldens; (c) refs only, which met only "without re-asking" of the core plan exit. G-A, 2026-10-20: the four `ref` paths that can never match a recorded source ref today are a known limit ("6 ok"), and a recorded source ref counts only from a read whose `EvidenceRef.completeness` is `complete`, so a not-found read carries nothing ("7 yes") |

## Global Constraints

- **Branch** `phase4/conversation-chat` from `main` at `b52f979` (Phase 3 merged, PR #7).
  - Stage explicit paths. Every commit ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
  - `main` is protected (strict, five required checks): changes reach it only through a PR whose checks pass.
  - Merge, push and rebase only on the owner's instruction.
- **Harness phase `4`.**
  - Features live in `harness/state/4/features.json` (`F-4a-1` … `F-4f-2`, one per task). `F-4c-4` is the answer value formats task added in round 3; the first draft's 4c.4 (Postgres) was merged into 4c.3 by PL-5.
  - Each task has one contract (`uv run e-agent-harness new-task 4 <id> --feature <F-id> --gate <set> --paths ...`).
  - Run `check-scope` before each commit, `gate <set>` after the commit on a clean tree, and `close-check` before a task closes (ENG-WORK-1, ENG-EVID-1).
  - `harness/context.toml` `active_plan` points at this plan from the planning commit. Phase 3 switched it at 3a.2; here it switches now so that every Phase 4 contract pins this plan's digest.
  - UI tasks that write a brief or a mockup add `research/**` to their contract's paths; `research/**` is create-only, so they create new files and never edit an earlier study (ENG-BOUND-2).
- **Gate commands** (from `harness/context.toml`):
  - `full`: `uv sync --locked`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy`, `uv run lint-imports`, `uv run python scripts/export_openapi.py --check`, `uv run pytest -q`, `pnpm --dir ui gen:check`, `pnpm --dir ui check`, `uv run python scripts/check_core_only.py`.
  - `ui`: `pnpm --dir ui check`.
  - `pg`: `E_AGENT_TEST_STORE=postgres uv run pytest -q tests/unit/kernel tests/conformance tests/unit/adapters/postgres`, with `E_AGENT_TEST_PG_DSN` set to the `e_agent_test` database, never the live ledger's database (HP-13). Tasks 4d.4 and 4d.5 add `tests/unit/server/test_conversation_api.py` and `tests/unit/server/test_conversation_e2e.py` to this set in `harness/context.toml` (PL-5), and those tests read `E_AGENT_TEST_STORE` like the kernel tests.
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
- **Authorization (PR-27).** Every new route has a session dependency. Conversations are scoped by tenant and owner; a foreign conversation, or another requester's, looks absent (`NOT_FOUND`, PR-24) on every route and in the kernel facade. Task 4d.4 adds the `/v1/*` route enumeration test that PR-27's row lacks.
- **API changes regenerate types.** A task that adds or changes a route regenerates `ui/packages/client/openapi.json` (`uv run python scripts/export_openapi.py`) and `ui/packages/client/src/schema.ts` (`pnpm --dir ui gen`) in the same commit; `full` checks both.
- **Stores (ENG-STORE-1, PR-30).** Both stores change together under `tests/conformance`, in the same task (4c.3). The migration is forward-only.
- **Driver changes.** No driver or prompt change is planned. If one becomes necessary, run `uv run pytest -q tests/unit/server/test_recorded_model_replays.py tests/unit/adapters/pydantic_ai/test_prompt_golden.py` (PR-32).
- **Hygiene.** No `os.environ`, `os.getenv` or `asyncio.create_task` under `src/e_agent` (ENG-ARCH-6, ENG-ARCH-7). Import contracts, exemptions and allow-lists are never widened (PR-06). Kernel modules stay at or under `MAX_KERNEL_MODULE_LINES = 500` (`tests/unit/kernel/test_structure.py`), so the memory conversation store, routing and carrying are new modules (`kernel/memory_conversations.py`, `kernel/conversation.py`, `kernel/carried.py`). `kernel/memory_store.py` is at 499 lines: Phase 4 adds at most one net line to it. `kernel/registry.py` is at 497 lines: Task 4c.4 adds one import and one call, to 500 with the shared `document` line of review B1-3; the call keeps a short signature, for example `check_format_declarations(document, cap)`, so ruff does not wrap it (plan review PL4-1). Each new kernel module is added, in sorted order, to the `source_modules` of the import contract "Only the facade module imports e_agent.kernel.coordinator" (`pyproject.toml`); no contract is widened in any other way.
- **UI rules.** Every UI task goes through its `ag-*` stage. State the server owns is rendered, never derived (EA-1). Approved, committed, verified and grounded are separate labels (EA-3, PR-19). No provider identifiers in UI packages (PR-11, EA-6). Announcements are polite (EA-16).
- **Review.** Each task's close review runs in a fresh context (`eng-review`). Kernel, store and trust-anchor tasks (4c.3, which now holds the Postgres `FOR UPDATE` check of the first draft's 4c.4; 4c.4, the answer value format check; 4d.1, 4d.2, 4d.3; 4e.6 too, if the follow-up builds it) get a second reviewer: Codex when it has quota, else a second fresh-context Claude reviewer adjudicated by the advisor, as the owner ruled for Phase 3 on 2026-10-20.
- **Boundaries.**
  - Containers: only `e-agent-ledger` (test database `e_agent_test`) for `pg`, and `odoo19-learning` plus `e-agent-ledger` in the live check (Task 4f.2). Never `odoo-bench` (ENG-BOUND-1).
  - `archive/**` and existing `research/**` files are read-only.
  - No change under `addons/**` is planned (ENG-BOUND-2).
  - Never read or grep `profiles/*.local.json` or `~/.config/e-agent/**`; every grep passes `--exclude='*.local.json'`.

## Review Focus

These are failure modes the tests below do not fully exercise. Each item names the task that adds its test; the reviewer of that task checks it by reading.

1. **A message read as a decision** (PR-13, PR-15). "Yes, approve it" typed while a run waits for approval must not touch the action. Task 4d.1 adds `test_message_while_waiting_approval_never_touches_the_action` and `test_message_text_is_never_a_decision`. The reviewer checks that nothing reachable from the message route calls `approval_flow` or writes an `approval.decided` event.
2. **Instructions inside carried text** (T1, PR-34). A user's earlier message, or a record ref, that reads like an instruction must reach the model fenced as data. Task 4d.2 adds `test_carried_user_text_is_fenced` and `test_injected_carried_text_does_not_change_the_proposal`. The reviewer checks that the fence cannot be closed from inside the carried text.
3. **Carried facts used as current facts** (PR-15, PR-19, PR-24). An earlier run's values may be stale. Task 4d.2 adds `test_citation_to_carried_evidence_is_kernel_citation` and `test_validation_ignores_carried_values`. The reviewer checks that the citation lookup and the validator read only this run's evidence. A carried `ref` value is one the earlier run recorded; Task 4d.2 adds `test_ref_not_among_recorded_source_refs_is_dropped`.
4. **Personal data in the carried layer** (T23, PR-26). Task 4d.2 adds `test_carried_personal_value_masked_on_hosted_route`. The reviewer checks that every carried field, user text included, goes through the class walk, and that `conversation.compared` holds no value.
5. **A foreign conversation** (PR-24, PR-27). Tasks 4c.3, 4d.1 and 4d.4 test another owner and another tenant on both stores, in the facade and through the API; every case is `NOT_FOUND`, never `FORBIDDEN`, including a `reply_to` that names another user's run (Task 4d.1, `test_reply_to_foreign_run_is_not_found`). The reviewer checks that every store query filters by tenant and owner, not only by id.
6. **Two runs from one thread** (PR-17). Two concurrent messages, or one retried message, must start at most one run. Task 4c.3 tests the revision check, the one-active-run rule and a concurrent pair on both stores; Task 4d.1 tests the idempotency key and the answer retry. A retried start is looked up by its (tenant, actor, Idempotency-Key) record before any routing or conversation check, so it replays while the first run is still active. The reviewer checks the Postgres path under concurrency (the check runs inside the run-creating transaction).
7. **`shadow` that acts** (ADR 0027, PR-22, PR-23). `shadow` must add no model call, read or budget use, give the driver no carried item, and refuse nothing today's path accepts. A would-be refusal, a `ConcurrencyConflict` from the conversation check, or any conversation-step error falls back to today's unlinked run or plain input, records `conversation.shadow_failed` or `route: refuse`, and fails no request. Task 4d.3 asserts each case, server-side; Task 4e.3 asserts that the UI never re-posts after a conversation-route error. The reviewer checks every `DriverInput` and pack built for a run pinned `shadow`, and every exception path out of the shadow flow.
8. **The UI claiming more than the server says** (EA-1, EA-3, PR-19). A carried summary or a grounded answer must never read as verified. Task 4e.5 tests the labels. The reviewer checks that every status label comes from a server field.
9. **An answer for the wrong question** (PR-15, PR-17). A message typed for Q1 must not answer Q2, and a retried answer must not become a refusal or a second input. Task 4d.1 tests both; Task 4d.4 tests the stale `reply_to` through the API. The reviewer checks that the conversation revision is never used to bind an answer.

## Design refs

| Area | Section | Task |
|---|---|---|
| Conversational reply runs | ADR 0022 Decision 3 | 4a.1, 4b.2 |
| Event log is the source; rows are projections | target §5.1 item 2 | 4a.1, 4c.2, 4d.4 |
| `recent_turns` layer, budgets, drop order, fencing | target §7.2; ADR 0032 §1, §2, §4 | 4a.1, 4d.2 |
| Rendering | target §7.4; ADR 0032 §6 | 4d.2 |
| Data classes and class-per-route rule | target §13.3; ADR 0030; ADR 0032 §5 | 4c.2, 4d.2 |
| Feature toggles | ADR 0027; target §6.4.8 | 4c.1, 4d.3 |
| Citations, explanation, rationale | ADR 0033 §1, §4, §6 | 4d.2, 4e.5, 4e.6 (deferred at G-A) |
| `ApprovalPresentation` | UI architecture §4.2 | 4a.1, 4e.6 (deferred at G-A) |
| Task workspace and surfaces | UI architecture §10, §11; ADRs 0015, 0016 | 4a.1, 4e.4 |
| Member-readable projections | ADR 0017; UI architecture §11 | 4d.4 |
| Conversation model (not yet in the design) | new target §5.7, written in 4a.1 | 4a.1 |
| Declarations beside the schemas | ADR 0030 (`data_classes`, the pattern `answer_value_formats` follows); ADR 0023 (D17) | 4c.4, 4d.2 |

## ADRs

| ADR | Status | Decides | Needed by |
|---|---|---|---|
| 0023 Conversation model (new) | Accepted at G-A (2026-10-20) | D1–D9, D11, D12 and D17: the `Conversation` record, `RunRecord.conversation_id`, the `ConversationStore` port and the one-active-run rule, routing, carried context and its non-evidence rule, the toggle, pinning, fallback and startup rule, routes and their authorization, events and reason code; the plugin manifest's `answer_value_formats` (D17, a plugin contract change); amends ADR 0022 (D3) and refines ADR 0032 (`recent_turns` filled) | 4c, 4d |
| 0034 Conversation-first workspace and explanation UI (new) | Accepted at G-A (2026-10-20), except §5 (rationale), deferred | D10, D13, D15: EA-10, the thread view's surfaces, the citation and explanation display, the "grounded, not verified" wording, and the `ApprovalPresentation.rationale` section (shown second, never an approval input, never in the digest) | 4e |
| 0022 Conversational turns | Accepted; amended by 0023 (accepted at G-A) | reply runs | 4b.2, 4d.1 |
| 0027 Feature toggles | Accepted; refined by 0023 (accepted at G-A) | the toggle and reservation rules | 4c.1, 4d.3 |
| 0030 Data governance | Phase 3 parts accepted | record classes, class-per-route; retention stays Phase 7 | 4c.2, 4d.2 |
| 0032 ContextAssembler | Accepted; refined by 0023 (accepted at G-A) | the pack and its `recent_turns` layer | 4d.2, 4d.3 |
| 0033 Explanation and grounded answers | Accepted | run-scoped citations, the explanation projection | 4d.2, 4e.5, 4e.6 (deferred at G-A) |
| 0007, 0011, 0015, 0016, 0017, 0018, 0020 | Accepted | event stream, layered UI, workspace, surfaces, member projections, reason codes, connection-level write admission | throughout |

A Proposed ADR blocks the merge. 4c to 4e wait for G-A; 4b does not.

## Toggles and fallback

One new toggle, `features.conversations`, pinned per run at admission (D9). The chat defects in 4b have no toggle: they are fixes inside the approved design (D14). The route enumeration test in 4d.4 has no toggle: it is a check, not a runtime path.

| Mode | Behaviour |
|---|---|
| `off` | Today. The UI shows the per-run task view. `GET /v1/me/features` reports `off`. The conversation routes exist in every mode, so the OpenAPI document is the same, but in `off` they refuse with `NOT_FOUND` and the fixed message "conversations are off". No run is linked, no pin is written, and no new event appears. |
| `shadow` | The UI keeps the per-run task view, and its controller posts messages through `POST /v1/conversations/{id}/messages`, one conversation per "New task". `answer` and `start` routes are linked as in `on`, because today's client does the same. Nothing today's path accepts is refused. A message the router would refuse starts an unlinked run (`conversation_id = None`) as today, and the run records `conversation.compared` with `route: refuse`. A linked start or answer that fails in the conversation step (`ConcurrencyConflict`, a missing conversation, a store error on the conversation row) falls back, server-side, inside the same request and under the message's own idempotency record, to today's unlinked run or plain input, and records `conversation.shadow_failed`; the request does not fail. A start carries the message's `host_context` exactly as `POST /v1/runs` does. A stale `reply_to` gets `CONFLICT`, as `/v1/runs/{id}/inputs` does today. At admission of a run with earlier runs in its conversation, the kernel builds the carried items and the `recent_turns` layer they would render, records `conversation.compared` (carried run ids, item counts, the layer digest, the kernel's token estimate, masked and dropped counts), and gives the driver nothing. No model call, read or budget use is added. A shadow error records `conversation.shadow_failed` with a stage and a fixed message and changes nothing else.<br>Real consumers: `test_shadow_layer_digest_equals_on_layer_digest` over the fixture thread corpus (Task 4d.3), which asserts its case count; and the evidence bundle's `conversation` key. |
| `on` | The UI shows the thread view. Messages route as in `shadow`. At admission the kernel builds the carried items, stores them in the continuation, records `conversation.context_carried` (conversation id, carried run ids, carried digest; no text), and every pack of the run renders them in `recent_turns`, fenced and class-walked. Startup refuses `on` unless `context_assembler` is `on` (D7). |

| Toggle | Fallback code (`feature.fallback`, before the first reservation only, never ends a run) | Terminal code |
|---|---|---|
| `conversations` | `CONVERSATION_CONTEXT_FAILED`: building the carried items failed at admission; the run starts without them, as in `off` | none of its own: after admission the carried layer is part of the pack, so a failure ends with ADR 0032's `CONTEXT_UNAVAILABLE`, or goes to reconciliation when a reservation is unresolved |

UI fallback: the UI decides by the error code, never by the HTTP status alone. Every e-agent error carries the envelope `{code, message, correlation_id}` (`server/api.py:194-198`); a route that is not mounted (an older server) answers FastAPI's own 404, `{"detail": "Not Found"}`, with no `code`. The UI uses `POST /v1/runs` or `/v1/runs/{id}/inputs` only when `GET /v1/me/features` reports `conversations: off`, or when a conversation route answers 404 or 405 without the envelope (an older server's static mount answers a POST with 405, PL4-2); then it uses its own fresh `Idempotency-Key`. An enveloped error, `NOT_FOUND` included (a missing conversation, or "conversations are off" after a mode change), is shown to the user with the draft kept and never starts an unlinked run; after an enveloped `NOT_FOUND` the UI re-reads `/v1/me/features`. When `GET /v1/me/features` fails, the UI shows the per-run task view and keeps the composer draft. In `shadow` and `on`, a conversation-route error is never re-posted elsewhere, because the server already did today's thing (Task 4d.3).

**Observability** (ENG-TOGGLE-3): `/health/ready` and the evidence bundle report `features.conversations` with the other four toggles. The evidence bundle also reports the run's pinned `conversations` mode, its `conversation_id` and its carried run ids.

## Gate

| Task | Gate set |
|---|---|
| 4a.1, 4a.2 | `full` (docs only) |
| 4b.1–4b.5 | `ui`, plus `make e2e` through `eng-verify` |
| 4c.1, 4c.2, 4c.4 | `full` |
| 4c.3 | `full` and `pg` |
| 4d.1, 4d.2, 4d.3 | `full` and `pg` |
| 4d.4, 4d.5 | `full`, `pg` and `e2e` |
| 4e.1, 4e.2 | `full` (docs only), plus the mockup's own `verify.mjs` in 4e.2 |
| 4e.3, 4e.4, 4e.5 | `full` and `e2e` |
| 4e.6 (deferred at G-A) | `full`, `pg` and `e2e`, in the follow-up |
| 4e.7 | `full` (docs only), with the `pnpm --dir ui check` and `pnpm --dir ui conformance` output quoted in the review |
| 4f.1 | end-of-phase levels 1–3 |
| 4f.2 | level 4 (live) |

A contract carries one gate set (HP-6). Where a task names more, the contract's set is the first one named, and the others run through `eng-verify` and are named in the handoff.

**End-of-phase levels** (`eng-verify`, in order, on a clean tree): (1) the `full` gate; (2) the Postgres run (the `pg` gate); (3) `make e2e`; (4) the live check on `odoo19-learning`.

## Live check

Run in Task 4f.2 only on the owner's instruction, through the `live-sandbox` skill, with the identity flags on every sandbox mutation, and in this order. It uses temporary `profiles/*.local.json` copies, deleted after the check; the agent never reads them. The owner's 4f.2 instruction is the Phase 3 ruling's trigger: item 3 is the first qualified live write with `context_assembler: on`.

The domain-erp manifest changed in 4c.4; re-pin the domain-erp artifact (`live-sandbox` wheel re-pin) before the live check.

1. `/health/ready` and `GET /v1/me/features` report `conversations` in each mode.
2. Core plan Phase 0 exit, `conversations: off`, `context_assembler: off`: in the per-run view, "hi" → "hi" → "which products are short?". No `undefined` anywhere in the timeline, one reply label, and the new Context chip copy.
3. Single-run draft PO, `context_assembler: on`, `conversations: off`, after `reset` and `seed` of `e-agent-demo`: "draft a PO for the shortage". If the model proposes the PO, the owner approves it in the UI, never with `--approve` (that would be the agent's self-approval under the live profile). The write, its read-back and the acknowledgement turn rendered from the pack close the Phase 3 live-write gap. This isolates the pack from the conversation feature.
4. Thread, `conversations: on` and `context_assembler: on`, after a fresh `reset` and `seed`: "hi" → "which products are short?" → "draft a PO for it" (core plan exit).
   - Expected: two runs in one conversation. Run 1 is the greeting's reply run, answered by the question. Run 2 starts after run 1 ends.
   - Run 2's evidence bundle shows `conversation.context_carried` naming run 1. Its packs' `recent_turns` layer holds run 1's verified shortage answer (its `shortage` quantity and its `demand_ref`, D17), if run 1 ended with one; otherwise refs and user text only (D5). The `demand_ref` is carried only when run 1 read the demand itself with `procurement.demand.read.v1`; the open-demands read is located `open`, so a run that only listed demands carries the quantity without the ref (ADR 0023 §7).
   - Run 2 does not ask again which products are short; it may re-read.
   - If the model proposes the PO, the owner approves it in the UI, as in item 3.
5. While run 2 waits for approval, typing "approve it" is refused with the fixed hint, and the action is unchanged.
6. The sidebar shows one thread.
7. `conversations: shadow`, `context_assembler: off`, read-only thread: "hi" → "which products are short?" → "which offers cover it?". The per-run view is unchanged, no message is refused, and the second run records `conversation.compared` with no carried item in its model request. This item makes no write: the prompts ask for none, and if the model proposes one anyway the owner rejects it, so it never counts toward the cap.

"No PO proposed" in item 3 or item 4 is a partial result, recorded as model behaviour (ADR 0010), as in Phase 3; it does not block the merge.

The live check must not touch:
- `odoo-bench`, or any container outside `odoo19-learning-*` and `e-agent-ledger`;
- live business data;
- a hosted model route;
- any write beyond two draft POs (items 3 and 4 only; items 1, 2, 5, 6 and 7 make none) in the `e-agent-demo` namespace.

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
- records: the 4c.2 list (`Conversation`, `CarriedRef`, `CarriedAnswer`, `CarriedRun`, `ReplyTo`, `RouteKind`, `MessageRoute`, `ConversationPage`, `ConversationSummary`, `ConversationList`, `ThreadRun`, `ConversationSnapshot`, `MemberFeatures`);
- the reason code `CONVERSATION_CONTEXT_FAILED`;
- the manifest field `CapabilityDescriptor.answer_value_formats`, its closed format set and its admission refusals (D17);
- the events `conversation.context_carried`, `conversation.compared` and `conversation.shadow_failed`;
- the routes of Task 4d.4;
- for ADR 0034: the thread view's surfaces, the citation and explanation display rules, and `ApprovalPresentation.rationale`.

- [ ] For every answer contract (each one in `src/e_agent/plugins/erp/domain/e_agent_plugin.json`, the core `grounded.answer.v1`, and the notes test pack in `tests/unit/kernel/conftest.py`), list in ADR 0023 the `/input` paths that get a value format under D17 and the format of each, and name every free-text path that gets none (`explanation`, `summary`). Read the ERP manifest's shape before naming the field: `answer_value_formats` sits on each capability entry beside `data_classes`. For each `ref` path, record whether a read in the same task records that ref as its `EvidenceRef.locator` today, in the simulator (`plugins/erp/simulator/fake_erp.py`) and the Odoo executor (`plugins/erp/odoo/executor.py`). Known so far: `demand_ref` and `product_ref` match (the demand and stock reads use them as locators); `offer_ref`, `supplier_ref`, `late_order_refs` and `overdue_invoice_refs` do not (the offers read's locator is the product ref, and the open-orders and open-invoices reads use the `as_of` date), so the guard drops them. Record that, without widening the guard. Check `git tag` for a released `sdk_api` 1.2: none on 2026-10-20, so the field joins the unreleased 1.2 list; a release before 4c.4 means a bump to 1.3, named in the ADR.
- [ ] Write ADR 0023 from D1–D9, D11, D12 and D17, and the core plan Phase 1 option table. Read `kernel/coordinator.py`, `kernel/context.py`, `sdk/store.py` and `server/api.py` first, and cite current `file:line`. State the ADR 0022 amendment (D3) and the ADR 0032 refinement (`recent_turns` holds carried items; drop order unchanged).
- [ ] Write ADR 0034 from D10, D13 and D15: EA-10 with its research 16 source; the citation, explanation and "grounded, not verified" rules; a separate section for `ApprovalPresentation.rationale`, so the owner can accept or defer it on its own (D16).
- [ ] Add target §5.7 (a summary that cites ADR 0023, no restated rules) and the index rows.
- [ ] Run `uv run python scripts/repo_move.py check`; expected: no broken links. Run `uv run e-agent-harness refresh-task`.
- [ ] Commit `docs(adr): ADRs 0023 and 0034 for review`.

### Task 4a.2: owner acceptance (gate G-A)

**Files:** the ADRs above, `docs/adr/README.md`, this plan (status line and decisions).

**Interfaces:** consumes the ADRs of 4a.1; produces their accepted status, which 4c–4e cite.

- [ ] The owner accepts or amends ADRs 0023 and 0034, and confirms D1–D17. Record each answer in the decisions table and the ADR status lines, with the owner's words.
- [ ] If ADR 0034's rationale section is deferred, mark Task 4e.6 deferred in this plan and in `harness/state/4/features.json`.
- [ ] Run `uv run e-agent-harness validate-context`; expected: `ok: manifest valid for ...`.
- [ ] Commit `docs: Phase 4 ADRs 0023 and 0034 accepted (G-A)`.

## Part 4b: chat defects (no toggle, D14)

Each task uses `ag-ui-implement` for a change inside the approved design (core plan Phase 0). Task 4b.4 ends with one `ag-ux-review` over the four diffs and stops for the owner (gate G-0); Task 4b.5 resolves the findings.

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

### Task 4b.4: the sidebar says "Your turn" after a reply, and the 4b review (gate G-0)

`TaskNavigation.tsx` renders `resultStatusKey(h.state, h.reasonCode)`, and `TaskHistoryEntry` has no `replyPending`, so the sidebar says "Your answer is needed".

**Files:** `ui/packages/ui-core/src/controller.ts` (`TaskHistoryEntry.replyPending?: boolean`, set from `selectPendingReply`), `ui/packages/ui-core/src/presentation.ts`, `ui/packages/components/src/features/task-navigation/TaskNavigation.tsx`, `ui/packages/ui-core/test/controller.test.ts`, `ui/packages/ui-conformance/tests/composer.spec.ts`, `docs/reviews/2026-10-<dd>-chat-defects-ux-review.md`.

**Interfaces:** consumes `selectPendingReply` and `runStatusKey(state, events, replyPending)`; produces the review that 4b.5 answers.

- [ ] Failing tests: `controller.test.ts` "history entry records a pending reply", and "a stored entry without replyPending still loads"; `composer.spec.ts` "sidebar says Your turn after a reply".
- [ ] Run `pnpm --dir ui exec vitest run packages/ui-core/test/controller.test.ts`; expected: fails with `replyPending` undefined.
- [ ] Implement; run the same command and `pnpm --dir ui check`; expected: pass.
- [ ] Run `make e2e`; expected: exit 0, with its pass and skip counts quoted.
- [ ] Commit `fix(ui): sidebar Your turn after a reply (core plan 0.4)`.
- [ ] Run `ag-ux-review` in review mode over the diffs of 4b.1–4b.4 and the running UI. Write the review only; fix nothing (the review skill's stop gate).
- [ ] Commit `docs(reviews): chat defects UX review`.
- [ ] Stop. The owner reviews the four fixes and the review (gate G-0, the `ag-ui-implement` stop gate). Record the owner's words in the review file's header in 4b.5.

### Task 4b.5: chat defects review resolution

**Files:** the files the findings name, inside `ui/`; `docs/reviews/2026-10-<dd>-chat-defects-ux-review.md` (the owner's G-0 words in its header); `docs/reviews/2026-10-<dd>-chat-defects-ux-review-RESOLUTION.md`.

**Interfaces:** consumes the 4b.4 review and the owner's G-0 answer; must close before 4e.1 starts, so the gap audit in 4e.1 sees the fixed surface.

- [ ] Record the owner's G-0 words in the review file's header.
- [ ] For each finding, write its failing test first (Vitest in the package's `test/` folder, or a spec in `ui-conformance`), named after the finding id.
- [ ] Run `pnpm --dir ui exec vitest run <test file>`; expected: each new test fails on the reported defect.
- [ ] Fix; run `pnpm --dir ui check` and `make e2e`; expected: pass, with the real counts quoted.
- [ ] Answer every finding in the resolution file. No Blocker or High stays open.
- [ ] Commit `fix(ui): chat defects review resolution (G-0)`.

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
- `src/e_agent/contracts/conversation.py` (new):
  - `Conversation(tenant_id, conversation_id, owner_id, revision, created_at, updated_at)`;
  - `CarriedRef(contract_id, source_ref, revision, observed_at)`;
  - `CarriedAnswer(contract_id, arguments)`: the class-walked arguments of one `VERIFIED` answer action;
  - `CarriedRun(run_id, task_id, task_version, state, reason_code, user_messages, answers, refs)`;
  - `ReplyTo(run_id, run_revision)`: the waiting run and the revision the user saw with its question (D2);
  - `RouteKind` (`answer`, `start`, `refuse`) and `MessageRoute(kind, run_id, run_revision, hint)`;
  - `ConversationPage(items, next_after)`: the store's page;
  - `ConversationSummary(conversation_id, title, updated_at, latest_state, reply_pending)` and `ConversationList(items, next_after)`: the API list;
  - `ThreadRun(run_id, task, state, reason_code, revision, created_at)` and `ConversationSnapshot(conversation, runs)`: the API thread.
- `src/e_agent/contracts/features.py`: `MemberFeatures(conversations)`, the member projection (D10).
- `src/e_agent/contracts/run.py`: `RunRecord.conversation_id: str | None = None`.
- `src/e_agent/kernel/reconstruct.py`: `run_created_keys` adds `conversation_id` only when set.
- Tests: `tests/unit/contracts/test_conversation.py` (new), `tests/unit/kernel/test_off_projection.py`.

**Interfaces:** produces the records above, consumed by 4c.3–4e.

- [ ] Failing tests:
  - `test_conversation_record_holds_no_text`: the field set is ids, owner, revision and timestamps;
  - `test_carried_run_has_no_model_text_field`;
  - `test_carried_answer_has_only_contract_and_arguments` (the declared-paths rule is `carry`'s, Task 4d.2);
  - `test_message_route_answer_needs_run_and_revision`;
  - `test_member_features_has_only_conversations`;
  - `test_run_record_conversation_id_defaults_none`;
  - `test_run_created_has_no_conversation_key_when_unset`.
- [ ] Run `uv run pytest -q tests/unit/contracts/test_conversation.py`; expected: `ModuleNotFoundError: e_agent.contracts.conversation`.
- [ ] Implement.
- [ ] Run the same command, `tests/conformance/test_record_classes.py`, `tests/unit/kernel/test_off_projection.py` and the `off` baselines; expected: pass, the v3 goldens unchanged. Run `uv run python scripts/export_openapi.py --check`; expected: it changes, because `RunRecord` is in the API schema; regenerate `ui/packages/client/openapi.json` and `src/schema.ts` (`pnpm --dir ui gen`) in the same commit.
- [ ] Commit `feat(contracts): Conversation record and RunRecord.conversation_id (ADR 0023)`.

### Task 4c.3: the `ConversationStore` port on both stores, with migration `0007`

Both stores ship in this one task (ENG-STORE-1, PR-30). The first draft split this into 4c.3 (memory) and 4c.4 (Postgres); the plan review (PL-5) merged them.

**Line budget.** `src/e_agent/kernel/memory_store.py` has 499 lines, and `tests/unit/kernel/test_structure.py` holds every kernel module to `MAX_KERNEL_MODULE_LINES = 500`; it stays at or under 500, checked with `wc -l`. This task leaves `memory_store.py` unchanged apart from the FB-2 fix. That fix is one token at `memory_store.py:183` in `update_run` (`if driver_state` becomes `if driver_state is not None`), zero net lines. `wait_for_approval` (line 227) already keeps `{}`, so the Phase 3 handoff's FB-2 claim about it is stale; the test covers both paths. If the fix somehow cannot fit, the task moves the work-queue block (`enqueue_work` to `has_pending_work`, lines 397–495) into a new `kernel/memory_work.py` first, and names that move in the handoff. The memory conversation store is a subclass in the new module `kernel/memory_conversations.py`.

**Files:**
- `src/e_agent/sdk/store.py`: the `ConversationStore` protocol. `RunStore` is unchanged.
- `src/e_agent/kernel/memory_conversations.py` (new): `InMemoryConversationStore(InMemoryRunStore)`, which adds the conversation rows and the `ConversationStore` methods.
- `src/e_agent/kernel/memory_store.py`: the FB-2 fix only (above).
- `pyproject.toml`: `"e_agent.kernel.memory_conversations"` in the `source_modules` of the import contract "Only the facade module imports e_agent.kernel.coordinator", in sorted order (before `"e_agent.kernel.memory_store"`). No other contract changes (PR-06).
- `src/e_agent/server/bootstrap.py`: the memory store kind builds `InMemoryConversationStore`, which is both stores.
- `src/e_agent/adapters/postgres/migrations/0007_conversations.sql` (new): table `conversations (tenant_id, conversation_id, owner_id, revision, created_at, updated_at)` with primary key `(tenant_id, conversation_id)`; `runs.conversation_id` nullable, with a composite foreign key `(tenant_id, conversation_id)`; index `(tenant_id, conversation_id, created_at)`. Forward-only, no data rewrite. Ruling at implementation (ENG-PLAN-3): `runs` has no `created_at` column (0001), so the index is `runs (tenant_id, conversation_id, (record ->> 'created_at'))`, partial on a set `conversation_id`; the record's timestamp is fixed-width UTC (`_iso_utc`), so its text order is time order, and `list_conversation_runs` orders by the same expression. The migration also adds `conversations_by_owner (tenant_id, owner_id, created_at DESC, conversation_id COLLATE "C" DESC)` for `list_conversations`, `CHECK (revision >= 1)` (a new conversation starts at revision exactly 1; both stores refuse any other revision with `ValueError`), and `CHECK (conversation_id IS NOT DISTINCT FROM record ->> 'conversation_id')`, so the column can never disagree with the record. Fix round 1 (reviews A1-1 to A1-3, B1-2): one rule on both stores, enforced by the port before any SQL runs, with the FK and the CHECK kept as a backstop. Only `create_run_in_conversation` creates a linked run; `create_run` and `create_run_idempotent` refuse a run whose `conversation_id` is set (`ValueError(LINKED_RUN_REFUSED)`), and `update_run` and `wait_for_approval` refuse a record whose `conversation_id` differs from the stored run's (`ValueError(LINK_CHANGE_REFUSED)`). The memory overrides live in `kernel/memory_conversations.py`; `InMemoryRunStore` is unchanged, because the kernel suite uses it alone. A duplicate run id at admission is a `ConcurrencyConflict` on both stores (A1-7). `list_conversations` orders by `created_at` then id, newest first, so a revision bump never reorders a page; its `after` is the last id of the previous page, and a `limit` outside 1 to 100 raises `ValueError`.
- `src/e_agent/contracts/data_classes.py`: `RECORD_KINDS` gains `conversations` (audit skeleton, "a conversation's ids, owner and revision"). Moved from 4c.2: declared with the table, never ahead of it (4c.2 ruling).
- `src/e_agent/adapters/postgres/store.py`: implements `ConversationStore`; `create_run_in_conversation` runs the revision and active-run check in the same transaction as the run insert, with the conversation row locked `FOR UPDATE`.
- `.github/workflows/ci.yml`: in job `checks`, the step "kernel suite against the PostgreSQL ledger" runs `tests/unit/kernel tests/conformance tests/unit/adapters/postgres`, the `pg` gate's set (FB-1).
- Tests: `tests/conformance/test_conversation_store.py` (new), `tests/conformance/test_run_store.py`, `tests/unit/adapters/postgres/test_migrations.py`, `tests/conformance/test_record_classes.py` (`test_every_store_record_kind_declares_a_class` now lists `conversations`; moved from 4c.2 with the declaration).

**Interfaces:**
- `create_conversation(conversation) -> None`;
- `get_conversation(tenant_id, owner_id, conversation_id) -> Conversation`: `NotFound` for another owner or tenant;
- `list_conversations(tenant_id, owner_id, *, after: str | None, limit: int) -> ConversationPage`: newest first, `limit` at most 100;
- `list_conversation_runs(tenant_id, owner_id, conversation_id) -> tuple[RunRecord, ...]`: oldest first;
- `lookup_idempotent(tenant_id, actor_id, key) -> tuple[str, str] | None`: the (run id, request digest) that `create_run_idempotent` recorded for that key, or `None`; it reads the same record as `memory_store.py:129-132` and the Postgres idempotency table, and writes nothing;
- `create_run_in_conversation(run, events, state, actor_id, key, request_digest, conversation_revision) -> tuple[str, str]`: the arguments of `RunStore.create_run_idempotent` plus the revision. It requires `run.conversation_id`. It first looks up the (tenant, actor, key) record, as `memory_store.py:129-132` does today: a hit returns the recorded (run id, digest) at once, runs no conversation check and bumps nothing; the caller compares the digest. Only on a miss does it check that the conversation's revision equals `conversation_revision`, refuse when the conversation has a run in a non-terminal state, create the run as `create_run_idempotent` does, and bump the revision and `updated_at`. Both refusals raise `ConcurrencyConflict`. So a retried start replays while the first run is still `CREATED` or `RUNNING`.
- Memory lock order: `_conversation_lock`, then the parent's `_lock`, never the reverse. Under `_conversation_lock`: read `self._idempotency` (synchronous, no `await` in between, so it needs no `_lock`) → on a miss, the conversation checks → `await super().create_run_idempotent(...)`, which takes `_lock` and re-checks the record → bump. No parent method takes `_conversation_lock`, and the subclass never takes `_lock` itself (`asyncio.Lock` is not reentrant), so no cycle exists. The check is sound because only this method creates linked runs and terminal states are final.
- Postgres order, in one transaction: read the idempotency row; on a miss, `SELECT … FOR UPDATE` the conversation row, read the idempotency row again (a concurrent same-key request may have committed while this one waited), then the checks, the run insert with its idempotency row, and the bump.

- [ ] Failing tests, each parametrised over both stores, each printing its case count and failing on zero:
  - `test_create_and_get_conversation`;
  - `test_foreign_owner_conversation_looks_absent`;
  - `test_foreign_tenant_conversation_looks_absent`;
  - `test_list_conversations_is_paged_and_bounded`;
  - `test_run_creation_bumps_conversation_revision`;
  - `test_stale_conversation_revision_is_refused`;
  - `test_second_active_run_in_conversation_is_refused`;
  - `test_new_run_allowed_after_terminal_run`;
  - `test_idempotent_replay_starts_one_run`: the replay comes while the first run is still active, and returns it without a conversation check;
  - `test_concurrent_same_key_starts_one_run`: two requests with one key against one conversation; both return the same run;
  - `test_lookup_idempotent_reads_without_writing`;
  - `test_concurrent_messages_start_one_run`: two tasks against one conversation;
  - `test_empty_driver_state_round_trips` (FB-2, in `test_run_store.py`): both `update_run` and `wait_for_approval`, then restore;
  - `test_runs_conversation_id_column_matches_record` (Postgres, 4c.2 review R1-4): migration 0007's `runs.conversation_id` column is written from `RunRecord.conversation_id` at every insert site (`create_run`, `create_run_idempotent`, `create_run_in_conversation`) and never disagrees with the JSONB record;
  - `test_reconstruct_conversation_id_from_run_created` and `test_reconstruct_conversation_id_unknown_without_run_created` (in `tests/conformance/test_reconstruction.py`, 4c.2 review R1-2): a `run.created` payload carrying `conversation_id` rebuilds a known value; events without `run.created` give an unknown slot;
  - `test_migration_0007_applies_after_0006` (in `test_migrations.py`); the existing `test_migrations_apply_once_and_are_idempotent` and `test_modified_applied_migration_is_rejected` keep passing.
- [ ] Run `uv run pytest -q tests/conformance/test_conversation_store.py tests/conformance/test_run_store.py`; expected: fails with `ImportError` on `ConversationStore`.
- [ ] Implement both stores. Never hold a transaction across a model or ERP call (PR-17).
- [ ] Run the same command; then `E_AGENT_TEST_STORE=postgres uv run pytest -q tests/unit/adapters/postgres tests/conformance/test_conversation_store.py tests/conformance/test_run_store.py`; expected: pass on both stores. Run `wc -l src/e_agent/kernel/memory_store.py`; expected: at most 500. Run `uv run lint-imports`; expected: every contract kept.
- [ ] Run the `pg` gate; expected: pass.
- [ ] Commit `feat(store): ConversationStore on both stores, migration 0007; FB-1, FB-2 (ADR 0023)`.

### Task 4c.4: host-side answer value formats in the plugin manifest (D17)

Added in round 3 for the owner's D17 ruling. This is a plugin contract change, decided in ADR 0023 (accepted at G-A before this task starts). It follows the `data_classes` pattern of ADR 0030: a declaration beside the schemas, keyed by instance path, never sent to a model.

**Files:**
- `src/e_agent/contracts/value_formats.py` (new): `ValueFormat`, the closed set `decimal`, `integer`, `date`, `date-time`, `enum:<v1>|<v2>…` and `ref`; `parse_format(text) -> ValueFormat` (`ValueError` for anything else, an empty or duplicate enum value included); `check_format_declarations(document, cap)` for admission; `value_passes(fmt, value, *, nullable) -> bool` for carrying.
- `src/e_agent/contracts/data_classes.py` (scope amended in 4c.4, ruling R1): a public `schema_nodes(schema, tokens)` that returns the schema nodes at an instance path, an array element included, so the format check can see the types there. It shares a `_frontier` walk with `path_exists`, whose behaviour is unchanged.
- `src/e_agent/contracts/capability.py`: `CapabilityDescriptor.answer_value_formats: Mapping[str, str] = {}`, keys checked like `data_classes` keys (`check_class_key`), values by `parse_format`; the model validator refuses any format on a capability whose `effect` is not `answer`.
- `src/e_agent/kernel/registry.py`: one call to `check_format_declarations` beside `dc.check_declarations` (`registry.py:306-310`), in the same `try`, and one import: 497 → 500 (the shared `document` line of review B1-3) lines, at most 500. Keep the call on one line under ruff's 100-character limit with a short signature such as `(document, cap)`; `wc -l` confirms it (PL4-1).
- `src/e_agent/sdk/__init__.py`: the `SDK_API_VERSION` docstring lists `CapabilityDescriptor.answer_value_formats` with the other unreleased 1.2 fields; the version stays `"1.2"` (no tag or release of 1.2 exists on 2026-10-20). If 4a.1 found a release, the version becomes `"1.3"`, as ADR 0023 says.
- `src/e_agent/plugins/erp/domain/e_agent_plugin.json`, per answer contract:
  - `procurement.shortage.answer.v1`: `/input/demand_ref` and `/input/product_ref` `ref`; `/input/demand_quantity`, `/input/available`, `/input/inbound` and `/input/shortage` `decimal`;
  - `procurement.offer.recommend.v1`: `/input/demand_ref`, `/input/product_ref`, `/input/offer_ref` and `/input/supplier_ref` `ref`; `/input/unit_price` `decimal`; nothing on `/input/explanation`;
  - `sales.late-orders.answer.v1`: `/input/as_of` `date`; `/input/late_order_refs/items` `ref`; nothing on `/input/summary`;
  - `receivables.overdue-invoices.answer.v1`: `/input/as_of` `date`; `/input/overdue_invoice_refs/items` `ref`; nothing on `/input/summary` or `/input/totals` (a total without a checked currency is not carried).
- Tests: `tests/unit/contracts/test_value_formats.py` (new), `tests/unit/kernel/test_registry_value_formats.py` (new), `tests/unit/plugins/erp/domain/test_manifest_value_formats.py` (new).

**Interfaces:** produces `CapabilityDescriptor.answer_value_formats`, read through `Registry.descriptor(contract_id)`, and `value_passes`, both consumed by `carry` (4d.2). `value_passes` checks the value only: `decimal` is a JSON number or a canonical decimal string (as `DecimalStr` writes it), `integer` a JSON integer and not a boolean, `date` an ISO 8601 calendar date that parses, `date-time` an RFC 3339 time with an offset, `enum` one of the listed values, `ref` a non-empty string of at most 256 characters with no whitespace or control character. A `null` passes only when `nullable` is true; `carry` sets it from the schema property (a `null` member of its `anyOf` or `type`), and a passing `null` is carried as `null`. The recorded-source-ref check for `ref` is `carry`'s, because it needs the run's evidence (4d.2).

- [ ] Failing tests:
  - `test_every_format_in_the_closed_set_parses` and `test_unknown_format_is_refused`;
  - `test_value_passes_each_format`, with a passing and a failing value per format;
  - `test_format_on_a_non_answer_capability_is_refused`;
  - `test_registry_refuses_a_format_path_the_schema_lacks`;
  - `test_registry_refuses_a_format_the_schema_type_cannot_hold`: `integer` on a string property, `decimal` on a boolean;
  - `test_registry_refuses_a_format_without_a_data_class`: no entry on the path or an ancestor; an entry on an ancestor (`/input/late_order_refs` for `/input/late_order_refs/items`) admits (ADR 0023 §7);
  - `test_erp_answer_formats_are_declared`: the paths above, and no format on `explanation`, `summary` or `totals`;
  - `test_value_formats_never_reach_the_model`: the tool schemas built for every ERP answer contract are unchanged.
- [ ] Run `uv run pytest -q tests/unit/contracts/test_value_formats.py`; expected: `ModuleNotFoundError: e_agent.contracts.value_formats`.
- [ ] Implement.
- [ ] Run the three test files, `tests/unit/kernel/test_registry.py`, `tests/unit/kernel/test_registry_data_classes.py`, and both `off` model-request goldens (`tests/unit/adapters/pydantic_ai/golden/off_model_request.json`, `tests/unit/plugins/erp/simulator/golden/off_model_request_erp.json`); expected: pass, goldens byte-identical. Run `wc -l src/e_agent/kernel/registry.py`; expected: at most 500. Run `uv run python scripts/check_wheels.py`; expected: pass (the `domain-erp` artifact digest changes with the manifest; name it in the handoff).
- [ ] Commit `feat(contracts): host-side answer value formats in the plugin manifest (ADR 0023, D17)`.

## Part 4d: routing and carried context

### Task 4d.1: message routing in the kernel facade

**Files:**
- `src/e_agent/kernel/conversation.py` (new): `route_message(latest: RunRecord | None, reply_to: ReplyTo | None) -> MessageRoute`, pure (D2); `ConversationFlow`, which the coordinator delegates to.
- `src/e_agent/kernel/run_loop.py`: `input_replayed(actor, tenant_id, run_id, expected_revision, text) -> bool`, today's replay check moved out of the `/v1/runs/{id}/inputs` handler (`server/api.py`), unchanged in meaning. It refuses a non-requester with `FORBIDDEN` before it reads any event, exactly as `api.py:467-468` does today.
- `src/e_agent/server/api.py`: the `/inputs` handler calls `input_replayed`; its behaviour is unchanged.
- `src/e_agent/kernel/coordinator.py`: `create_conversation(principal) -> Conversation` and `post_message(principal, conversation_id, text, *, reply_to, host_context, idempotency_key, request_digest) -> tuple[MessageRoute, str]` (the route and the run id).
- `pyproject.toml`: `"e_agent.kernel.conversation"` in the same import contract's `source_modules`, in sorted order.
- `tests/unit/kernel/test_conversation_routing.py` (new); `tests/unit/server/test_api.py`.

**Interfaces:**
- An answer is bound to the question the user saw, never to the conversation revision. `reply_to` names the waiting run and the run revision the snapshot showed with its question. `answer` calls the existing `accept_input(run_id, text, reply_to.run_revision)`, so a message typed for question Q1 that arrives while Q2 is pending gets `CONFLICT` with the fixed hint "the question changed; read it again".
- Checks come in this order. (0) Before routing and before any conversation check, `post_message` looks up the (tenant, actor, Idempotency-Key) record with `lookup_idempotent`. A hit with the same request digest returns the original result, `(start, run_id)`, whatever state the run is in now; a hit with another digest is `CONFLICT` (PR-17). The digest covers the conversation id, the text, `reply_to` and `host_context`. Only a start writes such a record (the run store's; a shadow fallback's unlinked run writes it under the same key); an answer writes none, and its retry is caught by `input_replayed` in step (3). (1) The caller owns the conversation (tenant and owner), else `NOT_FOUND`. (2) When `reply_to` is set, `reply_to.run_id` is a run of this conversation, else `NOT_FOUND` in every mode. The one exception is `shadow` when the run's requester is the caller (an unlinked run a shadow fallback made): there it is a plain `accept_input`, as `/inputs` would take it, and records `conversation.shadow_failed {stage: "reply_to"}`. (3) Only then `input_replayed(principal, ...)`.
- A retried answer is idempotent. After those checks, when `reply_to` is set, `post_message` calls `input_replayed`. If the same text was already accepted at that revision, it returns the first result (`answer`, the same run id), even after the run has moved on.
- `start` (no `reply_to`, latest run terminal or none) calls the conversation variant of `admit_run`, which uses `create_run_in_conversation` with `conversation_id`, the conversation revision the flow just read, and the message's `host_context`, passed unchanged with the same `HostContext` type and validation as `CreateRun`. It uses the message's own `Idempotency-Key` and request digest. The shadow fallback (4d.3) runs inside the same request, under that same idempotency record.
- `refuse` raises `KernelError(CONFLICT, <fixed hint>)` in `on`. In `shadow` nothing is refused (Task 4d.3).
- Another requester's conversation is `NOT_FOUND` everywhere: posting, reading and listing (PR-24, no existence leak).

- [ ] Failing tests:
  - `test_waiting_input_message_answers_the_run`;
  - `test_answer_for_an_earlier_question_conflicts`: the run asked Q1 at revision n and then Q2 at revision n+2; a message with `reply_to` revision n gets `CONFLICT` and Q2 stays pending;
  - `test_message_without_reply_to_while_waiting_conflicts`;
  - `test_retried_answer_is_accepted_once`: the same text and `reply_to` twice give the same route and run, with one `input.received`, also after the run left `WAITING_INPUT`;
  - `test_inputs_route_replay_unchanged` (in `test_api.py`): `/v1/runs/{id}/inputs` still accepts a replay;
  - `test_terminal_run_message_starts_a_new_run`;
  - `test_empty_conversation_message_starts_a_run`;
  - `test_running_run_message_is_refused`;
  - `test_message_while_waiting_approval_never_touches_the_action` (Review Focus 1): the action's revision, the approval rows and the event list are unchanged;
  - `test_message_text_is_never_a_decision`: "approve", "yes" and "reject" each give the same route as any other text;
  - `test_retried_message_starts_one_run`: the same key and body twice, the second while run 1 is still `RUNNING`; the second returns `(start, run 1)`, with no `CONFLICT` and no second run;
  - `test_reused_key_with_other_text_conflicts`;
  - `test_other_requester_sees_not_found`;
  - `test_reply_to_foreign_run_is_not_found`: `reply_to` naming another user's run, or the caller's run in another conversation, is `NOT_FOUND`, and no replay check runs;
  - `test_input_replayed_refuses_a_non_requester`: the kernel replay check raises `FORBIDDEN` for an actor who is not the run's requester, before it reads events;
  - `test_start_passes_host_context_to_the_run`;
  - `test_new_run_cannot_reuse_an_earlier_approval`: run 2 proposes the same action as run 1; it gets a new digest and a new pending approval.
- [ ] Run `uv run pytest -q tests/unit/kernel/test_conversation_routing.py`; expected: `ModuleNotFoundError: e_agent.kernel.conversation`.
- [ ] Implement. `route_message` reads no clock and no store. `run_loop.py` stays at or under 500 lines.
- [ ] Run the same command on both stores, and `uv run pytest -q tests/unit/server/test_api.py`; expected: pass.
- [ ] Commit `feat(kernel): conversation message routing bound to the question the user saw (ADR 0023)`.

### Task 4d.2: carried context at admission, rendered in `recent_turns`

**Files:**
- `src/e_agent/kernel/carried.py` (new): `carry(runs, events_by_run, actions_by_run, evidence_by_run, declarations) -> tuple[CarriedRun, ...]`, pure (D5). `evidence_by_run` maps each run to its `{evidence_id: EvidenceRef}`, taken from the observations of its stored continuation (`load_continuation`); `declarations` maps an answer contract to its `data_classes` and `answer_value_formats` (`Registry.descriptor`); `render_carried(carried, rules, index) -> tuple[str, tuple[Dropped, ...]]`.
- `src/e_agent/kernel/context.py`: `assemble(..., carried: Sequence[CarriedRun] = ())` renders the `recent_turns` layer, fenced; carried items drop first after knowledge (ADR 0032 §2).
- `src/e_agent/kernel/continuation.py`: `_Continuation.carried: tuple[CarriedRun, ...] = ()`, left out of the stored continuation when empty (as at `continuation.py:169-178`), never merged into `observations` or `reads` (ADR 0023 §6).
- `src/e_agent/kernel/context_on.py`: passes the run's carried items from `cont.carried`.
- `src/e_agent/kernel/coordinator.py`: at admission of a run pinned `on`, builds the carried items, stores them in `cont.carried`, and records `conversation.context_carried`; on failure, `feature.fallback` with `CONVERSATION_CONTEXT_FAILED`.
- `src/e_agent/contracts/events.py`: `conversation.context_carried`.
- `pyproject.toml`: `"e_agent.kernel.carried"` in the same import contract's `source_modules`, in sorted order.
- `tests/unit/kernel/test_carried_context.py` (new); `tests/unit/kernel/test_context.py`.

**Interfaces:** consumes `RunModes.conversations`, the runs' action records (answer actions in state `VERIFIED` and their normalised arguments), the `input.received` events, the `read.recorded` events, the earlier runs' stored continuations (`load_continuation`, for their observations' `EvidenceRef`s), `Registry.descriptor` (`data_classes` and `answer_value_formats`), `Registry.schema_document` (nullability) and `value_passes` (4c.4). Produces the carried layer, which 4d.3 compares. An answer argument path is carried only when the answer contract declares a value format for it (Task 4c.4) and a `data_classes` entry, and its value passes `value_passes` (4c.4); a `ref` value must also equal the `locator` of an `EvidenceRef` that one of the same run's `read.recorded` events names. Any other path or value is dropped, never carried as `personal`. The record refs come from the same evidence map. A `read.recorded` event whose `evidence_id` names no observation in the stored continuation (a verifier's read, or evidence a staleness re-read replaced) gives no `CarriedRef` and no source ref, and is not an error (ADR 0023 §6). `CarriedRef.source_ref` holds `EvidenceRef.locator`. The carried items live only in `cont.carried`: never in `cont.observations` or `cont.reads`, so they never become an `ApprovedFact`, the approval presentation's baseline or a staleness re-read target (D6).

- [ ] Failing tests:
  - `test_carry_is_deterministic`;
  - `test_carried_items_are_not_approved_facts`: with carried items in `cont.carried`, a write proposal's `approved_facts` hold only this run's observations, the approval presentation's baseline holds no carried item, and the staleness check re-reads only `cont.reads`;
  - `test_carry_holds_no_model_text`: no `message.final`, reply, question or rationale text, and no raw observation, over a corpus that has all five;
  - `test_carry_takes_arguments_only_from_verified_answer_actions`: a `GROUNDED`, failed or unverified run carries refs and user messages only;
  - `test_undeclared_answer_path_is_dropped`;
  - `test_carry_drops_free_text_answer_fields`: over `VERIFIED` `procurement.offer.recommend.v1` and `sales.late-orders.answer.v1` answers, the `explanation` and `summary` text is absent from the carried layer on a local route too, and `as_of` is present;
  - `test_carry_drops_paths_without_a_format`: a path with a `data_classes` entry but no value format is not carried, even when its class is `internal`;
  - `test_value_failing_its_format_is_dropped`: `"12 units"` under `decimal`, `"2026-13-40"` under `date`;
  - `test_ref_not_among_recorded_source_refs_is_dropped`: a `VERIFIED` `ShortageAnswer` whose `demand_ref` matches no `locator` the run recorded carries no `demand_ref`, while its `shortage` quantity is still carried;
  - `test_ref_from_incomplete_read_is_not_carried`: a read whose `EvidenceRef.completeness` is `unknown` (Odoo's not-found demand read) gives no `CarriedRef` and no recorded source ref, so a `demand_ref` equal to its locator is dropped (G-A answer 7);
  - `test_carried_refs_come_from_recorded_evidence`: each `CarriedRef` is the `EvidenceRef` that a `read.recorded` event names, read from the finished run's continuation on both stores; a verifier read's `read.recorded` gives none;
  - `test_carry_holds_the_shortage_quantity_and_demand_ref`;
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

### Task 4d.3: `conversations: shadow`, its comparison and its fallback

`shadow` never refuses what today's path accepts (ADR 0027, PR-22, PR-23).

**Files:** `src/e_agent/kernel/carried.py` (shadow entry point), `src/e_agent/kernel/conversation.py` (the shadow fallback), `src/e_agent/kernel/coordinator.py`, `src/e_agent/contracts/events.py` (`conversation.compared`, `conversation.shadow_failed`), `tests/unit/kernel/test_conversation_shadow.py` (new), `tests/unit/kernel/fixtures/conversation_threads.json` (new: the fixture thread corpus: hi → hi, hi → question, question → PO, a message during approval, a thread over five runs).

**Interfaces:**
- Consumes `carry` and `render_carried`; produces `conversation.compared {conversation_id, route, carried_run_ids, items, layer_digest, layer_tokens, masked, dropped}`. For `route: refuse` the carried keys are empty or zero and `layer_digest` and `layer_tokens` are left out, because `on` would have started no run (ADR 0023 §11).
- In `shadow`, a message the router would refuse starts an unlinked run (`conversation_id = None`), as today, and records `route: refuse`.
- In `shadow`, when a linked start or answer fails in the conversation step, the flow does today's thing instead and fails no request. "Fails in the conversation step" means `ConcurrencyConflict` from the revision or active-run check, a missing conversation, or a store error on the conversation row. "Today's thing" means:
  - a start becomes an unlinked run, as `POST /v1/runs` would make it, with the message's `host_context`, inside the same request and under the message's own idempotency record;
  - an answer becomes a plain `accept_input`, as `/v1/runs/{id}/inputs` would do it.

  The resulting run records `conversation.shadow_failed {stage, code}`, with the kernel's fixed message for the stage. `stage` is one of `start`, `answer`, `reply_to` and `carry`; `code` is the kernel error code of the failure (ADR 0023 §11).
- The fallback is server-side only. The UI never re-posts after a conversation-step error (Task 4e.3).

- [ ] Failing tests:
  - the consumer `test_shadow_layer_digest_equals_on_layer_digest`: over the corpus, the layer `shadow` records equals the `recent_turns` layer of the `on` pack; prints the case count and fails on zero;
  - `test_shadow_gives_the_driver_no_carried_item` (Review Focus 7);
  - `test_shadow_adds_no_model_call_read_or_budget`;
  - `test_shadow_failure_changes_nothing`;
  - `test_shadow_would_refuse_starts_an_unlinked_run_and_records_it`: a message while the latest run waits for approval starts a run with `conversation_id = None`, as today, and records `route: refuse`;
  - `test_shadow_stale_revision_falls_back_to_an_unlinked_run`;
  - `test_shadow_concurrent_pair_starts_two_runs_as_today`: one linked, one unlinked with `conversation.shadow_failed`; neither request fails;
  - `test_shadow_conversation_error_falls_back_to_plain_input`;
  - `test_shadow_fallback_reuses_the_idempotency_key`: a retry of the same message after the fallback returns the same run;
  - `test_shadow_start_carries_host_context_as_create_run`: a shadow start, linked or fallen back, records the same resolved hints in `run.created` as `POST /v1/runs` with the same `host_context`;
  - `test_shadow_answer_to_own_unlinked_run_is_plain_input`;
  - `test_compared_event_holds_no_value_or_text`.
- [ ] Run `uv run pytest -q tests/unit/kernel/test_conversation_shadow.py`; expected: fails on the unknown event type `conversation.compared`.
- [ ] Implement.
- [ ] Run the same command on both stores; expected: pass, with the case count printed.
- [ ] Commit `feat(kernel): conversations shadow comparison and fallback (ADR 0023, ADR 0027)`.

### Task 4d.4: the API routes, member features and the route authorization test

**Files:**
- `src/e_agent/server/conversations.py` (new router, included by `api.py`):
  - `POST /v1/conversations` → `{conversation_id}`;
  - `GET /v1/conversations?after=&limit=` → `ConversationList`;
  - `GET /v1/conversations/{id}` → `ConversationSnapshot`, each `ThreadRun` with its `revision`, so the UI can send `reply_to`;
  - `POST /v1/conversations/{id}/messages` with the `Idempotency-Key` header and body `{text, reply_to: ReplyTo | null, host_context: HostContext | null}` → `{route, run_id}`. `host_context` reuses `CreateRun`'s type and validation (`server/api.py:76-78`).
- `src/e_agent/server/api.py`: `GET /v1/me/features` → `MemberFeatures`; the evidence bundle's `conversation` key (id, pinned mode, carried run ids, `conversation.compared` counts).
- `ui/packages/client/openapi.json` and `ui/packages/client/src/schema.ts` (regenerated).
- `docs/design/principles.md`: PR-27's check, and the routes outside its scope (below).
- `harness/context.toml`: the `pg` gate set gains `tests/unit/server/test_conversation_api.py` (PL-5). Run `uv run e-agent-harness refresh-task` after the change.
- `.github/workflows/ci.yml`: in job `checks`, the step "kernel suite against the PostgreSQL ledger" gains the same file, so CI's Postgres run equals the `pg` gate (PL2-6).
- Tests: `tests/unit/server/test_conversation_api.py` (new; its store fixture reads `E_AGENT_TEST_STORE` as `tests/unit/kernel/conftest.py` does, so it runs on both stores), `tests/unit/server/test_route_authorization.py` (new), `tests/unit/server/test_api.py`.

**Interfaces:** consumes `ConversationFlow`; produces the routes Task 4e.3 calls. Every new route has `Depends(session)`. In `off`, the conversation routes refuse with `NOT_FOUND` "conversations are off"; `/v1/me/features` answers in every mode.

**Route test scope (PL-9).** `test_every_v1_route_has_an_authorization_dependency` checks every `APIRoute` whose path starts with `/v1/`. Its allow-list holds exactly `POST /v1/local/session`, which creates the session, and the test asserts the allow-list has one entry, so it cannot be widened quietly (PR-06). Out of its scope, listed in PR-27's row with their current state, and left to Phase 7:
- `GET /health/live` and `GET /health/ready`: no session; operator probes;
- FastAPI's defaults `/openapi.json`, `/docs`, `/docs/oauth2-redirect` and `/redoc`: served without a session today (`FastAPI(...)` keeps the default `docs_url`), in local mode, which binds loopback only;
- the static mount `/` (UI assets, `server/api.py`): no session.

- [ ] Failing tests:
  - `test_conversation_routes_refuse_when_off`;
  - `test_create_list_get_and_post_message`;
  - `test_foreign_conversation_is_not_found` (Review Focus 5), for another owner and another tenant, on every conversation route;
  - `test_post_message_requires_idempotency_key`;
  - `test_answer_with_stale_reply_to_conflicts`;
  - `test_message_host_context_is_validated_like_create_run`;
  - `test_refusal_carries_the_fixed_hint`;
  - `test_conversation_errors_use_the_error_envelope`: the `off` refusal and a missing conversation both answer `NOT_FOUND` with `{code, message, correlation_id}`, which the UI tells apart from a not-mounted 404 (Task 4e.3);
  - `test_list_is_paged`;
  - `test_member_features_reports_the_mode`;
  - `test_evidence_bundle_reports_conversation`;
  - `test_every_v1_route_has_an_authorization_dependency`: prints the count and fails on zero (PR-27).
- [ ] Run `uv run pytest -q tests/unit/server/test_conversation_api.py tests/unit/server/test_route_authorization.py`; expected: `ModuleNotFoundError: e_agent.server.conversations`.
- [ ] Implement; HTTP handlers delegate to the kernel facade and hold no routing logic (PR-03).
- [ ] Run `uv run python scripts/export_openapi.py` and `pnpm --dir ui gen`; then the test command, `export_openapi.py --check` and `pnpm --dir ui gen:check`; expected: pass. Run the same test command with `E_AGENT_TEST_STORE=postgres`; expected: pass. Add the check to PR-27's row in principles.
- [ ] Change the `pg` gate set in `harness/context.toml`; run `uv run e-agent-harness validate-context` (expected: ok) and the `pg` gate (expected: pass, and the output names `test_conversation_api.py`).
- [ ] Commit `feat(server): conversation routes and member features, each with a session dependency (ADR 0023)`.

### Task 4d.5: a fixture thread end to end

**Files:** `tests/unit/server/test_conversation_e2e.py` (new; both-store fixture as in 4d.4); `harness/context.toml` (the `pg` gate set gains this file; then `refresh-task`); `.github/workflows/ci.yml` (job `checks`, step "kernel suite against the PostgreSQL ledger", gains the same file); `src/e_agent/plugins/erp/domain/testing/scripted_driver.py`, only if the scripted driver needs a branch for a carried shortage. A change there changes the `domain-erp` artifact digest; name it in the handoff.

**Interfaces:** consumes the routes of 4d.4 with the ERP fixture profile and `conversations` and `context_assembler` set `on` in a test profile.

- [ ] Failing tests:
  - `test_two_run_thread_carries_first_run_findings`: "hi" → "which products are short?" → "draft a PO for it". Expected:
    - two runs;
    - run 2's carried layer holds run 1's `VERIFIED` `ShortageAnswer` (`procurement.shortage.answer.v1`): its `shortage` quantity equals run 1's, and its `demand_ref` is run 1's demand (D17 (a); PL-4 restored);
    - run 2 never re-asks the user which products are short;
    - run 2 reads before it proposes;
    - the approval is decided through the approvals route only;
  - `test_thread_in_shadow_matches_per_run_behaviour`: the same thread in `shadow`, plus a message sent while run 2 waits for approval, gives the same run outcomes as the per-run tasks, plus `conversation.compared`; the approval-time message starts an unlinked run and changes nothing in run 2.
- [ ] Run `uv run pytest -q tests/unit/server/test_conversation_e2e.py`; expected: fails (the scripted thread is not wired).
- [ ] Implement only test wiring and, if needed, the scripted branch.
- [ ] Change the `pg` gate set; run `uv run e-agent-harness validate-context` (expected: ok). Run the same test command with `E_AGENT_TEST_STORE=postgres`, the `pg` gate and `make e2e`; expected: pass.
- [ ] Commit `test(server): fixture conversation thread end to end`.

## Part 4e: UI through the `ag-*` stages

Every task here reads `ag-ux-foundations` first and cites AG and EA criteria by ID. A stage never starts before the previous gate is recorded.

### Task 4e.1: design brief (gate G-B)

**Files:** `research/<NN>-conversation-thread-brief.md` (new; NN is the next free research number: 20 on 2026-10-20, re-checked against `research/README.md` and every worktree in `git worktree list` before writing).

**Interfaces:** consumes ADRs 0023 and 0034 and the current UI; produces the approved brief that 4e.2 builds from.

- [ ] Check that G-0 is recorded and 4b.5 is closed. Run `ag-ux-review` in gap-audit mode over the current chat surface after 4b, to `docs/reviews/2026-10-<dd>-chat-surface-gap-audit.md`.
- [ ] Write the brief with `ag-ux-brief`:
  - roles and the normative states: thread empty; reply pending; clarification; running; waiting approval with a refused message; verified; grounded; failed; per-run fallback; legacy runs;
  - the AG criteria and EA-1, EA-3, EA-5, EA-6, EA-9, EA-10 and EA-16;
  - 2–3 directions; how they will be judged;
  - the D15 surfaces (citations and explanation; the rationale on the card is deferred at G-A, so the card is unchanged);
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
  - "goes to /v1/runs or /inputs only when /v1/me/features reports off, or a conversation route answers 404 or 405 without the error envelope (not mounted), with a fresh Idempotency-Key";
  - "in on, a missing-conversation NOT_FOUND with the error envelope is shown as an error, keeps the draft, re-reads /v1/me/features and never calls /v1/runs";
  - "a shadow conversation-route error is shown with the draft kept; the UI does not re-post";
  - "a start sends the host context in the message body";
  - "an answer carries reply_to with the run revision shown with its question";
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

### Task 4e.5: citations and the explanation, "grounded, not verified" (second cut line, D16)

**Files:** `ui/packages/ui-core/src/selectors/evidence.ts` (the existing `approved_facts` reader, `:96-97`), `ui/packages/ui-core/src/store.ts` (`selectExplanation` and the citation selector, from the evidence bundle's `explanation` and `grounded_answer` keys, the `citations` of its `proposal.created` events, and `actions[].approved_facts` for cited values), `ui/packages/components/src/features/outcome/` and `ui/packages/components/src/features/timeline/` (citation and explanation display), `ui/packages/ui-core/src/i18n.ts`, `ui/packages/components/test/citations.test.tsx` (new), `ui/packages/ui-conformance/tests/explanation.spec.ts` (new), `ui/packages/ui-conformance/src/mock-api.ts`.

**Interfaces:** consumes `/v1/runs/{id}/evidence`: the `explanation` key (sources, validation, proposals with rationale refs, approvals, receipts, outcomes and their labels), the `grounded_answer` key, and, in a run whose `modes.grounded_answers` is `on`, the `citations` of its `proposal.created` events, each in the at-rest form (evidence id, pointer and value digest, or digests only). A citation shows its record (evidence id, with the source's contract and revision from `explanation.sources`) and its field (the pointer). The value beside a typed answer's citation is read from that run's `actions[].approved_facts`, from the fact whose `evidence.evidence_id` is the citation's, at its pointer, never from model text. Limits (ADR 0034 §3, review R1-1): an answer's own action records no approved facts, so the value shows only when another action of the run recorded that evidence; a `GROUNDED` run has no action and shows no value. Where no value is recorded the UI says so, never an empty value (EA-8). The UI already fetches the whole bundle and reads `actions[].approved_facts` (`ui/packages/ui-core/src/selectors/evidence.ts:96-97`). No contract change.

- [ ] Failing tests:
  - `citations.test.tsx` "a citation shows its record and field from the server";
  - "a grounded run says grounded, not verified" (EN and VI);
  - "free text outside citations is labelled unverified";
  - "the explanation lists facts before any rationale";
  - "an unresolved citation is never shown as a fact";
  - "a cited value comes from the run's approved facts, and an answer-only run shows value not recorded";
  - `explanation.spec.ts` "explanation opens from the outcome" (Review Focus 8).
- [ ] Run `pnpm --dir ui exec vitest run packages/components/test/citations.test.tsx`; expected: fails with the missing component.
- [ ] Implement.
- [ ] Run the same command, `pnpm --dir ui check` and `make e2e`; expected: pass.
- [ ] Commit `feat(ui): citations and explanation, grounded not verified (ADR 0033, ADR 0034)`.

### Task 4e.6: rationale on the approval card (cut line, D16; only if ADR 0034's rationale section is accepted)

**Deferred** by the owner at gate G-A, 2026-10-20 ("3 defer"): ADR 0034 §5 is deferred, so this task is not built in Phase 4 and moves to a named follow-up with its own plan. The approval card is unchanged in Phase 4. The text below is kept for that follow-up.

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

**Interfaces:** consumes the diffs of 4e.3–4e.5 (4e.6 is deferred at G-A) and the running UI.

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
  - that 4e.6 was deferred at G-A (ADR 0034 §5) and moved to a named follow-up, and whether 4e.5 shipped or moved to Phase 4′.
- [ ] Commit `docs: Phase 4 handoff and roadmap status`.

### Task 4f.2: live check

**Files:** `docs/handoffs/<date>-phase4-conversation-chat.md` (its "Level 4: live check" section); `harness/state/evidence/live/4f.2-*` (redacted run evidence and readiness output); `harness/state/4/features.json` (`F-4f-2`).

**Interfaces:** consumes the Live check section above, in its order. The owner's instruction to run 4f.2 is also the trigger the Phase 3 ruling named: step 3 is the first qualified live write with `context_assembler: on`.

- [ ] Only on the owner's instruction, through `live-sandbox`. Run `uv run e-agent-harness live-check`. Expected: the live gate passes, `odoo_sandbox.py info` reports the marker `odoo19-learning`, and the evidence is written under `harness/state/evidence/live/`.
- [ ] Run the Live check items 1–7 in order. Save each run's evidence bundle, redacted, as `harness/state/evidence/live/4f.2-<item>.json`. Nothing in this task reads the secret store or a key value.
- [ ] Run the CI secret scanner over the evidence: `gitleaks dir --redact --no-banner --no-color -c .gitleaks.toml harness/state/evidence/live/`. This is the `dir` form of the `gitleaks git` command in the "secret scan and dependency audit" job of `.github/workflows/ci.yml`. Use version 8.28.0, as CI pins it, if installed; otherwise use the local version and name it in the handoff. Expected: "no leaks found", zero findings.
- [ ] Run the key-shape scan: `grep -rEn -i --exclude='*.local.json' '\b[0-9a-f]{40}\b|bearer [A-Za-z0-9._-]{20,}|"(api_key|password|authorization)"' harness/state/evidence/live/4f.2-*`. Expected: no matches. grep exits 1 here, and exit 1 is the pass. The `\b…{40}\b` bound keeps 64-hex digests from matching. An optional comparison against the real key value is the owner's own step, outside this plan.
- [ ] Record the results in the handoff, labelled live and separate from fixture results. A missing PO in item 3 or item 4 is recorded as a partial result (model behaviour, ADR 0010); it does not block the merge.
- [ ] Commit `docs: Phase 4 live check results`.

## Self-review

- **Spec coverage.**
  - Roadmap row 4:
    - conversation model (ADR 0023, thread of runs with carried context) → 4a.1, 4c.2, 4c.3, 4d.1–4d.5;
    - chat defects: `status.undefined` → 4b.1; label noise → 4b.2; Context chip copy → 4b.3; sidebar → 4b.4; review resolution → 4b.5;
    - UI through `ag-*` with owner gates → 4b.4 (G-0), 4e.1 (G-B), 4e.2 (G-C), 4e.7 (G-D);
    - toggle `features.conversations` with fallback to the per-run task view → 4c.1, 4d.3, 4e.3.
  - Core plan Phase 0 exit (live "hi → hi → question" with no `undefined`, one label, the chip copy) → 4f.2 item 2; fixture specs → 4b.1–4b.4.
  - Core plan Phase 1 interfaces:
    - `Conversation` → 4c.2. `ConversationTurn` is not a stored record: the thread is a projection (D4);
    - `RunRecord.conversation_id` → 4c.2;
    - `ConversationStore` on both stores → 4c.3, with migration `0007`, not the stale `0005`;
    - routes → 4d.4;
    - the conversation SSE stream is replaced by the run stream plus snapshots (D12).
  - Core plan Phase 1 tasks:
    - task 4 (carried context) uses the Phase 3 ContextAssembler, not a precursor → 4d.2;
    - task 3's run-less turn is replaced by D3.
  - Core plan exit evidence ("the second run uses the first run's findings without re-asking"), met in full under D17 (a): run 2's carried layer holds run 1's verified shortage quantity and demand ref → 4c.4 (formats), 4d.2 (carry), 4d.5 (fixture) and 4f.2 item 4 (live; a partial result if the model ends run 1 without a verified answer); the sidebar shows one thread → 4e.4; conformance on both stores → 4c.3, with the server tests on both stores through the `pg` gate → 4d.4, 4d.5.
  - Phase 3 handoff items: D10 → 4e.5, and 4e.6 (deferred at G-A to a named follow-up); the live-write gap → 4f.2 item 3; FB-1 and FB-2 → 4c.3; item 14 (grounded wording review) → 4e.1, 4e.7.
  - EA-10 → 4a.1 (ADR 0034), 4e.4.
  - PR-27's missing check → 4d.4, scoped to `/v1/*` with the out-of-scope routes listed.
  - Plan review PL-1 to PL-14 (`harness/state/4/reviews/4-plan.json`) and re-review PL2-1 to PL2-8 (`harness/state/4/reviews/4-plan-r2.json`), both 2026-10-20 → this revision. Owner ruling D17 = (a) and round 3 PL3-1 to PL3-3 (`harness/state/4/reviews/4-plan-r3.json`), 2026-10-20 → this revision: PL3-1 → D17, 4c.4, 4d.2, 4d.5; PL3-2 → 4c.3, 4d.1; PL3-3 → the UI fallback paragraph, 4d.4, 4e.3.
- **Placeholder scan.** The research number (20) and the mockup version are re-checked at task time because the `ag-*` skills require it. `<dd>` and `<date>` in file names are the dates the review or handoff is written. No step says "add tests" without naming them.
- **Type consistency.**
  - `contracts/conversation.py` (4c.2) holds `Conversation`, `CarriedRef`, `CarriedAnswer`, `CarriedRun`, `ReplyTo`, `RouteKind`, `MessageRoute`, `ConversationPage`, `ConversationSummary`, `ConversationList`, `ThreadRun` and `ConversationSnapshot`. `MemberFeatures` is in `contracts/features.py` (4c.2).
  - `ConversationPage` is returned by `list_conversations` (4c.3). `ConversationList`, `ConversationSnapshot` and `MemberFeatures` are returned by the routes (4d.4).
  - `route_message` and `ConversationFlow` live in `kernel/conversation.py` (4d.1). `input_replayed` lives in `kernel/run_loop.py` (4d.1). `carry` and `render_carried` live in `kernel/carried.py` (4d.2, 4d.3). `InMemoryConversationStore` lives in `kernel/memory_conversations.py` (4c.3).
  - Each new kernel module is added, in sorted order, to the `source_modules` of the coordinator import contract in the task that creates it (4c.3, 4d.1, 4d.2).
  - `RunModes.conversations` (4c.1) is read by 4d.2 and 4d.3.
  - `CapabilityDescriptor.answer_value_formats` and `value_passes` (4c.4) are read by `carry` (4d.2) through `Registry.descriptor`.
  - `ConversationStore.lookup_idempotent` (4c.3) is called first by `post_message` (4d.1).
  - `ConversationStore.create_run_in_conversation(..., conversation_revision)` (4c.3) is called by `post_message` through the conversation variant of `admit_run` (4d.1); `RunStore` is unchanged.
  - `HostContext` is shared by `CreateRun` and the message body (4d.4), and reaches the started run unchanged (4d.1, 4d.3).
  - `input_replayed(actor, ...)` (4d.1) refuses a non-requester, and runs only after the ownership and `reply_to` membership checks.
  - `ReplyTo.run_revision` is passed to `accept_input` and `input_replayed` (4d.1). `ThreadRun.revision` carries it to the UI (4d.4, 4e.3).
  - `CONVERSATION_CONTEXT_FAILED` (4c.1) is used in 4d.2. The events `conversation.context_carried` (4d.2), `conversation.compared` and `conversation.shadow_failed` (4d.3) are in `contracts/events.py`.
- **Review Focus coverage.**
  - Item 1 → 4d.1.
  - Items 2, 3 and 4 → 4d.2.
  - Item 5 → 4c.3, 4d.1, 4d.4.
  - Item 6 → 4c.3, 4d.1.
  - Item 7 → 4d.3.
  - Item 8 → 4e.5.
  - Item 9 → 4d.1, 4d.4.
- **Toggles.** One runtime feature, one toggle. Its fallback code is used only at admission, before any reservation, and never ends a run. After admission the carried layer follows ADR 0032's terminal path. `shadow` has a real consumer (4d.3), and it never refuses what today's path accepts: a would-be refusal or a conversation-step failure falls back to today's run or input path (4d.3, 4e.3). The chat defects and the route test state why they have no toggle.
