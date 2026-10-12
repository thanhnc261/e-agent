# e-agent candidate design system

Date: 2026-10-10. An interactive design specification for study 04, with shared assets already used by the chat mockup. Production implementation remains paused.

Read the [default foundation contract](FOUNDATION.md) and [foundation review](FOUNDATION-REVIEW.md). Inspect the [identity](../identity.html) and [embedded preview](../overlay.html).

Open [the catalog](../components.html) through the local server described in [the study README](../README.md). It covers foundations, identity, controls, forms, conversation, work/evidence, feedback, and navigation/overlays. All demonstrations are local and fictional.

## Ownership and files

| Source                                                        | Responsibility                                                                  |
| ------------------------------------------------------------- | ------------------------------------------------------------------------------- |
| `tokens/base.tokens.json`                                     | Foundation palette and public semantic/component tokens                         |
| `tokens/dark.tokens.json`, `tokens/high-contrast.tokens.json` | Theme overrides                                                                 |
| `build.mjs`                                                   | Alias resolution and generated CSS, resolved JSON, `TokenName` union            |
| `icons.js`                                                    | One 24-unit, rounded monoline icon family and connected graph mark              |
| `export-icons.mjs`                                            | 46 individual SVGs, sprite, connected graph identity variants, `IconName` union |
| `components.js`, `components.css`                             | Shared composer/status views and component styling                              |
| `catalog.js`, `catalog.css`                                   | Interactive examples and catalog-only composition                               |
| `../styles.css`, `../app.js`                                  | Full chat/workspace composition and local scenario transitions                  |
| `generated/`                                                  | Build output; change authored sources instead                                   |

The catalog and chat import the same tokens, icons, composer markup, status renderer and tab keyboard behavior. `brand.js` owns the current identity. The embedded specimen bundles the same complete styling with `build-overlay.mjs`; `overlay.css` owns only its placement geometry. Generated metrics keep JavaScript breakpoints and inline/exported icon stroke defaults tied to the token source. Scenario content remains separate in `../chat-content.js` and the preserved study 03 fixtures/action records. Catalog behavior is demonstrative; it is not a second authorization implementation.

## Tokens and themes

There are 100 public tokens in warm light, warm dark, and high contrast. The current working color direction is Soft Lagoon on lighter ivory; the header mark has no filled badge. Foundation palette values resolve through semantic roles such as `color.canvas` and `color.accent`; component aliases refer to reusable decisions rather than new colors. CSS exposes `--ea-` names, for example `color.canvas` becomes `--ea-color-canvas`. Components consume semantic roles; raw palette values stay in source JSON.

Generated scopes also set the native control `color-scheme`. Warm light is the intentional default for this study; production OS/user/host preference precedence remains separate.

Use `data-theme="light"`, `data-theme="dark"`, or `data-theme="high-contrast"` on the document root. The catalog selector changes the full catalog; its Open mockup link preserves the selected theme. The mockup also accepts `?theme=dark` or `?theme=high-contrast`.

Typography uses a system-only font stack, a bounded type scale, and shared weights/line heights. Spacing, radii, control sizes, icon sizes, focus rings, shadows, motion, layers and major shell widths have named tokens. Component CSS contains no literal hex colors. Composition-specific constraints and media-query thresholds remain explicit CSS: custom properties cannot directly supply ordinary media-query conditions. Checks verify mobile/compact conditions against source tokens; application code consumes the generated mobile media query.

The token files follow a **supported subset** of the [Design Tokens format](https://www.designtokens.org/tr/2025.10/format/), not a complete conforming parser. Every token has an explicit type. The compiler supports whole-value aliases, normalized sRGB color objects, dimensions in px/rem, durations in ms/s, font-family arrays, font weights, numbers, and single shadows. It rejects missing references, cycles, alias type mismatches, invalid color channels/alpha, wrong dimension/duration units, unsupported types and generated-output drift. It does not implement inherited types, arbitrary color spaces, composite aliases or a general schema validator.

## Components and behavior

| Group        | Included patterns                                                                       | Interaction/state contract                                                                                                    |
| ------------ | --------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| Identity     | connected graph mark, vector wordmark, 46 icons                                         | Light/dark/mono exports; decorative SVGs hidden; icon buttons require names                                                   |
| Actions      | Primary, secondary, quiet, destructive, icon button, tooltip                            | Default, focus, disabled, pending; tooltip dismisses with Escape                                                              |
| State        | Draft, working, review, verified, unknown, failed, access needed, cancelled             | Text and distinct icon accompany color; unknown remains distinct from failed                                                  |
| Forms        | Text, select, multiline, checkbox, radio, switch, source search                         | Persistent labels, hint/error association, invalid state, no results; switches only for reversible preferences                |
| Conversation | User/agent message, citation, artifact card, suggestions, composer, context chips       | Suggestions prefill; blank send disabled; Enter sends, Shift+Enter inserts newline; removable references do not grant access  |
| Work         | Scope/terms, source excerpt, read-back record, paginated table                          | Source provenance stays separate from independent outcome evidence; table scroll stays inside its region                      |
| Feedback     | Pending/skeleton, measured progress, empty, error, access needed, unknown, notification | No invented percentage; visible persistent feedback; no blind resend after an unknown write                                   |
| Navigation   | Rail/drawer, workspace, tabs, disclosure, confirmation dialog                           | Arrow/Home/End tab navigation; native disclosure; modal focus containment, safe initial focus, Escape cancel and focus return |

`composerMarkup(prefix)` supplies shared markup with a validated ID prefix; behavior belongs to its owning page. `statusMarkup(tone, label)` validates the tone and escapes the label. `icon(name)` rejects unknown names. These are native prototype views; they are not production component APIs.

Status selection and button visibility never authorize a business action. Production approval must still bind the exact normalized action, scope and versions on the server. The local examples preserve separate document/message confirmations and the stale/unknown boundaries.

## Responsive specification

| Context                                 | Behavior                                                                                                   |
| --------------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| Narrow phones, including 320px          | Single main view; compact wrapping metadata and stacked content; dialogs fit the viewport                  |
| Phone/tablet at 800px or below          | Navigation becomes a drawer; chat and artifact switch views; the same conversation state remains           |
| Tablet above 800px / small laptop       | Collapsible rail and proportional chat/workspace; workspace can close to recover conversation width        |
| Desktop and wide screens                | Bounded reading widths; chat remains wider than the right workspace; no extra permanent columns            |
| Short viewport at 540px height or below | Smaller chrome and composer padding; independently scrolling content; action footer stays reachable        |
| Coarse pointer                          | Core compact chat controls enlarge to 44px; chip removal remains at least 32px; form/composer text is 16px |
| Reduced motion / forced colors          | Spinner motion stops; system-color boundaries supplement semantic status/icon text                         |

Standard controls are 44px, compact controls 32px, and the minimum target token is 24px. These design sizes are informed by [WCAG target-size guidance](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html); they do not establish whole-interface conformance. Actual hardware, virtual keyboards, assistive technologies and browser zoom need further testing during implementation. The shorter 390×500 viewport is a layout simulation, not real keyboard evidence.

## Production adoption in the existing FE layers

Follow [the frontend development guide](../../../../docs/frontend-development-guide.md) and existing UI packages. Do not add a parallel design-system package or copy the prototype string renderer into React.

1. **`ui/packages/tokens`:** reconcile these values with existing token names and theme/appearance/density axes. Its current compiler consumes color strings, while this candidate uses sRGB objects. Convert the candidate inputs deliberately or extend that compiler with compatibility tests; do not replace it silently. Keep one public token contract.
2. **`ui/packages/components/primitives`:** extend existing ActionButton, Icon, StatusBadge, TextAreaField, Disclosure and Surface primitives. Use typed props, token-based variants and the established [React Aria styling/state approach](https://react-aria.adobe.com/styling). Add a new primitive only for a concrete missing control.
3. **Feature components:** assemble conversation, composer, artifact, evidence and review views from primitives. Receive data and callbacks through props; keep provider identity/icons/forms supplied by server manifests.
4. **`ui-core` / `ui-react`:** own task state, drafts, selectors and hooks. Layout changes must not remount or reset conversations. Do not port simulated scenario transitions as business logic.
5. **Layouts:** own placement, responsive geometry, rail/drawer and workspace switching. Verify embedded host/Shadow DOM behavior separately; these standalone screenshots do not cover it.
6. **Existing gallery and conformance suites:** migrate this catalog's states into the runnable production gallery, then verify keyboard behavior, themes, responsive geometry and approval/failure boundaries through public APIs.

## Build and verify

From the repository root, with the local server running for browser checks:

```sh
node research/mockups/agentic-chat-v4/design-system/build.mjs
node research/mockups/agentic-chat-v4/design-system/export-icons.mjs
node research/mockups/agentic-chat-v4/design-system/check.mjs
node research/mockups/agentic-chat-v4/design-system/export-icons.mjs --check
node research/mockups/agentic-chat-v4/design-system/build-overlay.mjs
node research/mockups/agentic-chat-v4/verify-foundation.mjs
EAGENT_BROWSER=webkit node research/mockups/agentic-chat-v4/verify-foundation.mjs
node research/mockups/agentic-chat-v4/verify-system.mjs
node research/mockups/agentic-chat-v4/verify.mjs
```

The browser scripts use the repository's installed Playwright dependency. The checks cover generated drift, alias errors, text/status/action contrast, focus/control boundaries, icon exports, unresolved CSS tokens, responsive bounds and exercised interactions. Inspect the resulting screenshots as well as assertions. See [QA](../QA.md) for tested dimensions, corrections and limitations.

## Review decisions

[Claude review](CLAUDE-REVIEW.md) and [resolution](REVIEW-RESOLUTION.md) record hover, focus, token-consumption and high-contrast corrections. Short confirmations initially focus Back; long action reviews initially focus the heading. Both avoid focusing the consequential action. Status pairs may share a color family, but always retain distinct text and icons, with explicit borders in high contrast.

## Color comparison studies

`../palettes.html` uses `palettes.js`/`palettes.css` with the shared brand, composer and icons. `tokens/palette-studies.json` compares Soft Lagoon (inheriting the current default), Sage Lagoon, Sea Glass, Rose Clay, Dusty Iris and Linen Blue; these are not additional production themes. The normal base/dark/high-contrast token files remain authoritative for the working default. The contrast gate validates comparison values against the same semantic roles.

## Identity pose and brand color

`brand.js` owns node geometry, clockwise rotation, backward perspective and solid extruded sidewalls with a fine highlight. `defaultLogoPose` is 22.5° clockwise / 35° back / depth 3. Depth choices 1/3/5 are named Subtle/Sculpted/Deep. `logoGlyphFor()` generates bounded SVG geometry and rejects unsupported pose input; `logo()` uses the default unless a pose is supplied. `identity.js` owns local pose and six-color preview controls and creates/revokes SVG download URLs matching the selected pose and color. Palette links initialize the matching local selection; they do not change the application default. Theme lockup downloads remain explicitly labelled as the default pose. The exporter includes separate 15°/22.5°/30° symbols at the default backward tilt.

`color.brand` is a public semantic color role separate from `color.accent`. Header/hero symbols and exported lockups use the lighter brand role; action buttons retain the accent/foreground pair. The contrast gate checks brand visibility (3:1) and action text (4.5:1) independently.

Run `node research/mockups/agentic-chat-v4/verify-identity.mjs` for the Chromium/WebKit pose, palette, responsive and selected-export checks.

## Logo cast shadow

The shared logo accepts `shadow: "none" | "soft" | "raised"`, with `soft` as the default. Layered translucent vector silhouettes form a small downward cast shadow; there are no filter IDs or external style dependencies. The identity selector updates all selected-pose specimens and the downloaded SVG. The shadow remains separate from the solid sidewall shading and highlight.

## Reflective surface and per-node color

The logo accepts `finish: "satin" | "glossy"` (default glossy) and `colorMode: "brand" | "multicolor"` (default brand). The multicolor mode requires four valid hex `nodeColors`; these color only the outer faces and their sidewalls. The central node and connections always use `currentColor`, bound to the selected `color.brand`. Identity preview derives the outer colors from the existing palette-study source and excludes the selected brand. No separate palette values are duplicated in the logo generator.

Layered white specular patches suggest a polished surface independently of the cast shadow. All effects remain self-contained SVG artwork. `identity.html?nodes=multicolor` opens the new color mode. `verify-materials.mjs` checks both finishes and modes across six brands, including computed center/edge color and matching downloaded SVGs.
