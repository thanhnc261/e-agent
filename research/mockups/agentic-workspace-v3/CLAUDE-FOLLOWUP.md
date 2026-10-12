## Review — `research/mockups/agentic-workspace-v3`

**Method:** I read source and the named screenshots only. I did not run `verify.mjs`, the static server or any browser; every statement below is source/image inspection or a reading of what the suite *asserts*. QA.md:7 reports the pass; I take that as the study's claim, not mine.

### B1–B3

**B1 — resolved.** `app.js:224` now emits `.scope-line` → `termList(a.fields)` → `.document-preview` inside `artifact()`, and the confirmation (`app.js:299`) repeats metadata, material values, disclosure and content. `04-expanded-review.png` shows the scope line plus all four terms above the fold with the footer pinned. `verify.mjs:254-259` asserts `terms.y < preview.y`. Two caveats: that assertion sits inside the 390/320 loop only — desktop order is unasserted (same DOM, so low risk) — and nothing asserts above-the-fold visibility. `16-review-320.png` still cuts at "Project owner" while `Review & approve` is visible. QA.md:37 states this plainly, and the confirmation is now the binding surface, so I accept it.

**B2 — resolved, convincingly.** `action-model.js:2-55` is a single presentation record; title, destination, scope, fields, disclosure, confirmation and read-back all read from it. `verify.mjs:204-224` asserts "Project owner only" in confirmation 1, `Alex Morgan · project owner only` in action-2 terms, `Direct message / Alex Morgan` in confirmation 2, and `doesNotMatch /8 internal members/` on both — the exact contradiction I flagged is now negatively asserted.

**B3 — resolved, with one honest limit.** `verificationEvidence()` (`app.js:226-244`) renders observed record ID, read-back time, verifier, check result, full action metadata and observed material values; `app.js:450-461` branches so the review-screen button still opens "Task sources". `verify.mjs:102-108` asserts two records, the verifier string and zero `.source-card`. The limit: `sampleReadBack()` `structuredClone`s the approved action and hardcodes "Observed values match", so the observation is derived from the proposal. Correct as fixture, but the study never draws the one state that makes read-back meaningful — observed ≠ approved. Worth a slide, not a blocker.

### Remaining issues (none blocking)

- `design-system.html:238` shows the recovery button with a search icon; `app.js:260` renders it bare — catalog diverges from the surface it documents.
- `styles.css:617` keeps one non-tokenized hover border (`#bcb2eb`) that will not re-theme in dark.
- `artifact(s)` (`app.js:214`) takes one parameter but is called `artifact(s, true)` at `:182` and `:184` — dead argument.
- `verify.mjs:168-177` still asserts dark mode by hardcoded `rgb()` equality on `body`; it will fail on any legitimate token change.
- H9 (requester ≠ approver) is unresolved and correctly recorded as an adoption requirement (REVIEW-RESOLUTION.md:17, STATE-MATRIX.md:20).

### Identity and layout

The "open e" glyph has one geometry source (`icons.js:36-37`) consumed by the app, the design-system page and `export-assets.mjs` — so the 27-icon family and four logo assets cannot drift, and `design-system.html` says outright it is not the Agentic Design or UX Pilot mark. Palette is warm paper / charcoal / navy with a violet assistant cue, fully semantic in `:root` with dark overrides. `01-workspace.png` is genuinely simple — generous whitespace, one primary action, no decoration — and `04-expanded-review.png` reads as three clean regions. Only nit: the `YOUR WORK, CONNECTED` eyebrow duplicates the H1 verbatim.

### Production adoption gaps

Unchanged and correctly stated: the renderer (`innerHTML` + one delegated click chain) and fixture string interpolation must not be ported; `actionView` is presentation only and is not a normalized action or approval token; no keyboard/screen-reader, usability, role-model or live-integration evidence exists anywhere.

**Ready for owner design review: yes.** B1–B3 are each closed with code and a negative assertion behind them, and the residual scroll is disclosed rather than papered over. Not ready for production adoption, which the study does not claim.
