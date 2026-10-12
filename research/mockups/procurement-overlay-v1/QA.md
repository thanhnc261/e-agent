# Prototype verification

Date: 2026-10-08. Scope: standalone design simulation only. Chromium checks use the repository's existing Playwright dependency. No backend, ERP, model, database or production UI was exercised.

## Commands and results

From the repository root, start the static server in a terminal:

```bash
python3 -m http.server 4178 --bind 127.0.0.1 --directory research/mockups/agentic-overlay
```

In a second terminal, with the declared UI dependencies already installed:

```bash
node --check research/mockups/agentic-overlay/app.js
node research/mockups/agentic-overlay/verify.mjs
git diff --check
```

All three commands passed in this session. The first browser pass found host metric overflow at 320px; the mobile metric layout was corrected and the complete prototype script passed on rerun. Screenshot timing was also adjusted to wait for placement transitions before capture.

The Browser plugin could not initialize because its runtime referenced a missing `browser-service.mjs`. No browser connection was established through that plugin. Local headless Chromium through the existing Playwright installation was used for verification instead.

## Checked behaviors

- Calm, AI Presence and Operator render the same review fixture.
- Review opens an explicit confirmation dialog, initially focused on its heading. Enter on that heading does not approve; Escape returns to review.
- A separate approval click advances to executing; explicit scene controls then advance to committed/verifying and verified.
- Unknown-result status checking remains unresolved; no approve control or write retry appears. Stale approval requires refreshing the proposal fixture.
- Decline and stop produce their corresponding fixture outcomes.
- Appearance changes and minimize/restore retain composer text. Minimize focuses the launcher.
- Submitted HTML-like text is displayed literally rather than mounted as markup.
- Floating, expanded and docked desktop layouts retain reachable decision footers.
- The nine primary scenarios fit horizontally at 390 × 844; review also fits at 320 × 740. The panel stays inside the viewport and its decision footer does not overlap the studio controls.
- The reference board fits horizontally at desktop width.
- No JavaScript page errors or external requests were observed during the scripted checks.

## Visual review

Inspected captured desktop Calm, AI Presence, Operator, expanded and uncertain views; the reference board; and mobile review and confirmation. The task body intentionally scrolls while actions remain anchored. Screenshots cover additional states for review:

| View | Artifact |
|---|---|
| Calm review | [Screenshot](screenshots/calm-review.png) |
| AI Presence review | [Screenshot](screenshots/presence-review.png) |
| Operator review | [Screenshot](screenshots/operator-review.png) |
| Expanded review | [Screenshot](screenshots/expanded.png) |
| Docked review | [Screenshot](screenshots/docked.png) |
| Ready | [Screenshot](screenshots/ready.png) |
| Unknown outcome | [Screenshot](screenshots/uncertain.png) |
| Verified fixture result | [Screenshot](screenshots/verified.png) |
| Mobile ready | [Screenshot](screenshots/mobile-ready.png) |
| Mobile review | [Screenshot](screenshots/mobile-review.png) |
| Mobile confirmation | [Screenshot](screenshots/mobile-confirmation.png) |
| Mobile unknown | [Screenshot](screenshots/mobile-uncertain.png) |
| Mobile verified | [Screenshot](screenshots/mobile-verified.png) |
| Reference board | [Screenshot](screenshots/reference-board.png) |

## Limits

This is not the product conformance suite. No real approval digest, authorization, durable event streaming, reconciliation or independent ERP verification runs here. Other browsers, screen readers, localization, formal contrast/zoom audits and human usability studies were not evaluated. No production build or Python test suite was run because only a static research prototype and documentation were added. Existing unrelated working-tree changes were preserved.
