Read-only review complete. **No blocker for the paused production work** — everything below is a small fix in the candidate artifact.

## Logo

Legible and professional. The mark reads clearly as a lowercase "e" with an open bottom-right terminal at every size in `01-identity-desktop.png`, including the 24px header chip and the panel header in `04-dark-420.png`; the wordmark resolves unambiguously as "e-agent" and the wordmark's "e" echoes the mark's open terminal. Two polish items, not defects:

- **Weight/medium mismatch.** The mark is fill-based (`brand.js:3`), the wordmark is stroked at `stroke-width: 2.6` (`brand.js:6`). The mark holds its weight as it shrinks while the wordmark thins toward gray — already visible in the large lockup in `01-identity-desktop.png`, where the mark reads noticeably heavier than the lettering.
- **Two-tone primary lockup.** Navy mark, near-black wordmark in the same lockup, against guidance on the same page to "use one color."
- `brand.js:4` comment ("Hand-drawn, outlined lowercase lettering") no longer describes the render; it's clean geometric monoline.

## Defects

1. **Focus is dropped at wide container widths** — `overlay-preview.js:22-25`. `#open-work` calls `setView("work")` then `$("#view-toggle").focus()`, but `.overlay-view-toggle` is `display: none` at ≥801px (`overlay.css:158-160`). At the 640px and 1040px panel settings the view switch is a no-op (both panes already shown) and `.focus()` silently lands on `<body>`, so a keyboard user loses their place on the primary in-conversation affordance. The suite can't see it: `verify-foundation.mjs:103-105` sets 420px before clicking `#open-work` and `:169-170` sets 320px — the wide path is never exercised.

2. **Missing `:host([hidden])` in the portable bundle** — `build-overlay.mjs:6` emits `:host { all: initial; display: block; }`. Author `:host` rules beat the UA `[hidden] { display: none }`, so `preview.hidden = true` (`overlay-preview.js:75`) would not hide a consumer's element. It only works here because `overlay-host.css:135` — harness-only, explicitly "never an overlay dependency" — adds `[hidden] { display: none !important }`. `verify-foundation.mjs:117-119` asserts only that the launcher is visible and focused, never that the panel hid, so the suite would not catch the regression off-harness.

3. **Confirmation feedback can land in a hidden subtree** — `#local-messages` lives inside `.overlay-chat` (`overlay-preview.js:12`), which is `display: none` in the work view at ≤800px (`overlay.css:145-147`). Confirming the dialog from the work view writes the result there (`:64`); it is neither visible nor announced, since live-region updates in a `display:none` subtree are dropped. Not covered by the suite.

4. **Typography isolation is narrower than claimed** — `all: initial` is close to decorative: any document-tree rule targeting the host beats a `:host` rule, `!important` not required. The real defense is the explicit list at `overlay.css:7-15`, which omits `font-style`, `font-variant`, `text-indent`, `text-shadow` and `tab-size`. The stress fixture structurally cannot expose `font-style`: `.host-stress e-agent-foundation-preview { font: 30px/4 Georgia !important }` (`overlay-host.css:159-163`) uses the `font` shorthand, which resets `font-style` to `normal`. And the assertion (`verify-foundation.mjs:38-63`) measures seven properties on `#review` — a button, the least inheritance-sensitive element in the tree. Probe `.overlay-messages p` instead.

5. **Bundle cascade order is hand-reconstructed and unchecked** — `build-overlay.mjs:4-14` strips every `@import` from `styles.css` and re-assembles tokens → components → shell → overlay by hand. Nothing verifies that order matches `styles.css`'s own import sequence, so same-specificity rules could resolve differently in the shadow bundle than on the production page; the `--check` guard at `:16` only proves the bundle matches itself. This weakens the "bundles the SAME CSS" claim. Separately, confirm the font strategy is system-only — `@font-face` inside a shadow root is not honored.

6. **Container breakpoint is an unchecked magic number, duplicated into the test** — `overlay.css:148` hard-codes `min-width: 801px` and `verify-foundation.mjs:97` asserts `width > 800`. The token drift guard that covers `MOBILE_QUERY` (`build.mjs:92`) gives no protection here; CSS and test would drift together. Same for `max-width: 390px` at `overlay.css:162`.

7. **Text-enlargement test under-stresses the scale** — `verify-foundation.mjs:156-160` raises only `--ea-font-size-md`, `-body` and `-xs`. It leaves `--ea-font-size-caption` (`.overlay-heading small`, `.composer-note`) and `--ea-font-size-xl` (both pane headings) untouched, so `06-enlarged-text` doesn't represent a real 200% enlargement.

## Smaller / one-line

- `aria-label` on `<e-agent-foundation-preview>` (`overlay.html:61`) is inert — a custom element has no implicit role, so AT drops it; the inner `<section aria-label="e-agent conversation">` carries the name, though it now wraps both panes, not just the conversation.
- `overlay-preview.js:4,12` fetches the CSS and injects it as a `<style>` string per instance — production should use a constructed `CSSStyleSheet` + `adoptedStyleSheets`; the `fetch` also makes the element unusable outside a served context.
- Design question, not a defect: a 480px modal (`overlay.css:126`) over a 320/420px docked panel deliberately overflows onto the host page. Intended? (It is viewport-anchored and bounded — `verify-foundation.mjs:150-151` already checks that at four viewports and will catch WebKit if it differs.)
- Compressible: the `forced-colors` block (`overlay.css:174-181`) covers four containers only and that step makes no assertions; `errors` captures `pageerror` only and is asserted last; two screenshots share the `07-` prefix.

## Claims — what held, what I didn't verify

Held in the files: shared bundle sourcing (`build-overlay.mjs:4-14`), container-driven geometry (`overlay.css:2,148,162`), `:host` attribute selectors for dark/high-contrast (`build.mjs:81-84`), independent theme instances (`verify-foundation.mjs:126-138`), draft retention, 320–1040px panels, dialog focus/restore, narrow viewports, long localized content. Demo-only framing is consistent throughout ("no live integrations", "cannot execute or authorize an action", "candidate shadow-root evidence only").

Not verified within this scope: the 99-token / 46-icon counts; the Chromium pass itself (I read the two screenshots, I did not run the suite); `styles.css` and `components.css` contents.

Last item, matching your constraint: the PASS string at `verify-foundation.mjs:188` enumerates "Shadow DOM host isolation, host themes, … forced colors" and reads like a qualification result. Word it as candidate-harness evidence so the log can't be quoted as production readiness.
