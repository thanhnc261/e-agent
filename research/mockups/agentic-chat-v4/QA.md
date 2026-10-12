# Verification — conversation workspace

Date: 2026-10-10. Synthetic local mockup evidence only.

`node research/mockups/agentic-chat-v4/verify.mjs` passed after visual corrections. It verifies:

- Left navigation collapses/expands and returns space to chat; draft text survives.
- Right workspace closes/reopens; conversation draft and per-thread state survive navigation.
- Six example scenarios, read-only answer and missing-access behavior.
- Exact confirmation, initial focus and Enter safety; two actions require separate approvals.
- Owner-only clarification carries into the message destination and both confirmations.
- Two independent sample read-back records; input source excerpts stay separate.
- Stale proposals cannot be approved; unknown effects cannot be resent.
- Escaped free-text input and explicit non-executing follow-up behavior.
- 1440, 1024, 768, 390 and 320px layouts: page bounds, composer/footer bounds and welcome/composer non-overlap.
- Mobile navigation makes the main view inert; Escape closes it without losing draft text.
- No browser page errors or external requests in the exercised flows.

Source chooser tests initially had ambiguous locators matching the welcome behind the dialog; corrected to scope those choices to the dialog. Visual inspection then found a zero-height flex item causing welcome/composer overlap; corrected its flex basis and added an explicit overlap assertion. The final suite passed and regenerated all screenshots.

Personally inspected the final desktop start screen, split workspace, expanded navigation, mobile chat, mobile document and 320px start screen. Screenshots are under `screenshots/`.

This does not establish user acceptance, task efficiency, screen-reader conformance, complete keyboard coverage, production authorization or live integration support. Embedded host placement, persistent history, separately assigned reviewers and real agent streaming remain outside this revision. Production implementation stays paused.

## Review corrections

Claude's read-only critique is recorded in `CLAUDE-REVIEW.md`; changes are in `REVIEW-RESOLUTION.md`. Additional checks cover chat remaining wider than the right workspace, restoring a thread's open Sources tab, clearing a cancelled chooser prompt, narrowing the second action audience without widening prior document access, and preventing completed/unknown examples from silently returning to unsent review. The final suite passed after these changes.

## Warm canvas / composer checks

The browser suite also passed source excerpt inspection, add/remove reference chips, retaining a reference across navigation collapse, Shift+Enter without submission, growing multiline input, suggestion-prefill without auto-send, disabled empty submission and a prepared follow-up carrying its source reference. The proposal remains unexecuted after chat messages. Desktop conversation/composer and 320px chat screenshots were visually inspected; `16-composer-with-context.png` and `17-follow-up.png` show the new interactions.

## Design system and responsive checks

All three commands passed after the shared token/component changes:

- `node research/mockups/agentic-chat-v4/design-system/check.mjs`: 97 public tokens × three themes; generated drift, missing/circular aliases, text/status/action contrast, focus/control boundaries, 46 SVG exports and CSS token references. No literal hex colors remain in the three component/composition stylesheets.
- `node research/mockups/agentic-chat-v4/verify-system.mjs`: catalog at 320×720, 390×844, 600×960, 768×1024, 820×1180, 1024×768, 1440×900, 1920×1080 and 844×390. Form validation/search, shared composer, pagination, keyboard tabs, dialog focus/Escape/return, notification and theme selection passed.
- `node research/mockups/agentic-chat-v4/verify.mjs`: existing chat/approval/source/context behavior still passes after migration to shared tokens, icons, composer and status views.

The system suite also checks the chat at 1440×1000 and 390×844 in dark, 1440×1000 and 320×720 in high contrast, and 844×390, 390×500 and 1920×1080 in light. Workspace actions stay within the viewport. Reduced motion and forced-colors smoke checks passed. A separate touch-emulated context confirms the coarse-pointer rules, 16px composer text and 44px context control. No page errors or external requests were observed in the exercised flows.

Contrast assertions initially found muted text too light on selected surfaces. The light muted-text token was darkened from `#706759` to `#665e52`; all asserted pairs then passed. Personally inspected desktop foundations, dark/high-contrast controls, 320px composer/forms/dialog, mobile dark workspace and short-landscape chat/workspace screenshots. Screenshots are in `screenshots/system/`.

This evidence is Chromium viewport simulation. It does not establish real-device, virtual-keyboard, screen-reader, browser zoom or full WCAG conformance. The candidate compiler supports a documented token-format subset, and production adoption remains unimplemented.

The workspace now uses the same tab semantics as the catalog: selected tab, one tab stop, labelled panel, Arrow/Home/End navigation. Regression tests exercise this at each themed chat viewport. Both browser suites passed after this correction.

## Design-system review corrections

[Claude’s review](design-system/CLAUDE-REVIEW.md) identified hover, high-contrast boundaries, navigation focus and token-consumption gaps. The [resolution](design-system/REVIEW-RESOLUTION.md) records each correction or explicit design decision. Extended checks cover destructive hover across themes, native color schemes, high-contrast badge borders, inline/exported icon stroke parity, component-token consumption, CSS/JS breakpoint consistency, desktop toggle focus, initial composer focus, tabpanel reachability after reject/refresh and full-chat forced colors.

All three checks passed again after the review corrections, as did formatting for the authored code. Visually inspected the corrected high-contrast controls, aligned dark chat/composer and full-chat forced-colors render. Non-selected tabs now suppress their otherwise forced border so the active underline stays distinct.

## Default foundation and connected graph identity review

The [foundation review](design-system/FOUNDATION-REVIEW.md) records the new identity and embedding audit. Current sources contain **99 public tokens** after separating destructive-action colors from brand accents. Identity assets are original vector geometry with no font dependency. All existing catalog/chat checks pass after the new mark, shadow-host selectors and 44px Send correction.

The new `verify-foundation.mjs` runs against Chromium and, with `EAGENT_BROWSER=webkit`, WebKit 26.0 (Playwright build 2215). It checks conflicting host styles including the collapsed launcher, independent shadow themes, 320/420/640/1040px containers inside a 1440px browser, retained drafts, close/reopen and modal focus, shared shadow-root tab keys, phone/tablet/landscape layouts, all public type-size tokens enlarged to 200%, long Vietnamese copy/unbroken source identifiers, and forced-colors/reduced-motion emulation. Theme transitions no longer animate background and foreground out of sync. Engine-specific screenshots are under `screenshots/foundation/`.

This evidence covers the new specimen and current mockup, not the real production custom element or physical Safari/iOS devices. See the foundation contract for remaining adoption and accessibility work.

The independent foundation review led to additional checks for artifact-heading focus at 640/1040px, visible confirmation feedback in the compact work view, host-hidden behavior against a conflicting rule, inherited paragraph styling, full-screen focus containment, all type sizes at 200%, and Send remaining unobscured in short landscape. Confirmation close/cancel restores focus synchronously, including in WebKit, avoiding a delayed callback that can steal the next Tab. The [resolution](design-system/CLAUDE-FOUNDATION-RESOLUTION.md) records each finding.

### Graph identity revision — 2026-10-11

Replaced the letterform symbol with six connected entities and one cross-connection. Inline and exported SVGs share `brand.js`. Inspected 24/32/40/48/64px samples, the light/dark/high-contrast variants, launcher and short landscape. The Chromium and WebKit foundation harnesses, catalog/responsive suite, full chat regression suite, token checks and generated-asset drift checks all passed with this geometry. Full-size identity evidence is `screenshots/foundation/chromium/identity-full.png`.

### Color revision — 2026-10-11

The default moved from navy/cream to charcoal/warm white, with matching dark/high-contrast accents and transparent header marks. The palette comparison uses the shared identity, icons and composer. The existing contrast gate also checks all three comparison palettes. The final six-node logo follows Claude's critique of the intermediate four-node mark; see [the review resolution](design-system/CLAUDE-FOUNDATION-RESOLUTION.md).

After the color revision: token/contrast and generated-asset checks passed; the catalog/full-chat suites passed; the foundation harness passed in Chromium and WebKit. The palette comparison was inspected at 320/768/1440px with no document overflow or page errors, and its composer correctly reports that preview messages are not sent. The host-isolation launcher assertion now derives its expected color from the generated accent token.

### Identity restart

The new concept board replaces literal node diagrams with three abstract connected forms. Source/export parity and contrast checks cover its concept assets and all three color treatments. Its responsive and interaction verification is separate from earlier full-chat evidence. Earlier Claude reports concern superseded marks; no Claude endorsement is claimed for these concepts.

Chromium and WebKit passed all nine shape/color combinations at 320, 390, 768 and 1440px, native keyboard shape selection, retained composer draft and preview-only submission, with no document overflow or page errors. Screenshots are `screenshots/identity-directions-{engine}-{width}.png`. The WebKit phone view and desktop board were also visually inspected.

### Connected-node / Warm Lagoon revision

Following the owner's clarification, the shared identity now has one central node connected to four evenly spaced surrounding nodes. The palette shifts Lagoon toward warmer green-teal and uses an ivory canvas with warm paper surfaces; dark/high-contrast accents are updated too. Inline/exported assets use the same geometry, and the three abstract-loop studies are now explicitly archived. The current palette comparison inherits the default tokens directly and contrasts them with original Lagoon.

The connected-node / Warm Lagoon revision passed token/contrast validation, generated asset checks, the full catalog and chat regression suites, and both Chromium/WebKit foundation harnesses. Warm/original Lagoon comparisons were checked at 320/768/1440px without overflow. Identity and comparison screenshots were visually inspected; these are browser specimens, not production/device qualification.

[Claude’s Warm Lagoon review](design-system/CLAUDE-WARM-LAGOON-REVIEW.md) led to longer exposed connectors and explicit comparison swatches. The [resolution](design-system/CLAUDE-WARM-LAGOON-RESOLUTION.md) records geometry changes and computed-color assertions. The warm accent is now `#326d5c`; the browser verifies that both symbol and Send button differ correctly from original Lagoon `#24696a`.

### Lighter colors and perspective pose

The default pose is 22.5° clockwise / 35° backward. Three clockwise choices and three backward tilts are available in the identity preview. Soft Lagoon, Sage Lagoon and Sea Glass use the new `color.brand` role; primary actions remain separately contrast-checked. Token/asset checks now cover 100 public tokens, 3 main themes, all palette comparisons and the angle SVG exports. The full catalog/chat and Chromium/WebKit foundation harnesses passed after this revision.

Additional Chromium and WebKit checks passed for all nine pose combinations at 320/768/1440px: no document overflow, SVG geometry stays inside its viewBox, selected captions match the controls, and downloaded SVG geometry matches the selected preview. The three palette layouts also passed at those widths without page errors. Desktop palette and mobile identity screenshots were visually inspected. This pose revision has not received a new Claude review; earlier reviews concern earlier geometry.

### Sculpted depth and six palettes — 2026-10-11

`verify-identity.mjs` passed in Chromium and WebKit for 27 rotation/tilt/depth combinations at 320/768/1440px. Geometry stays inside the viewBox and selected SVG downloads match the preview. All six palette selections update the downloaded base color. Palette pages have no document overflow; no page errors were observed. Token contrast checks passed for all six studies and the three foundation themes. The Chromium foundation harness also passed. Desktop logo and six-palette screenshots were visually inspected. This is mockup/browser evidence, not production or physical-device qualification.

WebKit native select sizing initially reduced the pose controls below the intended touch target. Explicit custom select appearance corrected this; the browser harness now requires both controls to remain at least 44px tall in both engines. Palette deep-link initialization and keyboard color selection were also checked.

A read-only Claude review was requested for this revision. The CLI returned no review output during the available wait and was stopped; no Claude approval or findings are claimed for the sculpted revision.

### Soft cast shadow — 2026-10-11

Added None/Soft/Raised shadow choices to the shared vector logo and selected SVG download; Soft is the default. Token checks and generated asset/bundle drift checks passed. The Chromium/WebKit identity harness passed 81 rotation/tilt/depth/shadow combinations at 320/768/1440px with matching inline/exported geometry, working color choices, 44px select targets, no document overflow and no page errors. The default shadow screenshot was visually inspected. Shadow silhouettes and their stroke spread stay within the 32-unit viewBox. These remain mockup checks.

### Reflective surface and colored nodes — 2026-10-11

Added Glossy reflection/Satin surfaces and a Color per node option. `verify-materials.mjs` passed in Chromium and WebKit across 320/768/1440px, both finishes, both color modes and all six brand palettes. Computed fills show five distinct node colors in multicolor mode; the center and connections retain the selected brand. Selected SVG downloads match the inline artwork. Both new select controls meet the 44px height target and no page errors/overflow were observed. The existing 81-combination pose/shadow harness passed in both engines, as did token and generated-asset/bundle checks. The multicolor deep link was checked. Desktop glossy/colored logo and mobile WebKit screenshots were visually inspected. This remains a mockup, not a production qualification.
