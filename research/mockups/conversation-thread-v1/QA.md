# QA: conversation thread mockup (v1)

Date: 2026-10-22. Phase 4, Task 4e.2. Brief: [research 20](../../20-conversation-thread-brief.md) (approved at G-B, 2026-10-21; decisions recorded in the Phase 4 plan, Task 4e.1). Standard: ag-ux-foundations at `3ab6d7c2`. Status: awaiting the owner's selection at gate G-C (last section).

## Commands run

| Command | Result |
|---|---|
| `AXE_CORE_PATH=~/.vscode/extensions/ms-toolsai.datawrangler-1.24.2/out/axe-core/axe.min.js node research/mockups/conversation-thread-v1/verify.mjs` | Pass: 336 cases, 0 failed; 150 screenshots written (19 MB): every state at 1440 px per variant, every state at 390 px for A1 and six comparison states at 390 px for A2 and A3, plus the 320, 768, landscape, theme, 200 %, VI, docked and fallback sets |
| The same script with the `legacy` state removed from `scenario.js` (a temporary local edit, reverted before the final run) | Fail, as intended: `FAIL [registry] state legacy present: missing state: legacy`, then every `legacy` state case failed. The script fails when a state is missing |
| `grep -nE "#[0-9a-fA-F]{3,8}\b\|rgba?\(\|hsla?\(" styles.css compare.html index.html app.js` | No literal colour values (AG-DS-1) |

Output of the final run, verbatim:

```text
conversation-thread-v1 verify · 2026-10-22
states required: 13 (empty, reply, clarification, running, approval, refused, verified, grounded, failed, ended-answer, fallback, legacy, gallery); variants: a1, a2, a3; widths: 320x720, 390x844, 768x1024, 1440x1000, 844x390
axe-core 4.10.3 from ~/.vscode/extensions/ms-toolsai.datawrangler-1.24.2/out/axe-core/axe.min.js
  registry     13/13 passed
  states      195/195 passed
  axe          78/78 passed
  workspace     9/9 passed
  refusal       3/3 passed
  keyboard      3/3 passed
  stop          3/3 passed
  sidebar       3/3 passed
  themes        9/9 passed
  motion        3/3 passed
  text-200      3/3 passed
  vi            3/3 passed
  docked        3/3 passed
  fallback      4/4 passed
  inert         1/1 passed
  overview      1/1 passed
  network       1/1 passed
  console       1/1 passed
PASS: 336 cases; screenshots in research/mockups/conversation-thread-v1/screenshots/
```

The repository has no `axe-core` package; the run used the copy (4.10.3) bundled with a locally installed editor extension, passed through `AXE_CORE_PATH`. Without that variable the script prints "axe-core: NOT RUN … Recorded as a gap." and runs everything else.

## Mechanics verified

- **States.** All 13 required states (the brief's 11 in-scope rows, with "waiting approval" split into before and after the refusal, plus the reference sample for the other seven normative states) × 3 variants × 5 viewports: each renders, shows its expected labels, a sample label and the stop slot, has no horizontal overflow, keeps the composer inside the width, and contains no provider identifier and no leaked key or `null`.
- **Viewports:** 320×720, 390×844, 768×1024, 1440×1000, 844×390 (landscape); 1280×900 at 200 % text for four states per variant; Docked (26 rem panel) for three states per variant.
- **Themes:** light everywhere; dark and high contrast for the refused and grounded samples of each variant (with axe); forced colours (screenshot and control visibility); reduced motion (transitions removed).
- **Keyboard and focus:** per variant, the main path by keyboard (`hi` → reply → grounded → `draft a PO for it` → clarification → `40` → running → approval → confirm → verifying → verified). Focus stays in the composer after every send (EA-16); the polite region announces "Your turn"; the confirm step focuses its prompt, not Confirm (AG-APPR-8); Escape backs out of confirm; Tab reaches Confirm. Workspace: close and Escape return focus to the run card's Open; opening moves focus to the workspace heading; the phone view's Back returns focus. Tabs: arrow keys, Home and End. The legacy drawer on a phone closes with Escape and returns focus to its toggle.
- **Behaviour:** a message sent while a decision waits is refused with the server's hint, the draft is kept, the card text is byte-identical before and after, and nothing is added to the thread; closing and reopening the workspace keeps the draft and the card; Stop while running reaches "Task cancelled" and says nothing was sent; typed markup stays text.
- **Console errors and external requests:** none in any case.
- **Automated accessibility:** axe-core 4.10.3, tags wcag2a, wcag2aa, wcag21a, wcag21aa and wcag22aa: 78 runs (every variant × state at 1440 and 390 in light) plus dark and high contrast for two states per variant inside the `themes` group. No violations.

## Self-review against the rubric

The screenshots listed below were inspected and scored with the `ag-ux-review` rubric (binding requirements first, then criteria by enforcement, then state coverage). A passing script is not a passing design; the findings below come from looking at the renders.

### Fixed in this study

| Problem seen in a render | Criteria | Fix |
|---|---|---|
| The prototype "next event" button floated over the composer on phones; a `display` rule overrode `hidden` | AG-ENT-2 | `[hidden]` wins; the button sits in the prototype bar |
| Every sample opened scrolled to the top, so on a phone the latest run card was below the fold | AG-STAT-1 | The thread opens at the latest run; re-renders keep the scroll position |
| The sidebar showed the current conversation as "Completed · verified" while its run waited for review | AG-STAT-1, AG-FE-2 | The row shows the latest run's state, as `GET /v1/conversations` would |
| "null" rendered under the fallback composer | AG-UNC-4 | Fixed; `verify.mjs` now fails on `null`, `undefined` or a raw string key in the copy |
| In A2's 24 rem workspace the approval table squeezed "Current value" into broken lines | AG-APPR-3, AG-A11Y-3 | The table reflows on the workspace's own width (a `ws` container), not the app's |
| "Your turn" shown twice on one sidebar row; the legacy view kept the conversation's title; the explanation disclosure had no expand marker; the running card's line contradicted the recorded event | AG-DS-7, AG-STAT-2 | Each corrected |
| Forced colours: unselected tabs showed an underline and the Stop icon vanished | EA-14 | System colours for both |

### Open findings

#### S-1 — A3 inverts the hierarchy on a desktop with the sidebar

- **Severity:** Medium
- **Violates:** EA-10
- **Where:** `screenshots/a3/refused-1440.png`, `screenshots/a3/verified-1440.png`
- **Observed:** At 1440 px with the sidebar shown, A3's workspace is about 730 px wide and the conversation about 410 px. The conversation reads as the secondary column.
- **Expected:** The conversation is the primary surface (EA-10, ADR 0034 §1).
- **Recommendation:** If A3 is chosen, cap the workspace so the conversation stays at least as wide; otherwise choose A1's width (G-C question 4).

#### S-2 — No connection or reconnect state is shown in the thread

- **Severity:** Medium
- **Violates:** AG-STAT-3
- **Where:** every screenshot; no connection element in `app.js`
- **Observed:** The mockup marks legacy runs as "last seen", but has no live-stream connected, reconnecting or stale presentation at any width (the gap audit's F-9 notes the product hides it in narrow surfaces).
- **Expected:** AG-STAT-3.
- **Recommendation:** Task 4e.4 keeps today's connection status in the thread header at every width; not a G-C choice.

#### S-3 — A2 hides the run that "it" refers to while the decision waits

- **Severity:** Low
- **Violates:** AG-EXPL-3
- **Where:** `screenshots/a2/refused-1440.png`, `screenshots/a2/refused-390.png`
- **Observed:** Run 1 (the grounded answer naming Bracket B-12) folds to one row while run 2 waits for approval; its messages are one click away. The decision itself is complete on the card, so nothing material is hidden.
- **Expected:** Context the user relies on is visible at the summary level (AG-EXPL-3).
- **Recommendation:** If folding is chosen (G-C question 3), keep the latest run and the run it carried from unfolded.

#### S-4 — A2's narrow workspace pushes the decision controls below the fold

- **Severity:** Low
- **Violates:** AG-APPR-3
- **Where:** `screenshots/a2/refused-forced-colors-1440.png`, `screenshots/a2/refused-1440.png`
- **Observed:** At 24 rem the approval table stacks into rows, and "Review and approve" sits below the fold at 1440×1000. The workspace scrolls as one region with its terms in order above the controls; there is no inner scroll region.
- **Expected:** AG-APPR-3 (terms visible without an unindicated scroll region).
- **Recommendation:** Prefer the medium width (G-C question 4).

#### S-5 — Two of the four ADR 0016 surfaces are not rendered

- **Severity:** Low
- **Violates:** AG-ENT-3
- **Where:** README "Surfaces covered and not covered"
- **Observed:** Workspace (full page) and Docked are rendered; Compact (overlay) and Workbench are not. The layout switches on the app's width, so the phone and docked renders stand in for the narrow placements.
- **Expected:** The same task in each placement (AG-ENT-3).
- **Recommendation:** Task 4e.4's conformance run covers all four surfaces in the product.

### Inherited and unchanged

- **F-5 (gap audit):** the card's capped inner scroll region in Compact and Docked is not reproduced; here the whole workspace scrolls. The card follow-up (ADR 0034 §5) still owns F-5.
- **F-11:** the acting identity and connection are shown on the card only, not on answers or reads; in the backlog, not asked at G-B.
- **The grounded state** has no normative state; it is judged as a product state with AG-APPR-6, AG-EXPL-2 and AG-ID-1, as the brief says (decision 8 is a separate skill change).

### Interpretation recorded

The task asks for a stop control in every state. Where nothing runs (the empty thread, ended runs, legacy, the gallery's ended states), the stop slot stays in place, disabled, with the visible reason "Nothing is running"; it is enabled on every active run, and in "Result not confirmed" it is disabled with its own reason while the safe check is offered (EA-4). This satisfies AG-CTRL-1 without an enabled control that fails (AG-ENT-1).

### Opinions (no severity)

- The active run has two Stop buttons, on its card and under the composer. One may be enough once the stop slot is always in view.
- The permanently disabled Stop in ended states adds a grey control to most screens; the reason text alone might be calmer.
- A run's title is its task text, so run 1 reads "hi" on its card and in the workspace although it answered "which products are short?". Tasks 4e.3 and 4e.4 should decide which server field titles a run.
- The neutral "·" marker on "Completed · grounded, not verified" still reads as punctuation (gap audit opinion).
- A refusal uses `role="alert"`, like today's errors; run-state changes use the polite region (EA-16).

## Design-system conformance

| Requirement | Result | Evidence |
|---|---|---|
| AG-DS-1 | met | Colours, sizes and durations come from the linked production `tokens.css`; the literal-colour grep above found none |
| AG-DS-2 | met | The production token contrast test covers the three themes; axe colour-contrast passed in light, dark and high contrast here |
| AG-DS-3 | not exercised | No density switch in the mockup; controls use `--ea-control-min-height` (44 px) and badges `--ea-control-min-target` |
| AG-DS-4 | met | The "AI" chip marks the disclosure and the agent's words only; verified values, citations and the card carry none (`a1/grounded-1440.png`, `a3/verified-1440.png`) |
| AG-DS-5 | met | Every status pairs a marker with text (✓ ✕ ◆ ◍ ？ ·); forced-colours screenshots keep them |
| AG-DS-6 | met | `motion` group: transitions removed under reduced motion; no essential animation |
| AG-DS-7 | met | One label and marker per state in the sidebar, run card, stop slot and workspace; grounded never takes the verified tone (checked in `states`) |
| EA-12 | met | Light, dark and high-contrast renders and axe runs (`*/refused-dark-1440.png`, `*/refused-high-contrast-1440.png`) |
| EA-13 | not exercised | As AG-DS-3 |
| EA-14 | met | `*/refused-forced-colors-1440.png`: controls, current item, selected tab and status markers visible |
| EA-15 | met | As AG-DS-5 |
| EA-16 | met | One polite region announces state changes; the keyboard path checks the announcement and that focus did not move |

## Screenshots inspected

Looked at, not only generated (some before and again after the fixes above):

- `screenshots/00-overview.png`
- `screenshots/a1/refused-1440.png`, `a1/grounded-1440.png`, `a1/empty-390.png`, `a1/gallery-1440.png`, `a1/refused-dark-1440.png`, `a1/approval-workspace-390.png`, `a1/refused-text200-1280.png`, `a1/running-390.png`, `a1/refused-forced-colors-1440.png`
- `screenshots/a2/grounded-1440.png`, `a2/legacy-1440.png`, `a2/vi-refused-390.png`, `a2/refused-forced-colors-1440.png`
- `screenshots/a3/verified-1440.png`, `a3/grounded-390.png`, `a3/refused-high-contrast-1440.png`
- `screenshots/fallback/features-1440.png`, `fallback/route-error-390.png`

## Limits

This QA does not establish:

- real assistive-technology behaviour (axe and focus checks only);
- real-device behaviour (Chromium viewport emulation only);
- moderated user evaluation against the brief's metrics (M-3 to M-7);
- live integration: no server, model or business system; the thread is fixed sample data;
- the Compact and Workbench placements (S-5) or a density switch.

At 200 % text a 1280 px window becomes the one-view composition (the app is under 60 rem), so the workspace replaces the conversation while open; the check confirms no loss or overflow, not that this is the preferred design. Script checks verify mechanics only.

## Decisions for G-C

Reply with the numbers and one word each, for example "1 A1, 2 inside, 3 keep, 4 medium, 5 card, 6 compact". Question 1 picks a variant; questions 2 to 6 let you take one detail from another variant. Answering 1 alone takes that variant as rendered.

1. **Variant.** Recommended: A1 (run cards, workspace about 40 %, hint inside the composer). Options: A1 / A2 / A3.
2. **Where the refusal hint sits.** Recommended: inside the composer, above the kept draft (A1). Options: inside / under / callout.
3. **Ended runs in the thread.** Recommended: keep their messages (A1, A3); folding hides the run a follow-up refers to (S-3). Options: keep / fold.
4. **Workspace width on desktop.** Recommended: medium, about 40 % (A1); wide inverts the hierarchy (S-1), narrow stacks the card (S-4). Options: medium / narrow / wide.
5. **When the workspace is closed on desktop.** Recommended: the run card and the stop slot carry the status (A1, A2). Options: card / bar.
6. **Run card detail.** Recommended: compact (status, one result line, Open; A1). Options: compact / rich.

**Selection:** awaiting G-C. The owner's answer is recorded in the Phase 4 plan (Task 4e.2) and the handoff, because this file is create-only once committed.
