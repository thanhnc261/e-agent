# Core: conversation, context and cognition (phased plan)

> **For agentic workers:** this is a spec-level phased plan. Each phase gets its own detailed, bite-sized plan (superpowers:writing-plans) when it starts. Execute phases with superpowers:subagent-driven-development. Phases marked `[OWNER]` stop for an owner decision first.

**Goal:** make e-agent behave like an assistant, not a task runner. A conversation keeps its context across messages and runs. The agent works from typed state rather than an ever-growing chat transcript. Every answer, including a plain "here are the records", can be independently verified. The UI shows one coherent thread without duplicates.

**Why now:** on 2026-10-12 the owner tested the live agent and reported three things: "a simple chat still does not work well", "duplicated", and "there is no context at all". The previous real-agent work (ADR 0022) patched symptoms inside the kernel instead of building the cognition layer the target design specifies. This plan returns to the design's order.

**Design anchor:** [target architecture](../design/target-architecture.md) roadmap **P1 (C11)** and **P2 (C8, C9, driver conformance)**: §5.4 step record, §6 multi-step reasoning and the progress ledger, §7 context management and the §7.4 rendering rules, §17 ADR candidates C8, C9, C11. The design does **not** specify a conversation that spans runs, so Phase 1 adds it through a new ADR.


> **Phase order is governed by the [roadmap](../roadmap.md)** (owner decision 2026-10-12): this plan's Phase 2 (task definitions) moves into roadmap Phase 2 (execution IR); Phases 3–4 are roadmap Phase 3; Phases 0–1 are roadmap Phase 4. Every new runtime feature here ships behind a profile toggle (`off/shadow/on`) with a fallback to the existing path before any write is reserved.

**Status:** Proposed. Nothing in this plan is implemented. Every phase below is `[P]`.

## Owner complaints and where each one is resolved

| Complaint | Cause today | Resolved in |
|---|---|---|
| "Duplicated" | Every message creates or continues a separate "task"; the sidebar fills with "Hi" / "hi". Every greeting carries a "Reply · not a verified result" label. The timeline repeats state rows. | Phase 0 (label, timeline rows), Phase 1 (one thread instead of one task per message) |
| "No context at all" (conversation) | Context lives only inside one run's driver message history. A new run starts blank. | Phase 1 (thread context), Phase 3 (ContextAssembler) |
| "No context at all" (business) | Nothing tells the model what was already read, tried, blocked or verified, except raw tool results in chat history. | Phase 3 (step records + progress ledger) |
| "No context at all" (page) | The Context chip says "this workspace sends no page context", which reads as "the agent knows nothing". | Phase 0 (copy), ADR 0011 scope for real host hints |
| "Does not work well" | `status.undefined → status.undefined` in the timeline; plain answers after reads end in `VERIFICATION_FAILED`; small budgets. | Phase 0 (defects), Phase 3 (grounded answer contract), Phase 4 (conformance + repeat detection) |

## Not in this plan (and why)

- **P0 concurrency** (C1 run slots, C2 LISTEN streaming, C3 durable writer lease) and **P1 C4 worker role / kernel split (SR-06)**: these don't change single-user chat quality. They get their own plan. `[OWNER]`: confirm this deferral. The design orders P0 before P2; this plan inverts that for the owner's priority. The risk is low for one local user and real for multi-user deployment.
- **Odoo tools breadth**: separate plan, [Odoo integration tools from ERP-Bench](2026-10-12-odoo-tools-from-erp-bench.md). That plan depends on Phases 2–3 here.
- **Memory across conversations, knowledge graph** (§8, §9, roadmap P4): later.
- **Real page/host context** (host adapters passing record ids from the embedding app): ADR 0011 scope; only the misleading copy is fixed here.

## Global constraints

- Trust anchor unchanged:
  - Run and action state machines, gateway, approval digests, admission and verifier invocation stay in the kernel.
  - Model output is a proposal.
  - Every write is approved.
- Contracts never import framework types. The kernel never imports domains, adapters or the server (import-linter).
- Hidden chain-of-thought is never persisted.
- Retrieved or remembered content is untrusted data.
- Both `RunStore` implementations change together under `tests/conformance`.
- Contract changes regenerate OpenAPI and TS types.
- UI work follows the `ag-*` skills, with an owner gate at brief and mockup for new UX (Phase 1 conversation UI).
- End to end after every task: full gate, Postgres run, `make e2e`, UI tests. A live check on the `odoo19-learning` sandbox at each phase exit.
- Each phase is its own branch. Merge only after the phase ADRs are accepted.

---

## Phase 0: visible defects (no design change)

**Design refs:** none (defects). **Gate:** none.

| Task | Deliverable |
|---|---|
| 0.1 | Fix `accept_input`'s `run.state_changed` payload from `{"state": …}` to `{"from": "WAITING_INPUT", "to": "RUNNING", "reason": null, "reason_code": null}`. The timeline then stops rendering `status.undefined → status.undefined`. Old rows keep rendering: the UI accepts `state` as a fallback for `to`, with `from` shown as unknown, not `undefined`. |
| 0.2 | The reply label shows on the first conversational reply of a thread only, or as a quiet tooltip. It must not appear on every greeting. Keep the truthful-state rule: a reply is still visibly not a verified result. Use the `ag-ui-implement` skill. |
| 0.3 | Context chip copy: replace "this workspace sends no page context" with what the agent *does* use, for example "Uses this conversation and your ERP connection; this page sends no extra details". VI translation included. |
| 0.4 | The sidebar's "Recent tasks" entry for a run whose last state is `WAITING_INPUT` after a reply reads "Your turn", not "Your answer is needed". |

**Exit evidence:** the UI conformance specs for each fix, plus the live `odoo19-learning` "hi → hi → question" run with no `undefined`, a single label, and correct chip copy.

---

## Phase 1: conversation model `[OWNER]` (ADR 0023)

**Design refs:** none, which is the gap. ADR 0023 adds it. It touches §5 (ledger), §7.2 ("recent turns" layer) and ADR 0022.

**Decision needed (owner):**

| Option | Shape | Pros | Cons |
|---|---|---|---|
| **A. Thread of runs (recommended)** | A `Conversation` record owns many runs. A message either answers the run that is waiting for input, or starts a new run in the same conversation. Each new run gets a carried context: prior turns as summaries plus `EvidenceRef`s, never raw tool output. | Runs stay bounded and auditable (one task, one acceptance, one budget). Cross-run context is explicit and governed by the ContextAssembler. It fits approvals and verification as they are. | New contract, store table and API, and UI threads. |
| B. One long-lived run per conversation | Every message continues the same run forever. | Smallest change. | Unbounded budgets. One approval or failure state for many unrelated tasks. Repair and verification semantics blur. Contradicts §5 bounded runs. |

**ADR 0022 consequence:** under option A, `input.requested {kind: "reply"}` stays for a reply *inside* a run that is waiting for clarification. A pure greeting at the start of a conversation needs no run at all. The conversation answers it as a conversational turn with no business claim, recorded in the conversation log, not as a failed or verified run. ADR 0023 amends ADR 0022, so the two Proposed ADRs don't conflict.

**Interfaces (proposed):**
- `Conversation(tenant_id, conversation_id, owner_id, title, created_at, updated_at, state)` and `ConversationTurn(role, text, run_id | None, created_at)` in `e_agent.contracts.conversation`.
- `RunRecord.conversation_id: str | None`. Old runs have `None`.
- `ConversationStore` port, with memory and Postgres implementations, plus migration 0005.
- API: `POST /v1/conversations`, `POST /v1/conversations/{id}/messages` (the server routes the message to the waiting run or a new run), `GET /v1/conversations`, and the conversation SSE stream.

**Tasks:**
1. ADR 0023 draft with options A and B and the ADR 0022 amendment. `[OWNER]` accepts it.
2. Contracts plus `ConversationStore` in both stores, under conformance.
3. Message routing in the server or kernel facade:
   - answer the run that is waiting for input;
   - otherwise create a new run in the conversation;
   - conversational turns that need no run are recorded in the conversation log.
4. Cross-run carried context: when a run starts in an existing conversation, its `DriverInput` carries the prior turns as summaries and refs. This is the thin precursor of Phase 3's ContextAssembler, and Phase 3 replaces it.
5. UI: `ag-ux-brief`, then `ag-ux-mockup` `[OWNER]`, then `ag-ui-implement`. The deliverables are conversation threads in the sidebar, one composer per thread, and runs shown as cards inside the thread.

**Exit evidence:**
- Live: "hi" → "which products are short?" → "draft a PO for it" runs in one thread, as two runs. The second run uses the first run's findings without re-asking.
- The sidebar shows one thread.
- Conformance runs on both stores.

---

## Phase 2: task definitions and acceptance specs (C11)

**Design refs:** §2.3 (task definitions), §7.2 rule 1 (fixed tool set per run), §17 C11, roadmap P1.

**Why first among the cognition work:** the ContextAssembler's stable prefix needs the run's task definition. That definition supplies the goal, acceptance criteria and the fixed tool set. Without it, every run gets every tool, about 18 today and many more after the tools plan.

**Interfaces (proposed):**
- `TaskDefinition(task_id, version, goal_template, acceptance: AcceptanceSpec, capabilities: tuple[str, ...], budgets: Budgets | None, approval_ttl: timedelta | None)`, packaged in domain packs as resources.
- `AcceptanceSpec`: required effects or answers, for example "a verified shortage answer" or "a draft PO for the demand". Used by the kernel at run end and producing the `Acceptance` finding from §6.1.
- Task selection: the kernel or server picks a task definition from the user's message through a lightweight classifier step, or the user picks one in the UI. A general `assistant` definition with read-only tools exists for open questions.

**Tasks:** contracts; domain-pack task definitions for the eight existing ERP tasks plus `assistant`; admission resolves the tool set from the definition; acceptance check at run end; per-task TTL replaces the global approval TTL (ADR 0019 follow-up).

**Exit evidence:**
- A run's tool list equals its definition's capability set, fixed for the whole run.
- An acceptance-unmet run ends with a typed acceptance finding.
- Live: an open question uses `assistant` with read tools only.

---

## Phase 3: step records, progress ledger, ContextAssembler, grounded answers (C8, C9)

**Design refs:** §5.4 step record, §6.2 progress ledger, §6.3 loop, §7.1–§7.4, §17 C8, C9.

**Interfaces (from the design sketches):**
- `StepRecord`, `StepKind` and `StepStatus` (§5.4). They are written in the same transaction as their run events (both stores).
- `ProgressLedger` (§6.2), a projection over steps, actions and findings. It is never a source of truth.
- `ContextPolicy` and `ContextPack` (§7.3). `DriverInput` carries a `ContextPack`. The driver maps it to framework messages.
- **Grounded answer contract** (new, core):
  - `grounded.answer.v1` with fields `summary` (text) and `citations: tuple[Citation, ...]`, where each `Citation` holds an `evidence_id`, a JSON path and a value.
  - The host verifies every citation against recorded observations of this run.
  - Any read-only question ("list the POs", "who supplies X") can then end `SUCCEEDED/verified` without a bespoke answer contract per question type.
  - Free text outside citations stays unverified and is labelled as such.

**Driver rewrite, not a tweak:** §7.4 rule 1 reverses today's behaviour. Today the driver appends findings to the persisted message history as a user prompt (`driver.py` `advance`). Under C9, the ledger and findings go into a dynamic suffix that is rebuilt every turn and never persisted. Tool results older than the retention window are cleared to stubs with their `EvidenceRef`, and call and return pairing is preserved. This changes the driver continuation schema, so the `STATE_SCHEMA` version bumps. Old continuations either migrate or fail closed with a clear error.

**Tasks:**
1. ADR C8 and C9, then ADR C8/C9 `[OWNER]`.
2. Step records in both stores under conformance.
3. ProgressLedger projection.
4. The ContextAssembler, with layer budgets, the drop log and untrusted fencing.
5. Driver adapter rewrite per §7.4.
6. The grounded answer contract and its verifier.
7. UI: the timeline is built from step records, and grounded answers show their citations, which link to the evidence panel.

**Exit evidence:**
- Roadmap P2: budget respected over 12 turns; repair rate and token cost compared against the pre-change baseline on fixtures.
- Live: "list the open demands and their shortage" ends verified with citations.
- A 20-turn conversation stays under the token budget.

---

## Phase 4: driver conformance and repeat detection

**Design refs:** §4.2 seams, §6.3 (KERNEL-REPEAT), roadmap P2 exit.

**Tasks:**
- A reusable driver conformance suite in `tests/conformance`. It covers deferred reads and writes, resume after restart, context pack rendering, clearing, findings in the suffix, and grounded answers. It runs against the Pydantic AI driver and a scripted reference driver.
- `KERNEL-REPEAT`: a proposal whose digest equals an already blocked revision gets a finding without re-validation and counts against the repair budget.
- Plain-text repair turns are visible (already done in real-agent) and shown in the ledger.

**Exit evidence:**
- Both drivers pass the suite.
- A repeated blocked proposal is short-circuited.
- The context ablation from research 03 §8 is designed and its first run is recorded (chat history vs typed state).

---

## Phase map and cost

| Phase | Size (tasks) | Depends on | Owner gates |
|---|---|---|---|
| 0 Defects | 4 | none | none |
| 1 Conversation (ADR 0023) | 5 | 0 | ADR 0023, UI mockup |
| 2 Task definitions (C11) | 5 | 1 | none beyond review |
| 3 Steps, ledger, context, grounded answers (C8/C9) | 7 | 2 | ADR C8/C9 |
| 4 Conformance, repeat | 3 | 3 | none |

The owner decides first:
1. Defer P0 concurrency (yes or no).
2. Conversation shape A or B.
3. After Phase 2, accept the ADRs before merge.
