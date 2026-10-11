# QA: study 05

Date: 2026-10-11.

## Commands run

| Command | Result |
|---|---|
| `node research/mockups/agentic-chat-v5/verify.mjs` (server on 127.0.0.1:4181) | 10 check groups passed. Covers 3 themes × 5 viewports. 13 named screenshots plus the theme set |

## Mechanics verified

- **Viewports:** 320×720, 390×844, 768×1024, 1440×900 and landscape 844×390. No horizontal overflow; the composer, workspace, footer and status stay within the width.
- **Themes:** light, dark and high contrast, set through `?theme=` and the in-page selector. The selector defaults to the OS preference.
- **Keyboard and focus:**
  - The approval dialog focuses its heading, and Enter does not approve.
  - Closing the workspace returns focus to the Workspace button.
  - Tabs keep the v4 arrow-key behaviour.
- **Truthful flow:**
  - Working, then Stop, gives Stopped (nothing sent).
  - Review, then Approve, gives Executing, then Committed · checking, then Verified.
  - Execution failure gives Failed, with "Nothing was created".
  - Stop while sending gives Outcome unknown, with no approve or resend path.
  - A source change gives Review outdated, naming the source.
- **Prototype separation:** the study controls are outside `<main>`.
- **Identity:**
  - The mark has no `data-shadow` layer and keeps the glossy reflection.
  - The light brand computes to `rgb(79, 138, 116)`.
  - The v4 comparison keeps its shadow.
  - The download link is a blob SVG.
- **No literal colours** in the v5 sources outside the documented brand override.
- **Console errors and external requests:** none in any run.
- **Automated accessibility:** **not run.** No axe package is installed in the repository, and the study must work offline. This gap is open.

## Self-review against the rubric

Fixed during this study:
- The "Study controls" toggle first floated over the workspace footer and covered Approve (found by the script). It was moved to an in-flow strip.
- The disclosure card was centred while the welcome text was left-aligned. It is now aligned.
- On a 390 px mobile screen, the topbar clipped the status pill. The title now truncates and the theme selector is narrower.
- The sticky dialog decision row had a different background from the dialog. It is now unified.

Also fixed after an advisor check (2026-10-11):
- The brief scoped Needs input in, but the first build lacked it. The handoff now asks for the audience in the conversation, and **Change audience** creates a new revision (AG-UNC-1, AG-CTRL-2; gap-audit F-14).
- The identity page now matches the v4 catalog's identity items:
  - light, dark, high-contrast and mono lockups with downloads;
  - sizes 24, 32, 40, 48, 64 and 96 px;
  - app tiles, the 48 px launcher and the author mark.

Still open:
- **Medium:** the embedded or docked overlay composition was not redrawn. `../agentic-chat-v4/overlay.html` still shows the v4 pose. The skill requires an embedded variant; it is excluded from this slice in the README and brief.
- **High:** no density scale (EA-13, AG-DS-3; gap-audit F-5).
- **Medium:** the reversibility text is fixed per example in the prototype. A product must get it from the server's action presentation (EA-2), never from the client.
- **Medium:** the glossy highlight and sidewall shading in `brand.js` still use literal white and black (AG-DS-1; gap-audit F-17). This was out of scope; tokenising needs a `brand.js` change, which is v4 territory.
- **Medium:** no automated accessibility run (see above). Contrast was checked only for the brand mark against the canvas (3.79:1).
- **Low:** the AI disclosure is shown at every new conversation. Whether to show it once per user is an owner decision (AG-DISC-1 asks for the first interaction).

## Design-system conformance

| Requirement | Result | Evidence |
|---|---|---|
| EA-12 (three verified themes) | partial | All three themes render at 5 viewports. A full contrast matrix for the new v5 components was not recomputed |
| EA-13 (density scale) | missing | Open |
| EA-14 (forced colours) | partial | v5 components declare forced-colours borders. Not verified in an emulator |
| EA-15 (icon and text) | met | Status uses the v4 `statusMarkup`; Stop is icon plus text |
| EA-16 (polite announcements) | met | `#announce` is polite; state changes announce, e.g. "Stopped" |
| AG-DS-1 (semantic tokens) | partial | v5 sources are token-only except the documented brand override. `brand.js` shading is still literal |
| AG-DS-2 (verified themes) | partial | As EA-12 |
| AG-DS-4 (AI-origin scoped) | met | The marker appears only on AI-drafted content and author labels |

## Screenshots inspected

These were looked at, not just generated:
- `01-entry-light`
- `04-review`
- `05-approve-dialog`
- `10-light-390`
- `10-dark-390`
- `11-identity`
- `13-needs-input`

## Limits

This QA does not establish real assistive-technology behaviour, real-device behaviour, moderated user evaluation or live integration. Script checks verify mechanics only. The design still needs the owner's selection before any production work.
