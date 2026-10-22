# Phase 4: conversation and chat UX (2026-10-22)

## Summary

- **Plan:** [Phase 4 plan](../plans/2026-10-20-phase4-conversation-chat.md), Parts 4a to 4f; [roadmap](../roadmap.md) row 4.
- **ADRs:** [ADR 0023](../adr/0023-conversation-model.md) (conversation model) and [ADR 0034](../adr/0034-conversation-workspace-and-explanation-ui.md) (workspace and explanation UI). Both were accepted at gate G-A on 2026-10-20, with ADR 0034 §5 deferred.
- **Branch:** `phase4/conversation-chat`, cut from `main` at `b52f979` (Phase 3 merged). Not pushed and not merged.
- **Execution:** subagent-driven development under the development harness. Each task went through contract, `check-scope`, fresh-context review, gate evidence on a clean commit, feature flip, handoff and `close-check`. Review records are in `harness/state/4/reviews/`.
- **Result:** one new profile toggle, `features.conversations: off | shadow | on`. It is `off` by default and `off` in every committed profile.
  - In `on`, a conversation is a thread of runs.
  - A message is routed to the question the user saw: it starts a run, answers the pending question, or is refused with a hint.
  - A new run carries a bounded set of hints from at most five earlier runs, fixed at admission. The hints are refs from complete reads, checked typed answer values and the user's own words.
  - `on` needs `features.context_assembler`.
  - The UI shows the conversation as a thread, with a server-listed sidebar and a closable artifact workspace. The workspace has Decision, Result, Sources and Activity tabs, and shows citations and the explanation as grounded, not verified.
- **Carried context is a hint and never evidence of the new run.** The carried items are never an `ApprovedFact`, never part of the approval baseline and never a staleness re-read target. Validation, approval and verification use only the new run's own reads.
- **A `GROUNDED` end is not verified** (PR-19), in the server and in the UI.
- **4e.5 shipped; 4e.6 was deferred.** 4e.5 (citations and the explanation UI) shipped in Phase 4. 4e.6 (the rationale on the approval card) was deferred at G-A, because ADR 0034 §5 was deferred. It moves to a named follow-up.
- **Evidence:** levels 1 to 3 are fixture evidence: the simulator, scripted and authored drivers, the memory and test Postgres stores, and the conformance mock API for the UI. The thread corpus is authored fixture input, not model evidence (PR-29). The live check 4f.2 has not run; it runs only on the owner's instruction.

## What changed

| Task | Commits | Content |
|---|---|---|
| 4a.1 | `3ceeb48`, `bca8306`, `1980b3f` | ADR 0023 and ADR 0034 written; plan amended (D15 citations from `grounded_answer` and `proposal.created`, values from `actions[].approved_facts`) |
| 4a.2 | `a517e91`, `f8aec01` | Gate G-A: ADRs accepted; ADR 0034 §5 deferred, so 4e.6 is deferred |
| 4b.1–4b.5 | `56463fb`, `fb80f63`, `2f1d5a7`, `039b6af`, `2ef6d5a`, `0e78bfe`, `1efbcc9` | Chat defects: `status.undefined`, reply label noise, Context chip copy, sidebar reply-pending state; review resolved at G-0 |
| 4c.1 | `6c914e2`, `0538e6e`, `b4f120a` | `features.conversations`, `RunModes.conversations`, `CONVERSATION_CONTEXT_FAILED`, the `on` → `context_assembler` startup rule |
| 4c.2 | `761f102`, `5fa79bc`, `23432a3` | `contracts/conversation.py`: `Conversation`, `CarriedRef`, `CarriedAnswer`, `CarriedRun` (no text in the conversation record) |
| 4c.3 | `8819ef6`, `522c44a`, `caec990` | `ConversationStore` on both stores, Postgres migration 0007, `FOR UPDATE` on the conversation row |
| 4c.4 | `c50c5a1`, `38e67ef`, `76af4fb` | Answer value formats (`contracts/value_formats.py`), checked at admission |
| 4d.1 | `69b7bb0d`, `28e29763` | Kernel message routing (ADR 0023 §4): start, answer, refuse; idempotency, `KEY_REUSED` |
| 4d.2 | `95169a02`, `e5861e64`, `c2cf5fb` | Carried context (`kernel/carried.py`), rendered fenced in the pack's `recent_turns` layer; `conversation.context_carried` |
| 4d.3 | `2796508b`, `82368007`, `a110063c`, `88e874af` | `conversations: shadow` with its consumer `conversation.compared`, and `conversation.shadow_failed` |
| 4d.4 | `c7402764`, `66bd694b`, `07be2cf0` | HTTP routes: `POST/GET /v1/conversations`, `GET /v1/conversations/{id}`, `POST /v1/conversations/{id}/messages` (202 `{route}`), `GET /v1/me/features`; the bundle's `conversation` key |
| 4d.5 | `b7555680`, `e023b30c` | Fixture conversation thread end to end over HTTP on both stores |
| 4d.6 | `18df9713` | G-B 3: a `reply_to` naming an ended or absent run is refused (`QUESTION_CHANGED`) |
| 4e.1 | `a720c991`, `62a29b83` | Chat surface gap audit and the conversation-thread brief; gate G-B |
| 4e.2 | `922d793c` | Mockup study `research/mockups/conversation-thread-v1/`; gate G-C (variant A1) |
| 4e.3 | `89112fff`, `4682f487` | ui-core conversation state, the client methods and the controller fallback rules |
| 4e.4 | `29f85a26`, `b7869105`, `da561bf9` | Thread view, server-listed sidebar, closable workspace; axe-core 4.10.3 (dev only) |
| 4e.5 | `e2760b1a`, `d3678423`, `5bdfbf1e` | Citations and the explanation, grounded not verified |
| 4e.7 | `1a7f0483`, `0d79968c` to `356341f4`, `eb543338`, `9a8eb109` | G-D UI review and its fixes 4.U1 to 4.U7, plus the VI fixes ([resolution](../reviews/2026-10-22-conversation-thread-ux-review-RESOLUTION.md)) |
| 4.R2 | `dfeeadb` | `context.noHost` VI says "yêu cầu" (advisor ruling on the owner's delegation) |
| 4.R1 | `50103d72` | Phase-review tests: an UNKNOWN write and a crash in a conversation-linked run (KB-1) |
| 4f.1 | `09bc0ba`, `92aa9cc`, `84630ae9`, `815e0411`, this commit | Phase-close ADR and design lines, README and roadmap, this handoff |

Task-level detail, rulings and evidence are in `harness/state/4/handoffs/*.json` and `harness/state/4/reviews/*.json`.

## What was verified

Every task's own gate passed on a clean commit (`harness/state/evidence/gates/<task>/`). The UI tasks also ran `make e2e`; their handoffs quote the counts.

End-of-phase levels 1 to 3 ran on a clean tree. All results are fixture evidence; none is live.

```text
# Level 1: full
uv run e-agent-harness gate full  -> ok, pytest 2223 passed, 32 skipped; pnpm --dir ui check ok (commit 815e041, clean tree)
harness/state/evidence/gates/4f.1/2026-10-22T04-18-51.228455+00-00-full.json

# Level 2: pg
uv run e-agent-harness gate pg    -> ok, 1312 passed on Postgres e_agent_test (commit 815e041, clean tree)
harness/state/evidence/gates/4f.1/2026-10-22T04-20-28.589529+00-00-pg.json

# Level 3: make e2e
uv run e-agent-harness gate e2e   -> ok, make e2e exit 0, 219 passed, 4 skipped (commit 70ac1a5, clean tree)
harness/state/evidence/gates/4f.1/2026-10-22T03-58-25.722424+00-00-e2e.json
```

No `src/` or `ui/` file changed between `70ac1a5` and `815e041`; only tests (4.R1) and documentation did.

An earlier level 1 and 2 run on `e57fea59`, before 4.R1, gave 2221 passed / 32 skipped and 1310 passed (same directory).

A secret scan (`gitleaks git` over `b52f979f..HEAD`) scanned 158 commits and found no leaks. It does not read image content.

### Level 4: live check (4f.2)

**Attempted 2026-10-22 and blocked at identity, before any mutation.** The attempt followed the advisor's go on the owner's delegation.

- `odoo_sandbox.py info` reached the sandbox at `http://localhost:8069` and got `OdooRejected: 401 REJECTED` on the bridge's `sandbox_info` call.
- `env_check.py` ran against database `training19_demo`, server 19.0-20260630. Its key check was skipped: "database or API key not provided".
- Nothing was seeded, reset, upgraded or started. The live profile was not touched, and the domain-erp re-pin did not run.
- The key value and the secret store were not read.

`info` authenticates with the admin key `E_AGENT_ODOO_ADMIN_KEY` from `live.env` (`scripts/odoo_sandbox.py:55-56`), so the rejected key is the admin key. Both keys were last stored on 2026-10-20. What unblocks it is an owner step: renew both keys as on 2026-10-20. The admin key goes into `live.env`, and the integration key is set with `uv run e-agent secret set secretref:local/odoo-integration`. After that, step A (identity, the harness `live` gate, the re-pin) runs again.

Until then the live check has not run. The rest of this section describes how it will run. It runs only on the owner's instruction, through the `live-sandbox` skill, in the order the plan's "Live check" section gives. The owner's instruction is also the Phase 3 ruling's trigger: step 3 is the first qualified live write with `context_assembler: on`.

## Phase review

- **Whole branch** (`4-phase.json`, fresh Claude context): rework on P4-1, which flagged that no `make e2e` evidence was recorded. Fixed: the `e2e` gate ran on a clean tree. The other findings were Low:
  - P4-2 and P4-3, stale status lines, were fixed in the docs pass.
  - P4-4 is the shadow comparison's blind spot, now documented in ADR 0023.
  - P4-5 is the `updated_at` clock.
  - Areas not reached in that pass were covered by `4-phase-r2.json` (accept):
    - the e2e evidence;
    - value formats enforced at admission;
    - migration 0007 forward-only, checksummed and tenant-scoped;
    - the conformance mock matching the server's shapes field by field.
- **Docs pass** (`4f.1-docs.json`): accept. D4-1 (status wording repeated outside the roadmap) is fixed.

### Final check

Codex was not used. Two fresh-context Claude kernel reviewers ran instead, adjudicated by the advisor. The plan allows this: Codex when it has quota, otherwise two Claude reviewers, following the owner's ruling for Phase 3 on 2026-10-20.

- **Kernel A** (`4-kernel-A.json`): accept. KA-1 to KA-4 are Low notes.
- **Kernel B** (`4-kernel-B.json`): accept. Two findings were acted on:
  - KB-1 (no committed test for an UNKNOWN write or a crash in a linked run) became task 4.R1.
  - KB-2 (the refusal hint says "stop" under `NEEDS_RECONCILIATION`) is an ADR 0023 phase-close note.

  KB-3 to KB-5 are follow-ups.
- **Adjudication:** kernel A and B accept. KB-1 is fixed in 4.R1, KB-2 is documented, and the rest are follow-ups.

## Rulings

These are the main rulings. The full list, each with its cost if wrong, is in the SDD ledger and in each task handoff's `rulings`.

- Routing follows the profile toggle; carry and compare follow the run's pinned mode.
- Every fallback is one write (PR-17).
- `off` is refused in the kernel facade.
- The plan's "never FORBIDDEN" wins over `/inputs` parity.
- In `on`, a legacy (unlinked) run's answer goes through `/inputs` (C3-1).
- The stop control follows EA-4:
  - enabled while active;
  - disabled with "Nothing is running" otherwise;
  - disabled with the safe status check while the result is unconfirmed.
- Phase 3 internal events are hidden in the timeline. Failure and fallback events get labelled rows.
- E5-1: the outcome's argument list is labelled "Values of this action", so a free-text answer field is never shown as verified. A per-field label from the server needs an ADR.
- G-D fixes stayed inside 4e.7. 4.U4 keeps the workspace's inner scroll region, with a sticky head and a scroll cue. 4.U5's button only opens. V-3: the user's task is "yêu cầu" everywhere.

## Owner decisions

- **G-0**, 2026-10-20: "1 ok, rest yes". Later: "VI ok" for the 4b.5 strings, recorded in the [chat-defects resolution](../reviews/2026-10-20-chat-defects-ux-review-RESOLUTION.md).
- **G-A**, 2026-10-20: "1 accept 2 accept 3 defer 4 ok 5 ok 6 ok 7 yes". This accepted ADR 0023 and ADR 0034, deferred §5 (and with it 4e.6), confirmed D15, accepted the four never-carried refs, and ruled that a carried ref comes only from a complete read.
- **G-B and G-C** were delegated by the owner to the advisor ("advisor can decide all on behalf me"; "Advisor"). The answers are recorded in the plan's 4e.1 and 4e.2 sections.
- **G-D**, 2026-10-22, answered by the owner directly: "Fix all". This is read as: fix 4.U1 to 4.U7 and the flagged VI rows V-1 to V-4, and accept the 68 unflagged VI rows.

### Delegated owner answers (2026-10-22)

The owner replied "Ask advisor and continue" to three questions, and the advisor ruled on each:

1. **The 33 "New VI since G-D" rows:** accepted.
2. **`context.noHost`:** changed to "yêu cầu" in task 4.R2 (`dfeeadb`).
3. **The live check 4f.2:** go, with hard stops:
   - identity is checked first;
   - the pin is checked before any mutation;
   - the check stops on an expired key, `NOT_READY`, a missing secrets path, or a pin or identity mismatch;
   - no bridge upgrade.

   The owner can countermand this in one word. Merge and push still wait for the owner's explicit ask.

## Not implemented or not proven

- **4e.6**, the rationale on the approval card (ADR 0034 §5), is deferred to a named follow-up.
- **No live result.** Conversations have not run against the sandbox or a live model (4f.2).
- **UI checks** are browser mechanics on the conformance mock only: no real `on` server, and no assistive-technology, device or user testing.
- **Refusal causes in the mock.** The mock reduces every refusal to one CONFLICT, so the real refusal triggers (a stale revision, a reused key) are proven by the server tests, not end to end (P4R-2).
- **Follow-ups:**
  - `RuleFindings.tsx:24` shows raw rule statuses in the approval card.
  - A server declaration of free-text answer fields, which needs an ADR (E5-1 option b).
  - The `contracts/context_pack.py` `Dropped` docstring needs the carried ref forms (B2-4).
  - The `updated_at` clock: KA-3 = KB-3 = P4-5.
  - The `runs_by_conversation` index does not cover the tie-break (KB-4).
  - `list_conversations` makes one query per conversation (KB-5).
  - The coordinator imports the private `_Turns` (KA-4).
  - The focus-not-obscured spec does not cover the split layout and runs in Chromium only (GS-1).
  - A state-aware refusal hint under `NEEDS_RECONCILIATION` (KB-2).
  - The G-B 8 follow-up: a "grounded answer" state in the `ag-ux-foundations` state model, with the EA-10 source moved to ADR 0034. This is outside Phase 4.
- **Harness gotcha (ENG-WORK-3).** Three reviewers stopped at their 40-turn limit this phase (4e.4, the whole-branch review, kernel B), and each had to be resumed to write its JSON. The proposal is to add a line to `eng-review` telling reviewers to split broad scopes and write the JSON by turn 30. That skill was outside this task's scope, so this is a named follow-up.

## Incidents

- A stale background `until grep` loop from this session (2026-10-18) was found and killed during Phase 4. Two processes belonging to another session, in `~/dev/lab/validity`, were not touched.
- No container other than `e-agent-ledger` (test database `e_agent_test`) was used.

## Changes outside the repository

None.
