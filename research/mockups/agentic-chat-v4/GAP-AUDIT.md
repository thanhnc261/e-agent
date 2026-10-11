# Gap audit: agentic-chat-v4 conversation workspace and design system (2026-10-11)

- **Surface:** `research/mockups/agentic-chat-v4/` (chat mockup, catalog, identity, overlay specimen and `design-system/`), folder state as read on 2026-10-11. Its README and QA.md are dated 2026-10-10, with revisions dated 2026-10-11. The worktree-isolated session could not run git against the main checkout, so no commit hash is recorded for the surface.
- **Standard:** ag-ux-foundations at 60e1851 (`.agents/skills/ag-ux-foundations/references/`)
- **Auditor:** Claude (Opus 5.5) agent, ag-ux-review gap-audit mode, read-only

This is a dated snapshot. It records the gap between the surface and the standard. It does not change the standard.

## Scoring rules applied

- **Server-backed requirements are scored.** The study simulates approval, verification and unknown outcomes locally. Server-backed requirements (EA-1, EA-2, EA-3, AG-FE-1, AG-FE-12, AG-APPR-2, AG-APPR-7, AG-APPR-9) are therefore scored on what the UI presents, not marked not applicable. The absence of a server is recorded under Limits.
- **Not applicable** is used only where the subject is absent:
  - no API or wire contract: AG-FE-3, AG-FE-13;
  - no proactivity: AG-CTX-2;
  - no adaptation: AG-MEM-2;
  - no capability-change mechanism: AG-MEM-4;
  - no density scale: AG-DS-3.
- **Prior documents are claims, not evidence.** QA.md, FOUNDATION-REVIEW.md and the CLAUDE-REVIEW and REVIEW-RESOLUTION files are the study's own statements. They are cited as claims. They are not counted as independent evidence.

## Summary

| Score | Count |
|---|---|
| met | 35 |
| partial | 39 |
| missing | 8 |
| not applicable | 6 |
| conflict | 0 |

Total: 88 rows. That is 16 EA requirements plus 72 AG criteria: 52 in `standard.md`, 7 in `design-system.md` and 13 in `frontend.md`.

- EA: 8 met, 7 partial, 1 missing.
- standard.md: 20 met, 23 partial, 6 missing, 3 not applicable.
- design-system.md: 2 met, 4 partial, 1 not applicable.
- frontend.md: 5 met, 5 partial, 1 missing, 2 not applicable.

Top gaps, by severity:

- **F-1 (Blocker):** approval jumps straight to "Checking result". There is no committed or executing state and no failed path (EA-3, AG-APPR-6).
- **F-2 (High):** there is no AI disclosure and no capability or limits statement at entry, and AI-drafted documents carry no AI-origin mark (AG-DISC-1, AG-DISC-2, AG-ID-1, AG-DS-4).
- **F-3 (High):** there is no Working state and no Stop control anywhere (AG-CTRL-1, AG-STAT-1).
- **F-4 (High):** the decision surface omits consequences and reversibility. Exact-action metadata is collapsed on the document, and the 320px confirmation hides content behind an unindicated scroll (EA-2, AG-APPR-1, AG-APPR-3).
- **F-5 and F-9 (High):** there is no density scale (EA-13). Theme verification misses composer and selected-state boundaries, and the chat has no user-facing theme selection (EA-12, AG-DS-2, AG-A11Y-4).

## Binding requirements

| ID | Score | Evidence | Gap or finding |
|---|---|---|---|
| EA-1 | partial | The prototype derives identity, connection and revision locally (`../agentic-workspace-v3/action-model.js:26-54`). The README says production must not copy this (`README.md:42`). The verified marker is produced by a user-clicked "Simulate read-back" (`app.js:222-223, 418-427`), not by an authoritative record. | F-6 |
| EA-2 | partial | One action per decision, with approval blocked on stale (`app.js:302-310, 220-221`). Reversibility and consequences are absent from the presentation (`action-model.js:26-54`). No expiry or authorization-change state exists. | F-4, F-7 |
| EA-3 | partial | Confirm sets `scene = "verifying"` directly (`app.js:411-417`). No committed or executing label exists. Verified is client-generated (`app.js:418-427`). | F-1, F-6 |
| EA-4 | met | Unknown outcome offers "Check result" and then "Recovery details", never a resend (`app.js:113-114, 218-219, 451-461`; `scratchpad/v4-audit/08-unknown-1440.png`). | none |
| EA-5 | met | No chain-of-thought, no percentages, no ETA and no timers in `app.js`. The catalog's progress specimen is a counted "2 of 3" (`design-system/catalog.js:245`). | none |
| EA-6 | met | Systems are generic ("Documents", "Team chat"; `../agentic-workspace-v3/fixtures.js:200-243`). A grep for common provider names found none. | none |
| EA-7 | met | Only the authored string renderer is used. All model-like text is escaped (`app.js:10-14`), and the decision surface is fixed markup (`app.js:302-310`). | none |
| EA-8 | met | Missing directory access is explicit: "No employee records have been read" and "Not connected · Administrator setup required" (`app.js:108-110`; `fixtures.js:236-242`). The missing region is stated (`app.js:111-112`). | none |
| EA-9 | partial | Draft and task survive navigation and workspace changes (QA.md:7-8; observed). An open "Approve this exact change?" stays open after a 1440 to 390 resize (`scratchpad/v4-audit/09-confirm-after-resize-390.png`). Theme changes only through a `?theme=` reload, which discarded all threads (0 history items after reload). | F-8 |
| EA-10 | met | The conversation is primary. The workspace is closable, with Sources and Activity as tabs (`index.html:82-135`). There is no catalog homepage, only three starters (`app.js:96-98`; `scratchpad/v4-audit/01-welcome-1440.png`, `02-review-1440.png`). | none |
| EA-11 | partial | Responses are labelled "Sample response", the footer "Verified · sample" and the composer "Sample conversation". The document badge reads plain "Verified" or "Needs review", and the header says "Interactive study" (`app.js:198, 225`; `index.html:75`). | F-11 |
| EA-12 | partial | Three token themes exist, and `check.mjs` passes on the scratch copy. That check omits `border`, `border-subtle` and `surface-selected` pairs. The composer boundary is 1.36:1 (light) and the selected history item 1.05:1. The chat has no theme selection except a URL parameter (`app.js:15-16`), and `prefers-color-scheme` is ignored. | F-9 |
| EA-13 | missing | There is no density scale. The only density artefact is one `--ea-control-compact: 32px` token (`design-system/generated/tokens.css:75`), used once (`design-system/components.css:317`). | F-5 |
| EA-14 | met | Forced-colours rules exist (`styles.css:1432-1450`; `design-system/components.css:333`). The chat was observed operable and legible under emulation (`scratchpad/v4-audit/07-forced-colors-1440.png`). | none |
| EA-15 | partial | Badges pair icon and text (`design-system/components.js:43-60`). The history status, footer status and artifact-link status are text only (`app.js:69, 102, 213-227`). | F-10 |
| EA-16 | met | A single polite live region (`index.html:142`) announces task changes (`app.js:285, 314`). There is no streaming. Focus moves to `#workspace-body` only after a user action destroys the focused control (`app.js:311-318`). | none |

## Criteria

### standard.md

| ID | Enforcement | Score | Evidence | Finding |
|---|---|---|---|---|
| AG-DISC-1 | review | missing | The welcome screen and assistant label say "e-agent · Sample response". The word "AI" appears nowhere in `index.html`, `app.js` or `chat-content.js`. The accessibility tree has no disclosure (snapshot of the review state). | F-2 |
| AG-DISC-2 | review | missing | The welcome screen shows only a slogan and starters (`app.js:96-98`). Systems and limits are reachable only via the Connections dialog. | F-2 |
| AG-DISC-3 | review | met | No performance or accuracy claims appear in the chat or catalog. | none |
| AG-CTX-1 | review | partial | The standalone chat starts empty. "Add context" attaches sample sources (`app.js:165-179`). The overlay specimen does not carry a host record into a task (`overlay.html:40-58`). | F-18 |
| AG-CTX-2 | review | not applicable | There is no proactive behaviour in the study. | none |
| AG-STAT-1 | test, review | partial | Per-task status is shown in the document badge and artifact link. There is no global agent state and no Working state. | F-3 |
| AG-STAT-2 | review | partial | No timers or looping progress. The "Unknown result" prototype control renders "Sent · unresolved" and "The request was sent" for a proposal that was never approved (`app.js:211, 113-114, 198`). | F-6 |
| AG-STAT-3 | test, review | missing | There is no lost-connection, reconnecting or stale-data presentation. Connections are "not probed" (`app.js:299`). | F-12 |
| AG-STAT-4 | test | met | `role="status" aria-live="polite"` (`index.html:142`). Announcements were observed: "Customer handoff: Checking result." No automated check exists (see Limits). | none |
| AG-CTRL-1 | test, review | missing | There is no Stop control (0 matches for "Stop" in any state). | F-3 |
| AG-CTRL-2 | review | partial | Invocation and dismissal (close workspace, Reject) work. Proposal correction exists only as "Change audience" inside "Explore prototype states" (`app.js:211, 468-473`). Free text never refines the proposal (`chat-content.js:45`). | F-14 |
| AG-CTRL-3 | review | partial | The composer is always available and the agent never takes input. There is no explicit indicator of who holds initiative. | F-3 |
| AG-CTRL-4 | review | partial | Reject is present (`app.js:226, 428-431`). Reversal is neither offered nor stated for created or posted items. | F-4 |
| AG-CTRL-5 | review | missing | There is no settings surface, no capability toggles and no in-surface appearance preference. | F-8 |
| AG-APPR-1 | test, review | partial | The confirmation shows operation, destination, audience, identity, connection, revision and values (`app.js:183-193, 302-310`; `scratchpad/v4-audit/03-confirm-1440.png`). Consequences and reversibility are absent. | F-4 |
| AG-APPR-2 | test | met | `t.approved = structuredClone(action())` binds to the shown action (`app.js:413`). Changing the audience creates a new revision that needs review (`app.js:475-482`). QA.md:10 claims a separate-approval test (not re-run). | none |
| AG-APPR-3 | test, review | partial | On the document, Operation, Acting identity, Connection and revision sit in a collapsed `<details>` (`app.js:198`; observed `open=false`). At 320px the confirmation scrolls (937 vs 670 px) with no indicator, and the action row is not sticky (`styles.css:800-844`; `scratchpad/v4-audit/06-confirm-320-hc.png`). | F-4 |
| AG-APPR-4 | test, review | met | Every write needs a modal confirmation, and the action cannot proceed without it (`app.js:302-310, 411-412`). | none |
| AG-APPR-5 | test | partial | "Review outdated" reads "A source changed". It does not say which source or what changed (`app.js:115-116`). There is no expiry or authorization-change invalidation. | F-7 |
| AG-APPR-6 | test, review | partial | Approved, verifying and verified labels are separate. There is no committed or executing label, and verified is client-produced. | F-1 |
| AG-APPR-7 | test | met | No tier is displayed. No control bypasses the confirmation (`app.js:302-303, 412`). | none |
| AG-APPR-8 | test | met | Focus goes to the dialog heading, not Approve (observed `dialog-title`; `app.js:254`). | none |
| AG-APPR-9 | test | partial | Stale proposals cannot be approved (`app.js:220-221, 303`). Changed or expired authorization is not modelled. | F-7 |
| AG-EXPL-1 | review | partial | The rationale is a one-line intro plus source list. Rule findings are not stated as such (`app.js:124`). No chain-of-thought is shown. | F-13 |
| AG-EXPL-2 | review | partial | Sources carry a revision but no observation time (`fixtures.js:27-43`). Citations are not tied to individual claims. | F-13 |
| AG-EXPL-3 | review | partial | Summary in chat and detail in the workspace. Critical action details are collapsed (see AG-APPR-3). | F-4 |
| AG-EXPL-4 | review | met | Uncertainty is qualitative ("Outcome unknown", region not supplied). No numeric confidence is shown. | none |
| AG-UNC-1 | review | partial | The read-only answer states a safe degradation for the missing region (`app.js:111-112`). The agent never asks a clarification question, and there is no Needs-input state. | F-14 |
| AG-UNC-2 | test, review | met | Same evidence as EA-4. | none |
| AG-UNC-3 | test, review | partial | No failed action state exists in the chat (the catalog specimen only, `design-system/catalog.js:263`). The access error points to "View connections" (`app.js:108-110`). | F-15 |
| AG-UNC-4 | test, review | met | Same evidence as EA-8. | none |
| AG-MEM-1 | test | partial | Drafts and threads survive navigation and placement (QA.md:7-8). An appearance change via `?theme=` reload discards everything. There is no retention across visits (by design, README:28). | F-8 |
| AG-MEM-2 | review | not applicable | There is no adaptive behaviour. | none |
| AG-MEM-3 | review | missing | There is no feedback control on any message, proposal or result. | F-19 |
| AG-MEM-4 | review | not applicable | There is no capability or policy change mechanism in the study. | none |
| AG-ID-1 | review | partial | Assistant messages carry the logo and "e-agent" label. The AI-drafted document carries no AI-origin mark and is indistinguishable from read-back facts except by heading. In forced colours the user bubble loses its fill and is distinguished by alignment only (`07-forced-colors-1440.png`). | F-2 |
| AG-ID-2 | test | met | `esc()` is applied to prompts, follow-ups and fixture text (`app.js:10-14, 125`). QA.md:14 claims an escaped-input test. | none |
| AG-ID-3 | test | met | Identity and connection are fixture constants. No text path can select them (`action-model.js:36-40`). | none |
| AG-ID-4 | test | met | No credentials, no storage APIs (grep) and nothing in URLs except the theme. | none |
| AG-ID-5 | review | met | "Acting identity" and "Connection" appear in the confirmation (`app.js:183-193`; `03-confirm-1440.png`). | none |
| AG-ID-6 | test | met | Message text is rendered escaped inside fixed article markup and cannot form controls. | none |
| AG-A11Y-1 | test, review | partial | No full WCAG run. Known failures are in F-9 (boundary contrast, colour-only selected state). There are no automated accessibility checks. | F-9, F-16 |
| AG-A11Y-2 | test | met | Native modal dialog with focus to heading and return (`app.js:249-259`). The tabs use roving tabindex and Arrow, Home and End keys (`design-system/components.js:63-79`). The disclosures are native `<details>`. | none |
| AG-A11Y-3 | test | met | 320px: `scrollWidth` 320, no horizontal scroll (`05-doc-320-hc.png`). 200% type is claimed in QA.md:59 (`screenshots/foundation/chromium/06-enlarged-text.png`). | none |
| AG-A11Y-4 | test | partial | Composer boundary 1.36:1 (light) and 2.13:1 (dark). The selected history item differs only by a 1.05:1 background and has no `aria-current` (`styles.css:177-179, 378-384`; `app.js:69`). | F-9 |
| AG-A11Y-5 | test | met | `prefers-reduced-motion` rules (`styles.css:1080`; `design-system/components.css:328, 360`). | none |
| AG-ENT-1 | test, review | partial | One role (Jamie Lee). The blocked capability is explained rather than enabled-then-failing. There is no second role. | F-20 |
| AG-ENT-2 | review | partial | Icon-only rail buttons get `title` tooltips (`app.js:38-41`). There is no contextual help mechanism. | F-20 |
| AG-ENT-3 | test, review | partial | The overlay specimen shares tokens and controls but not the full task flow (FOUNDATION-REVIEW.md:37). | F-18 |
| AG-ENT-4 | test | met | Long Vietnamese copy and unbroken identifiers are claimed in QA.md:59 (`screenshots/foundation/chromium/07-long-content.png`). | none |
| AG-SOC-1 | review | met | The professional, plain enterprise copy suits the audience. | none |
| AG-SOC-2 | review | met | Content about people (names, teams) shows no stereotyped wording in the sample. | none |

### design-system.md

| ID | Enforcement | Score | Evidence | Finding |
|---|---|---|---|---|
| AG-DS-1 | gate, test | partial | DTCG `$type`/`$value` sources (`design-system/tokens/base.tokens.json`). `check.mjs` PASS: "100 tokens × 3 themes … no component color literals" (scratch copy). The logo hard-codes `black`/`white` fills (`design-system/brand.js:101, 128-131, 150`), and the check scans CSS only for hex (`check.mjs:116-127`). There are no AI-specific tokens. | F-17 |
| AG-DS-2 | test | partial | Per-theme checks cover text, status, action, `border-strong`, focus against surface and brand (`check.mjs:77-103`). Missing are `border`, `border-subtle`, `surface-selected` and focus against canvas. The chat uses `border` for the composer. | F-9 |
| AG-DS-3 | test | not applicable | There is no density scale. The binding gap is EA-13. The compact 32px token still clears 24px. | F-5 |
| AG-DS-4 | review | partial | The logo marks assistant messages only (`app.js:125`) and is not used on verified facts. AI-drafted workspace documents carry no AI treatment, and no AI style tokens exist. | F-2 |
| AG-DS-5 | test, review | met | Every `ds-status` tone carries text and icon (`design-system/components.js:43-60`). Text-only statuses are not colour-only. | none |
| AG-DS-6 | test | met | `motion.fast` and `motion.base` tokens plus reduced-motion rules (`check.mjs:142-152`; `design-system/components.css:328, 360`). | none |
| AG-DS-7 | review | partial | "Review outdated" uses the same tone and shield icon as "Needs review" (`app.js:198`). Unknown is labelled "Outcome unknown", "Sent · unresolved" and "Result unresolved" in three places. The `check` icon (Verified) also marks "Checked 3 sample sources" (`app.js:124`). | F-10 |

### frontend.md

| ID | Enforcement | Score | Evidence | Finding |
|---|---|---|---|---|
| AG-FE-1 | test | partial | The approval record and verification are client state (`app.js:413, 420`). No interaction approves implicitly. | F-6 |
| AG-FE-2 | review | partial | `workspaceOpen` and `tab` are held both globally and per thread (`app.js:19-21, 79, 229, 359-360`). | F-21 |
| AG-FE-3 | gate, test | not applicable | There is no API or schema. | none |
| AG-FE-4 | review | met | A single `scene` string discriminates the task states (`app.js:29-37`). | none |
| AG-FE-5 | test | met | Native dialog and details, and APG-style tabs (`design-system/components.js:63-79`). QA.md:38, 47 claim keyboard tests (not re-run). | none |
| AG-FE-6 | test | partial | The overlay specimen uses `@container` (`design-system/overlay.css:152, 166`). The standalone chat uses viewport queries (FOUNDATION.md:35). | F-18 |
| AG-FE-7 | test | met | Shadow-root modal focus containment, inert host and launcher return are implemented (`design-system/overlay-preview.js:95-134`) and claimed tested in Chromium and WebKit (QA.md:59). | none |
| AG-FE-8 | review | met | Features in use (`dialog`, `inert`, container queries, `structuredClone`, `:host`) are Baseline Widely available at the review date. | none |
| AG-FE-9 | review | partial | Browser suites exist (`verify*.mjs`). There is no automated accessibility checker (no `axe` in any `verify*.mjs`) and no recorded human assistive-technology check. | F-16 |
| AG-FE-10 | test | met | No storage APIs. The URL carries only `theme`. | none |
| AG-FE-11 | test | missing | There is no INP or responsiveness measurement. | F-16 |
| AG-FE-12 | test | partial | "Verified" renders from a client-created `sampleReadBack` (`app.js:420`; `action-model.js:56-63`). | F-6 |
| AG-FE-13 | test | not applicable | There are no wire responses. `statusMarkup` throws on an unknown tone (`design-system/components.js:54`). | none |

## State coverage

| Normative state | Surface state | Reachable | Forbidden items observed |
|---|---|---|---|
| Ready | Welcome: "What shall we move forward?" with three starters and the composer | yes | No unmeasured quality claims. The disclosure is absent (F-2). |
| Working | none (no in-progress agent state) | no | n/a; Stop is missing (F-3) |
| Needs input | none (no agent clarification question) | no | n/a (F-14) |
| Blocked by rules | "Needs access" (people directory) | yes | None. No approval is offered. |
| Awaiting decision | "Needs review" / "Action n of 2" | yes | Material terms are collapsed on the document, and the confirmation scrolls unindicated at 320 (F-4). Approve is not focused. |
| Decision invalidated | "Review outdated" (via the prototype "Changed source") | yes, prototype control only | None. Approve is unavailable. |
| Rejected | "Not approved" (`cancelled` tone) | yes | None. "No action was sent". |
| Executing | none (confirm jumps to "Checking result") | no | Approved and executing are conflated (F-1) |
| Verifying | "Checking result" | yes | No success shown. A user-triggered "Simulate read-back" is offered (F-6). |
| Outcome uncertain | "Outcome unknown" / "Sent · unresolved" | yes, prototype control only | No resend. Reachable from an unapproved proposal (F-6). |
| Failed | none in the chat (catalog specimen only) | no | n/a (F-15) |
| Cancelled or stopped | none | no | n/a (F-3) |
| Verified complete | "Verified · sample" | yes | No over-claim. The document badge omits "sample" (F-11). |

The surface also has a "Read-only answer" state (knowledge scenario). It has no direct normative equivalent: it is neither an action outcome nor verified. It is recorded here and not force-mapped.

## Findings

### F-1 — Approval jumps straight to "Checking result"; there is no committed or executing state

- **Severity:** Blocker
- **Violates:** EA-3, AG-APPR-6
- **Where:**
  - `app.js:411-417` (confirm sets `scene = "verifying"`) and `app.js:29-37` (no executing or committed label);
  - `app.js:119-120`, `222-223`;
  - `scratchpad/v4-audit/04-verifying-1440.png` at 1440, light theme.
- **Observed:**
  - After "Approve this action" the badge reads "Checking result", announced as "Customer handoff: Checking result.".
  - The chat says "The action was approved. The next step is an independent check".
  - No state says whether the effect was executed or committed, or whether the write failed to execute.
  - There is no Failed path for the action.
- **Expected:** Approved (decision recorded), committed (effect executed) and verified are separate states with separate labels, per EA-3 and AG-APPR-6. The state model needs Executing distinct from approved.
- **Recommendation:**
  - Add explicit "Approval recorded", "Executing" or "Sending", "Committed · checking result", "Failed" and "Verified" scenes with distinct labels and icons.
  - Show the committed step in Activity.
  - Owner: the action presentation and the scene model in the next mockup revision, and the server run state in production.

### F-2 — No AI disclosure, capability or limits at entry; AI-drafted documents unmarked

- **Severity:** High
- **Violates:** AG-DISC-1, AG-DISC-2, AG-ID-1, AG-DS-4
- **Where:** `app.js:96-98` (welcome); `app.js:125` (author label "e-agent · Sample response"); `app.js:194-199` (document view); `scratchpad/v4-audit/01-welcome-1440.png`; accessibility snapshot of the review state.
- **Observed:**
  - The entry surface shows a slogan and three starters.
  - Nothing says the user is interacting with an AI, what it can act on, or what it cannot do.
  - Reachable systems appear only in a Connections dialog.
  - The workspace document, an AI-prepared proposal, has no AI-origin marking. No AI-origin token exists.
- **Expected:** The disclosure at first interaction and in-context capabilities and limits are required by AG-DISC-1 and AG-DISC-2. AG-ID-1 and AG-DS-4 require AI-originated content to be marked visibly and programmatically, and only that content.
- **Recommendation:**
  - Add a concise, programmatically exposed disclosure line and a capability and limits statement (systems, what it will not do) to the welcome screen.
  - Mark AI-drafted documents and messages with an AI-origin label backed by a dedicated token.
  - Keep that treatment off read-back facts and decision terms.

### F-3 — No Working state, no Stop control, no initiative indicator

- **Severity:** High
- **Violates:** AG-CTRL-1, AG-STAT-1, AG-CTRL-3
- **Where:** All chat states (no element named "Stop"); `index.html:61-136`; `design-system/components.js:45` (the `progress` status is defined as "Working" but the chat never uses it as such).
- **Observed:**
  - Responses appear instantly.
  - No state represents the agent working.
  - No control stops it.
  - Nothing indicates who holds initiative.
  - "Checking result" is also not stoppable.
- **Expected:** AG-CTRL-1 requires that the user can stop at any time and reach a safe state, with the in-flight action status reported. AG-STAT-1 requires visible status that maps to the state model.
- **Recommendation:**
  - Add Working, Stop and "Stopped" scenes, showing the status of any in-flight action, to the mockup's scene model.
  - Show a persistent status line in the conversation header that maps to the state model.

### F-4 — Decision surface omits consequences and reversibility and hides material terms

- **Severity:** High
- **Violates:** EA-2, AG-APPR-1, AG-APPR-3, AG-EXPL-3, AG-CTRL-4
- **Where:**
  - `../agentic-workspace-v3/action-model.js:26-54` (no reversibility or consequence field);
  - `app.js:198` (`details.audit` collapsed by default; summary target 21px tall);
  - `styles.css:800-844` (dialog actions not sticky);
  - `scratchpad/v4-audit/06-confirm-320-hc.png` at 320 in high contrast (scrollHeight 937 against clientHeight 670).
- **Observed:**
  - The document review hides Operation, Acting identity, Connection and Proposal revision under "Exact action & access details".
  - The confirmation dialog shows them, but at 320px the disclosure line and the Approve and Back buttons are below an unindicated scroll.
  - Neither surface states what the action changes downstream or whether, and how, it can be reversed (create document, post message, update request).
- **Expected:**
  - AG-APPR-1 requires consequences and reversibility.
  - AG-APPR-3 forbids material terms only behind collapsed or unindicated scroll regions.
  - EA-2 requires the complete approval presentation.
- **Recommendation:**
  - Add "Consequences" and "Reversibility" terms to the action presentation and render them in both the document and the confirmation.
  - Show operation, identity and connection uncollapsed on the document.
  - Give the dialog a sticky action row with a visible scroll affordance at narrow widths.

### F-5 — No density scale

- **Severity:** High
- **Violates:** EA-13
- **Where:** `design-system/generated/tokens.css:75` (single `control-compact` token); `design-system/tokens/*.tokens.json` (no density group); `design-system/catalog.js:51` ("44px standard controls · 32px compact").
- **Observed:** There is no comfortable and compact density switch, no density tokens and no per-density target measurement. The compact size is a single control token used once.
- **Expected:** EA-13 requires at least comfortable and compact densities, with compact keeping WCAG minimum targets.
- **Recommendation:**
  - Add a density token layer (spacing, control height, type line-height) with `data-density`.
  - Expose density in the catalog and the chat.
  - Measure targets at each density in `check.mjs` or the browser suite.

### F-6 — Prototype controls produce outcome claims in the product surface

- **Severity:** High
- **Violates:** EA-1, EA-3, AG-STAT-2, AG-FE-1, AG-FE-12
- **Where:**
  - `app.js:222-223` ("Simulate read-back" is the only footer action in Verifying);
  - `app.js:418-427` and `action-model.js:56-63` (the read-back clones the approved action);
  - `app.js:211, 371-378, 113-114, 198` (the "Unknown result" control on an unapproved proposal yields "Sent · unresolved" and "The request was sent").
- **Observed:**
  - The verified state is produced by the user clicking a footer button. Its "observed" values are a copy of the approved action.
  - A proposal that was never approved can be shown as sent with an unknown outcome.
  - Both sit in the real decision footer or in Activity, not in a separate harness.
- **Expected:**
  - Verified only from an independent, authoritative record (EA-3, AG-FE-12).
  - Activity reflects real events only (AG-STAT-2).
  - The client never records the outcome (EA-1, AG-FE-1).
- **Recommendation:**
  - Move every scene-forcing control into a clearly separated prototype harness outside the task surface.
  - Make Verifying offer only "Wait" or "Stop where safe".
  - Let Unknown be reachable only after a simulated dispatch.
  - Production: render verified only from the server field.

### F-7 — Invalidation covers only an unnamed source change

- **Severity:** High
- **Violates:** EA-2, AG-APPR-5, AG-APPR-9
- **Where:** `app.js:115-116, 220-221`; `chat-content.js:33-34`.
- **Observed:**
  - "A source changed after the draft was prepared" names neither the source nor the change.
  - No state covers an expired decision or a changed authorization, connection or credential revision. The connection revision shown is static (`action-model.js:38-40`).
- **Expected:**
  - AG-APPR-5 requires a visible invalidation reason and what changed.
  - EA-2 and AG-APPR-9 require changed or expired authorization to block execution until re-review.
- **Recommendation:** Add "Decision expired" and "Access changed" scenes that block Approve. Name the changed source or revision with a before and after, and offer only "Prepare new review".

### F-8 — Appearance and placement changes do not respect the presentation boundary

- **Severity:** Medium
- **Violates:** EA-9, AG-MEM-1, AG-CTRL-5
- **Where:**
  - `app.js:542-549` (the resize handler ignores the open dialog);
  - `scratchpad/v4-audit/09-confirm-after-resize-390.png` (confirmation still open after a 1440 to 390 change);
  - `app.js:15-16` (theme only via `?theme=`, observed 0 threads after reload).
- **Observed:**
  - An open exact confirmation survives a placement switch.
  - The only way to change appearance in the chat reloads the page and discards all threads and drafts.
  - There is no settings surface for preferences.
- **Expected:**
  - EA-9 requires a confirmation to reset to review on a surface or placement switch, and appearance changes to keep task state.
  - AG-CTRL-5 requires visible preferences.
- **Recommendation:**
  - Close the confirmation and return to review when the placement mode changes.
  - Add an in-page appearance control (theme and density) that changes attributes without reloading.
  - Add a minimal preferences surface.

### F-9 — Theme verification misses boundaries and selected states; the chat has no theme selection

- **Severity:** High
- **Violates:** EA-12, AG-DS-2, AG-A11Y-4, AG-A11Y-1
- **Where:**
  - `styles.css:378-384` (composer `--ea-color-border`);
  - `styles.css:13` (`--line` is `border-subtle`, used for the dialog, starters and secondary buttons);
  - `styles.css:177-179` and `app.js:69` (selected history item: class only, no `aria-current`);
  - `design-system/check.mjs:77-103` (pairs tested);
  - `app.js:15-16`.
- **Observed:**
  - Measured from the generated tokens:
    - the `border`/surface contrast is 1.36:1 (light) and 2.13:1 (dark);
    - the `surface-selected`/`surface-sunken` contrast is 1.05:1 (light) and 1.74:1 (dark).
  - The resting composer boundary and the selected-conversation indicator therefore fall below 3:1.
  - The selected conversation is not exposed programmatically.
  - The gate's PASS does not cover these pairs.
  - The chat offers no user theme choice and ignores `prefers-color-scheme`.
- **Expected:**
  - EA-12 and AG-DS-2 require every theme to be verified for the non-text contrast of components and states.
  - AG-A11Y-4 requires state never to be conveyed by colour alone.
- **Recommendation:**
  - Use `border-strong` (or an equivalent at 3:1 or more) for the composer and input boundaries.
  - Add `aria-current="true"` and a non-colour marker to the selected thread.
  - Extend `check.mjs` to cover every border, selected and hover pair against canvas and surface in all three themes.
  - Expose theme selection and honour the OS preference by default.

### F-10 — Status pairing and scale are inconsistent

- **Severity:** Medium
- **Violates:** EA-15, AG-DS-7
- **Where:** `app.js:69` (history), `app.js:102` (artifact link), `app.js:213-227` (footer), `app.js:198` (stale shares `attention`/shield), `app.js:124` (the `check` icon on "Checked 3 sample sources").
- **Observed:**
  - Three status placements use text only.
  - "Review outdated" looks identical to "Needs review" apart from its text.
  - The unknown outcome has three different labels.
  - The Verified check icon also marks source consultation.
- **Expected:**
  - EA-15 requires icon plus text for status indicators.
  - AG-DS-7 requires one icon, label and colour per level, used everywhere.
- **Recommendation:**
  - Render every status through `statusMarkup`.
  - Add a distinct "invalidated" tone and icon.
  - Use one label per state.
  - Reserve `check` for verified.

### F-11 — Sample labelling is incomplete inside the workspace

- **Severity:** Medium
- **Violates:** EA-11
- **Where:** `app.js:198` (document badge "Verified" or "Needs review", no sample marker); `index.html:75` ("Interactive study"); `02-review-1440.png`.
- **Observed:** Chat messages and the footer are labelled as samples. The workspace document, its title and its status badge are not. A screenshot of the workspace alone reads as a real record, for example "Verified" on `DOC-DEMO-084`.
- **Expected:** EA-11 requires fixture data always to be labelled as sample.
- **Recommendation:** Add a persistent "Sample data" marker to the workspace header and to the document badge text ("Verified · sample"), and change "Interactive study" to "Sample data · interactive study".

### F-12 — No connection-loss or stale-data presentation

- **Severity:** Medium
- **Violates:** AG-STAT-3
- **Where:** `app.js:296-301`; all scenes.
- **Observed:** No disconnected, reconnecting or stale-data state exists. Connections are labelled "not probed".
- **Expected:** AG-STAT-3 requires distinct presentations with a last-updated time.
- **Recommendation:** Add disconnected, reconnecting and stale-source scenes to the catalog and the chat header, with a last-updated time.

### F-13 — Explanation is not structured or attributable per claim

- **Severity:** Medium
- **Violates:** AG-EXPL-1, AG-EXPL-2
- **Where:** `app.js:124, 130-137, 200-207`; `fixtures.js:27-43, 69-80`.
- **Observed:**
  - The rationale is an intro sentence plus a list of sources. Rule findings (for example "IT triage guide → Workplace IT, Normal") are not stated as findings.
  - Citations are not attached to the claims they support.
  - Sources have revisions but no observation time.
- **Expected:**
  - AG-EXPL-1 requires facts, rules and findings.
  - AG-EXPL-2 requires each claim to link to its source with its observation time.
- **Recommendation:** Add a "Why" block in the order facts, then rule findings, then proposal, with inline citation markers per claim and observation times on each source.

### F-14 — No clarification state; correction lives only in the prototype drawer

- **Severity:** Medium
- **Violates:** AG-UNC-1, AG-CTRL-2
- **Where:** `app.js:211, 468-473`; `chat-content.js:45`.
- **Observed:**
  - The agent never asks a clarifying question.
  - Changing the audience, the only proposal correction, is under "Explore prototype states".
  - Typed refinements are explicitly not applied.
- **Expected:**
  - AG-UNC-1 requires clarification, or a stated degradation, for ambiguous requests.
  - AG-CTRL-2 requires correction without restarting.
- **Recommendation:** Add a Needs-input scene (for example "Who should receive this?") asked by the agent in the conversation, and expose "Edit proposal" in the workspace.

### F-15 — No failed-action state in the chat

- **Severity:** Medium
- **Violates:** AG-UNC-3
- **Where:** `app.js:29-37` (no failed scene); `design-system/catalog.js:263` (catalog specimen only).
- **Observed:** No action can fail in the mockup. The access error gives "View connections", but the authorized next step ("Ask your administrator") appears only in a follow-up answer.
- **Expected:** AG-UNC-3 requires the problem, cause and authorized next step, tied to the affected action and kept visible.
- **Recommendation:** Add a "Failed · not committed" scene with cause and next step in the workspace footer, and put the administrator step directly in the access reply.

### F-16 — No automated accessibility or responsiveness checks

- **Severity:** Medium
- **Violates:** AG-FE-9, AG-FE-11, AG-A11Y-1
- **Where:** `verify.mjs`, `verify-system.mjs`, `verify-foundation.mjs` (no `axe`); QA.md:23, 45.
- **Observed:** The browser suites assert mechanics only. No automated WCAG checker runs per state, theme or width, and no INP measurement exists. QA.md itself disclaims screen-reader conformance.
- **Expected:** AG-FE-9 requires automated accessibility checks on every state, theme and width, plus a human check. AG-FE-11 requires an INP measurement.
- **Recommendation:** Add axe-core runs to the existing suites over the state × theme × width matrix, and record a lab INP for send, approve and tab switch.

### F-17 — Logo and AI styling are outside the token contract

- **Severity:** Low
- **Violates:** AG-DS-1
- **Where:** `design-system/brand.js:101, 128-131, 150` (`black`/`white` literals); `design-system/check.mjs:116-127` (hex-only scan of CSS); `design-system/identity.js:63-66` (multicolour node colours are light-palette values).
- **Observed:**
  - The logo's sidewalls, reflections and highlights use literal named colours.
  - The multicolour node option takes light-palette brand values regardless of theme, and these are contrast-checked only against the light canvas.
  - No AI-specific style tokens exist.
- **Expected:** AG-DS-1 requires semantic tokens and no literal colours, with tokens backing each AI style.
- **Recommendation:** Add `color.brand-shade`, `color.brand-highlight` and an AI-origin token set per theme. Have `check.mjs` scan JS-generated SVG for named colours.

### F-18 — Work-context entry and placement consistency are unproven for the full task

- **Severity:** Medium
- **Violates:** AG-CTX-1, AG-FE-6, AG-ENT-3
- **Where:** FOUNDATION.md:35; FOUNDATION-REVIEW.md:37; `overlay.html:40-58`.
- **Observed:**
  - The standalone chat uses viewport queries.
  - The embedded specimen covers composer, workspace and focus, but not the full approval and outcome flow.
  - It does not carry an open host record into the task.
- **Expected:**
  - AG-CTX-1 requires context carried on launch.
  - AG-FE-6 requires container-relative layout.
  - AG-ENT-3 requires the same task in each placement.
- **Recommendation:** Run the handoff scenario inside the overlay specimen with a host-selected record attached, and port the standalone layout to container queries.

### F-19 — No granular feedback

- **Severity:** Low
- **Violates:** AG-MEM-3
- **Where:** `app.js:125` (assistant articles), `app.js:194-199` (document).
- **Observed:** There is no feedback control on messages, proposals or results.
- **Expected:** AG-MEM-3 requires per-output feedback.
- **Recommendation:** Add a compact "Feedback" control per assistant message and per proposal revision.

### F-20 — Single role, no contextual help

- **Severity:** Low
- **Violates:** AG-ENT-1, AG-ENT-2
- **Where:** `index.html:52-57`; whole surface.
- **Observed:** Only one user role is shown, and no help mechanism exists.
- **Expected:** Role-differentiated views (AG-ENT-1) and consistent contextual help (AG-ENT-2).
- **Recommendation:** Add a second-role variant (for example read-only viewer) and a help entry in a fixed location.

### F-21 — Mirrored view state in the prototype controller

- **Severity:** Low
- **Violates:** AG-FE-2
- **Where:** `app.js:19-21, 79, 229, 359-360`.
- **Observed:** `workspaceOpen` and `tab` are held both globally and per thread and are synchronised by hand.
- **Expected:** One owner per state (AG-FE-2).
- **Recommendation:** Derive the view from the active thread only. The README already forbids copying this controller, so this is guidance for the next study.

## Opinions (no severity)

- **The logo.** The current mark combines tilt, extrusion, a glossy reflection, a cast shadow and an optional multicolour mode. That is heavy for a 24px author label. At message size the gloss and sidewalls read as noise next to the flat monoline icon family. A flat, single-colour default with the 3D treatment reserved for hero use would match the "warm, quiet system" intent better. The multicolour option weakens the symbol's role as one stable identifier.
- **Documentation drift.** FOUNDATION-REVIEW.md:9 describes the mark as a "six-node connected graph", while the geometry (`brand.js:10-16`) and README.md:78 describe five nodes. The identity page also says "No … gradient" while the glossy finish layers translucent specular patches. Tidying these avoids confusing later reviewers.
- **Welcome copy.** "What shall we move forward?" and "Untangle a problem" are warm but vague for an enterprise action agent. Stating what the agent does would serve both tone and F-2.
- **Conversation-first hierarchy.** This is the strongest part of the study. The chat stays wider than the workspace, the workspace closes cleanly, and Sources and Activity stay inside it.

## Decision proposals

None. No criterion conflicts with a binding requirement.

## Backlog suggestion

1. **Truthful outcome scenes** (F-1, F-6, F-15, F-12):
   - add Executing, Committed, Failed, Disconnected and Stale scenes;
   - move every scene-forcing control into a separate prototype harness;
   - render verified only from a record that is not user-triggered.
2. **Decision surface completeness** (F-4, F-7):
   - add consequences and reversibility to the action presentation;
   - uncollapse identity and connection on the document;
   - give the dialog a sticky action row and a scroll affordance;
   - add expired and access-changed invalidation that names what changed.
3. **Entry disclosure and AI origin** (F-2, F-17):
   - add the AI disclosure and the capabilities and limits statement on the welcome screen;
   - add AI-origin tokens and labels on AI-drafted content;
   - tokenise the logo shading.
4. **Control and status** (F-3, F-10, F-14):
   - add Working and Stop with in-flight status, and a persistent status line;
   - make every status pair icon and text through the shared helper on one scale;
   - add an agent clarification scene and an "Edit proposal" control.
5. **Design-system binding gaps** (F-5, F-9, F-8):
   - add a density token layer with a switch;
   - move boundaries to 3:1 roles and add `aria-current`;
   - extend `check.mjs` to all boundary, selected and hover pairs;
   - add in-page theme and density controls that honour the OS preference and keep state;
   - reset the confirmation on a placement change.
6. **Evidence and explanation** (F-13, F-11):
   - add a facts, then rule findings, then proposal "Why" block with per-claim citations and observation times;
   - add sample markers in the workspace.
7. **Verification tooling and placement** (F-16, F-18):
   - add axe-core across the state × theme × width matrix;
   - record a lab INP;
   - run the full scenario inside the overlay specimen with host context.
8. **Polish** (F-19, F-20, F-21): feedback control, second role, help entry, single-owner view state.

## Limits

- **Not done:**
  - real assistive-technology testing: no screen reader was used, and the accessibility tree was read from Playwright only;
  - real-device testing;
  - moderated user evaluation against `metrics.md`;
  - live integration: the study has no server, so every approval, policy, verification and connection behaviour is a local simulation, and server-backed requirements were scored on what the UI presents.
- **Checks run on this revision:** `node <scratch copy>/agentic-chat-v4/design-system/check.mjs` returned "PASS: 100 tokens × 3 themes, aliases/output drift, text/status/action contrast, focus/control boundaries, 46 icon assets, no component color literals." It ran on a copy under `scratchpad/v4-audit/copy/` so that nothing in the study folder could be written.
- **Not re-run:** `verify.mjs`, `verify-system.mjs`, `verify-foundation.mjs`, `verify-identity.mjs` and `verify-materials.mjs`. Results cited from QA.md are the study's own claims.
- **Own inspection:** Chromium via Playwright against the already-running server at `http://127.0.0.1:4181/agentic-chat-v4/`.
  - Viewports and themes:
    - 1440 light: welcome, review, confirmation, verifying, unknown;
    - 1440 under forced-colours emulation;
    - 320 high contrast: document and confirmation;
    - 1440 to 390 resize with the confirmation open;
    - a `?theme=dark` reload.
  - Keyboard: partial only (Reject activated with Enter; focus after dialog open).
  - Not inspected by me: 768 or landscape. Those rely on the study's existing `screenshots/`.
  - My screenshots are in `/private/tmp/claude-501/-Users-thanhnguyen-dev-projects-personal-e-agent/febe187a-dc5a-4bfd-920d-7e7a914b47f7/scratchpad/v4-audit/`.
- **Contrast figures** in F-9 were computed from `design-system/generated/tokens.css` with the WCAG relative-luminance formula, not measured from rendered pixels.
- **Missing automated checks**, recorded rather than counted as findings on their own: no automated live-region test (AG-STAT-4), no target-size measurement per density (AG-DS-3 and EA-13), and no automated forced-colours legibility assertion beyond the study's smoke check.
- **Tool side effect:** the Playwright tool wrote a console log under the worktree's `.playwright-mcp/` directory, outside the study folder. Nothing in the study folder was modified except this file.
- Browser and script checks prove mechanics, not design quality or usability.

## Resolution log

<!-- Append-only. Later work adds dated entries here, for example "YYYY-MM-DD — F-3 resolved in <commit>, <evidence>". The scores above are never edited; a new audit supersedes this one. -->
