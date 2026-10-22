# Conversation thread: design brief

Date: 2026-10-21. Status: candidate, pending owner approval at gate G-B. Standard: ag-ux-foundations at `3ab6d7c2`. Written with the `ag-ux-brief` skill for Phase 4 Task 4e.1.

## Request

The request is Task 4e.1 of the [Phase 4 plan](../docs/plans/2026-10-20-phase4-conversation-chat.md), which the owner approved on 2026-10-20:

> Write the brief with `ag-ux-brief`:
> - roles and the normative states: thread empty; reply pending; clarification; running; waiting approval with a refused message; verified; grounded; failed; per-run fallback; legacy runs;
> - the AG criteria and EA-1, EA-3, EA-5, EA-6, EA-9, EA-10 and EA-16;
> - 2–3 directions; how they will be judged;
> - the D15 surfaces (citations and explanation; the rationale on the card is deferred at G-A, so the card is unchanged);
> - the "grounded, not verified" wording (handoff item 14);
> - open questions, among them: where legacy runs appear (D11), and the VI copy of 4b.3.

The owner's answers that bind this brief, verbatim:

- G-A, 2026-10-20, on ADRs 0023 and 0034: "1 accept 2 accept 3 defer 4 ok 5 ok 6 ok 7 yes". ADR 0023 and ADR 0034 are accepted. ADR 0034 §5 (the rationale on the approval card) is deferred, so Task 4e.6 is not built and the card is unchanged. The D15 amendment stands: a cited value comes only from `actions[].approved_facts`, so it is rarely shown. `offer_ref`, `supplier_ref`, `late_order_refs` and `overdue_invoice_refs` are never carried. A carried ref counts only from a complete read.
- G-0, 2026-10-20, on the chat-defects review: "1 ok, rest yes". The Context panel splits what is sent from what is used, the wording is "this task's messages", later replies show a visible "not verified" note, and Activity says "Your turn". All of this is built (4b.5, [resolution](../docs/reviews/2026-10-20-chat-defects-ux-review-RESOLUTION.md)).
- 2026-10-21, on the 4b.5 Vietnamese strings: "VI ok". This confirms the Context "sent" and "used" lines and "chưa xác minh".

| Said by the owner | Assumed (correct if wrong) |
|---|---|
| A thread of runs (ADR 0023), conversation first with a closable workspace (ADR 0034 §1) | The brief extends research 16 (study 04) and research 17 (v5); it does not restart them (plan D13) |
| The card is unchanged in Phase 4 (G-A "3 defer") | "Unchanged" means its content and its gates. Where it sits (in the workspace, per ADR 0034 §1) is a layout question for this brief |
| "this task's messages" (G-0) | That wording stays in `off` and `shadow`. In `on`, where carried context reaches the model, the "used" line must name the conversation; the new copy is drafted below for the owner |
| "VI ok" (2026-10-21) | It covers the 4b.5 strings only. New strings in this brief need their own confirmation |
| A reply aimed at a run that already ended is still open | ADR 0023 §4 today starts a new run; the reviewers recommend `CONFLICT`. Either way the UI must say what happened; the choice is decision 3 below |
| — | The four ADR 0016 surfaces (Compact, Workbench, Docked, Workspace) all get the thread (ADR 0034 §2); layout differs only by width |
| — | One person is requester and approver in this study, as in research 17 |

## Context

- **Extends:** [research 16](16-conversation-workspace-revision.md) and its study 04 (`research/mockups/agentic-chat-v4/`), which put chat at the centre with the artifact in a closable workspace on the right and a switch between conversation and artifact on mobile; [research 17](17-agentic-chat-v5-brief.md) (identity and truthful states). Nothing is superseded.
- **Binding design:** [ADR 0023](../docs/adr/0023-conversation-model.md) (routing table §4, carried context §6, toggle §9, routes §10) and [ADR 0034](../docs/adr/0034-conversation-workspace-and-explanation-ui.md) (§1 EA-10, §2 the thread view, §3 citations, §4 explanation and wording; §5 deferred).
- **What the server provides (Part 4d, done):**
  - `POST /v1/conversations`;
  - `GET /v1/conversations`, a paged list with `title`, `latest_state` and `reply_pending`;
  - `GET /v1/conversations/{id}`, a `ConversationSnapshot` whose `ThreadRun`s each carry the `revision` the UI sends back in `reply_to`;
  - `POST /v1/conversations/{id}/messages`, which answers 202 `{route: start|answer, run_id}`, or a 409 error envelope `{code, message, correlation_id}` when it refuses;
  - `GET /v1/me/features`, the `conversations` mode (`off`, `shadow` or `on`);
  - the evidence bundle's `conversation` key: id, pinned mode, carried run ids and compared counts.
- **What carried context is:** later runs see earlier runs' checked answer values, complete-read record refs and the user's own messages, as hints, never as evidence (ADR 0023 §6). A message sent while a run waits for approval is refused in `on`; in `shadow` it starts a separate unlinked run.
- **Current-state evidence:** [gap audit 2026-10-21](../docs/reviews/2026-10-21-chat-surface-gap-audit.md): 56 met, 25 partial, 4 missing, 19 findings. The ones this brief must answer are F-1, F-2, F-3, F-4, F-6, F-7, F-8, F-9 and F-10; F-12 and F-17 bind the build.

## Roles and states

| Role | Need |
|---|---|
| Requester | Ask, follow up and refine in one thread; see which run is doing what, and stop it |
| Approver (the same person here) | Decide one exact action without losing the conversation that led to it; know a message cannot approve |
| Administrator (outside the UI) | Set the `conversations` mode; read the evidence bundle's `conversation` key. The UI shows the mode's effect, never a control for it |

The plan's thread states, mapped to the normative states. Each product state maps to one normative state; a row that is not a task state says so.

| Thread state (plan) | Normative state | In scope | User need | Current gap (finding) |
|---|---|---|---|---|
| Thread empty | Ready | yes | Know it is an AI agent, what it can do here and that nothing changes without approval | F-1 |
| Reply pending ("Your turn") | Needs input | yes | Know the agent replied conversationally, that the reply is not a verified result, and that it is their turn | met in 4b; across runs, the "reply" label shows once per thread (ADR 0034 §2) |
| Clarification ("Your answer is needed") | Needs input | yes | Answer the question shown, bound to that question (`reply_to`) | F-8 (a stale answer's refusal is generic) |
| Running | Working | yes | See which run is active and stop it | F-2 (one run per view) |
| Waiting approval, with a refused message | Awaiting decision | yes | Decide the card; if they type meanwhile, see why the message was not sent, with the draft kept and the card untouched | F-2, F-8 |
| Verified | Verified complete | yes | Know what was verified, apart from what the agent wrote | F-4 |
| Grounded | none (see below) | yes | Know the answer rests on this task's own records but nothing read it back | F-4, F-6, F-7 |
| Failed | Failed | yes | Know what failed in which run, and that the thread continues | none in the run; F-2 for the thread |
| Answer to a run that ended | Failed or Ready, per decision 3 | yes | Know the answer was not delivered to the question they saw, and what happened instead | not built |
| Per-run fallback | not a task state: a mode | yes | In `off`, `shadow` or when `/v1/me/features` fails, get today's per-run view with the draft kept, and no re-post after an error | not built |
| Legacy runs | not a task state: a placement in the sidebar | yes | Find tasks started before the thread existed, without mistaking them for a thread | F-9, F-10 |

Every other normative state (Blocked by rules, Decision invalidated, Rejected, Executing, Verifying, Outcome uncertain, Cancelled or stopped) stays as it is today inside a run. In the thread it must be reachable on the run it belongs to; its content does not change.

**Grounded has no normative state.** `SUCCEEDED` with reason code `grounded` is not Verified complete (PR-19); mapping it there would break that state's Forbidden item. The gap audit proposes a new normative state "Grounded answer" (decision 8). Until the owner decides, the design treats it as a product state judged by AG-APPR-6, AG-EXPL-2 and AG-ID-1.

## Criteria the design must satisfy

| State or area | Binding (EA) | Criteria (AG) | Currently failing |
|---|---|---|---|
| Whole thread | EA-1, EA-10, EA-6 | AG-CTRL-2, AG-MEM-1, AG-CTX-1, AG-FE-1, AG-FE-2 | F-2, F-3 |
| Thread empty | EA-10 | AG-DISC-1, AG-DISC-2, AG-DISC-3 | F-1 |
| Reply pending, clarification | EA-1, EA-3 | AG-UNC-1, AG-CTRL-3, AG-ID-1 | none |
| Running | EA-5, EA-16 | AG-STAT-1, AG-STAT-2, AG-STAT-4, AG-CTRL-1 | none |
| Refused message (any state) | EA-1, EA-9 | AG-UNC-3, AG-MEM-1, AG-FE-1 | F-8 |
| Waiting approval | EA-2 (card unchanged), EA-9 | AG-APPR-1 to AG-APPR-9 (unchanged), AG-CTRL-3 | F-5 (recorded for the card follow-up, not Phase 4) |
| Verified, grounded | EA-3, EA-5 | AG-APPR-6, AG-ID-1, AG-FE-12, AG-DS-7 | F-4, F-7 |
| Citations and explanation (D15) | EA-1, EA-3, EA-5, EA-8 | AG-EXPL-1, AG-EXPL-2, AG-EXPL-3, AG-UNC-4, AG-FE-13 | F-6 |
| Carried context shown to the user | EA-1, EA-5 | AG-CTX-1, AG-EXPL-2 | not built |
| Sidebar and legacy runs | EA-1 | AG-STAT-3, AG-FE-2, AG-FE-10, AG-MEM-1 | F-9, F-10 |
| Per-run fallback | EA-9 | AG-MEM-1, AG-FE-13, AG-UNC-3 | not built |
| Every state, every surface | EA-6, EA-9, EA-12, EA-14, EA-15, EA-16 | AG-A11Y-1 to AG-A11Y-5, AG-ENT-3, AG-ENT-4, AG-FE-6, AG-FE-9 | F-12, F-16, F-17 |

What these bind, briefly:

- **EA-1.** The thread is built only from the snapshot and the active run's events (ADR 0034 §2). The UI never routes a message itself, never infers which run a message answers, and never shows carried items as facts.
- **EA-3.** Approved, committed, verified and grounded are four labels.
- **EA-5.** No "thinking", no invented progress; carried context is not "memory" and is never presented as something the agent knows.
- **EA-6.** No provider names in the copy below.
- **EA-9.** Closing the workspace, switching surface or a refused message keeps the conversation, the active run, the approval state and the draft.
- **EA-10.** ADR 0034 §1.
- **EA-16.** A new run and every run-state change are announced politely; streamed text is not.

**Patterns** (decisions as in `patterns.md`):

- Apply: Chat Interface, Conversational Interface, Mixed-Initiative Interface, Agent Status & Activity, Progressive Disclosure, Trust and Transparency, Error Handling and Recovery, Human-in-the-Loop, Cross-Platform Agent UX, Onboarding and Education.
- Limit: Visual Reasoning (evidence chain only), Transparent Data Handling (sources and observation time only), Confidence Visualization (none shown).
- Exclude: Generative UI; Context Window Management UI (carried context is fixed by the kernel, so the user does not prune it).

## Fixed for every direction

These follow from ADR 0023, ADR 0034 and the gap audit; the directions only differ in layout.

1. **Mode first.** The UI reads `GET /v1/me/features`. `on` shows the thread. `off`, `shadow`, or a failed features read, shows today's per-run view (ADR 0034 §2). The UI uses `/v1/runs` only when the mode is `off`, or a conversation route answers 404 or 405 without the error envelope (not mounted). A route error in `shadow` is shown with the draft kept and never re-posted (ADR 0023 §9).
2. **One composer, server routing.** A message goes to `POST …/messages` with `reply_to` set to the run and the `revision` shown with the pending question. The answer is `start` or `answer`; the UI never decides which.
3. **A refusal keeps the draft** and shows the server's fixed hint beside the composer. The hint is localised by mapping the two fixed hints to i18n keys; any other message is shown verbatim. The `correlation_id` is shown on demand, and the approval card does not change (ADR 0034 §2; F-8).
4. **Runs are visible as runs.** Each run shows its own status label from the server, on its own place in the thread. Only the latest run can be active, because the server allows one active run per conversation.
5. **The first reply of a thread** is labelled "Reply · not a verified result"; later replies show "· not verified" (4b.2, 4b.5).
6. **The empty thread** carries the AI disclosure and the capability detail now on the Overview, in every surface (F-1).
7. **The agent's final answer is labelled as its own words.** The result says what the server verified or grounded (F-4, ADR 0034 §4). The grounded composer pill takes the grounded tone, not the verified colour (F-7).
8. **Carried context is visible in the workspace of the run that used it.** The evidence bundle's `conversation` key lists the carried run ids, shown as "Used earlier runs as hints: run 1, run 2", each a link to that run in the thread, and never as evidence. In `shadow`, nothing is shown, because nothing reached the model.
9. **The sidebar** in `on` lists `GET /v1/conversations` (title, latest state, "Your turn" from `reply_pending`). Legacy runs follow decision 2. No task text is newly written to browser storage for threads (F-10).
10. **Accessibility.** A polite announcement for a new run and each state change (EA-16); focus never moves on a new message; the workspace close control returns focus to its opener (AG-A11Y-2); an axe check per state (Task 4e.4, F-12); container queries, not viewport media queries (F-17).

## Citations, explanation and wording (D15)

The rationale on the approval card is deferred (ADR 0034 §5), so the card shows no rationale and does not change. What Task 4e.5 shows, all from the existing `/v1/runs/{id}/evidence` bundle:

- **A citation** is its record and field. The record is the evidence id, resolved to the run's source in `explanation.sources` (contract and revision); the field is the pointer. Shown from two places only: `grounded_answer.citations`, and the citations of a typed answer's `proposal.created` event in a run whose bundle reports `modes.grounded_answers: on`. Citations recorded in `shadow` are never shown (ADR 0034 §3).
- **The cited value** comes only from `actions[].approved_facts`, from the fact with the same evidence id, at the pointer. An answer's own action records none, and a grounded run has no action, so **in practice the value is rarely shown**. Where it is absent the UI says "Value not recorded", never an empty value (EA-8).
- **A citation stored only as digests** named nothing in the run. It is shown at most as "A source that could not be matched", with no id or pointer, never as a fact.
- **The explanation** opens from the result and from Activity in the workspace, in the server's order: goal, source facts, rules checked, proposal, rationale references, approval, receipt, outcome (ADR 0033 §6). Facts come first. A rationale is shown only as the ids and digests the bundle holds; its text is not there.
- **Model-authored text** (the grounded summary, a free-text answer field, the final message) is labelled as the agent's words and sits after the facts.
- **Known limits, stated where they apply:** `offer_ref`, `supplier_ref`, `late_order_refs` and `overdue_invoice_refs` are never carried, and a carried ref counts only from a complete read (G-A "6 ok", "7 yes"). The UI never implies a later run "remembers" more than the carried run ids show.

**"Grounded, not verified" (Phase 3 handoff item 14).** Today's labels are EN "Completed · grounded, not verified" and VI "Hoàn tất · có dẫn chứng, chưa xác minh" (`ui/packages/ui-core/src/i18n.ts:156,427`). The brief keeps the EN label and adds one explanatory line in the result:

| Key (proposed) | EN | VI (draft, needs confirmation) |
|---|---|---|
| `outcome.groundedExplain` | "Grounded: its sources are records this task read. Not verified: nothing read the result back independently." | "Có dẫn chứng: nguồn là các bản ghi mà tác vụ này đã đọc. Chưa xác minh: chưa có bước kiểm tra độc lập nào đọc lại kết quả." |
| `messages.agentWords` | "Written by e-agent. The result shows what was checked." | "Do e-agent viết. Phần kết quả cho biết điều gì đã được kiểm tra." |
| `citation.valueNotRecorded` | "Value not recorded" | "Không ghi lại giá trị" |
| `citation.unresolved` | "A source that could not be matched" | "Một nguồn không khớp được" |

The exact copy is reviewed at G-D (Task 4e.7), which closes item 14.

## Copy that changes with the mode

Only `on` carries context to the model, so only `on` changes the Context panel's "used" line. The 4b.5 strings stay, as the owner confirmed them, in `off` and `shadow`.

| Key | Mode | EN | VI |
|---|---|---|---|
| `context.sentNoHost` | all | (unchanged, confirmed "VI ok") | (unchanged) |
| `context.noHost` | `off`, `shadow` | (unchanged: "…this task's messages…") | (unchanged, confirmed "VI ok") |
| `context.noHostThread` (new) | `on` | "e-agent also uses your earlier messages in this conversation, checked values and record references from its earlier answers, and any systems you have connected, within your permissions. These are hints, not evidence: it reads the records again before relying on them." | "e-agent cũng dùng các tin nhắn trước đó của bạn trong cuộc trò chuyện này, các giá trị đã kiểm tra và tham chiếu bản ghi từ những câu trả lời trước, cùng mọi hệ thống bạn đã kết nối, trong phạm vi quyền của bạn. Đây chỉ là gợi ý, không phải bằng chứng: e-agent đọc lại bản ghi trước khi dựa vào chúng." (draft) |
| `conversation.refusedQuestion` (new; server hint "the question changed; read it again") | `on` | "The question changed. Read it again before answering." | "Câu hỏi đã thay đổi. Hãy đọc lại trước khi trả lời." (draft) |
| `conversation.refusedBusy` (new; server hint "wait, decide the approval, or stop the run") | `on` | "This conversation is busy. Wait, decide the approval, or stop the task." | "Cuộc trò chuyện đang bận. Hãy chờ, quyết định phê duyệt, hoặc dừng tác vụ." (draft) |
| `nav.legacy` (new, if decision 2 is "group") | `on` | "Earlier tasks · this session · last seen" | "Tác vụ trước · phiên này · trạng thái lần cuối" (draft) |

## Directions

All three extend study 04 (research 16) and the v5 identity (research 17), on the same scenario: "hi", then "which orders are late?" (grounded), then "draft a PO for the shortage" (approval), with a message typed while the card waits, then a verified result.

### A. Thread with run cards and a side workspace (recommended)

- **Description:** Study 04's composition made a thread. The conversation is the centre column. Each run appears in it as a small run card: its status label, a one-line result or "Needs review", and "Open". The workspace opens on the right for the selected run, holding the approval card, the result with its citations and explanation, the carried runs, evidence and activity. It opens by itself once when a decision is waiting or a result arrives (decision 6), can be closed at any time, and its run card keeps "Open" and the status visible, so a pending decision is never only behind a closed panel. Below about 60rem the workspace becomes a full-height view that switches with the conversation, with Back returning to the run card (research 16's mobile rule). The sidebar lists conversations.
- **Trade-offs:** The largest layout change from today: the card and the result leave the conversation column (ADR 0034 §1 asks for this). On a phone, deciding means switching views, so the run card must carry the status and the "Open" control in reach of the composer.
- **Makes easier:** EA-10, AG-CTRL-2, AG-MEM-1, AG-STAT-1 (one status per run card), AG-EXPL-3 (summary in the card, detail in the workspace), AG-ENT-3 (one composition at every width).
- **Makes harder:** AG-APPR-3 on narrow widths stays as today (F-5, unchanged card), and AG-A11Y-2 needs a careful focus return for the switching view.

### B. Run-grouped thread with a drawer workspace

- **Description:** The thread is grouped by run: each run is a section with a header (task, status, time) and its messages under it; ended runs fold to their header. The workspace is a drawer over the right part of the thread on every width, modal below 60rem, closable with Escape.
- **Trade-offs:** The clearest view of where one run ends and the next begins, and the thread keeps its full width. But while the drawer is open the thread is covered, so the approver cannot see the conversation that led to the card beside it; a modal drawer needs focus containment in all four surfaces, including the embedded overlay.
- **Makes easier:** AG-STAT-1, AG-MEM-1, AG-CTRL-3.
- **Makes harder:** AG-APPR-1 in context (the purpose sits under the drawer), AG-FE-7 and AG-A11Y-2 (modal focus in an embedded host), AG-ENT-3.

### C. Split view, workspace open by default

- **Description:** Closest to today's page: the thread on the left and the workspace on the right, open by default on wide screens and closable; one column below about 74rem (the current 4b.5 container query). Runs are separated by a thin divider with the status label.
- **Trade-offs:** The smallest change from today's code and the most context beside the decision. But the workspace competes with the conversation on every visit, which is the hierarchy the owner rejected in study 03 (research 16), and at 200 % text it falls back to one column with the workspace below the composer.
- **Makes easier:** AG-APPR-1 (card and thread side by side), AG-STAT-3.
- **Makes harder:** EA-10 (conversation first), AG-A11Y-3 at 200 % text.

**Recommendation:** A. It is study 04's accepted composition with the thread added, it satisfies ADR 0034 §1 as written, and it keeps the decision reachable from the run card when the workspace is closed. B gives clearer run boundaries but costs the decision its context; C repeats the hierarchy the owner rejected.

## Evaluation

| Metric | Method | Target or question |
|---|---|---|
| M-3 Approval comprehension | Moderated, role-matched, on the scenario above | With the workspace opened from a run card, can the person say what will change, where, and whether it is reversible? |
| M-4 Oversight effectiveness | Moderated, with a seeded bad proposal in the second run | Do people find Stop on the active run and the card's Reject, and do they understand that a typed message cannot approve? |
| M-6 Recovery success | Moderated, with a refused message and an answer to an ended run | Do people recover without retyping and without sending the same text as a new task by mistake? |
| M-7 Clarification count | Instrumented, fixture thread | Does a follow-up run ask again for what an earlier run already found (carried refs)? |
| M-5 Trust calibration | Moderated | After a grounded answer and a verified one, can people tell which was independently checked? |

Browser checks will verify, for each direction and each state above: every state is reachable; the workspace closes and reopens with the conversation, draft and approval state kept; a refused message keeps the draft and leaves the card unchanged; announcements are polite and focus does not move; the four surfaces at 320, 390, 768 and 1440 px, landscape, and 200 % text; light, dark, high-contrast and forced colours; keyboard only; no external requests; every sample labelled as a sample (EA-11). They will not establish design quality or usability.

## Open questions for the owner

1. Which direction, A, B or C?
2. **Legacy runs (D11).** Runs with no conversation stay in session-local history. Should they appear as a separate group under the conversations, marked "last seen", be hidden in `on`, or be mixed into the list?
3. **An answer to a run that has ended.** Today (ADR 0023 §4) it starts a new run with the answer as its task, so a reply like "north" becomes a task. The reviewers recommend refusing it with `CONFLICT` "the question changed; read it again". With a refusal, the user sees the draft kept, the hint, and the thread re-read showing how the run ended. With a new run, the user sees a new run card whose task is their answer. Choosing "refuse" needs a small amendment to ADR 0023 §4 before Task 4e.3.
4. **Typing while a decision waits.** Should the composer stay open, sending to the server and showing its refusal hint with the draft kept (the plan's 4e.4 test "a message during approval shows the hint, and the card is unchanged"), or stay locked as today?
5. **Where the agent's words are labelled.** On the final message and on the result, or on the result only?
6. **Workspace on desktop.** Should it open by itself when a decision is waiting or a result arrives (closed for replies), or open only when the user asks?
7. **Vietnamese copy.** "VI ok" covered the 4b.5 strings, so the 4b.3 Context copy is settled. Still open are the new strings above: `context.noHostThread`, the two refusal hints, the grounded explanation line ("có dẫn chứng" for "grounded"), `messages.agentWords`, the citation strings and `nav.legacy`. Accept the drafts, or revise?
8. **The standard.** Should `ag-ux-foundations` gain a normative state "Grounded answer" (gap audit, Decision proposals)? It is a separate skill change with its own check. Separately, its EA-10 source still names research 16 and should move to ADR 0034.
9. Not asked at this gate: the acting identity on answers (F-11) and the decision-body scroll cue (F-5). Both stay in the backlog, and F-5 waits for the card follow-up.

## Approval

Pending. This brief awaits the owner's approval at gate G-B, which must name this brief and the chosen direction; it is recorded here verbatim when given. The mockup (Task 4e.2) does not start before it.

## Decisions for G-B

Reply with the numbers and one word each, for example "1 A, 2 group, 3 refuse…".

1. **Direction.** Recommended: A (run cards, side workspace). Options: A / B / C.
2. **Legacy runs in the sidebar.** Recommended: a separate group marked "last seen". Options: group / hide / mix.
3. **Answer to a run that ended.** Recommended: refuse, keep the draft, show "the question changed" (needs a small ADR 0023 §4 amendment). Options: refuse / start.
4. **Typing while a decision waits.** Recommended: open composer; the server refuses with its hint, the draft is kept and the card is unchanged. Options: hint / lock.
5. **Label on the agent's words.** Recommended: on the message and on the result. Options: both / result.
6. **Workspace on desktop.** Recommended: opens by itself for a decision or a result; the user can close it. Options: auto / manual.
7. **New Vietnamese copy.** Recommended: accept the drafts in this brief. Options: accept / revise.
8. **"Grounded answer" state in the standard.** Recommended: yes, as a separate skill change. Options: yes / no.
