# Gap audit: chat surface after Part 4b (2026-10-21)

- **Surface:** `ui/` on branch `phase4/conversation-chat` at `272abbf2` (last `ui/` change: the 4b.5 resolution, `0e78bfe`), served from `ui/dist/web` by the fixture-profile server, with the conformance `MockApi` for scripted states.
- **Standard:** ag-ux-foundations at `3ab6d7c2`.
- **Auditor:** Claude (ag-ux-review, gap-audit mode), task 4e.1, 2026-10-21.
- **Binding decisions read with it:** ADR 0023 and ADR 0034 (accepted at G-A, 2026-10-20; ADR 0034 §5 deferred), the owner's G-0 answer "1 ok, rest yes" (2026-10-20) and "VI ok" (2026-10-21), as recorded in [the 4b resolution](2026-10-20-chat-defects-ux-review-RESOLUTION.md).

This is a dated snapshot. It records the gap between the surface and the standard. It does not change the standard. It is the backlog for the conversation thread brief ([research 20](../../research/20-conversation-thread-brief.md)).

## What was run and inspected

| Check | Command or method | Result |
|---|---|---|
| Product checks | `pnpm --dir ui check` | Pass: typecheck, format, Vitest 22 files and 196 tests, boundaries ("no dependency violations found (151 modules, 402 dependencies cruised)"), "ok  no provider identifiers in ui/", build |
| Conformance | `make e2e` (`ui-build`, then `pnpm --dir ui conformance`) | "168 passed (1.4m)", 4 skipped (the two reference-UI reply tests, `overlay-visual` and `visual-review`, all opt-in or skipped by design) |
| Scripted captures | A scratch Playwright spec (outside the repository) using `MockApi`: welcome (standalone overview, task route, embedded overlay), reply thread, clarification, approval, grounded success, a 409 refusal | 40 screenshots at 320×720, 390×844, 844×390 (landscape), 768×1024 and 1440×1000, in the session scratchpad `audit/shots/`. Horizontal overflow measured 0 px in every capture |
| Themes | Light captures above; dark, high-contrast and forced colours from the existing `theming`, `forced-colors` and `tokens/test/contrast.test.ts` checks | The scratch dark and high-contrast approval captures did not run (the remembered run re-attached after reload); themes are scored from the existing checks |
| Keyboard | Existing specs: `contract.spec.ts` "8. keyboard-only approval with visible focus", `preferences.spec.ts` focus return, `surfaces.spec.ts` Escape | Pass (in the conformance run above) |

Screenshot names below refer to `audit/shots/<state>-<width>x<height>.png` in the session scratchpad; they are not committed.

## Summary

| Score | Count |
|---|---|
| met | 56 |
| partial | 25 |
| missing | 4 |
| not applicable | 3 |
| conflict | 0 |

88 items scored: 16 EA requirements, 52 standard criteria, 13 AG-FE and 7 AG-DS.

Top gaps, by severity:

- **F-1 (High):** the embedded and task-route entry has no AI disclosure and no capability statement (AG-DISC-1, AG-DISC-2).
- **F-2 (High):** there is no thread. A follow-up after a finished run starts an unrelated run, and the earlier exchange leaves the view (AG-CTRL-2, AG-MEM-1).
- **F-3 (High):** the task artifact is not in a closable workspace (EA-10, now ADR 0034 §1).
- **F-4 (High):** the agent's final answer text carries no origin or verification label beside "Completed · verified" or "grounded, not verified" (EA-3, AG-APPR-6, AG-ID-1).
- **F-6 (High):** there are no citations and no explanation (AG-EXPL-1, AG-EXPL-2, AG-EXPL-3; Phase 3 D10).
- **F-8 (Medium):** a server refusal (409) is shown as a generic "The task has changed", and the server's message is dropped (AG-UNC-3). The conversation route's refusals depend on this path.

## Binding requirements

| ID | Score | Evidence | Gap or finding |
|---|---|---|---|
| EA-1 | met | Approval, run state and verification come from server records (`ui-core/src/approval.ts`, `presentation.ts:51-54`); `contract.spec.ts` 2a, 2b, 5 | none |
| EA-2 | met | `presentationMatchesCanonical` (`presentation.ts:26-41`); `contract.spec.ts` "1." to "2c." | none |
| EA-3 | partial | Status labels split approved, recorded, checking, verified and grounded (`i18n.ts:150-188`); but the model's final text is unlabelled, and a grounded run's composer pill carries the verified colour | F-4, F-7 |
| EA-4 | met | `OutcomePanel.tsx:45-50` offers "Check operation status", never a resend; `RunStatus.tsx:22-24` hides Stop on `NEEDS_RECONCILIATION` | none |
| EA-5 | met | Activity comes from recorded events only (`store.ts:144-185`); no confidence, no plan, no reasoning text; the progress line is driven by `RUNNING` (`Messages.tsx:107-112`) | none |
| EA-6 | met | `pnpm --dir ui lint:neutral`: "ok  no provider identifiers in ui/" | none |
| EA-7 | met | Model text renders through `MessageText.tsx` as literal text and audited links; `contract.spec.ts` "4. model text never loads remote content" | none |
| EA-8 | met | `projections.spec.ts` (missing provenance shown as unknown), `discovery.spec.ts` (denied is not empty), unsupported events and bundles (`EvidencePanel.tsx:43-48`) | none |
| EA-9 | met | `surfaces.spec.ts` "view switch preserves draft and exact review", `presentation.spec.ts` "changing presentation never changes the reviewable terms" | none |
| EA-10 | partial | Conversation is the primary column (`TaskSurface.tsx:63-75`), but the approval and the result sit in the conversation column, and the Evidence and Activity inspector cannot be closed | F-3 |
| EA-11 | partial | Fixture-profile records ("restock widget-a", `supplier:approved-co`) render with no sample label; `i18n.ts` has no sample key | F-15 |
| EA-12 | met | `tokens/test/contrast.test.ts` checks the light, dark and high-contrast themes; `theming.spec.ts` | none |
| EA-13 | met | Comfortable and compact density; `presentation.spec.ts` checks compact target size | none |
| EA-14 | met | `forced-colors.spec.ts` "forced colours keep the current section, controls and decision visible" | none |
| EA-15 | met | `StatusBadge.tsx:8-15` pairs a shape marker with text; the sidebar shows the same marker (4b.5 F-8) | none |
| EA-16 | met | The run-state pill is the polite live region (`RunStatus.tsx:27-36`, `role="status"`); streamed text has no live region (`Messages.tsx:85-94`); focus is not moved. Note: four status regions exist in the reply state (connection, run state and two more), and in `RUNNING` the progress line and the pill both announce; see the opinions | none |

## Criteria

### standard.md

| ID | Enforcement | Score | Evidence | Finding |
|---|---|---|---|---|
| AG-DISC-1 | review | partial | Standalone Overview shows "e-agent is an AI agent and can make mistakes" (`apps/web/src/pages/Overview.tsx:45-56`). The welcome in every other placement and on `#/task` has none: a count of the text "AI agent" was 0 on both (`welcome-overlay-390x844.png`, `welcome-task-1440x1000.png`) | F-1 |
| AG-DISC-2 | review | partial | Capabilities and limits only behind the Overview disclosure; the shared welcome (`Messages.tsx:18-28`) says "You review changes before they are sent." only | F-1 |
| AG-DISC-3 | review | met | No performance claim in any string (`i18n.ts`) | none |
| AG-CTX-1 | review | met | Embedded hosts send host context, shown in the Context panel (`ContextPreview.tsx:17-28`; `composer.spec.ts` "an embedded surface shows the context it will send") | none |
| AG-CTX-2 | review | not applicable | The surface has no proactive engagement | none |
| AG-STAT-1 | test, review | met | `runStatusKey` maps every server state (`presentation.ts:64-78`); see State coverage | none |
| AG-STAT-2 | review | met | Timeline and progress from recorded events only (`store.ts:144-185`) | none |
| AG-STAT-3 | test, review | partial | `ConnectionStatus` is `display:none` in the compact overlay (`layouts.css:27`), the stacked surfaces (`layouts.css:18`) and below 640 px (`components.css:594-596`); the sidebar shows each task's last-known state from session storage with no "last known" marker (`TaskNavigation.tsx:52-63`) | F-9 |
| AG-STAT-4 | test | met | `role="status"` on the run pill, progress line and connection; `role="alert"` on errors | none |
| AG-CTRL-1 | test, review | met | "Stop task" in every non-terminal state except reconciliation (`RunStatus.tsx:22-39`); `CANCELLED` shown in the result | none |
| AG-CTRL-2 | review | partial | After a run ends, the composer starts a new, unrelated run (`presentation.ts:84-86`, `controller.ts:175-208`) and the earlier exchange leaves the view; while a decision waits, the composer is locked with client copy "Review this task or start a new one from the task menu." (`approval-390x844.png`) | F-2 |
| AG-CTRL-3 | review | met | "Your turn" and "Your answer is needed" versus "Working on it" (4b.5 F-5; `reply-390x844.png`) | none |
| AG-CTRL-4 | review | met | Reject on the card; `live.spec.ts` "reject writes nothing" | none |
| AG-CTRL-5 | review | partial | Preferences hold theme, appearance, density, view and language (`Preferences.tsx`); no user control turns a capability off or shows that it is off | F-14 |
| AG-APPR-1 | test, review | met | `contract.spec.ts` "1. shows every material field, marks changes, shows findings"; card unchanged since the 2026-10-12 review | none |
| AG-APPR-2 | test | met | Digest check (`ui-core/test/digest.test.ts`, `contract.spec.ts` 2a) | none |
| AG-APPR-3 | test, review | partial | In the overlay, docked and below 640 px the decision body is `max-height` with `overflow:auto` and no scroll affordance (`layouts.css:29,60`, `components.css:611-614`); `redesign.spec.ts` "mobile review keeps exact fields scrollable" proves the terms are reachable only by scrolling that region | F-5 |
| AG-APPR-4 | test, review | met | `contract.spec.ts` "5. approval needs an explicit confirm" | none |
| AG-APPR-5 | test | met | `contract.spec.ts` "2c. a new revision while confirming forces re-review" | none |
| AG-APPR-6 | test, review | partial | Action and run labels keep the split (`i18n.ts:176-187`); the model's final text sits beside them unlabelled | F-4 |
| AG-APPR-7 | test | met | No client tier; the server's presentation is rendered as given | none |
| AG-APPR-8 | test | met | `contract.spec.ts` "8. keyboard-only approval with visible focus" | none |
| AG-APPR-9 | test | met | `contract.spec.ts` 2a, 2b (approve disabled on mismatch and expiry); server re-check | none |
| AG-EXPL-1 | review | missing | No explanation surface; the `explanation` key of the evidence bundle is not read (Phase 3 D10, Task 4e.5) | F-6 |
| AG-EXPL-2 | review | partial | Evidence panel lists sources with observed time and completeness (`EvidencePanel.tsx:73-89`); the answer's claims link to nothing | F-6 |
| AG-EXPL-3 | review | partial | Evidence is summary then detail (`Disclosure`), but there is no explanation to stage | F-6 |
| AG-EXPL-4 | review | met | No confidence shown anywhere | none |
| AG-UNC-1 | review | met | Clarification question shown and answered on the same run (`contract.spec.ts` "clarification answers the same run") | none |
| AG-UNC-2 | test, review | met | Unknown outcome offers a status check, never a resend (`OutcomePanel.tsx:45-50`) | none |
| AG-UNC-3 | test, review | partial | `controller.ts:472-474` maps every 409 to `error.stale`; a 409 with `message: "the question changed; read it again"` shows "The task has changed. Review the latest details before continuing." (`conflict-390x844.png`). The draft is kept | F-8 |
| AG-UNC-4 | test, review | met | `projections.spec.ts`, `discovery.spec.ts` | none |
| AG-MEM-1 | test | partial | Draft and active run survive navigation and surface change (`routes.spec.ts`, `surfaces.spec.ts`); recent tasks are session-local and the transcript of a previous run is gone once a new one starts | F-2 |
| AG-MEM-2 | review | not applicable | No adaptive behaviour | none |
| AG-MEM-3 | review | missing | No feedback control on any output | F-13 |
| AG-MEM-4 | review | missing | No notice of capability or behaviour changes | F-13 |
| AG-ID-1 | review | partial | User and agent messages are marked (avatar and author); replies say "not verified" (4b.5 F-6); the final answer (`Messages.tsx:96-104`) has no AI-origin or verification label | F-4 |
| AG-ID-2 | test | met | `MessageText.tsx`; `contract.spec.ts` "4." | none |
| AG-ID-3 | test | met | No client connection choice; `discovery.spec.ts` "the connection view offers no credential or connect control" | none |
| AG-ID-4 | test | met | No credential reaches the client; session storage holds run ids and task text only (see F-10) | none |
| AG-ID-5 | review | partial | The card shows "Connection" and "Acts as"; an answer, a reply or a read shows neither | F-11 |
| AG-ID-6 | test | met | Model text is plain text with marked links; it cannot render controls | none |
| AG-A11Y-1 | test, review | partial | No automated WCAG check runs per state in `ui-conformance` (no axe or equivalent); contrast, forced colours, focus and reflow are covered by their own specs | F-12 |
| AG-A11Y-2 | test | met | React Aria primitives; `<details>` disclosures with Escape (`ContextPreview.tsx:31-41`); `preferences.spec.ts` | none |
| AG-A11Y-3 | test | partial | 200 % text fixed in 4b.5 F-1; at 320 and 390 px the section row scrolls sideways inside itself and clips "Current task" with no indication (`grounded-320x720.png`, `standalone.css:55-58`) | F-16 |
| AG-A11Y-4 | test | met | `contrast.test.ts`; status pairs marker and text | none |
| AG-A11Y-5 | test | met | `presentation.spec.ts` "reduced motion removes animation in every appearance" | none |
| AG-ENT-1 | test, review | met | One role in this surface; unavailable actions are absent or explained (locked composer has a reason; catalog reasons) | none |
| AG-ENT-2 | review | met | Composer hint, labelled icon controls, Context panel | none |
| AG-ENT-3 | test, review | partial | Stream status shown in the workspace header only; overlay and docked hide it; the inspector is beside the thread in the page variant and below the composer in the stack variant | F-9 |
| AG-ENT-4 | test | met | `contract.spec.ts` "7. Vietnamese labels render without overflow", `routes.spec.ts` Vietnamese | none |
| AG-SOC-1 | review | met | Plain, neutral business tone in EN and VI | none |
| AG-SOC-2 | review | not applicable | No content or suggestions about people | none |

### frontend.md

| ID | Enforcement | Score | Evidence | Finding |
|---|---|---|---|---|
| AG-FE-1 | test | met | Approval and status from server records; Enter never approves (`contract.spec.ts` 5) | none |
| AG-FE-2 | review | partial | Task history keeps a second copy of each run's state in session storage (`controller.ts:216-221`) and shows it as current | F-9 |
| AG-FE-3 | gate, test | met | `pnpm gen:check` regenerates `client/src/schema.ts` from `openapi.json` | none |
| AG-FE-4 | review | met | Approval phase is one union (`ui-core/src/approval.ts`) | none |
| AG-FE-5 | test | met | React Aria Components; native `<details>` for disclosures | none |
| AG-FE-6 | test | partial | The workspace uses a container query (4b.5 F-1, `layouts.css:4,37`); the overlay and workbench still switch at viewport widths (`layouts.css:38-49,63-72`) | F-17 |
| AG-FE-7 | test | met | `surfaces.spec.ts` "minimize retains draft; Escape backs out of confirm before minimizing"; `theming.spec.ts` overlay isolation | none |
| AG-FE-8 | review | met | Size container queries are Baseline widely available (4b.5 resolution) | none |
| AG-FE-9 | review | partial | Unit, component and browser tests exist (196 Vitest, 168 Playwright); no automated accessibility check per state, theme and width | F-12 |
| AG-FE-10 | test | partial | Task text is written to `sessionStorage`: the history (`controller.ts:220`) and the pending submission (`controller.ts:193,197`) | F-10 |
| AG-FE-11 | test | missing | No INP measurement, with or without streaming | F-19 |
| AG-FE-12 | test | met | Verified only from server state; grounded from the server's `reason_code` (`selectors/outcome.ts:73-76`; `components/test/grounded-status.test.tsx`) | none |
| AG-FE-13 | test | met | Unknown events and bundle schemas reported (`store.ts:96-98`; `projections.spec.ts`) | none |

### design-system.md

| ID | Enforcement | Score | Evidence | Finding |
|---|---|---|---|---|
| AG-DS-1 | gate, test | partial | Tokens in DTCG format (`tokens/tokens/*.json`); literal shadow colours in `layouts.css:24,33` (`rgb(0 0 0 / .16)`, `rgb(0 0 0 / .12)`) | F-18 |
| AG-DS-2 | test | met | `contrast.test.ts` across three themes | none |
| AG-DS-3 | test | met | `presentation.spec.ts` checks compact target size | none |
| AG-DS-4 | review | met | Brand-mark avatar only on agent messages; not on facts or decision terms | none |
| AG-DS-5 | test | met | Marker and text on every status (`StatusBadge.tsx`) | none |
| AG-DS-6 | test | met | Duration tokens; reduced-motion spec | none |
| AG-DS-7 | review | partial | A grounded run shows "· Completed · grounded, not verified" in grey in the result and in the verified green in the composer pill (`RunStatus.tsx:26` adds `ea-state-succeeded`, coloured by `components.css:135-140`; `grounded-1440x1000.png`) | F-7 |

## State coverage

Mapped on 2026-10-21 against `state-model.md`. Each product state maps to one normative state.

| Normative state | Surface state | Reachable | Forbidden items observed |
|---|---|---|---|
| Ready | Welcome: Overview (standalone) or the shared welcome (`Messages.tsx:18-28`) | yes | none; but F-1 (no disclosure outside the Overview) |
| Working | `CREATED`, `RUNNING` / "Getting started", "Working on it" | yes | none |
| Needs input | `WAITING_INPUT` clarification / "Your answer is needed"; `WAITING_INPUT` after a reply / "Your turn" | yes | none |
| Blocked by rules | Blocked findings on the card (conformance fixtures) | yes | none |
| Awaiting decision | `WAITING_APPROVAL` / "Needs review" | yes | material terms in an unindicated scroll region at narrow widths (F-5) |
| Decision invalidated | Expired, digest mismatch, stale | yes | none |
| Rejected | "Rejected. Nothing will be written." | yes | none |
| Executing | An action `DISPATCHING` / "Sending the change" | yes (unit-tested) | none |
| Verifying | `VERIFYING`, or an action `COMMITTED` / "Change recorded · checking" | yes | none |
| Outcome uncertain | `NEEDS_RECONCILIATION`, or an action `UNKNOWN` | yes | none |
| Failed | `FAILED` / "Task stopped" | yes | none |
| Cancelled or stopped | `CANCELLED` / "Task cancelled" | yes | none |
| Verified complete | `SUCCEEDED` / "Completed · verified" | yes | the unlabelled final text beside it can read as verified (F-4) |

`SUCCEEDED` with reason code `grounded` / "Completed · grounded, not verified" has **no normative state**. It is not Verified complete (no independent read-back, PR-19), and mapping it there would break that state's Forbidden item "claiming more than was verified". It is recorded under Decision proposals.

Thread states the conversation model adds (ADR 0023) do not exist on this surface yet: an empty thread, a thread with several runs, a message refused while a run waits for approval, a reply to an ended run, the per-run fallback when the mode is `off` or the features route fails, and legacy runs outside any conversation. They are the subject of the brief, not findings here.

## Findings

### F-1 — No AI disclosure or capability statement outside the standalone Overview

- **Severity:** High
- **Violates:** AG-DISC-1, AG-DISC-2
- **Where:** `ui/packages/components/src/features/conversation/Messages.tsx:18-28`; `welcome-overlay-390x844.png`, `welcome-task-1440x1000.png` (count of "AI agent" on the page: 0 in both)
- **Observed:** The Overview page discloses the AI and states what it can and cannot do. The welcome every other placement shows (Compact, Workbench, Docked, and the standalone `#/task` route) says "YOUR WORKSPACE · What would you like to get done? · Bring a question… · You review changes before they are sent." The author name "e-agent" and the brand mark are the only cues.
- **Expected:** AG-DISC-1 and AG-DISC-2 at first interaction, in every placement. Rated High rather than Blocker: the standalone entry discloses, and the embedded panel names an agent; a person can still start a task without being told it is an AI or what it cannot do.
- **Recommendation:** Move the Overview's one-line disclosure and its on-demand capability detail into the shared empty-thread state, so every surface shows it (L6 components, `Messages` welcome). The brief makes it part of "thread empty".

### F-2 — No thread: a follow-up starts an unrelated run and the earlier exchange leaves the view

- **Severity:** High
- **Violates:** AG-CTRL-2, AG-MEM-1
- **Where:** `ui/packages/ui-core/src/presentation.ts:84-86` (`canCompose`), `ui/packages/ui-core/src/controller.ts:175-208` (`start` creates a new run), `Messages.tsx` (renders one run); `grounded-1440x1000.png` (after the end: "Describe what you need… · Send task"); `approval-390x844.png` (locked composer)
- **Observed:** Once a run ends, the composer offers "Send task", which creates a new run with no link to the previous one; the view switches to it and the earlier transcript is reachable only from the session's recent-task list. While a decision waits, the composer is disabled with the client's own sentence, so the user cannot even draft a question.
- **Expected:** Refining or following up without restarting the task (AG-CTRL-2), and recent interactions surviving (AG-MEM-1). ADR 0023 (a thread of runs) and ADR 0034 §2 are the accepted design.
- **Recommendation:** The 4e thread view (Tasks 4e.3, 4e.4): a conversation of runs, one composer, `reply_to` bound to the question the user saw, and refusals shown with the server's hint while the draft is kept.

### F-3 — The task artifact is not in a closable workspace

- **Severity:** High
- **Violates:** EA-10 (ADR 0034 §1)
- **Where:** `ui/packages/layouts/src/shared/TaskSurface.tsx:16-19` (`TASK_ORDER` puts outcome and approval in the conversation column; `INSPECTOR_ORDER` holds evidence and timeline), `:63-75` (the inspector renders whenever a run exists, with no close control); `reply-390x844.png` (Evidence and Activity below the composer)
- **Observed:** The approval card and the result render inside the conversation column. Evidence and Activity sit in an aside that cannot be closed or reopened; at narrow widths they stack under the composer.
- **Expected:** ADR 0034 §1: the task artifact (approval card, outcome, evidence, activity) opens in a workspace beside the conversation that the user can close and reopen, keeping the conversation, active run, approval state and draft. Rated High rather than Blocker: nothing misleads or is lost; the hierarchy the owner chose is not built.
- **Recommendation:** Built by Task 4e.4 from the direction chosen at G-C. The brief states where the approval card lives (it stays unchanged in content, ADR 0034 §5 deferred).

### F-4 — The agent's final answer carries no origin or verification label

- **Severity:** High
- **Violates:** EA-3, AG-APPR-6, AG-ID-1
- **Where:** `Messages.tsx:96-104` (`final-message`); `grounded-1440x1000.png`
- **Observed:** The final message is shown as plain agent text. In a grounded run it reads "Two orders are late: sample A and sample B." with only the result pill saying "grounded, not verified"; in a verified run the same unlabelled model text sits under "Completed · verified", where it reads as the verified result. Replies, by contrast, are labelled "not verified" (4b.5).
- **Expected:** Model-authored text is labelled as such and never presented as verified (ADR 0034 §4, EA-3); AI-generated content is distinguishable from verified facts (AG-ID-1). The verified values the server checked are in the result's "Verified values", which is a different thing from the model's sentence.
- **Recommendation:** Label the final answer as the agent's text in every run, and say beside it which parts the server verified or grounded (Task 4e.5 wording). Covered by the brief's "grounded" and "verified" states.

### F-5 — Material terms can sit in an unindicated scroll region

- **Severity:** High
- **Violates:** AG-APPR-3
- **Where:** `ui/packages/layouts/src/layouts.css:29,60`; `ui/packages/components/src/components.css:611-614`; `redesign.spec.ts` "mobile review keeps exact fields scrollable and actions reachable" (10 fields)
- **Observed:** In Compact, Docked and below 640 px, the decision body is capped (`36dvh`, `45dvh`, `48dvh`) with `overflow:auto` and no visible cue; on touch devices the scrollbar is hidden until scrolling. "Review and approve" stays reachable without scrolling the region.
- **Expected:** AG-APPR-3. The confirmation step (AG-APPR-4) is a partial mitigation, hence High rather than Blocker.
- **Recommendation:** Out of Phase 4 scope (the card is unchanged; ADR 0034 §5 deferred). Record it for the card follow-up: a visible "more terms below" cue or no inner scroll region on the decision body.

### F-6 — No citations and no explanation

- **Severity:** High
- **Violates:** AG-EXPL-1, AG-EXPL-2, AG-EXPL-3
- **Where:** `ui/packages/ui-core/src/selectors/evidence.ts` reads `actions[].approved_facts` only; no reader of the bundle's `explanation` or `grounded_answer` keys; `EvidencePanel.tsx`
- **Observed:** The user can inspect source observations, but cannot see which records an answer rests on, which rules were applied, or why. Phase 3 built the data (ADR 0033); the UI was left for later (Phase 3 D10, handoff item 14).
- **Expected:** AG-EXPL-1 to AG-EXPL-3, with ADR 0034 §3 and §4 fixing what may be shown.
- **Recommendation:** Task 4e.5 (second cut line, D16), from the brief's D15 section.

### F-7 — A grounded run's composer pill uses the verified colour

- **Severity:** Medium
- **Violates:** AG-DS-7, EA-3
- **Where:** `ui/packages/components/src/features/composer/RunStatus.tsx:26` (`ea-state-${run.state}`), `components.css:135-140` (`.ea-state-succeeded` → `--ea-color-status-verified`); `grounded-1440x1000.png`
- **Observed:** The same status ("Completed · grounded, not verified", neutral marker "·") is grey in the result and green in the composer pill, because the pill's class comes from the run state alone.
- **Expected:** One treatment per status level (AG-DS-7); nothing styled as verified that the server did not verify (EA-3). The text is correct, so the effect is a mixed signal, not a false claim.
- **Recommendation:** Derive the pill class from the same tone as the badge (`runStateTone`), not from `run.state`.

### F-8 — A server refusal shows a generic message; the server's hint is dropped

- **Severity:** Medium
- **Violates:** AG-UNC-3
- **Where:** `ui/packages/ui-core/src/controller.ts:472-474` (`fail`); `conflict-390x844.png`
- **Observed:** Any 409 shows "The task has changed. Review the latest details before continuing." The server's `message` ("the question changed; read it again" in the scripted case) and `correlation_id` are not shown. The draft is kept.
- **Expected:** The problem, its cause and an authorized next step (AG-UNC-3). ADR 0034 §2: a refused message shows the server's fixed hint and keeps the draft. The conversation route refuses with fixed hints (ADR 0023 §4), so this path decides what a refused message looks like.
- **Recommendation:** Show the error envelope's fixed hint for conversation-route refusals (Task 4e.3 test "a refused message keeps the draft and shows the server's hint"), with the correlation id on demand.

### F-9 — Stale state is not shown as stale

- **Severity:** Medium
- **Violates:** AG-STAT-3, AG-ENT-3, AG-FE-2
- **Where:** `layouts.css:18,27`, `components.css:594-596` (connection status hidden); `TaskNavigation.tsx:52-63` and `controller.ts:216-221` (history state)
- **Observed:** The stream status ("Reconnecting…") is hidden in Compact, Docked, the stacked surfaces and below 640 px, so a lost connection is invisible there. The sidebar shows each task's state as last seen in this tab, for example "Needs review" for a run another tab may have decided, with no "last known" marker; it is re-read only when opened (`routes.spec.ts` "recent tasks show last-known state and re-read a task before a decision").
- **Expected:** AG-STAT-3 in every placement (AG-ENT-3); one owner for run state (AG-FE-2).
- **Recommendation:** Keep a compact stream indicator in every placement. In `on`, the sidebar reads `GET /v1/conversations` (`latest_state`, `reply_pending`, D11), which removes the mirrored copy; legacy entries say "last seen".

### F-10 — Task text is kept in session storage

- **Severity:** Medium
- **Violates:** AG-FE-10
- **Where:** `controller.ts:193,197` (pending submission), `:216-221` (history `task`)
- **Observed:** The user's task text is written to `sessionStorage` for the recent-task list and for the submission recovery record. It is cleared when the tab's session ends and is keyed by tenant and principal.
- **Expected:** AG-FE-10: no task text in browser storage. Rated Medium: session scope, same origin, no credential.
- **Recommendation:** In `on`, list conversations by id and take titles from the server (D4: the title is derived at read time). Keep only ids locally; review the pending-submission record separately.

### F-11 — Answers and reads do not show the acting identity or connection

- **Severity:** Medium
- **Violates:** AG-ID-5
- **Where:** `ApprovalReview.tsx:33-38` shows "Connection" and "Acts as" under "Execution details"; `Messages.tsx` and `OutcomePanel.tsx` show neither
- **Observed:** A read-only answer or a reply gives no indication of which connection or identity read the data.
- **Expected:** AG-ID-5 for every action, reads included.
- **Recommendation:** Show the connection and identity the server recorded with each answer's sources (from the evidence bundle), never a model-chosen value. Not required by ADR 0034; listed for the brief as a candidate.

### F-12 — No automated accessibility check per state

- **Severity:** Medium
- **Violates:** AG-A11Y-1, AG-FE-9
- **Where:** `ui/packages/ui-conformance/tests/` (no axe or equivalent)
- **Observed:** Contrast, forced colours, focus, reflow and reduced motion are checked by their own specs; no general WCAG 2.2 AA check runs per state, theme and width.
- **Expected:** AG-FE-9: automated accessibility checks on every state shown.
- **Recommendation:** Task 4e.4 adds "an axe check per state" for the thread; extend it to the existing states.

### F-13 — No per-output feedback and no change notice

- **Severity:** Low
- **Violates:** AG-MEM-3, AG-MEM-4
- **Where:** `Messages.tsx`, `OutcomePanel.tsx`; no notice surface
- **Observed:** No control to give feedback on a specific answer; no notice when capabilities change.
- **Expected:** AG-MEM-3, AG-MEM-4 (Medium caps).
- **Recommendation:** Backlog; not in Phase 4 scope.

### F-14 — No user control over capabilities

- **Severity:** Low
- **Violates:** AG-CTRL-5
- **Where:** `ui/packages/components/src/features/header/Preferences.tsx`
- **Observed:** Preferences cover presentation only.
- **Expected:** AG-CTRL-5.
- **Recommendation:** Backlog. The conversations mode is an administrator toggle; the brief shows it (read-only) where it changes what the user sees.

### F-15 — Fixture records are not labelled as sample

- **Severity:** Low
- **Violates:** EA-11
- **Where:** Captures against the fixture profile (`approval-390x844.png`: "supplier:approved-co")
- **Observed:** Fixture-profile records render like real records. The fixture profile is a development and test profile.
- **Expected:** EA-11. Rated Low: the profile is not a user-facing environment.
- **Recommendation:** Mockups label every sample (the 4e.2 mockup must). For the product, a server-reported environment marker is a separate decision.

### F-16 — The narrow section row clips "Current task"

- **Severity:** Low
- **Violates:** AG-A11Y-3
- **Where:** `ui/apps/web/src/app/standalone.css:55-58`; `grounded-320x720.png`, `reply-390x844.png`
- **Observed:** At 320 and 390 px the Overview, Capabilities and Current task links sit in a row that scrolls sideways inside itself; "Current task" is cut off with no cue. The page itself does not scroll sideways.
- **Expected:** AG-A11Y-3 (no loss of information at 320 px).
- **Recommendation:** Wrap the row or show a scroll cue; recheck in the thread layout.

### F-17 — Overlay and workbench reflow at viewport widths

- **Severity:** Low
- **Violates:** AG-FE-6
- **Where:** `layouts.css:38-49,63-72`
- **Observed:** The workspace now uses a container query; the overlay and workbench still use `@media (max-width:760px|900px)`.
- **Expected:** AG-FE-6.
- **Recommendation:** Use container queries in the thread layout (Task 4e.4).

### F-18 — Literal shadow colours in layout CSS

- **Severity:** Low
- **Violates:** AG-DS-1
- **Where:** `layouts.css:24,33`
- **Observed:** `rgb(0 0 0 / .16)` and `rgb(0 0 0 / .12)` instead of tokens.
- **Expected:** AG-DS-1.
- **Recommendation:** Add an elevation token.

### F-19 — No interaction-latency measurement

- **Severity:** Low
- **Violates:** AG-FE-11
- **Where:** none found in `ui/`
- **Observed:** No INP measurement, with or without streaming.
- **Expected:** AG-FE-11.
- **Recommendation:** Add a lab INP check once the thread view streams several runs.

## Decision proposals

No conflict with a binding requirement was found.

One gap in the standard itself, for the owner, not a defect of the surface: `state-model.md` has no state for an answer that is **grounded but not verified** (`SUCCEEDED` with reason code `grounded`, ADR 0033 §3, PR-19). Mapping it to Verified complete would break that state's Forbidden item. Proposal: add a normative state "Grounded answer" (user need: know the answer rests on recorded sources but was not independently checked; forbidden: presenting it as verified; criteria AG-APPR-6, AG-EXPL-2, AG-ID-1). Changing the standard needs owner approval and the skill check; until then the brief treats it as a product state with the nearest criteria named.

Recorded for the skill owner: `ag-ux-foundations/references/e-agent.md` still names research 16 as EA-10's binding source. ADR 0034 (accepted at G-A) says the source moves to the ADR; that edit is outside this task's paths.

## Backlog suggestion

| Work item | Findings | Where it lands |
|---|---|---|
| Thread of runs, one composer, refusals with the server's hint, `reply_to` | F-2, F-8 | 4e.3, 4e.4 (brief: research 20) |
| Closable artifact workspace in all four surfaces | F-3, F-9 (placement consistency), F-17 | 4e.4 |
| Disclosure and capability statement in the empty thread | F-1 | 4e.4 |
| Final-answer labelling; grounded and verified wording; citations and explanation | F-4, F-6, F-7 | 4e.5 (second cut line) |
| Server-sourced sidebar; no task text in storage | F-9, F-10 | 4e.3, 4e.4 (in `on`) |
| Accessibility check per state | F-12 | 4e.4, then the existing states |
| Approval card follow-up (with ADR 0034 §5) | F-5 | Named follow-up after Phase 4 |
| Identity on answers; feedback; change notice; capability controls; sample marker; narrow nav; tokens; INP | F-11, F-13, F-14, F-15, F-16, F-18, F-19 | Backlog |

## Opinions (no severity)

- Four status regions in the reply state, and two in `RUNNING` (the progress line and the pill), may make a screen reader announce the same change twice. EA-16 is met; one region per change would be calmer.
- The leading "·" marker on neutral statuses reads as punctuation ("· Completed · grounded, not verified"). A distinct shape would read better.
- "Send task" after a finished run and "Send" after a reply are two verbs for what a thread will treat as one action.

## Limits

- No real assistive-technology testing, no real-device testing, no moderated user evaluation against `metrics.md`, and no live integration (fixture profile and scripted `MockApi` only; no Odoo, no model).
- Dark and high-contrast themes were scored from the existing automated checks; the scratch theme captures for the approval did not run.
- No automated accessibility check (axe or equivalent) exists in `ui-conformance` (F-12), so AG-A11Y-1 is scored from inspection and the targeted specs only.
- No INP measurement exists (F-19).
- Script and browser checks verify mechanics only. They do not establish design quality or usability.

## Resolution log

<!-- Append-only. Later work adds dated entries here, for example "YYYY-MM-DD — F-3 resolved in <commit>, <evidence>". The scores above are never edited; a new audit supersedes this one. -->
