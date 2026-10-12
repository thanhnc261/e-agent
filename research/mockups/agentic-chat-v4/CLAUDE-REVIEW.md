Read-only: I read `README.md`, `QA.md`, `index.html`, `app.js`, `styles.css`, `../agentic-workspace-v3/action-model.js` and the five screenshots. I did not run `verify.mjs`; QA.md's reported pass is its claim, not something I verified — none of the findings below are assertions that suite makes.

## Does the structure answer the criticism

Partly. Chat is unambiguously the entry surface (`01`), the rail collapses to 68px, the workspace is on the right and closable, and mobile switches views. The messiness is gone: one column, one artifact, tabs instead of extra columns.

The "center on chat" part is only half-answered. Once work exists, the workspace is the visually dominant object: 53% width (`styles.css:542`, 54–56% ≤1100px, 50% ≥1600px), framed paper with border and shadow, holding the only primary-navy CTA, against unframed chat on canvas. In `02` chat is ~565px vs ~711px. Worse, chat is the only elastic column: expanding navigation takes the space from chat, never the workspace (`styles.css:929`, `958`) — in `03` chat drops to ~482px while the workspace grows. The surface claimed primary is the one that yields.

## Interaction contradictions

1. **Context loss on thread switch** (`app.js:283-291`): selecting a history item forces `workspaceOpen = false` and `tab = "document"`. README §4 promises the selected task survives placement changes; the draft does, the open artifact and tab do not. Returning to a thread in `review` hides the document you were reviewing.
2. **Stale prompt after dismissing the sample chooser** (`app.js:327`, vs `app.js:430-433`): `close-dialog` never clears `pendingPrompt`; only Escape does. Type text → submit → close with the X → click any welcome starter, and that old text silently replaces the scenario's canonical prompt. QA's "escaped free-text" item does not cover this path.
3. **Approval scope dead end**: "Change audience" exists only while `s.next && !t.step` (`app.js:159`). At step 2 — the message actually being sent, where `scope` is the recipient (`action-model.js:11-15`) — there is no way to narrow it. Reject → "Prepare new review" (`app.js:354`) keeps `step = 1`, bumps `revision`, and returns the identical proposal. A revision increment with no content change weakens revision-as-evidence.
4. **Prototype controls re-arm executed actions** (`app.js:298-303`): setting scene back to `review` from `done` leaves `records` and `step`, so the footer reads "has not been sent" while Activity still lists both read-backs. Labelled prototype, but it contradicts the invariant the mockup teaches.
5. **Mobile approval without context** (`13-workspace-320`): the composer is absent in workspace view, so you cannot question an action while approving it; document text is clipped at the footer with no scroll affordance.
6. Minor: welcome offers 3 starters, the chooser 6; rail panel-toggle and clock both only expand nav.
