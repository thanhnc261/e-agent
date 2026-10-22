# Review: conversation thread UI (Phase 4, Tasks 4e.3 to 4e.5)

- **Artifact:** the product UI under `ui/`, branch `phase4/conversation-chat` at `2343467d` (HEAD; the last `ui/` change is `5bdfbf1e`). The diff reviewed is `2ac2b015..HEAD -- ui/`: 47 files, 5815 insertions, 143 deletions, from commits `89112fff`, `4682f487` (4e.3), `29f85a26`, `b7869105`, `da561bf9` (4e.4), `e2760b1a`, `d3678423`, `5bdfbf1e` (4e.5).
- **Brief:** [research 20](../../research/20-conversation-thread-brief.md), approved at G-B (2026-10-21; answers "1 A, 2 group, 3 refuse, 4 hint, 5 both, 6 auto, 7 accept, 8 yes", recorded in the [Phase 4 plan](../plans/2026-10-20-phase4-conversation-chat.md), Task 4e.1). Mockup: `research/mockups/conversation-thread-v1/`, variant A1 as rendered (G-C, 2026-10-22, Task 4e.2). Earlier audit: [chat surface gap audit](2026-10-21-chat-surface-gap-audit.md).
- **Reviewer and date:** Claude (`ag-ux-review`, review mode), task 4e.7, 2026-10-22. Feeds owner gate G-D.
- **Standard:** ag-ux-foundations at `3ab6d7c2` (last commit touching `.agents/skills/ag-ux-foundations`).

## Verdict

**Accept with findings.** No Blocker and no High finding. The thread, the closable workspace, the refusal path, the labels on the agent's words and the grounded-not-verified wording hold the binding requirements (EA-1 to EA-10, EA-16) in every state reached. Four Medium findings remain: carried context is not shown (brief item 8 is unbuilt), the narrow workspace view hides Stop and the stream status, the thread opens scrolled to the top on narrow and Compact surfaces, and a tall decision sits in an unindicated inner scroll region on desktop. Three Low findings are also open. 81 new or changed Vietnamese strings are listed for the owner: 8 were accepted at G-B, and 73 are to be confirmed (72 new since G-B, 1 changed). 5 rows are flagged.

Counts: Blocker 0, High 0, Medium 4, Low 3.

## What was run and inspected

| Check | Command or method | Result |
|---|---|---|
| Product checks | `cd ui && pnpm check` on `2343467d` | **Exit 0.** `tsc -p tsconfig.json` clean; "All matched files use Prettier code style!"; Vitest "Test Files 28 passed (28) · Tests 240 passed (240)"; depcruise "✔ no dependency violations found (173 modules, 501 dependencies cruised)"; "ok  no provider identifiers in ui/"; build of web, overlay and reference apps "✓ built" |
| Conformance | `cd ui && pnpm conformance` on `2343467d`, after the build above | **Exit 0.** "Running 205 tests using 1 worker" … "201 passed (1.7m)", "4 skipped", 0 failed. The 4 skipped are the two reference-UI tests in `contract.spec.ts` (":78 a conversational reply is labelled as not verified…", ":135 a clarification without kind…"), `overlay-visual.spec.ts` and `visual-review.spec.ts`, all opt-in by design |
| Automated accessibility | The axe states inside the run above (axe-core 4.10.3, WCAG 2.2 AA tags) | 14 states, 0 violations each, 27 to 33 rules run per state: empty thread, decision open, workspace closed, refused message (light, dark, high contrast), verified result, narrow workspace, legacy group, off per-run view, grounded explanation (light, dark, high contrast), explanation from the activity |
| Scripted captures | A scratch Playwright config and spec outside the repository, against the fixture-profile server on port 8797 serving `ui/dist/web`, with the conformance `MockApi` (`features: on`) | 125 screenshots and 5 measurement logs in `/private/tmp/claude-501/-Users-thanhnguyen-dev-projects-personal-e-agent/30e35c7d-9cc1-475e-b4fa-41eeb645f95a/scratchpad/4e7-shots/` (below, shots are named relative to that folder). Horizontal overflow was 0 px in every capture |
| Viewports | 320×720, 390×844, 768×1024, 1440×1000, 844×390 (landscape); 1280×900 at 200 % text; 1280×800 and 1440×900 for a ten-field card | Eight thread states at every width (`<state>-<vp>.png`), and at the narrow widths again after opening the workspace (`<state>-<vp>-workspace.png`). Docked, Compact and Workbench at 1440 (`surface-*-decision-1440.png`, `empty-*-1440.png`) |
| Themes | `?theme=dark`, `?theme=high-contrast`; `emulateMedia({ forcedColors: "active" })` | Decision, grounded and verified at 1440 in dark and high contrast; decision, grounded, verified, refused and empty in forced colours. Computed border and colour values were logged for tabs, Stop, Send and the agent's-words figures |
| Keyboard only | Composer → Shift+Tab to the run card's "Open the decision" → Enter → Tab to "Review and approve" → Enter → Escape → Escape. Also Enter, Space and click on Open at 1440 and 390, and reopening after closing by click, Escape and keyboard | Focus moves to the workspace heading on every open (`measurements2.jsonl`, `measurements3.jsonl`). Enter on Approve focuses the confirm prompt, not Confirm; the first Escape returns to Approve; the second closes and returns focus to Open. No decision was posted (`decisions: 0`). Every focused control showed a 2 to 3 px solid outline |
| Language | `?lang=vi` on the grounded explanation and the verified activity | Text captured in `vi-grounded-workspace.txt` and `vi-verified-activity.txt` |

## State mapping

Mapped on 2026-10-22, in `conversations: on` unless stated. Each artifact state maps to one normative state.

| Artifact state | Normative state | Reached how |
|---|---|---|
| Empty thread with the AI disclosure (`thread-empty`) | Ready | `#/task` with no conversation; also Docked, Compact and Workbench (`empty-*.png`) |
| Reply waiting ("Your turn") | Needs input | `input.requested` with `kind: reply` on the latest run (`reply-*.png`) |
| Clarification ("Your answer is needed") | Needs input | `input.requested` with no kind (`clarification-*.png`) |
| Running ("Working on it") | Working | Latest run `RUNNING` (`running-*.png`) |
| Waiting approval ("Needs review"), workspace open or closed | Awaiting decision | `waitingForApproval()` (`decision-*.png`) |
| Message refused while a decision waits | not a task state: a composer state over Awaiting decision | 409 `CONFLICT` "wait, decide the approval, or stop the run" (`refused-busy-*.png`) |
| Answer to an ended run refused ("The question changed") | not a task state: a composer state; the run stays as it ended (G-B 3) | 409 `CONFLICT` "the question changed; read it again" (`refused-question-1440.png`) |
| Completed · verified | Verified complete | `finish()` with `outcome.reported` VERIFIED (`verified-*.png`) |
| Completed · grounded, not verified | none: product state, judged by AG-APPR-6, AG-EXPL-2 and AG-ID-1 (G-B 8 adds a normative state as a separate skill task) | `groundedEnd()` (`grounded-*.png`) |
| Task stopped | Failed | `finish(…, "FAILED")` (`failed-*.png`) |
| Result not confirmed, Stop replaced by the status check | Outcome uncertain | `NEEDS_RECONCILIATION` (`reconcile-*.png`) |
| Per-run view in `off`, `shadow` or a failed features read | not a task state: a mode | `fallback-off-1440.png`, `fallback-shadow-1440.png`, `features-failed-1440.png` |
| "Earlier tasks · this session · last seen" group | not a task state: a placement | `legacy-1440.png`, `legacy-open-1440.png` |

Blocked by rules, Decision invalidated, Rejected, Executing, Verifying and Cancelled or stopped render through the same slots inside the workspace and are covered by the existing conformance specs on the per-run view (`contract.spec.ts` 1 to 8, `live.spec.ts`). They were not captured inside the thread in this review (see Limits). Normative states not reachable: none.

## Binding requirements

Scored first (rubric §2.1), on the thread view in `conversations: on`, and on the per-run view only where the diff changed it.

| ID | Score | Evidence | Finding |
|---|---|---|---|
| EA-1 | met | The thread is built only from the conversation snapshot and run events (`selectThread`, `ui-core/src/store.ts`). The UI never routes a message: the server's `route` decides (`controller.ts`, `sendMessage`). Carried items are never shown as facts | none |
| EA-2 | met | The card is unchanged inside the workspace (`ConfiguredSlot name="approval"`). Conformance `contract.spec.ts` 1 to 2c pass. "the workspace closes and reopens…" checks the card text is byte-identical | none |
| EA-3 | met | "Completed" (never "verified") on sidebar rows without a reason code (`TaskNavigation.tsx:190-225`). Neutral tone for grounded. `outcome.values` claims no verification. The agent's words are labelled on the message and the result (`verified-1440-forced.png`) | none |
| EA-4 | met | `NEEDS_RECONCILIATION` disables Stop with its reason and offers "Check operation status" (`StopSlot.tsx:40-64`, `reconcile-1440.png`; conformance "the thread stop slot offers the safe check…") | none |
| EA-5 | met | The run card's line comes from recorded events only (`selectRunLine`, `selectors/thread.ts:76-80`). Rationale is shown as ids and digests only. No confidence, plan or progress estimate | none |
| EA-6 | met | `pnpm lint:neutral`: "ok  no provider identifiers in ui/" | none |
| EA-7 | met | Model text renders as inert text (`MessageText`; `Explanation.tsx:120-123` plain escaped text). No model-generated UI | none |
| EA-8 | met | Unread messages say "The messages of this run could not be read." (`thread.notLoaded`). A citation with no recorded value says "Value not recorded". A null field says "Not recorded". An unknown bundle schema or label is shown as unsupported (`Explanation.tsx:82-87`, `explain.label.unsupported`) | none |
| EA-9 | met | Closing the workspace resets an open confirmation to review (`Layout.tsx`, `close()` calls `controller.back()`). The close persists across a surface switch, and the draft is kept (conformance "a workspace the user closed stays closed after a surface switch", "the workspace closes and reopens…") | none |
| EA-10 | met | The conversation is the primary column. The artifact sits in a closable `aside` at about 40 % (448 px beside a 640 px thread at 1440), or in a full view with Back on narrow surfaces (`decision-1440.png`, `decision-390-workspace-full.png`) | none (4.U2 and 4.U4 concern what the workspace hides, not the hierarchy) |
| EA-11 | partial | Unchanged from the gap audit's F-15: mock texts carry "(sample)", while fixture-profile records do not. The diff adds no sample marker | inherited F-15, not re-raised |
| EA-12 | met | Dark and high-contrast captures (`*-dark.png`, `*-high-contrast.png`); axe in three themes for the refused and grounded states; `tokens/test/contrast.test.ts` in the 240 unit tests | none |
| EA-13 | not exercised | The thread adds no density-specific CSS. Compact density was not captured in the thread | Limits |
| EA-14 | partial | Controls, the current conversation, status markers and the dashed agent's-words border stay visible in forced colours, and disabled controls take GrayText. Every workspace tab is underlined | 4.U7 |
| EA-15 | met | Every status pairs a marker with text (`StatusBadge`; run card, stop slot, workspace head, sidebar `statusMarker`) | none |
| EA-16 | met | One polite region announces "Run N: status" (`Thread.tsx:31-33`). Streamed text is not in it, and focus does not move (conformance "a new run is announced politely") | none |

## Findings

### 4.U1 — Carried context is not shown for the run that used it

- **Severity:** Medium
- **Violates:** AG-EXPL-2 (the brief's "Fixed for every direction" item 8 and its "Carried context shown to the user" row, which names AG-CTX-1 and AG-EXPL-2)
- **Where:** `ui/packages/ui-core/src/store.ts:15` (`conversation.context_carried` is in `HIDDEN_EVENT_TYPES`); `ui/packages/ui-core/src/selectors/explanation.ts` (reads no `conversation` key of the bundle); no i18n key for it in `git diff 2ac2b015..HEAD -- ui/packages/ui-core/src/i18n.ts`; `docs/design/ui-architecture.md` §12 does not mention it; `decision-1440.png`, `grounded-1440-explanation.png` (neither the Sources nor the Activity tab names earlier runs)
- **Observed:** In `on`, a later run receives earlier runs' checked values and record refs as hints (ADR 0023 §6). The UI says so only in general, in the Context panel (`context.noHostThread`). No run shows which earlier runs it used. The brief fixed this for every direction ("Used earlier runs as hints: run 1, run 2", from the bundle's `conversation` key), and mockup A1 rendered it; the 4e.2 report lists "Used earlier runs as hints" among its strings. No handoff records it as deferred.
- **Expected:** AG-EXPL-2: what a run relied on is inspectable. Rated Medium: the general statement exists and nothing is presented as evidence, so no one is misled; the user cannot see which earlier answers shaped this one.
- **Recommendation:** In the workspace of a run whose bundle reports `modes.conversations: on`, list the bundle's carried run ids as links to those runs in the thread, labelled as hints and not evidence; show nothing in `shadow` (L3 selector beside `selectExplanation`, L6 in Sources or Activity). Two new strings will need VI. If the owner prefers to defer it, record the deferral in the plan and in UI architecture §12.

### 4.U2 — The narrow workspace view hides Stop and the stream status

- **Severity:** Medium
- **Violates:** AG-CTRL-1, AG-STAT-3
- **Where:** `ui/packages/layouts/src/layouts.css:113` (`.ea-thread-grid[data-workspace-open="true"] > .ea-thread-main { display:none; }`) hides the stop slot, the run card's Stop and the thread head with `ConnectionStatus`; `measurements.jsonl` "after: open-workspace" rows; `running-390-workspace.png`, `decision-390-workspace-full.png`
- **Observed:** Below 60 rem of thread width (320, 390, 768, landscape, Docked and Compact at any width), opening a run's workspace replaces the thread. In every state measured there, visible Stop controls went from 2 to 0 and the connection status from visible to hidden. The workspace head keeps the run's status badge. A running run can be stopped only after "Back to conversation". The mockup's phone view has the same shape.
- **Expected:** AG-CTRL-1 (stop at any time) and AG-STAT-3 (lost connection shown) in every view. Rated Medium: Stop is one action away (Back) and nothing is executed by being in the workspace; a stale view could still be read as current there.
- **Recommendation:** When the workspace is a full view, render a compact stop slot (Stop with its disabled reason, or the status check under `NEEDS_RECONCILIATION`) and the connection status in its head (L7 `ArtifactWorkspace`, reusing `StopSlot` and `ConnectionStatus`). Add a spec at 390 px: a running run's workspace offers an enabled Stop.

### 4.U3 — On open, the thread starts at the top; the latest run, its status and the composer are below the fold

- **Severity:** Medium
- **Violates:** AG-STAT-1, AG-ENT-3
- **Where:** `ui/packages/components/src/features/conversation/Thread.tsx` (no scroll to the latest run); `measurements2.jsonl`: Docked 390×844, latest run card top 866 px and composer top 1049 px against a 844 px viewport (`scrollY` 0); Workspace page 390×844, card top 823 px, composer 1006 px; `running-390.png`, `decision-390-docked-open.png`, `surface-compact-decision-1440.png`
- **Observed:** Opening a conversation shows run 1 first. On a phone, in Docked and in the Compact overlay, the latest run's card (with "Needs review" and "Open the decision"), the composer and the stop slot are all out of view, and the sidebar list is a closed disclosure. The mockup QA lists this exact defect as fixed in the selected study ("The thread opens at the latest run").
- **Expected:** AG-STAT-1: the agent's current state is visible; AG-ENT-3: the same in every placement (at 1440 the Workspace page shows the composer). Rated Medium: the state is one scroll away and nothing proceeds without a decision.
- **Recommendation:** When a conversation opens and when a new run is added, scroll the latest run card into view (`block: "end"` or `nearest`) without moving focus, honouring reduced motion, and keep the position on later re-renders (L6 `Thread`). Add a spec at 390 px in Docked: the latest card and the composer are in the viewport after opening.

### 4.U4 — On desktop a tall decision sits in an unindicated inner scroll region, and the workspace head scrolls away

- **Severity:** Medium
- **Violates:** AG-APPR-3, AG-STAT-1
- **Where:** `ui/packages/layouts/src/layouts.css:118` (`.ea-artifact-workspace { position:sticky; … max-height:calc(100dvh - 7rem); overflow:auto; }`); `ui/packages/components/src/features/approval/ApprovalPanel.tsx:23-28` (`scrollIntoView({ block: "nearest" })` on a new proposal); `measurements5.jsonl`; `decision-10fields-1280x800.png`, `decision-10fields-1440x900.png`
- **Observed:** With a ten-field card, the workspace scrolls inside itself. At 1280×800 its own `scrollTop` is 127 px on open, so the run title, the status badge and Close are scrolled out of view, and "Review and approve" starts at 821 px of 800. At 1440×900 Approve starts at 886 px of 900. Nothing shows that the region scrolls (macOS hides scrollbars). With the three-field fixture at 1440×1000, Approve is in view (bottom 813 px). Every term sits above Approve, so a user who reaches Approve has passed the terms. The run card and the stop slot in the thread still show the run's status; only the workspace's own heading, badge and Close leave view.
- **Expected:** AG-APPR-3: material terms and the decision are not in an unindicated scroll region; AG-STAT-1: the workspace's status stays in view. This is the gap audit's F-5 shape, new here because the workspace container is new in 4e.4. Rated Medium: the confirm step remains and no term is skipped on the way to Approve; the cost is a hidden control and a hidden status.
- **Recommendation:** Let the side workspace scroll with the page (drop the inner `max-height` and `overflow`), or keep it but make the workspace head sticky inside it and add a visible scroll cue. Scope the approval panel's bring-into-view so it never scrolls the workspace head out (L7 `layouts.css`, L6 `ApprovalPanel`). Record the result with the F-5 card follow-up.

### 4.U5 — "Open the decision" stays the label while the decision is open, and pressing it closes the workspace

- **Severity:** Low
- **Violates:** AG-CTRL-2, AG-A11Y-2
- **Where:** `ui/packages/components/src/features/conversation/RunCard.tsx:85-98` (`aria-expanded={open}`, `onPress` toggles, the text never changes); `decision-1440.png`
- **Observed:** At 1440 the workspace opens by itself for the decision, and the run card's primary button beside it still reads "Open the decision". Pressing it closes the workspace. `aria-expanded="true"` tells assistive technology; the visible text does not.
- **Expected:** A disclosure control's visible state matches its effect (AG-A11Y-2); dismissal is clear (AG-CTRL-2). Polish: nothing is lost on close, and the draft and the card state are kept.
- **Recommendation:** While open, either label it for its effect ("Close the decision", "Shown in the workspace") or make it open-only (bring forward and focus the workspace) and leave closing to the workspace's Close and Back.

### 4.U6 — Server enum strings are shown untranslated in the explanation (handoff E5-3)

- **Severity:** Low
- **Violates:** AG-SOC-1
- **Where:** `ui/packages/components/src/features/outcome/Explanation.tsx:267` (rule `status`), `:320` (approval `decision`), `:333` (receipt `status`), `:346` (outcome `status`); `vi-grounded-workspace.txt` ("Kết quả · Có dẫn chứng, chưa xác minh · succeeded"); `grounded-1440-explanation.png`. The existing timeline detail does the same (`store.ts:214`, "Đã xác minh kết quả · VERIFIED" in `vi-verified-activity.txt`), which predates this diff.
- **Observed:** The explanation shows the server's lowercase or uppercase enums ("succeeded", "PASS", "approved", "VERIFIED") verbatim beside translated labels, in both locales.
- **Expected:** Terminology that matches the user's language (AG-SOC-1). Low: the translated label beside each enum carries the meaning, and showing an unknown value verbatim is the right fallback.
- **Recommendation:** Map the known enums to i18n keys with the verbatim value as the fallback, as `translateServerHint` does (L3 `i18n.ts`, used by L6 `Explanation`). New VI strings for G-D.

### 4.U7 — Under forced colours every workspace tab shows an underline

- **Severity:** Low
- **Violates:** EA-14
- **Where:** `ui/packages/layouts/src/layouts.css:104` (`border-bottom:2px solid transparent` on every tab), `:120-121` (only the selected tab gets `Highlight`); `measurements4.jsonl` (forced: unselected tabs `border-bottom` `rgb(0, 0, 0)` 2px, selected `rgba(5, 0, 73, 0.8)` 2px); `verified-1440-forced.png`, `grounded-1440-forced.png`
- **Observed:** Forced colours turn the transparent borders of unselected tabs into CanvasText, so all three tabs are underlined, and the selected one differs only by weight and a near-identical colour. The mockup QA fixed the same defect ("unselected tabs showed an underline").
- **Expected:** EA-14: operable and legible in forced colours, with the current item identifiable. Low: the selected tab is still bold and `aria-selected`.
- **Recommendation:** In `@media (forced-colors: active)`, give unselected tabs `border-bottom-color: Canvas` and keep `Highlight` for the selected one. Add a workspace state to `forced-colors.spec.ts`.

## Known open items from the handoffs

| Item | Disposition | Evidence |
|---|---|---|
| T4-7 (legacy "now" versus "last seen") | **Confirmed as behaviour, not a finding.** The legacy row and the opened legacy view show only the current state, and attaching the run overwrites the stored value (`controller.ts`, `remember()`). On reload the remembered run is re-attached automatically, so the "last seen" value was already the current one before the user opened it: the run was "Needs review", ended "Task cancelled" while away, and both the row and the view showed "Task cancelled". What is shown is read from the server and labelled "last seen", so no criterion is violated. Mockup A1 showed "Status read from the server just now. This session last saw: Needs review", which the build drops. The owner may want it back; see Opinions | `legacy-1440.png`, `legacy-open-1440.png`, `measurements.jsonl` (`legacyBeforeOpen`, `legacyAfterOpen`); mockup `screenshots/a1/legacy-1440.png` |
| E5-3 (server enum strings untranslated) | **Confirmed:** 4.U6 | as 4.U6 |
| E5-5 (mismatched citations listed as sources) | **Rejected: no reachable case.** In a run pinned `grounded_answers: on`, a citation that is not `RESOLVED` makes the answer not `grounded` (`src/e_agent/kernel/grounding.py:236-238`), and `_grounding_probe` returns the `KERNEL-CITATION` repair before the answer's action and its `proposal.created` exist (`:371-373`, called at `:390-392`; the event is written at `:427`, after the probe). Past `max_validation_repairs` the repair ends the run `FAILED` with `VALIDATION_FAILED` instead of proceeding (`src/e_agent/kernel/ir_on.py:202-205`). So no `proposal.created` in an `on` run carries a mismatched or unresolved citation. `shadow` citations are never shown (`ui/packages/ui-core/src/selectors/explanation.ts:351`), and the bundle's `modes` is the run's pin (`src/e_agent/kernel/evidence.py:306-308`). The UI relies on that server invariant, which EA-1 allows | code references at left |
| R5-1 ("Outcome verified" whatever the status) | **Rejected as stated.** The timeline maps `outcome.reported` to `outcome.<status>` (`store.ts:222`), and `OutcomeStatus` is only VERIFIED, FAILED or UNKNOWN (`src/e_agent/contracts/outcome.py:13-16`), each with its own label (`i18n.ts:135-139`). The run card's line uses the same key (`RunCard.tsx:70`). Nothing renders `event.outcome.reported` ("Outcome verified", `i18n.ts:74`, `:426`), and `outcome.references` ("Verified references", `:142`, `:494`) is unused. Deleting both keys is hygiene, and it removes two strings that would claim verification if reused | `grep` over `ui/packages` and `ui/apps`: no consumer outside `i18n.ts` |
| EA-14 (dashed border under forced colours) | **Rejected.** Both `.ea-agent-words` and `.ea-explain-words` keep a 1 px dashed CanvasText border in forced colours, and the meaning is carried by the visible label ("The agent's words · …"). A different forced-colours defect was found (4.U7). The missing forced-colours spec for the explanation is under Limits | `measurements.jsonl` (`forced` rows: `style: dashed`, `color: rgb(0, 0, 0)`); `verified-1440-forced.png`, `grounded-1440-forced.png` |
| E5-1 option (b) as a follow-up | **Confirmed as an unbuilt follow-up, by design.** Option (c) shipped: `outcome.values` now reads "Values of this action" / "Giá trị của hành động này" and claims no verification. Labelling a typed answer's free-text field as the agent's words needs the server to declare free-text fields, which needs an ADR (ADR 0034 §4). Not a finding in this review; it stays a named follow-up | `git diff 2ac2b015..HEAD -- ui/packages/ui-core/src/i18n.ts`; `harness/state/4/handoffs/4e.5.json` |

## Brief evaluation criteria

From the brief's "Browser checks will verify" list and its "Fixed for every direction" items.

| Check | Result | Evidence |
|---|---|---|
| Every state is reachable | Yes, for the brief's eleven rows | State mapping above |
| The workspace closes and reopens with the conversation, draft and approval state kept | Yes | `conversation.spec.ts` "the workspace closes and reopens…" and "a workspace the user closed stays closed after a surface switch" (passed); keyboard path above |
| A refused message keeps the draft and leaves the card unchanged | Yes. The hint sits inside the composer above the draft, focus stays in the input, and the value is kept | `refused-busy-1440.png`, `refused-busy-390.png`, `refused-question-1440.png`; `measurements.jsonl` (`focused: composer-input`, `value: north`); conformance "a message during approval shows the hint…" |
| Announcements are polite and focus does not move | Yes | conformance "a new run is announced politely" (`role="status"`, no alert); `Thread.tsx:31-33` |
| Four surfaces at 320, 390, 768, 1440, landscape and 200 % text | Yes, with 4.U2 and 4.U3 | `*-320.png` … `*-landscape.png`, `surface-*-1440.png`, `decision-text200-1280.png`, `grounded-text200-1280.png`; 0 px overflow everywhere |
| Light, dark, high contrast and forced colours | Yes, with 4.U7 | `*-dark.png`, `*-high-contrast.png`, `*-forced.png`; axe in three themes for the refused and grounded states |
| Keyboard only | Yes | Keyboard row above |
| No external requests | Not measured in this review | Limits |
| Every sample labelled as a sample (EA-11) | Unchanged from the gap audit's F-15: mock texts carry "(sample)", while fixture-profile records do not | Inherited |
| Item 1, mode first; item 2, one composer and server routing | Yes | `controller.ts:285-382`; `conversation.test.ts` (in the 240 unit tests) |
| Item 3, refusal hint localised, `correlation_id` on demand | Yes | `RefusalHint.tsx`; `i18n.ts` `translateServerHint` |
| Item 4, runs visible as runs | Yes | `decision-1440.png` |
| Item 5, the reply label on the first reply, then "not verified" | Yes | `reply-1440.png`; `Thread.tsx:144-157` |
| Item 6, AI disclosure and capability detail in the empty thread on every surface | Yes, in `on` (gap audit F-1 resolved for the thread) | `empty-*.png`; `measurements.jsonl` (`disclosureVisible: true` on Docked, Compact and Workbench) |
| Item 7, the agent's words labelled on the message and the result; the grounded pill not in the verified colour | Yes (gap audit F-4 and F-7 resolved) | `verified-1440-forced.png`, `grounded-1440-explanation.png` |
| Item 8, carried context visible in the workspace | **No:** 4.U1 | as 4.U1 |
| Item 9, sidebar from `GET /v1/conversations`, legacy group, no thread text in browser storage | Yes. `remember()` writes only legacy runs in `on` (`controller.ts`); the pending message is kept in memory only | `legacy-1440.png`; code at left. "Your turn" on a non-current row was not captured, because the mock always lists `reply_pending: false` (Limits) |
| Item 10, focus return, axe per state, container queries | Yes | Keyboard row; 14 axe states; `layouts.css` container query `ea-thread` at 60 rem |

## New VI since G-B

The owner accepted the Vietnamese drafts at G-B (decision 7) on the condition that new strings are flagged at G-D. This table lists every key that is new or changed in `git diff 2ac2b015..HEAD -- ui/packages/ui-core/src/i18n.ts`, cross-checked against the 4e.2 to 4e.5 reports in `.superpowers/sdd/2026-10-20-phase4-conversation-chat/`. The diff is the authority. No key was removed, and every EN key has a VI entry (`vi` is typed `Record<MessageKey, string>`, so `tsc` would fail otherwise).

- **81 rows:** 8 accepted at G-B (the brief's drafts, shipped verbatim), 72 new since G-B, and 1 changed since G-B (`outcome.values`). That makes 73 rows to confirm.
- The 4e.2 report's mockup-only strings ("Workspace closed", "Go to the decision", "Read the run again", "This session last saw", "Used earlier runs as hints") are not in the product, so they are not listed.
- **No VI string claims verification that its EN does not.** Every VI "xác minh" row has "verif" in its EN. The only "kiểm tra" rows without "check" in EN are `explain.absent` and `explain.missing`, which use "hồ sơ kiểm tra" for "audit record", the term already in the owner-confirmed `evidence.unsupported`.
- **Flags (5 rows):**
  - **V-1, `citation.valueNotRecorded`** "Không ghi lại giá trị". It was accepted at G-B, but it can read as an imperative, "Do not record the value", and it differs from the new `explain.notRecorded` "Không được ghi lại". Suggest "Giá trị không được ghi lại" (or "Chưa ghi nhận giá trị").
  - **V-2, `nav.lastSeen`** "lần cuối" means "last time" and drops "seen". Next to a status it reads "last time · Completed". Suggest "thấy lần cuối", matching `nav.legacyNote` "trạng thái phiên này thấy lần cuối".
  - **V-3, `conversation.refusedBusy`** (accepted at G-B) **and `run.nothingRunning`** say "tác vụ" for task. The button they sit beside is `run.cancel` "Dừng yêu cầu", and the older VI strings say "yêu cầu" 21 times. So the hint tells the user to "dừng tác vụ" with a button labelled "Dừng yêu cầu". The same split runs through the new strings (`thread.legacyNote`, `nav.legacy`, `explain.*`). The owner should pick one term. A wording issue, not a mistranslation.
  - **V-4, `explain.revision`** "Phiên bản" means "version", and the same word means "this version [of the app]" in `evidence.unsupported` and `explain.label.unsupported`. For a source revision ("Phiên bản rev-17") it may confuse. Minor.
- **Noted, not flagged:**
  - `explain.label.provider_receipt` "Hệ thống báo đã ghi, chưa xác minh" adds "đã ghi" ("recorded"), which is accurate for a receipt and claims no verification.
  - `thread.run` "Lượt" matches the existing "Lượt chạy".
  - `outcome.agentText` "Lời của agent" keeps the loanword "agent", as other VI strings do.

| # | Key | EN | VI | Task | Status | Flag |
|---|---|---|---|---|---|---|
| 1 | `conversation.refusedBusy` | This conversation is busy. Wait, decide the approval, or stop the task. | Cuộc trò chuyện đang bận. Hãy chờ, quyết định phê duyệt, hoặc dừng tác vụ. | 4e.3 | accepted at G-B (brief draft, verbatim) | Flag V-3 |
| 2 | `conversation.refusedQuestion` | The question changed. Read it again before answering. | Câu hỏi đã thay đổi. Hãy đọc lại trước khi trả lời. | 4e.3 | accepted at G-B (brief draft, verbatim) |  |
| 3 | `conversation.notSent` | This message could not be sent. Your text is kept and was not sent again. | Không gửi được tin nhắn này. Nội dung vẫn được giữ và chưa được gửi lại. | 4e.3 | new since G-B |  |
| 4 | `conversation.featuresFailed` | Conversations could not be loaded, so this message was not sent. Your text is kept. | Không tải được cuộc trò chuyện, nên tin nhắn này chưa được gửi. Nội dung của bạn vẫn được giữ. | 4e.3 | new since G-B |  |
| 5 | `outcome.values` | Values of this action | Giá trị của hành động này | 4e.5 | changed (was "Verified values" / "Giá trị đã xác minh") |  |
| 6 | `event.context.failed` | Context could not be prepared | Không chuẩn bị được ngữ cảnh | 4e.4 | new since G-B |  |
| 7 | `thread.run` | Run | Lượt | 4e.4 | new since G-B |  |
| 8 | `thread.open` | Open | Mở | 4e.4 | new since G-B |  |
| 9 | `thread.openDecision` | Open the decision | Mở phần quyết định | 4e.4 | new since G-B |  |
| 10 | `thread.openResult` | Open the result | Mở kết quả | 4e.4 | new since G-B |  |
| 11 | `thread.notLoaded` | The messages of this run could not be read. | Không đọc được tin nhắn của lượt này. | 4e.4 | new since G-B |  |
| 12 | `thread.legacyNote` | Earlier task · not part of a conversation | Tác vụ trước · không thuộc cuộc trò chuyện nào | 4e.4 | new since G-B |  |
| 13 | `thread.readThrough` | Read through | Đọc qua kết nối | 4e.4 | new since G-B |  |
| 14 | `messages.agentWords` | Written by e-agent. The result shows what was checked. | Do e-agent viết. Phần kết quả cho biết điều gì đã được kiểm tra. | 4e.4 | accepted at G-B (brief draft, verbatim) |  |
| 15 | `outcome.agentText` | The agent's words | Lời của agent | 4e.4 | new since G-B |  |
| 16 | `composer.answering` | Answering run | Đang trả lời lượt | 4e.4 | new since G-B |  |
| 17 | `refused.kept` | Not sent · your text is kept | Chưa gửi · nội dung vẫn được giữ | 4e.4 | new since G-B |  |
| 18 | `refused.details` | Details | Chi tiết | 4e.4 | new since G-B |  |
| 19 | `refused.reference` | Reference | Mã tham chiếu | 4e.4 | new since G-B |  |
| 20 | `run.nothingRunning` | Nothing is running | Không có tác vụ nào đang chạy | 4e.4 | new since G-B | Flag V-3 |
| 21 | `run.noStopReconcile` | Stopping is unavailable while the result is unconfirmed | Không thể dừng khi kết quả chưa được xác nhận | 4e.4 | new since G-B |  |
| 22 | `context.noHostThread` | e-agent also uses your earlier messages in this conversation, checked values and record references from its earlier answers, and any systems you have connected, within your permissions. These are hints, not evidence: it reads the records again before relying on them. | e-agent cũng dùng các tin nhắn trước đó của bạn trong cuộc trò chuyện này, các giá trị đã kiểm tra và tham chiếu bản ghi từ những câu trả lời trước, cùng mọi hệ thống bạn đã kết nối, trong phạm vi quyền của bạn. Đây chỉ là gợi ý, không phải bằng chứng: e-agent đọc lại bản ghi trước khi dựa vào chúng. | 4e.4 | accepted at G-B (brief draft, verbatim) |  |
| 23 | `ws.label` | Workspace | Không gian làm việc | 4e.4 | new since G-B |  |
| 24 | `ws.close` | Close workspace | Đóng không gian làm việc | 4e.4 | new since G-B |  |
| 25 | `ws.back` | Back to conversation | Quay lại cuộc trò chuyện | 4e.4 | new since G-B |  |
| 26 | `ws.earlierRun` | For an earlier run, only its recorded events are shown here. | Với lượt trước, chỉ hiển thị các sự kiện đã ghi của lượt đó. | 4e.4 | new since G-B |  |
| 27 | `tab.decision` | Decision | Quyết định | 4e.4 | new since G-B |  |
| 28 | `tab.result` | Result | Kết quả | 4e.4 | new since G-B |  |
| 29 | `tab.sources` | Sources | Nguồn | 4e.4 | new since G-B |  |
| 30 | `tab.activity` | Activity | Hoạt động | 4e.4 | new since G-B |  |
| 31 | `nav.conversations` | Conversations | Cuộc trò chuyện | 4e.4 | new since G-B |  |
| 32 | `nav.new` | New conversation | Cuộc trò chuyện mới | 4e.4 | new since G-B |  |
| 33 | `nav.legacy` | Earlier tasks · this session · last seen | Tác vụ trước · phiên này · trạng thái lần cuối | 4e.4 | accepted at G-B (brief draft, verbatim) |  |
| 34 | `nav.lastSeen` | last seen | lần cuối | 4e.4 | new since G-B | Flag V-2 |
| 35 | `nav.legacyNote` | Started before conversations. The status is the one this session last saw. | Bắt đầu trước khi có cuộc trò chuyện. Trạng thái là trạng thái phiên này thấy lần cuối. | 4e.4 | new since G-B |  |
| 36 | `nav.noConversations` | No conversations yet. | Chưa có cuộc trò chuyện nào. | 4e.4 | new since G-B |  |
| 37 | `nav.conversationsFailed` | Conversations could not be loaded. | Không tải được danh sách cuộc trò chuyện. | 4e.4 | new since G-B |  |
| 38 | `nav.completed` | Completed | Hoàn tất | 4e.4 | new since G-B |  |
| 39 | `nav.untitled` | Untitled conversation | Cuộc trò chuyện chưa có tiêu đề | 4e.4 | new since G-B |  |
| 40 | `outcome.groundedExplain` | Grounded: its sources are records this task read. Not verified: nothing read the result back independently. | Có dẫn chứng: nguồn là các bản ghi mà tác vụ này đã đọc. Chưa xác minh: chưa có bước kiểm tra độc lập nào đọc lại kết quả. | 4e.5 | accepted at G-B (brief draft, verbatim) |  |
| 41 | `citation.title` | Sources this answer cites | Nguồn mà câu trả lời này trích dẫn | 4e.5 | new since G-B |  |
| 42 | `citation.record` | Record | Bản ghi | 4e.5 | new since G-B |  |
| 43 | `citation.field` | Field | Trường | 4e.5 | new since G-B |  |
| 44 | `citation.value` | Value | Giá trị | 4e.5 | new since G-B |  |
| 45 | `citation.valueNotRecorded` | Value not recorded | Không ghi lại giá trị | 4e.5 | accepted at G-B (brief draft, verbatim) | Flag V-1 |
| 46 | `citation.unresolved` | A source that could not be matched | Một nguồn không khớp được | 4e.5 | accepted at G-B (brief draft, verbatim) |  |
| 47 | `explain.open` | Show the explanation | Hiện phần giải thích | 4e.5 | new since G-B |  |
| 48 | `explain.goal` | Goal | Mục tiêu | 4e.5 | new since G-B |  |
| 49 | `explain.facts` | Source facts | Dữ kiện từ nguồn | 4e.5 | new since G-B |  |
| 50 | `explain.rules` | Rules checked | Quy tắc đã kiểm tra | 4e.5 | new since G-B |  |
| 51 | `explain.proposal` | Proposal | Đề xuất | 4e.5 | new since G-B |  |
| 52 | `explain.rationale` | Rationale references | Tham chiếu lý do | 4e.5 | new since G-B |  |
| 53 | `explain.approval` | Approval | Phê duyệt | 4e.5 | new since G-B |  |
| 54 | `explain.receipt` | Receipt | Biên nhận | 4e.5 | new since G-B |  |
| 55 | `explain.outcome` | Outcome | Kết quả | 4e.5 | new since G-B |  |
| 56 | `explain.none` | None in this run | Không có trong lượt này | 4e.5 | new since G-B |  |
| 57 | `explain.rationaleIds` | Recorded as ids only; the text is not kept. | Chỉ ghi lại mã định danh; không lưu nội dung. | 4e.5 | new since G-B |  |
| 58 | `explain.notRecorded` | Not recorded | Không được ghi lại | 4e.5 | new since G-B |  |
| 59 | `explain.revision` | Revision | Phiên bản | 4e.5 | new since G-B | Flag V-4 |
| 60 | `explain.policy` | Policy | Chính sách | 4e.5 | new since G-B |  |
| 61 | `explain.step` | Step | Bước | 4e.5 | new since G-B |  |
| 62 | `explain.unresolvedRefs` | References that could not be matched | Tham chiếu không khớp được | 4e.5 | new since G-B |  |
| 63 | `explain.absent` | Opening this reads the task's audit record. | Mở mục này sẽ đọc hồ sơ kiểm tra của tác vụ. | 4e.5 | new since G-B |  |
| 64 | `explain.loading` | Reading the explanation… | Đang đọc phần giải thích… | 4e.5 | new since G-B |  |
| 65 | `explain.failed` | The explanation could not be read. | Không đọc được phần giải thích. | 4e.5 | new since G-B |  |
| 66 | `explain.retry` | Try again | Thử lại | 4e.5 | new since G-B |  |
| 67 | `explain.missing` | This audit record holds no explanation. | Hồ sơ kiểm tra này không có phần giải thích. | 4e.5 | new since G-B |  |
| 68 | `explain.partial` | Part of this task is not recorded, so the explanation is partial. | Một phần của tác vụ không được ghi lại, nên phần giải thích chưa đầy đủ. | 4e.5 | new since G-B |  |
| 69 | `explain.stale` | Read before the task's latest change. | Được đọc trước thay đổi mới nhất của tác vụ. | 4e.5 | new since G-B |  |
| 70 | `explain.refresh` | Read again | Đọc lại | 4e.5 | new since G-B |  |
| 71 | `explain.label.provider_read` | Read from the source system | Đọc từ hệ thống nguồn | 4e.5 | new since G-B |  |
| 72 | `explain.label.model_proposal` | Proposed by the agent | Do agent đề xuất | 4e.5 | new since G-B |  |
| 73 | `explain.label.approver_decision` | Decided by a person | Do người phê duyệt quyết định | 4e.5 | new since G-B |  |
| 74 | `explain.label.provider_receipt` | Reported by the system, not verified | Hệ thống báo đã ghi, chưa xác minh | 4e.5 | new since G-B |  |
| 75 | `explain.label.verified_outcome` | Verified by an independent check | Đã xác minh bằng kiểm tra độc lập | 4e.5 | new since G-B |  |
| 76 | `explain.label.not_verified` | Not verified | Chưa xác minh | 4e.5 | new since G-B |  |
| 77 | `explain.label.model_authored` | Written by the agent | Do agent viết | 4e.5 | new since G-B |  |
| 78 | `explain.label.grounded_answer` | Grounded, not verified | Có dẫn chứng, chưa xác minh | 4e.5 | new since G-B |  |
| 79 | `explain.label.grounded` | Grounded in this task's records | Có dẫn chứng từ bản ghi của tác vụ này | 4e.5 | new since G-B |  |
| 80 | `explain.label.unverified` | Not verified | Chưa xác minh | 4e.5 | new since G-B |  |
| 81 | `explain.label.unsupported` | A label this version does not understand | Nhãn mà phiên bản này chưa hỗ trợ | 4e.5 | new since G-B |  |

## Decision proposals (conflicts with binding requirements)

None. No criterion conflicts with an EA requirement. Two items stand from G-B and are not defects of this diff:

- G-B 8: a normative "Grounded answer" state in `state-model.md`, as a separate skill task.
- Moving EA-10's binding source to ADR 0034.

## Strengths

- **Server authority holds everywhere.**
  - The thread is built only from the conversation snapshot and run events (`selectThread`, `store.ts`).
  - A sent message appears only once the server lists it.
  - A refused message adds nothing to the thread (conformance "a message during approval shows the hint…": `messages` 1, `messageStarts` 0, `decisions` 0, card text byte-identical).
- **"Verified" is claimed only from server fields.**
  - Sidebar rows other than the open one say "Completed", because the list has no reason code (`TaskNavigation.tsx:190-225`).
  - The grounded pill and badges take the neutral tone (`grounded-1440-explanation.png`), resolving gap audit F-7.
  - `outcome.values` no longer says "verified" in either locale.
- **The agent's words are labelled on the message and on the result**, apart from what was checked (`verified-1440-forced.png`), resolving gap audit F-4. A grounded run says what "grounded, not verified" means in one line under the badge.
- **The refusal path is careful.**
  - The draft is kept, and focus stays in the input.
  - The hint is localised with a verbatim fallback, and the correlation id is shown on demand.
  - An unknown hint is never dropped (`translateServerHint`).
  - A lost response keeps its idempotency key for the user's own resend, and a different text waits (`controller.ts`, PR-18).
- **Citations never invent a value.**
  - A value comes only from `actions[].approved_facts` at the pointer, else "Value not recorded".
  - A digest-only citation is "A source that could not be matched", with no id (`selectors/explanation.ts`).
- **Accessibility.**
  - The workspace focus hand-off follows the APG pattern on open, close, Escape and Back.
  - The confirm step focuses its prompt, not Confirm.
  - The axe check now runs per state in the gate, with a pinned engine, resolving gap audit F-12 for the thread.
- **Placement.**
  - The stream status renders in the thread head at every width and surface while the thread is shown, resolving gap audit F-9 there.
  - The layout uses one container query in rem, so it holds at 200 % text (F-17 for the thread).

## Opinions (no severity)

- **Two Stop buttons for the active run.** One is on its card and one is in the stop slot, as in the mockup (its QA said the same). One may be enough.
- **The neutral "·" marker still reads as punctuation.** The legacy row shows "last seen · · Task cancelled" (`legacy-1440.png`), with two dots in a row.
- **A grounded run's Result tab shows the summary twice:** in the explanation's "The agent's words · Not verified" and in the result's "The agent's words" figure. With the message in the thread, that is three copies. One copy in the workspace would read better.
- **A run's title is its first message.** Run 1 reads "which products are short?" in the bubble and again as the card title, one line below.
- **An open workspace jumps to Result when a result arrives,** even if the user was reading Activity. Focus stays on the Activity tab, while the selected tab becomes Result (`measurements2.jsonl` `tab-forward`). This is the intended forwarding (G-B 6), but it can surprise.
- **T4-7.** The mockup's "Status read from the server just now. This session last saw: …" line told the user what changed while they were away. The owner may want it restored for legacy runs.
- **"Reconnecting…" in the thread head** appears in many captures, because the mock ends each stream response after three events. It is a mock artefact, not a product state.

## Limits

- **Not done:**
  - real assistive-technology testing;
  - real-device testing;
  - moderated user evaluation against `metrics.md` (the brief's M-3 to M-7);
  - live integration (fixture profile and scripted `MockApi` only; no Odoo, no model).
- **Not exercised in this review:**
  - **`conversations: on` against a real server.** `make e2e` runs the server in `off`, and every thread state here comes from the mock (4e.3 handoff).
  - **"Your turn" on a non-current sidebar row.** The mock always lists `reply_pending: false`.
  - **External requests.** These were not measured.
  - **Some normative states inside the thread view:** Blocked by rules, Decision invalidated, Rejected, Executing, Verifying and Cancelled or stopped. The existing per-run specs cover them, and in the thread they render through the same slots.
  - **The density scale (EA-13)** in the thread.
- **Missing automated checks (not findings on their own):**
  - no forced-colours spec covers the workspace or the explanation;
  - no spec measures the workspace's ~40 % width (measured here: 448 px workspace beside a 640 px thread at 1440 px with the sidebar);
  - no spec covers the scroll position on open (4.U3) or a tall card in the side workspace (4.U4).
- **Captures not kept:** screenshots and logs are in the session scratchpad and are not committed.
- **What the checks prove:** script and browser checks verify mechanics only. They do not establish design quality or usability.
