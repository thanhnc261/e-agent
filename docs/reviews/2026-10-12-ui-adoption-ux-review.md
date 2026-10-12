# Review: production UI after the v4 foundation adoption

- **Artifact:** `ui/` working tree on `main` at `af50c62`, plus the uncommitted 2026-10-12 adoption changes ([results](../handoffs/2026-10-12-ui-foundation-adoption-results.md)).
- **Brief:** the 2026-10-09 visual-rework package, as amended by EA-10, and the owner goals "use that logo. and finish all FE work" and "continue to done all UI".
- **Reviewer and date:** Claude (ag-ux-review, review mode), 2026-10-12.
- **Standard:** ag-ux-foundations at `888398e`.

## Verdict

**Approved, with Low findings.** No Blocker or High finding remains open. Six defects were found during this review and fixed in the same pass (see "Resolved in this pass"). Three Low findings remain.

## What was run and inspected

| Check | Command or method | Result |
|---|---|---|
| Product checks | `pnpm --dir ui check` | Pass: 153 tests; typecheck, format, boundaries, neutrality and build green |
| Conformance | `pnpm --dir ui conformance` | 139 passed, 2 skipped (138 before this pass; the new test is `forced-colors.spec.ts`) |
| Captures | `E_AGENT_UI_CAPTURE_DIR=… playwright test visual-review`, after `pnpm build` | 20 screenshots in `evidence/2026-10-12-ui-phase-d/`, all inspected |
| Viewports | 390, 768 and 1440 px captured; 320 px asserted in `preferences.spec.ts` (no horizontal overflow) | Landscape phone was not captured |
| Themes | light, dark and high contrast: approval and result. Forced colours (emulated): approval | Inspected; see R-2 |
| Keyboard only | Existing conformance specs (preferences, approval focus, focus return) and the new forced-colour focus check | Pass |

## State mapping

| Artifact state | Normative state | Reached how |
|---|---|---|
| `idle` / "Ready" | Ready | Load `/` |
| `CREATED`, `RUNNING` / "Working on it" | Working | Submit a task |
| `WAITING_INPUT` | Needs input | Clarification fixture (conformance) |
| Policy or validation block in the approval findings | Blocked by rules | Blocked-finding fixtures (conformance) |
| `WAITING_APPROVAL` / "Needs review" | Awaiting decision | Submit `restock widget-a` |
| Expired or digest-mismatch approval | Decision invalidated | Expiry and integrity fixtures (conformance) |
| Rejected approval | Rejected | Reject proposal |
| `RUNNING` with an action `DISPATCHING` / "Sending the change" | Executing | Action-state snapshot (unit-tested `runStatusKey`) |
| `VERIFYING`, or `RUNNING` with an action `COMMITTED` | Verifying | Approve, then confirm |
| `NEEDS_RECONCILIATION`, or an action `UNKNOWN` | Outcome uncertain | Reconciliation fixture (conformance) |
| `FAILED` | Failed | Failure fixture |
| `CANCELLED` | Cancelled or stopped | Stop task |
| `SUCCEEDED` / "Completed · verified" | Verified complete | Approve, then confirm |

Normative states not reachable: none.

## Findings

### R-1: Recent tasks collapse when the layout passes the compact breakpoint

- **Severity:** Low
- **Violates:** AG-CTX-1
- **Where:** `ui/packages/components/src/features/task-navigation/TaskNavigation.tsx:13`; compare `evidence/2026-10-12-ui-phase-d/desktop-result.png` (collapsed) with `desktop-approval.png` (open)
- **Observed:** The history `<details>` is opened by a render prop derived from `surface.compact`. After the window passes the compact width and returns, the list stays collapsed.
- **Expected:** Navigation context should not change because of a transient resize.
- **Recommendation:** Keep the user's toggle state in component state, seeded from `expandedHistory` once (L6 components).

### R-2: Compact overlay header pushes its controls onto a second row

- **Severity:** Low
- **Violates:** AG-DS-3
- **Where:** `evidence/2026-10-12-ui-phase-d/mobile-overlay-approval.png`
- **Observed:** At 390px the view switch, preferences and Stop move to a second header row, and the connection label is hidden. The controls remain reachable and labelled.
- **Expected:** Compact surfaces keep the header in a single scan line where possible.
- **Recommendation:** Move the view switch into the preferences popover on compact overlay surfaces (L6 header).

### R-3: Landscape phone viewport is not covered by a capture or an assertion

- **Severity:** Low
- **Violates:** AG-DS-3
- **Where:** `ui/packages/ui-conformance/tests/visual-review.spec.ts`
- **Observed:** The captures cover 390, 768 and 1440 px in portrait only.
- **Expected:** The review workflow asks for landscape inspection.
- **Recommendation:** Add an 844×390 capture of the approval state.

## Resolved in this pass

| Defect found | Criteria | Fix |
|---|---|---|
| The header said "Working on it" while an approved change was being sent, committed or unconfirmed (gap-audit F-1), even though the server already reports action states | EA-3, AG-APPR-6, AG-STAT-1 | `runStatusKey` in `ui-core/src/presentation.ts` names the phases "Sending the change", "Change recorded · checking" and "Change not confirmed", using only the server's action states. The header sets `data-phase`; the vanilla reference uses the same helper. |
| Task details showed raw enums (`COMMITTED`, `VERIFIED`) | AG-STAT-1, EA-3 | `actionStatusKey` labels in EN and VI for all 12 action states (`OutcomePanel.tsx`, `reference-vanilla`) |
| Agent messages still used the old "e" letter tile | Owner brand direction | `Messages.tsx` renders `BrandMark` |
| Evidence source disclosures were labelled "Task details" | AG-ID-1 | New `evidence.sourceValues` label: "Observed values" / "Giá trị đã quan sát" |
| No forced-colours support at all | EA-14 | A `@media (forced-colors: active)` block in `components.css`, plus `forced-colors.spec.ts` |
| Recent-task status was centred under a left-aligned title | Polish | `.ea-task-link` alignment |

Stop (gap-audit F-3) was already met in production. "Stop task" is offered in every non-terminal state except `NEEDS_RECONCILIATION`, where stopping cannot change an effect that may already have happened (`Header.tsx:62`).

## Decision proposals (conflicts with binding requirements)

None.

## Strengths

- The approval shows every material term without expansion, at every viewport and appearance (`desktop-approval*.png`, `tablet-approval.png`).
- Unknown outcomes have their own tone and label, separate from failed and from verified (`runStateTone.ts`, `outcome.ts`).
- Changing the appearance leaves terms, status and controls identical; this is asserted in `presentation.spec.ts`.

## Opinions (no severity)

- In high contrast the disabled "Send task" button is faint sage. WCAG exempts inactive controls, but a GrayText-style disabled colour would look more deliberate.
- The logo's brand green (#839675) on the light canvas is 3.02:1. That is fine for a decorative mark, but it is the lowest-contrast element on the page.

## Limits

- No real assistive-technology testing (screen reader, voice control).
- No real-device testing; forced colours were emulated in Chromium only.
- No moderated user evaluation against `metrics.md`.
- No live integration: all captures use the conformance mock API and fixture data, which is not a production data path.
- No automated axe audit, because the repository has no axe package.

Script and browser checks verify mechanics only.
