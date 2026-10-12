I reviewed the design-system sources, both HTML entry points, `styles.css`, `app.js`, `catalog.js`, the verifiers, and three screenshots from `screenshots/system/`. Note: several files were being reformatted while I read them (`components.css`, `styles.css`, `catalog.js`, `verify-system.mjs`, and the chat's workspace tabs all changed mid-review), so line numbers are from the state at my last read. I did not run anything; cascade and specificity claims below are source analysis, not observed renders.

## High

**1. The destructive button loses its fill on hover and becomes near-unreadable.**
`styles.css:61-63` applies `button:hover { background: var(--ea-color-surface-hover) }` to every button. Specificity `(0,1,1)` beats `.ds-button-danger` `(0,1,0)` at `design-system/components.css:148-154`, and `components.css` is `@import`ed first (`styles.css:2`), so it loses on source order too. `.ds-button-danger:hover` (`components.css:155-157`) only sets `filter`, so it never restores the background. On hover, the Remove button keeps `color: var(--ea-color-accent-text)` (`#ffffff` light) over `--ea-color-surface-hover` (`#e9e1d3`) — roughly 1.3:1. `.primary` and `.send-button` escape this only because they have explicit `:hover` rules at `styles.css:431-434`. Same root cause, cosmetic variant: `.new-chat`'s `surface-selected` background is also replaced on hover.
Fix: give `.ds-button-danger:hover` a background (e.g. a darkened `status-failed`), and narrow `button:hover` so it cannot repaint filled variants.

**2. High-contrast theme: status badges have no boundary.**
`.ds-status` sets `border: … solid transparent` (`components.css:10`) and relies on the tone surface for separation, but every `status-*-surface` in `tokens/high-contrast.tokens.json` is `#ffffff` — identical to canvas and surface. `screenshots/system/02-controls-high-contrast.png` shows all eight badges as bare colored text while every neighbouring control has a black border. The fix already exists for OS forced-colors (`components.css:329-334` sets `border-color: CanvasText`) but is not applied to the in-app high-contrast theme.
Fix: `border-color: currentColor` on `.ds-status` generally, or a `[data-theme="high-contrast"]` override.

## Medium

**3. The component-alias token layer is declared but bypassed, so "one owner per value" is not actually true for geometry.**
`base.tokens.json:990-1011` defines a component tier, and the catalog's Foundations copy sells it, but:
- `component.composer-radius` — unused; `.composer` uses `var(--ea-radius-xl)` directly (`styles.css:378`).
- `component.panel-radius` — unused; `.workspace` uses `var(--ea-radius-lg)` (`styles.css:545`).
- `component.composer-padding` — unused; `.composer` hardcodes spacing tokens (`styles.css:379`).
- `component.button-radius` is consumed only by `.ds-button-danger` (`components.css:151`), while `.primary`/`.secondary` use `--ea-radius-md` (`styles.css:746,752`). They agree at 8px today purely by coincidence; changing the component token would move one button.
- `control.min-target` (24px) is asserted by `check.mjs:49` but referenced by no CSS; `.context-chip button` hardcodes `24px` (`styles.css:1301-1306`).
- `motion.fast` / `motion.base` and `layer.base` are unreferenced, yet the Foundations entry lists `motion.*` as a consumed contract (`catalog.js`, Spacing/shape/motion entry).

Root cause is testable: `check.mjs:51-59` only checks *referenced → exists*, never *declared → referenced*. Add the inverse assertion and these six regress to failures instead of drift.

**4. Collapsing or expanding the navigation drops keyboard focus, and `aria-expanded` lives on a hidden control.**
`setNav` (`app.js:50-57`) only restores focus when `open && innerWidth <= 800`. Clicking `.expanded-toggle` to collapse hides the clicked button (`.nav-open .expanded-toggle { display: flex }` / otherwise `display:none`, `styles.css:131-133,228-233`), so focus falls to `<body>`; the same happens on desktop expand, since `.collapsed-toggle` is hidden by `.nav-open`. The Escape path already does this correctly (`app.js:529-534`), which shows the intent. Separately, `aria-expanded` is set only on `.collapsed-toggle` (`index.html:28`, `app.js:54`) — the control that is `display:none` whenever the value is `"true"`. The two visible controls (`.expanded-toggle`, `.mobile-nav`) expose no state and no `aria-controls="sidebar"`, even though the workspace tabs now do wire `aria-controls` properly.
Fix: in `setNav`, focus whichever toggle is now visible, and mirror `aria-expanded`/`aria-controls` onto all three.

**5. `update()` permanently removes the tab panel from the tab order.**
`index.html:119` gives `#workspace-body` `tabindex="0"` (correct for a tabpanel whose content may have no focusable elements). `app.js:309` sets it to `-1` on every state transition and never restores it, so after the first approve/verify/reject the panel can no longer be reached by Tab. The `setAttribute` is also unnecessary — the element is already focusable.

**6. The focus ring is defined twice with different geometry, and the offset token is half-dead.**
`components.css:315-318` uses `--ea-control-focus-width`/`--ea-control-focus-offset` (2px/3px). `styles.css:55-60` redefines it for `button, a, textarea` with literal `2px` and `outline-offset: 4px`, winning on specificity `(0,1,1)` vs `(0,1,0)`. Result: buttons/links/textareas get 4px, inputs/selects/summaries get 3px, and `control.focus-offset` only governs the latter. `check.mjs:53` bans hex colors but nothing bans geometry literals, so this is invisible to the suite.

**7. The mobile breakpoint is hardcoded in twelve places while a token for it exists and is unused.**
`layout.mobile-breakpoint` (800px) and `layout.compact-breakpoint` (390px) are generated and exported in `token-names.d.ts`, but consumed nowhere. `styles.css:969,1162,1369` and `catalog.css:307` hardcode `800px`; `app.js` hardcodes `innerWidth <= 800` at lines 55, 56, 270, 282, 352, 354, 532, 537, 538, 540. They agree today (both inclusive at exactly 800). Media queries can't read `var()`, so either drop the tokens or have the JS use `matchMedia("(max-width: 800px)")` from a single exported constant so CSS and JS can't drift apart silently.

**8. No `color-scheme`, and OS dark preference is never mapped.**
Neither stylesheet nor either HTML file declares `color-scheme` anywhere, so in the dark theme the UA chrome (scrollbars on `.conversation-scroll`, `.workspace-body`, `.history`, `.ds-tokens`, select popups, caret) stays light. `build.mjs:9` scopes light to `:root, :host, [data-theme="light"]` and dark to `[data-theme="dark"]` only, with no `@media (prefers-color-scheme: dark)` block, so a user on a dark OS gets the light theme unless they pass `?theme=`. Both are build-level fixes: emit a `color-scheme` declaration per theme and an optional preference-mapped block.

**9. Icon stroke width is now a CSS dependency of the inline icons.**
`icons.js:53` emits `class="ea-icon"` and no `stroke-width`; the value comes from `components.css:1-3`. Any consumer rendering `icon()` output without `components.css` loaded — including a React port that imports the icon module alone — gets stroke-width 1 instead of 1.65. The exported standalone assets take the opposite approach and inline the token value (`export-icons.mjs:7`), which is correct. `check.mjs:61-66` asserts `viewBox` and `currentColor` on the exported files but never asserts stroke width on either path, so the two paths can diverge from `icon.stroke` without failing.

## Low

**10. The message column and the composer are misaligned by 48px once a conversation starts.** `.messages` hardcodes `max-width: 720px` (`styles.css:307-311`) while `.composer-wrap` uses `--ea-layout-conversation-max` = 768px (`styles.css:365-369`); both are centered with equal 24px padding, so the composer overhangs the text block by 24px per side. The empty state was already fixed to use the token (`styles.css:1131`), which makes the non-empty case look like an oversight.

**11. Dead and orphaned CSS left over from adopting `statusMarkup`.** `.status` / `.status.verified` (`styles.css:616-627`), `.trace` / `.trace svg` (473-484) and `.text-action` (520-531) have no matching markup anywhere in v4 — the workspace now renders `.ds-status` via `components.js:59`. Conversely `.readback` (`app.js:459`) has no CSS, so the read-back dialog's `<h3>` falls back to UA sizing outside the type scale.

**12. Two tone pairs share one palette role.** `attention`+`unknown` and `progress`+`blocked` are visually identical (`components.css:24-37`), differing only by icon and text. That is defensible, but given this product's core distinction between "needs review" and "outcome unknown", it deserves an explicit decision in the tokens rather than an emergent one — especially in high-contrast, where surfaces collapse to white and color is the only remaining signal (see finding 2).

**13. Smaller items.**
- `catalog.js:417` calls `filterSources()` at load, which calls `note()` (line 414), so the `role="status"` region gets "3 sample sources found." immediately after page load. Skip the first announcement.
- Roving-tabindex tab logic is implemented twice with different mechanics — `app.js:545-559` (clicks the tab) and `catalog.js:491-512` (`selectTab` + `aria-controls`) — while `design-system/components.js` owns only the composer and status badge. Tabs are the obvious next thing to move into the shared module.
- `hydrate()` copies every `aria-label` onto `title` (`app.js:36-42`), including buttons that already have visible text (the Send button gets `title="Send message"`). The catalog doesn't do this, so hover behavior differs between the two pages.
- `.ds-menu > div` is in-flow despite `position: relative` on the parent (`components.css:231-249`), so the disclosure pushes siblings rather than overlaying. If intentional, say so in the entry's contract line.
- `app.js:4-5` imports fixtures and the action model from `../agentic-workspace-v3/`, so the candidate isn't self-contained and `verify-system.mjs:124` depends on the server rooting at `research/mockups`.

**14. Observation I could not resolve statically.** In both `07-chat-1440x1000-dark.png` and `07-chat-1920x1080-light.png`, the workspace "Document" tab renders with what looks like the focus ring (2px, 4px offset, `--ea-color-focus`), immediately after `[data-start=handoff]` — even though `start()` ends with `$("#prompt").focus()` (`app.js:276`) and `.composer textarea` suppresses its own outline in favor of `:focus-within`. It cannot be a border (`button { border: 0 }` zeroes all but the bottom edge). Either focus isn't landing in the composer after a starter click, or I'm misreading the render. Worth one browser check; if focus really is parked on the tab, keyboard users don't land in the composer when a conversation starts.

## Coverage challenges

The existing suite is genuinely strong (97 tokens × 3 themes, drift detection, 46 icon assets, the 320–1920 + short-landscape matrix, exact-separate-approval and unknown/stale boundaries in `verify.mjs`). The gaps that let the findings above through:

- **Token tests are one-directional.** `check.mjs:51-59` proves every `var(--ea-*)` resolves; nothing proves every declared token is consumed. That is the entire cause of finding 3. Also the scan covers only three CSS files — `catalog.js` builds `var(--ea-font-size-${size})`, `var(--ea-space-${n})`, `var(--ea-radius-${r})` and `var(--ea-color-${n})` in inline `style=` attributes that no test validates, so a typo there fails silently.
- **Contrast is checked on token pairs, never on computed states.** No assertion covers hover, disabled, or `.ds-alert p` (text-muted over a tone surface). Finding 1 is a hover-state contrast failure that the current matrix cannot see.
- **No geometry-literal guard.** `check.mjs:53` bans hex colors only; findings 6, 7, 10 and the hardcoded `24px` in finding 3 are all literals a sibling assertion would catch.
- **Forced colors is exercised on `components.html` only** (`verify-system.mjs:142-145`). `index.html` is never rendered in that mode, and `styles.css` contains no `forced-colors` block at all — the chat's own chrome has no fallback equivalent to `components.css:329-347`.
- **Icon assertions don't cover stroke width** in either the inline or exported path (finding 9), and nothing asserts that `icon()` output and the exported asset agree.
- **Focus is asserted at dialog boundaries but not at navigation boundaries.** `verify.mjs` clicks `.collapsed-toggle`/`.expanded-toggle` five times (lines 68, 78, 123, 130, 230-231) and never asserts `document.activeElement` afterwards, which is why finding 4 survives a passing suite.
- **Contract divergence between the two pages is untested as such.** `verify.mjs:39` enforces that the chat dialog focuses `#dialog-title`; `verify-system.mjs:66` enforces that the catalog dialog focuses `#dialog-back` — while the catalog entry's own copy states "Initial focus stays on Back" as the system contract. Both pass; the system still documents one rule and ships two.
- Minor: the chat viewport loop (`verify-system.mjs:114-134`) hits 320/390/844/1440/1920, and `verify.mjs:189` adds 1024/768 — so the split-view band is covered, but no chat run combines a desktop width with a state transition (the loop only loads the initial review scene).
