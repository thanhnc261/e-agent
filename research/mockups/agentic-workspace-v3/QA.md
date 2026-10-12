# Design study 03: verification

Date: 2026-10-09. Evidence is synthetic browser/prototype evidence only.

## Actual checks

`node research/mockups/agentic-workspace-v3/verify.mjs` passed against the local static server on port 4180.

- Six workflow examples; category filtering and six connection examples.
- Source inspection, explicit confirmation, initial confirmation focus, and Enter without accidental approval.
- Creating the handoff document does not approve its subsequent channel message.
- Separate read-back simulation precedes the verified-result screen.
- Unknown outcomes cannot be approved or resent; an unresolved read-back remains unresolved.
- Stale review blocks approval; refreshing creates a new displayed revision.
- Owner-only clarification carries through both actions and their confirmation without a conflicting team audience.
- Exact confirmation includes shared action metadata, material values and content. Material terms precede document content.
- Verification evidence contains two distinct fictional read-back records rather than input sources.
- Unknown actions are labelled sent/unresolved; read-only and missing-access state selectors are disabled.
- The bare `n` shortcut does not dismiss a review when focus is in the assistant.
- Rejecting the service action displays that no action was sent.
- Read-only answers have no approval action; missing access explains that no employee records were read.
- Composer text is escaped, and survives minimize/resume.
- Desktop 1440×1100, mobile 390×844 and 320×844: no horizontal overflow; decision footer does not overlap the study bar.
- Narrow topbar groups do not overlap; action sequencing text is at least 10px.
- Identity/component page contains 27 matching icons and SVG marks. Source coverage contains all 34 audited pages/articles.
- Light/dark presentation. Dark foreground/background regression assertions after visual correction.
- No JavaScript page errors and no external requests during the exercised flows.

## Visual inspection

Inspected workspace, expanded review, contextual overlay, mobile review, mobile unknown outcome and dark review. Corrected brand wrapping and dark-theme inheritance, then regenerated captures.

Screenshots: `01-workspace`, `02-connections`, `03-compact-review`, `04-expanded-review`, `05-source-detail`, `06-confirmation`, `07-second-approval`, `08-verified`, `09-unknown-outcome`, `10-working`, `11-in-context`, `12-knowledge`, `13-missing-access`, `14-dark-review`, `15-home-{320,390}`, `16-review-{320,390}`, `17-confirm-{320,390}`, `18-unknown-{320,390}`, `19-service-review`, and `20-design-rationale`, all in `screenshots/` as PNG files.

Additional captures `21-identity-components`, `22-identity-mobile`, `23-identity` and `24-components` show the final asset/component library. The final workspace, expanded review, narrow review, logo and component catalog were visually inspected after the palette and layout changes.

Scope and material terms precede the document body; the full action is repeated in confirmation. Long reviews and confirmations still scroll. Not every term is simultaneously visible on narrow screens. The decision footer occupies a separate layout region.

The original Claude review and resolution are in `CLAUDE-REVIEW.md` and `REVIEW-RESOLUTION.md`. The browser suite passed again after these fixes and identity changes. Claude source/screenshot inspection does not substitute for this browser run.

## Limits

No live integrations, model calls, production approvals, real business writes, user study, screen-reader evaluation, automated accessibility audit or certification. English-only concept copy. Multi-domain examples and connection availability are fictional; actual product support remains bounded by admitted plugins and current implementation evidence. The role model, workflow discoverability and task efficiency need evaluation with intended users before implementation.

The earlier production visual pass was paused at the user’s instruction. Its final regression suite was not completed after its last edits; this report does not qualify those changes. The new mockup was not applied to the production UI.

## Final follow-up result

Claude's read-only source/screenshot follow-up closed all three original walkthrough blockers and judged the mockup ready for owner design review. See `CLAUDE-FOLLOWUP.md`. Minor icon/hover/label cleanup followed; the full browser script passed again and regenerated screenshots. No production readiness claim follows from this review.
