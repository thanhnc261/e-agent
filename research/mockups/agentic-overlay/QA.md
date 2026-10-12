# Enterprise-wide prototype: verification

Date: 2026-10-08. Revision 2. Scope: standalone synthetic design simulation, not product conformance or live integration qualification. Historical procurement QA and screenshots remain in `../procurement-overlay-v1/`.

## Commands and actual result

```bash
# Repository root, terminal 1:
python3 -m http.server 4178 --bind 127.0.0.1 --directory research/mockups/agentic-overlay
# Terminal 2, with existing ui/ dependencies installed:
node --check research/mockups/agentic-overlay/app.js
node --check research/mockups/agentic-overlay/fixtures.js
node research/mockups/agentic-overlay/verify.mjs
```

All commands passed. `git diff --check` also passed. The browser run used the repository's existing Playwright Chromium installation. The Browser plugin was unavailable during the original prototype session because its runtime referenced a missing module; the same standalone browser-check approach was retained.

The first revision-2 browser pass used the desktop-only New task control in its mobile test helper and timed out. The helper was corrected to minimize the panel and use the mobile-visible Overview navigation. The next pass found actual navigation overflow at 320px. A compact navigation rule fixed it. The complete script then passed; failures are not presented as successful checks.

## Verified mechanics

- Five business workflows are discoverable and category filters work.
- Connections show seven fixture entries with separate read/write access; search, no-match state and scoped detail dialogs work.
- Customer handoff requires one explicit approval for document creation and a **second** explicit approval for the message. First-action verification does not submit the second action.
- Confirmation initially focuses the heading. Enter there does not approve; Escape returns to review.
- Executing, committed/verifying and verified are distinct scenes, advanced manually for design inspection.
- Final handoff results have separate inspectable document and message artifacts.
- Partial unknown shows the verified document and unresolved message. A status check remains unresolved and never repeats a write.
- Stale proposal has no approval control until refresh. Editing produces a new proposal revision and returns to review; HTML-like text renders literally.
- Knowledge answer is read-only with an inspectable source and no write-approval control.
- Missing people access remains missing after a **local** request preview/save. General onboarding does not invent role, manager or start date.
- IT triage proposes an internal comment without access provisioning or ticket closure.
- Task state survives appearance, placement and minimize/restore. The launcher receives focus on minimize.
- Free-text input opens an explicitly guided workflow chooser; original composer text remains available, and is not falsely treated as an arbitrary fulfilled request.
- Calm, AI Presence and Operator; floating, docked and expanded views; all five task cards at 390 × 844; review/unknown and home at 320 × 740; desktop at 1440 × 1100.
- No page or panel horizontal overflow in checked layouts. Action footers remain above the design controls.
- No JavaScript page errors or external network requests were observed in the completed script.

## Screenshots

Current evidence is under `screenshots-v2/`. The `screenshots/` directory contains retained revision-1 captures and is not evidence for the new UI.

| View | Screenshot |
|---|---|
| Neutral enterprise home | [Home](screenshots-v2/home.png) |
| Connection catalog | [Connections](screenshots-v2/connections.png) |
| Customer handoff, floating | [Review](screenshots-v2/handoff-review.png) |
| Customer handoff, expanded | [Expanded](screenshots-v2/handoff-expanded.png) |
| Second action requires review | [Message review](screenshots-v2/handoff-message-review.png) |
| Two verified effects | [Handoff results](screenshots-v2/handoff-verified.png) |
| Partial verified / unknown | [Partial outcome](screenshots-v2/partial-unknown.png) |
| Read-only knowledge answer | [Knowledge](screenshots-v2/knowledge-answer.png) |
| Onboarding with missing context | [Limited context](screenshots-v2/onboarding-limited.png) |
| IT service proposal | [Service](screenshots-v2/service-review.png) |
| Appearance / placement | [AI Presence docked](screenshots-v2/presence-docked.png), [Operator floating](screenshots-v2/operator-floating.png) |
| Mobile home | [Mobile home](screenshots-v2/mobile-home.png) |
| Mobile task surfaces | [Handoff](screenshots-v2/mobile-handoff.png), [Knowledge](screenshots-v2/mobile-knowledge.png), [Onboarding](screenshots-v2/mobile-onboarding.png), [IT service](screenshots-v2/mobile-service.png), [Procurement](screenshots-v2/mobile-procurement.png) |
| Mobile confirmation / unknown | [Confirmation](screenshots-v2/mobile-confirmation.png), [Unknown](screenshots-v2/mobile-unknown.png) |
| Research board | [Board](screenshots-v2/reference-board.png) |

Visual review inspected home, connection catalog, expanded handoff, limited onboarding, mobile home, mobile handoff, mobile unknown, mobile confirmation and the reference board. The main task body intentionally scrolls with fixed decision controls.

## Limitations

This work does not implement providers, real authorization, digest checks, semantic validation, durable coordination, OAuth, ACL enforcement, audience policy or outcome verification. Providers, people, records, timestamps and results are authored fixtures. Manual scenario selection can jump to a result; this is explicitly design-studio behavior, not actual execution authority.

No human usability study, screen-reader validation, formal contrast/zoom audit, cross-browser qualification, production build or Python test suite was run. The production application was not changed. The prototype stores state in memory only. The broader API and domain work needed to implement this vision remains separate.
