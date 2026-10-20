# Review: chat defect fixes (core plan Phase 0, Phase 4 tasks 4b.1 to 4b.4)

- **Artifact:** the product UI in `ui/` at `039b6af` (branch `phase4/conversation-chat`). The four fixes are `56463fb` (4b.1, legacy state rows), `fb80f63` (4b.2, reply label once per thread), `2f1d5a7` (4b.3, Context chip copy) and `039b6af` (4b.4, sidebar "Your turn"). Combined diff: `git diff 36ba189 039b6af -- ui/`.
- **Brief:** none. The checks come from [core plan Phase 0](../plans/2026-10-12-core-conversation-cognition.md) (tasks 0.1 to 0.4 and the exit evidence) and [Phase 4 plan](../plans/2026-10-20-phase4-conversation-chat.md) D3 and D14.
- **Reviewer and date:** Claude (ag-ux-review, Review mode), 2026-10-20.
- **Standard:** ag-ux-foundations at `3ab6d7c`.
- **Owner's answer at G-0 (2026-10-20), verbatim:** "1 ok, rest yes". Question 1 confirms the VI chip text; questions 2 to 7 accept the review's proposals. Resolution: [2026-10-20-chat-defects-ux-review-RESOLUTION.md](2026-10-20-chat-defects-ux-review-RESOLUTION.md).

## Verdict

**Needs fixes.** The four fixes do what their tasks ask: no `undefined` in the timeline, one visible reply label, new chip copy, and "Your turn" in the sidebar that clears once the user answers. But the new chip copy cannot be read at phone width (F-2, F-3) and reads awkwardly after its lead-in (F-4), and "Your turn" now disagrees with the Activity timeline (F-5). The pass also found a Blocker that predates these diffs: at 200 % text size, the conversation column collapses to zero width (F-1). These diffs do not cause it, so it does not block them, but the owner needs to schedule it (G-0 question 6).

## What was run and inspected

| Check | Command or method | Result |
|---|---|---|
| Product checks | `pnpm check` in `ui/` | pass: typecheck, format, Vitest 21 files and 188 tests, boundaries (149 modules), provider neutrality, build |
| Conformance | `pnpm conformance` in `ui/` | pass: 158 passed, 4 skipped (two reference-UI reply tests skipped by design, plus the opt-in `overlay-visual` and `visual-review` captures) |
| Running UI | Scratch Playwright specs outside the repo, reusing `ui-conformance/src/mock-api.ts` against the fixture-profile server (`e-agent --profile …/fixture_profile.json serve --static ui/dist/web`, port 8797; started and stopped by Playwright) | Scenario: legacy `run.state_changed {state}` row, reply, answer, second reply, `WAITING_INPUT`. Screenshots in the session scratchpad `4b-ux/` (names below) |
| Viewports | 320×720, 390×844, 768×1024, 1440×1000, landscape 844×390 | No horizontal page scroll while the Context panel is closed. With the panel open: page scroll width 348 px at 320 and 482 to 517 px at 390 (F-3) |
| Text resize | Root font size at 200 %, 1440 px wide | The conversation column is 0 px wide (F-1) |
| Themes | light, dark, high-contrast, forced colours (`emulateMedia`) | Measured contrast of the text these fixes touch: light 5.8 to 6.06:1, dark 8.23 to 9.2:1, high-contrast 14.25:1. Forced colours keep the "◆ Your turn" pill and the sidebar text legible (`thread-forced-colors-1440.png`) |
| Keyboard only | Tab from the page start through the thread at 1440 | Order: Recent tasks, history item ("restock · Your turn"), Stop task, composer, Context, Evidence, Activity, then header and navigation; every stop has a visible outline. Enter opens Context and Escape closes it and returns focus to the toggle at every width, EN and VI |
| Clearing of `replyPending` | Answered the second reply in the running UI, then reloaded | Sidebar went "Your turn", then "Working on it" after the answer and after the reload |

Screenshots (scratchpad `4b-ux/`): `thread-{light,dark,high-contrast}-{1440x1000,768x1024,390x844,320x720,844x390}.png`, `thread-forced-colors-1440.png`, `context-{en,vi}-{1440x1000,768x1024,390x844,320x720}.png`, `context-en-{dark,high-contrast}-1440.png`, `context-geom-{welcome,in-task}-{320x720,390x844,768x1024}.png`, `after-answer-1440.png`, `after-answer-reload-1440.png`, `text200-thread-1440x1000.png`, `text200-no-connections-1440x1000.png`. Raw measurements are in `observations*.jsonl` there.

## State mapping

| Artifact state | Normative state | Reached how |
|---|---|---|
| `WAITING_INPUT` with a pending reply ("Your turn", composer pill and sidebar) | Needs input | Reply, answer, second reply (`twoReplies`-style scenario) |
| `WAITING_INPUT` with a clarification ("Your answer is needed") | Needs input | Unit test `records no pending reply for a clarification question`; not re-captured |
| `RUNNING` ("Working on it") | Working | Answering the reply in the mock |
| Welcome with composer and Context chip ("Ready") | Ready | `/` with no run |

The legacy "Unknown" in "Unknown → Working on it" is a label for a historical transition, not a product state. The other normative states are not touched by these diffs and were not exercised.

## Binding requirements in scope

| ID | Score | Evidence |
|---|---|---|
| EA-3 | met | A reply never claims success. The first reply shows "Reply · not a verified result" (`thread-light-1440x1000.png`), and no verified marker appears on a reply |
| EA-5 | met | The timeline rows come from recorded events only. "Unknown" is shown, never guessed (`store.ts:157-160`) |
| EA-6 | met | `pnpm lint:neutral`: "no provider identifiers in ui/". The chip says "connected systems", not a provider name |
| EA-8 | partial | Met for the missing `from` ("Unknown", EN; "Chưa rõ", VI). Partial for the chip, which names connected systems when none exist (F-7) |
| EA-12 | met for the touched text | Contrast table above |
| EA-14 | met | `thread-forced-colors-1440.png` |
| EA-15 | partial | The composer pill pairs "◆" with text. The sidebar status is text only (F-8) |
| EA-16 | met (existing test) | `composer.spec.ts` asserts `role="status"` on `run-state`. These diffs do not change it |

## Findings

### F-1: At 200 % text size the conversation column collapses to zero width (predates these diffs)

- **Severity:** Blocker
- **Violates:** AG-A11Y-3, AG-A11Y-1
- **Where:** `ui/packages/layouts/src/layouts.css:8` (`grid-template-columns:minmax(0,1fr) 23rem`) and `:34` (the breakpoint is in px: `@media (max-width:1180px)`). The rule dates from `d0d9e70`; the combined diff changes no CSS. Screenshot `text200-thread-1440x1000.png`.
- **Observed:** At 1440 px with the root font size at 200 %, `main.ea-workarea` resolves to `0px 736px`. The thread, the reply label and every message break one character per line in a column 0 px wide (`ea-message-body` measures 0×930). The Evidence and Activity cards overlap the first message, and the composer's placeholder and help text are cut.
- **Expected:** Text resizes to 200 % with no loss of content or function (AG-A11Y-3). Someone who relies on large text cannot read the conversation, so the rubric's assistive-technology Blocker case applies.
- **Recommendation (layouts package):** Size the inspector column in a way that cannot starve the thread, for example `minmax(0,1fr) minmax(0,23rem)` with a minimum for the thread. Express the single-column breakpoint in `em`, or as a container query, so it fires when text grows. Add a conformance check at 200 % text for the thread.

### F-2: Below 640 px the Context panel hides the new chip copy and shows only its title

- **Severity:** High
- **Violates:** AG-A11Y-3, AG-DISC-2
- **Where:** `ui/packages/components/src/components.css:620-622`, inside `@media (max-width: 640px)` (`:580`): `.ea-composer-footer .ea-small { display: none; }`. `ContextPreview.tsx:45,56,60` puts its three paragraphs in `.ea-small`. Screenshots `context-en-390x844.png`, `context-geom-in-task-320x720.png`. Measured: `context-none` has no box at 320 and 390 and is 40 px tall at 768; the panel has one grid row at ≤640 px and four at 768.
- **Observed:** The rule was meant to hide the keyboard hint (`ea-composer-help`). It also hides the lead-in, the 4b.3 sentence and the server note. On a phone the panel reads only "Sent with your message", followed by nothing. The 4b.3 fix is invisible there in EN and VI, both in the welcome and in-task states.
- **Expected:** No loss of information at the reflow width (AG-A11Y-3). What the agent uses is stated in context (AG-DISC-2).
- **Recommendation (components):** Scope the rule to `.ea-composer-help`. Add a conformance assertion that `context-none` is visible at 320 px.

### F-3: With the Context panel open, the page scrolls sideways at 320 and 390 px

- **Severity:** Medium
- **Violates:** AG-A11Y-3, AG-ENT-4
- **Where:** `components.css:757-761`. The panel is placed at `left: 0` from the chip, with `width: min(22rem, calc(100vw - 2rem))`. Measured: the panel spans x 130 to 482 at 390 (page `scrollWidth` 482, 517 in a task) and x 60 to 348 at 320 (`scrollWidth` 348, 383 in a task). Screenshot `context-en-390x844.png` (title cut at the right edge).
- **Observed:** The width cap uses the viewport width, but the anchor is the chip's offset, so the panel runs past the right edge. Scrolling sideways reaches it.
- **Expected:** Reflow at 320 px without scrolling in two dimensions.
- **Recommendation (components):** At narrow widths, anchor the panel to the composer, not the chip (for example, position it from the composer footer with `inset-inline: 0`), or clamp it in the viewport. Assert `scrollWidth <= innerWidth` with the panel open at 320 and 390.

### F-4: The lead-in "Your message text, plus:" does not fit the new sentence, and the panel mixes "sent" with "used"

- **Severity:** Medium
- **Violates:** AG-DISC-2, AG-SOC-1
- **Where:** `ContextPreview.tsx:44-60`; `ui/packages/ui-core/src/i18n.ts:204-205,214-215` (EN) and `:473-474,483-484` (VI). Text captured at 1440: "Sent with your message / Your message text, plus: / Uses this conversation and your connected systems; this page sends no extra details. / The server checks every hint and drops what it cannot verify, then applies your permissions and connections."
- **Observed:** The lead-in promises a list of things sent with the message. What follows is a sentence with no subject ("Uses …") about what the agent uses on the server. Connected systems and the conversation are not sent with the message, so under this title the panel now says they are. The last line then talks about "every hint" when the panel has just said no hints are sent, and it repeats "connections". The VI text follows the same structure ("Nội dung tin nhắn, cùng với: Dùng cuộc trò chuyện này …"). In the embedded host branch the lead-in is still correct, because a `<dl>` list follows it.
- **Expected:** The panel states plainly what this message carries and what the agent draws on, without contradicting its title (AG-DISC-2), in natural wording (AG-SOC-1).
- **Recommendation (components and i18n):** In the no-host branch only, drop the lead-in or replace it. Keep the title for what this message carries, and give the "uses" statement its own short line. One possible shape: "Only your message text; this page adds nothing." then "e-agent also uses this conversation and your connected systems, with your permissions." Leave out the hints sentence when there are no hints. The owner chooses the wording (G-0 question 2).

### F-5: The same state reads "Your turn" in the composer and sidebar but "Your answer is needed" in Activity

- **Severity:** Medium
- **Violates:** AG-DS-7, AG-STAT-1
- **Where:** `ui/packages/components/src/features/timeline/Timeline.tsx:30-31` uses `resultStatusKey`, which ignores `replyPending`. `TaskNavigation.tsx:50` and the composer pill use `runStatusKey`. Screenshots `thread-light-1440x1000.png`, `thread-dark-390x844.png`.
- **Observed:** Three labels are on screen at once. The composer pill and the sidebar say "Your turn"; the last Activity row says "Working on it → Your answer is needed".
- **Expected:** One label for one status wherever it appears (AG-DS-7), consistent with the visible state (AG-STAT-1).
- **Recommendation (components):** Pass the reply context into the transition label, for example by having `selectTimeline` mark a `WAITING_INPUT` transition that follows a reply event. Alternatively, record a decision that Activity shows the plain run-state name and say so in the UI (G-0 question 5).

### F-6: Later replies carry no visible "not a verified result" marker

- **Severity:** Low
- **Violates:** AG-ID-1
- **Where:** `ui/packages/components/src/features/conversation/Messages.tsx:55-67`; `store.ts:199-213` (`firstReply`). Accessibility snapshot: `text: Reply · not a verified result Hello again! What next?`. Screenshot `thread-light-1440x1000.png`.
- **Observed:** Only the first reply shows the label. Later replies keep it as visually hidden text, which assistive technology reads inline. A sighted user who has scrolled past the first reply sees "e-agent" and the text with no visible reply marker. Core plan 0.2 says "a reply is still visibly not a verified result", and ADR 0022 says "the UI labels it as a reply". The plan also allows "a quiet tooltip", which the hidden span is not. Origin ("e-agent") stays visible, and nothing marks a reply as verified, so nobody is misled into a wrong decision.
- **Expected:** Origin and verification status stay distinguishable visibly and programmatically (AG-ID-1).
- **Recommendation (components):** Give later replies a compact visible marker (a small "Reply" tag, or an icon with a tooltip and an accessible name), or confirm at G-0 that showing it on the first reply only meets plan 0.2 (G-0 question 4). Note that `firstReply` counts per run, so once ADR 0023 threads exist the label shows once per run, not once per thread.

### F-7: The chip says "your connected systems" when there are none

- **Severity:** Low
- **Violates:** EA-8, AG-UNC-4
- **Where:** `ContextPreview.tsx:55-58` renders `context.noHost` without reading connections. In the scratch run with `connections: []`, the panel at 1440 still read "Uses this conversation and your connected systems; …" (`text200-no-connections-1440x1000.png`; the text is recorded in `observations4.jsonl`).
- **Observed:** The sentence is static. A workspace with no usable connection is told the agent uses its connected systems.
- **Expected:** A missing connection is stated, never implied as present (EA-8).
- **Recommendation (components):** Choose the sentence from the discovery state: connections present, none, or not loaded. Alternatively, phrase it so it holds in all three, for example "and any systems you have connected". Owner's choice (G-0 question 7).

### F-8: Sidebar status is text only; the composer pill pairs an icon with text (predates these diffs)

- **Severity:** Low
- **Violates:** EA-15, AG-DS-7
- **Where:** `TaskNavigation.tsx:49-50` (`<small>` text only); the composer pill shows "◆ Your turn". Screenshot `thread-light-1440x1000.png`.
- **Observed:** Since 4b.4 the sidebar shows the same status as the pill, but without the pill's icon. Colour is not the only carrier, because the text is present.
- **Expected:** Status indicators pair an icon with visible text (EA-15), and the same status looks the same everywhere (AG-DS-7).
- **Recommendation (components):** Reuse the status-icon mapping from the composer pill in the history item.

## Decision proposals (conflicts with binding requirements)

None.

## Strengths

- 4b.1: Legacy rows read "Unknown → Working on it" in EN and "Chưa rõ" in VI, with no `undefined` anywhere (`selectors.test.ts` "timeline transitions"; `contract.spec.ts` "legacy state row shows no undefined" on every target; `thread-*-1440x1000.png`). The missing value is shown as unknown, never guessed (EA-8).
- 4b.2: The first reply keeps the full label, and assistive technology still hears it on every later reply. The accessibility snapshot shows the hidden text inline before the body.
- 4b.4: The flag is derived from the same `selectPendingReply` as the composer pill (`controller.ts:218`). It only matters in `WAITING_INPUT` (`presentation.ts:70`). In the running UI it cleared to "Working on it" after an answer and after a reload. Older stored entries without the flag still load (`controller.test.ts`).
- Keyboard: The Context disclosure opens with Enter and closes with Escape, returning focus to its toggle at every width and in both locales. Focus outlines are visible at every Tab stop checked.
- Contrast of the touched text is at least 5.8:1 in all three themes. Forced colours keep the status pill legible.

## Opinions (no severity)

- `aria-describedby` on the role-less `.ea-message-body` `<div>` (`Messages.tsx:67`) does little in screen readers. The inline visually hidden span is what delivers the hint. The conformance test `a later reply keeps a quiet not-verified hint` asserts the attribute, not what assistive technology receives. Dropping the attribute, or asserting with an accessibility snapshot, would make the test match reality.
- The Activity list shows "Input requested" for a conversational reply. "Reply" would read more naturally next to the thread. This is outside these four diffs.
- The "Reconnecting…" in the header in every screenshot comes from the mock, which ends each stream on purpose. It is not a product finding.

## Limits

- No real assistive-technology testing (screen reader, voice control). Accessibility evidence is Playwright's accessibility snapshot only.
- No real-device testing. Viewports and forced colours were emulated in desktop Chromium only.
- No moderated user evaluation against `metrics.md`.
- No live integration: fixture server plus the conformance mock only. The core plan's exit evidence, the live `odoo19-learning` "hi → hi → question" run, was not part of this review.
- The `reference` (vanilla) UI target was not inspected visually. Its reply tests are skipped by design.
- Text at 200 % was checked at 1440 px only (F-1). Narrower widths at 200 % were not measured.
- Missing automated check: no test asserts that `replyPending` clears after the user answers. The clearing was observed in the running UI only (After answer and reload rows above), so it can regress unnoticed. Recommended in 4b.5: a `composer.spec.ts` case that answers the reply and expects the history item to read "Working on it".
- Browser and script checks prove mechanics, not design quality or usability.

## Questions for the owner (G-0)

1. Confirm the VI chip text: "Dùng cuộc trò chuyện này và các hệ thống bạn đã kết nối; trang này không gửi thêm thông tin nào." (or give a replacement).
2. Context panel lead-in (F-4): drop "Your message text, plus:" in the no-host case and split "what this message carries" from "what e-agent uses"? Choose the wording.
3. Until Phase 4d carries context across runs, the agent uses only the current task's turns. Keep "this conversation", or say "this task's messages" for now?
4. Later replies (F-6): keep the label on the first reply only, with a hidden hint after that, or add a small visible marker or tooltip on every reply?
5. Activity timeline (F-5): should a `WAITING_INPUT` transition after a reply also read "Your turn", or should Activity keep plain run-state names?
6. Scheduling: fix F-1 (200 % text collapse, predates these diffs) and F-2/F-3 (Context panel at phone width) in 4b.5, or in a separate task?
7. Chip copy with no connections (F-7): choose the sentence from the connection state, or reword it so it holds when none exist?
