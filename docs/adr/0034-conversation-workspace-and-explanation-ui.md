# ADR 0034: Conversation-first workspace, and citations, explanation and rationale in the UI

Date: 2026-10-20. Status: Proposed (Phase 4 Task 4a.1; the owner accepts or amends it at gate G-A, Task 4a.2). Section 5 has its own status and can be accepted or deferred on its own (D15, D16). Uses ADRs 0011, 0015, 0016, 0023 and 0033; settles requirement EA-10. [UI architecture](../design/ui-architecture.md) §4.2, §10, §11. Plan: [Phase 4](../plans/2026-10-20-phase4-conversation-chat.md) D10, D13, D15, D16; Tasks 4e.1–4e.6. Every `file:line` below is at `181585e`.

## Context

- **EA-10** ("conversation first, closable artifact workspace", `ag-ux-foundations/references/e-agent.md:73-78`) is an owner decision of 2026-10-11 that no accepted ADR states. It comes from [research 16](../../research/16-conversation-workspace-revision.md): the owner rejected a dashboard-first study, and study 04 put the conversation at the centre with the task artifact in a closable workspace holding its sources and activity. [Research 17](../../research/17-agentic-chat-v5-brief.md) refined the identity and truthful-state design. Production implementation was paused there.
- ADR 0023 makes a thread of runs. Today the UI shows one run per task, with session-local history (UI architecture §10) in the four surfaces of ADR 0016: Compact, Workbench, Docked and (standalone only) Workspace.
- ADR 0033 built citations, the generic grounded answer, `ProposalRationale` and the explanation projection, and left their UI to later work (Phase 3 D10). The Phase 3 handoff lists the "grounded, not verified" wording as never reviewed against the `ag-*` standard (pending item 14).
- What the server exposes today, without a contract change:
  - `GET /v1/runs/{id}/evidence` (`server/api.py:494-506`) builds the bundle in `kernel/evidence.py:220-293`. It holds the run, actions, approvals, receipts, outcomes and events (`:257-271`). Observation data is in it only inside `actions[].approved_facts`: each `ApprovedFact` holds an observation's contract, data and `EvidenceRef` (`contracts/evidence.py:29-37`). Write proposals record them from the continuation's observations (`kernel/proposals.py:184-187`, `kernel/plan_flow.py:321`). An answer action records none (`kernel/grounding.py:406-421`, default `()`, `contracts/action.py:66`). The UI already fetches the whole bundle (`ui/packages/client/src/index.ts:152-153`, `ui/packages/ui-core/src/controller.ts:421`), and `selectEvidence` reads `actions[].approved_facts` (`ui/packages/ui-core/src/selectors/evidence.ts:96-97`).
  - Its `explanation` key (`kernel/evidence.py:290-292`) is the ADR 0033 §6 projection: sources (evidence id, contract, revision), validation by rule id, proposals with their rationale refs (ids and text digests, `contracts/explain.py:116-157`), approvals, receipts and outcomes, each with a `ValueLabel` (`contracts/explain.py:36-54`). It holds **no citations**.
  - Citations are stored only on answers; `strip_grounding` drops them from write proposals (`kernel/rationale.py:187-189`). They are stored in their at-rest form: evidence id and pointer when the citation named a real value, otherwise only their digests, and always only the `value_digest`, never the value (`citation_at_rest`, `kernel/at_rest.py:114-121`; ADR 0033 §1). They appear in two places. The bundle's `grounded_answer` key, for a run that ended `GROUNDED`, holds the summary labelled `unverified` and each citation labelled `grounded` (`kernel/evidence.py:203-216`). A typed answer's `proposal.created` event holds `citations` in a run pinned `grounded_answers` `shadow` or `on` (`kernel/grounding.py:327-331`).
  - In `shadow` a typed answer's citations are stored whether or not they resolved, with no verdict per citation; only `grounding.compared` counts them. In `on` a citation that does not resolve is a `KERNEL-CITATION` repair before the answer's action exists (ADR 0033 §2), so a stored citation of an answer that reached its verifier resolved.
  - `ApprovalPresentation` (`kernel/approval.py:125-149`) has no rationale field. The checked rationale of the latest write proposal or plan lives only in the continuation (`rationale`, `step_rationales`, `kernel/continuation.py:152-157`), and `pending_approval` builds the presentation from the continuation at read time (`kernel/approval_flow.py:37-68`), never from an event.

## Decision

### 1. EA-10 is ratified (D13)

The conversation is the primary surface. The task artifact (the approval card, the outcome, the evidence and the activity of a run) opens in a workspace beside the conversation that the user can close and reopen; sources and activity are inside that workspace. Closing it keeps the conversation, the active run, the exact approval state and the composer draft, and never submits, decides or chooses a connection (EA-9, ADR 0016). Enterprise breadth comes from the capabilities and authorization the server reports, not from a homepage catalog. When this ADR is accepted, EA-10's binding source in `ag-ux-foundations` becomes this ADR, and its kind becomes ADR.

The Phase 4 brief and mockup (Tasks 4e.1, 4e.2) extend research 16 and research 17; they do not restart them.

### 2. The thread view (Tasks 4e.3, 4e.4)

- In `conversations: on` (read from `GET /v1/me/features`, ADR 0023 §10), each of the four ADR 0016 surfaces shows the thread: one conversation, its runs as cards in order, one composer. In `off` and `shadow`, and when the features route fails, the UI shows today's per-run task view and keeps the draft.
- The thread is built only from server snapshots (`GET /v1/conversations/{id}`) and the active run's events (AG-FE-2, EA-1). Every state label comes from a server field: run state, reason code, the action states and the `ValueLabel`s. Approved, committed, verified and grounded are four separate labels (EA-3, PR-19).
- A message the server refuses shows the server's fixed hint and keeps the draft. It never changes an approval card.
- An answer carries `reply_to` with the run revision the snapshot showed with the question (ADR 0023 §4).
- The ADR 0022 "reply" label shows once per thread, on its first reply.
- The sidebar lists the server's conversations in `on`. Runs with no conversation stay in today's session-local history (ADR 0023 §10, D11).
- A new run and each run-state change are announced through a polite live region; focus does not move (EA-16).
- No provider identifier appears in a UI package (EA-6, PR-11).

Layout, density and placement are the brief's and the mockup's, decided at gates G-B and G-C; this section fixes only what binds every direction.

### 3. Citations (Task 4e.5)

- A citation is shown as its **record and field**: the evidence id, resolved to that run's source in the `explanation` (`sources`: contract and revision), and the pointer.
- **The value beside it** is read from the run's `actions[].approved_facts`, from the fact whose `evidence.evidence_id` equals the citation's evidence id, at the citation's pointer. It is never read from model text or the citation itself (which stores only a digest). When no approved fact of the run holds that evidence, or the pointer names nothing in it, no value is shown and the citation keeps its record and field.
- Two limits follow from the code today, and are stated in the UI as "value not recorded", never as an empty value (EA-8):
  - an answer's own action records no approved facts, so a typed answer's cited value is shown only when another action of the same run (a write proposal) recorded that evidence. A verified write ends the run `SUCCEEDED` (`kernel/verification.py:264`), so that action can only be a blocked or superseded write proposal; in practice a typed answer's cited value is rarely shown, and in a run whose only action is the answer, no value is shown;
  - a `GROUNDED` run has no action, so its citations show the record and field and no value.
- Citations are shown from two server sources only:
  - the bundle's `grounded_answer.citations`, each already labelled `grounded` by the server;
  - the `citations` of a typed answer's `proposal.created` event, only in a run whose bundle reports `modes.grounded_answers: on`. In `shadow` they are not shown: they were recorded for comparison and may not have resolved.
- A citation stored only as digests (`evidence_id_digest`, `pointer_digest`) named nothing in the run. It is never shown as a fact; at most as "a citation that did not resolve", with no id or pointer.
- A citation is never "verified". On a typed answer, whether the answer is verified is the verifier's outcome, shown from `explanation.outcomes`, not from its citations.

### 4. Explanation and the "grounded, not verified" wording (Task 4e.5)

- The explanation opens from the outcome and from the timeline in the workspace, and renders the `explanation` key in its own order: goal, source facts, validation by rule id, proposal, rationale refs, approval, receipt, outcome (ADR 0033 §6). Facts come before any model-authored text.
- Each value keeps the server's label. A `grounded_answer` outcome reads "grounded, not verified": the answer's citations resolved against this run's own records, and no independent read-back took place (PR-19). A `verified_outcome` reads "verified". A `not_verified` outcome is never shown as a success.
- Model-authored text is labelled as such and shown after the facts: the grounded summary (`unverified`), and a free-text answer field such as `summary` or `explanation`. The UI never presents it as a fact or as verified.
- A rationale in the explanation is shown as the server holds it: evidence ids, rule ids and text digests (`RationaleRef`). Its text is not in the bundle.
- The exact EN and VI copy is the brief's (Task 4e.1) and is reviewed with `ag-ux-review` at gate G-D (Task 4e.7), which closes the Phase 3 handoff's pending item 14.

### 5. `ApprovalPresentation.rationale` (Task 4e.6)

Status of this section: Proposed, on its own. The owner accepts it or defers it at G-A independently of sections 1–4 (D15, D16). If it is deferred, Task 4e.6 moves to a named follow-up and the approval card is unchanged in Phase 4.

- `ApprovalPresentation` gains `rationale`, left out when absent: the summary text, the cited evidence ids and the rule ids of the checked rationale the continuation holds for the pending proposal (`kernel/continuation.py:152-155`). `pending_approval` reads it from the continuation, as it reads the rest (`kernel/approval_flow.py:37-68`). A run not pinned `grounded_answers` `shadow` or `on` holds no rationale, and its presentation is unchanged. A plan's step rationales (`step_rationales`) are not shown on the card in Phase 4; they stay in the explanation.
- **Never an approval input.** `digest_input` enumerates its fields (`kernel/approval.py:20`), so the new field is outside the digest by construction, and ui-core's digest check of `canonical_proposal` (UI architecture §4.2) is unchanged. The approve command sends what it sends today.
- **Shown second.** The card shows the canonical proposal, the material fields and the findings first, and the rationale after them, labelled as the agent's reason, model-authored (threat T9). It never changes whether "Approve" is enabled.
- **Never in an event.** The rationale text stays where ADR 0033 §4 keeps it, in the continuation. It enters no event payload, no evidence bundle and no export; the approval route returns it to the approver only while the continuation holds it.
- This is a change to a server-owned contract (UI architecture §4.2), so the client types are regenerated with it.

## Alternatives considered

- **Leave EA-10 as an owner decision without an ADR:** rejected. The thread view changes the layout of every surface; a binding requirement that only a skill file states can drift.
- **A server projection of the cited value:** deferred. It would read the continuation's observation at the citation's pointer for an authorized viewer, and so cover answer-only and grounded runs, but it is a contract change outside D15. Phase 4 shows the value only where `actions[].approved_facts` already holds it.
- **Show `shadow` citations:** rejected. They carry no verdict, so the UI would have to guess which resolved (EA-1).
- **A per-citation label in the `explanation` key:** deferred. It would let the UI show typed-answer citations without reading events and modes, but it changes the explanation contract; D15 keeps Phase 4 without a contract change.
- **Rationale first on the approval card, or as a digest input:** rejected (target §5.6, ADR 0033 §4, threat T9). It is model-authored and would let model text shape what the approver binds.
- **The rationale text in the evidence bundle:** rejected. The owner chose transient rationale text at G2 (ADR 0033 §4).

## Consequences

- UI: the thread view, the closable workspace, the citation and explanation display, and EN and VI copy (Tasks 4e.3–4e.5); UI architecture gains §12 "Conversation threads" (Task 4e.4).
- Server, only with section 5: `ApprovalPresentation.rationale`, `kernel/approval.py` and `kernel/approval_flow.py`, regenerated OpenAPI and client types (Task 4e.6).
- `ag-ux-foundations`: EA-10's binding source moves to this ADR when it is accepted (Task 4a.2 or the first `ag-*` task after it).
- Known limit: typed-answer citations are visible only in runs pinned `grounded_answers: on`. A cited value is visible only where another action of the run recorded the evidence as an approved fact; answer-only and grounded runs show none (section 3).

## Verification

- 4e.3: "reads the mode from /v1/me/features", "off and shadow keep the per-run view", "the thread comes from server snapshots only", "an answer carries reply_to with the run revision shown with its question".
- 4e.4: "two runs show in one thread", "the workspace closes and reopens, and the conversation stays" (EA-10), "a message during approval shows the hint, and the card is unchanged", "a new run is announced politely" (EA-16), an axe check per state.
- 4e.5: "a citation shows its record and field from the server", "a cited value comes from the run's approved facts, and an answer-only run shows value not recorded", "a grounded run says grounded, not verified" (EN and VI), "free text outside citations is labelled unverified", "the explanation lists facts before any rationale", "an unresolved citation is never shown as a fact".
- 4e.6 (section 5 only): `test_rationale_never_changes_the_approval_digest`, `test_presentation_without_rationale_is_unchanged`, `test_rationale_is_not_in_any_event_payload`, "rationale renders after the facts, labelled as the agent's reason".
- Gate G-D: the `ag-ux-review` of the built UI (Task 4e.7).
- Revisit when a cited value must be shown for an answer-only run or a `GROUNDED` run (the server projection deferred under Alternatives), or when a surface outside ADR 0016's four needs the thread.
