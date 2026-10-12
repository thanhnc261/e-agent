# Default overlay design foundation

Date: 2026-10-10. Intended visual foundation for the next e-agent overlay implementation. The sources and previews here are a candidate specification; production packages have not adopted this revision.

## Default visual contract

- Soft ivory canvas (`color.canvas`), warm paper work surfaces (`color.surface`), Soft Lagoon primary actions (`color.accent`) and warm neutral text. The default header mark sits directly on the canvas without a filled badge. Use separators to express grouping; do not turn every message into a card.
- Conversation is the primary entry surface. An artifact opens for structured review. Navigation collapses; narrow surfaces switch between conversation and work instead of compressing multiple columns.
- The connected-node identity uses one central node linked to four surrounding nodes, paired with a custom vector wordmark. It is a stable product identifier, never a progress indicator, provider logo or verification badge. Geometry lives in `brand.js` and all exported assets are generated from it.
- Body and field text use the system font stack. The wordmark is vector geometry and has no font dependency. Use the existing bounded type/spacing scales; 44px standard controls and 32px compact controls. Send is a standard 44px control. Bare brand symbol minimum 24px; app tile minimum 32px; launcher minimum 48px target.
- Three explicit themes: warm light by default, warm dark and high contrast. Native control color schemes match. Theme changes are immediate; background-only theme animations are prohibited because they temporarily mismatch text contrast.
- Text, a distinct icon and available actions express status together. Verified, pending, missing access, failed and unknown are separate states. Decorative borders use subtle roles; controls that depend on boundaries use strong roles. Destructive actions have their own foreground/background roles, independent of brand-accent customization.
- Motion is optional and limited to tooltip opacity and switch-thumb movement, with reduced-motion support. No decorative agent animation is required by the default foundation.

## Source ownership

| Concern                                        | Candidate source                                                   | Production owner during adoption                                |
| ---------------------------------------------- | ------------------------------------------------------------------ | --------------------------------------------------------------- |
| Semantic values, themes, aliases               | `tokens/*.tokens.json`                                             | Existing `ui/packages/tokens`                                   |
| Mark and wordmark                              | `brand.js`                                                         | Existing components/assets exports; no new package required     |
| Icon family                                    | `icons.js`                                                         | Existing Icon primitive                                         |
| Control styles and behavior                    | `components.css`, `components.js`, shared rules in `../styles.css` | Existing primitives, then feature views                         |
| Task/draft authority                           | Local fictional scenario code, demonstration only                  | Existing `ui-core` controller and `ui-react` hooks              |
| Placement and responsive behavior              | Standalone composition plus `overlay.css` specimen                 | Existing layout/presentation owner using available surface size |
| Shadow boundary, host preferences and lifetime | `overlay-preview.js`, demonstration only                           | Existing `overlay-element` host                                 |

The candidate still has shared control rules in the standalone composition stylesheet. `build-overlay.mjs` bundles the same complete CSS for the embedded specimen so the evidence cannot silently use a second palette. During production adoption, extract those rules into the existing primitive/feature styles and verify both entry points use them. Do not copy the entire standalone stylesheet into a host document, copy the prototype renderer into React, or ship the preview custom element.

## Embedding contract

The embedded preview has a real Shadow DOM boundary. External selectors such as `button { … !important }` cannot restyle its descendants; inherited typography is explicitly normalized inside the boundary. Public `--ea-*` custom properties remain intentional customization points. They are not a security boundary, and arbitrary host token overrides are not automatically contrast-validated. The host still owns placement of the custom element.

Theme selectors support both an internal `[data-theme]` root and `:host([data-theme])`. Two instances can use different themes on the same page without mutating the document. Every theme and deliberate token override must preserve contrast, forced colors and control states. [Shadow DOM reference](https://developer.mozilla.org/en-US/docs/Web/API/Web_components/Using_shadow_DOM).

Use available **surface width** for overlay composition. A 420px docked panel is compact even on a 1440px monitor. The specimen uses a named CSS container and splits only above 800px; the full standalone study still uses document-width queries. Production already has a layout-owned ResizeObserver/compact context: preserve that ownership rather than porting the standalone window query. CSS-only geometry should use container queries; behavior receives semantic placement from the layout owner. [Container queries](https://developer.mozilla.org/en-US/docs/Web/CSS/CSS_containment/Container_queries).

The docked desktop conversation is nonmodal; host controls remain available. When the preview covers the full phone/tablet viewport, it becomes a labelled modal surface, makes the fixture host regions inert and keeps keyboard focus inside. Closing restores host availability. Exact confirmations use native modal dialogs in both placements. The launcher lives inside the same shadow root. Closing the overlay returns focus to it. Shared keyboard helpers resolve the active element from their own document/shadow root. A compact view switch preserves drafts. Modal content remains inside the shadow styling/focus boundary, including the browser top layer. Long reviews focus their heading; short confirmations focus Back. Neither initially focuses the consequential action.

## Customization policy

Change the smallest public semantic role that expresses the need. Brand accents, surfaces, status roles and destructive actions are separate concerns. A feature must not add its own light/dark hex values. New states need a text/icon/action contract, not just a color. New components should compose existing primitives and typed callbacks; domain/provider names, icons and connection forms remain manifest-supplied data.

Author source JSON or geometry, regenerate, inspect the catalog and embedded preview, and run the relevant checks. Generated CSS, token-name/icon-name unions, metrics and SVGs are build outputs. The current compiler implements the subset documented in [README](README.md); production's existing color-string compiler requires deliberate conversion/compatibility work before importing these color objects.

## Evidence and remaining work

See [the foundation review](FOUNDATION-REVIEW.md) and [QA](../QA.md). Browser checks cover actual component behavior and CSS viewport/container simulations. They do not establish real-device, real virtual-keyboard, assistive-technology, user-task or live integration qualification.

Before production adoption is considered complete: map tokens to existing appearance/density/theme precedence; migrate shared primitives; integrate layouts without remounting the controller; run the real custom-element gallery/conformance suite with both default and host overrides; test live region/focus behavior with assistive technology; verify real-device keyboards and host portal placement. Existing server approval, uncertainty and independent verification boundaries stay authoritative.

## Earlier color revision — 2026-10-11 (superseded)

The user rejected the navy/cream scheme. Charcoal and warm white are the current working default, chosen while a palette preference remains open. The [color comparison](../palettes.html) shows forest/stone and espresso/linen alternatives using shared components. Candidate study values live in `tokens/palette-studies.json`; the default remains authored in the normal theme token files. These alternatives are comparison studies, not additional production themes. Base, dark and high-contrast tokens and generated identity exports were updated together.

## Earlier rejection — superseded by the connected-node brief below

The owner rejected the six-node graph and charcoal color direction as well. At that stage no identity/palette direction was accepted. [The new concept board](../identity-directions.html) separates shape selection from color selection. Existing functional chat/overlay evidence remains valid for those specimens; it does not imply owner acceptance of their identity. The board is an exploration, not a production adoption.

## Current direction — connected nodes and Warm Lagoon

The owner clarified that the identity should be modern and explicitly show connected nodes, rejected all three abstract-loop concepts, and preferred Lagoon with more warmth. The current candidate follows that direction: a central node and four evenly spaced surrounding nodes; teal `#326d5c`, soft ivory canvas `#f7f4ee`, paper `#fffdf9`, and warm ink `#2c342d`. Dark and high-contrast themes carry corresponding accents. This is the current implemented mockup direction, not a claim that the new logo shape has received final owner acceptance.

`brand.js` remains the single geometry source across inline symbols and exported assets. The earlier loop board is archived. `tokens/palette-studies.json` now compares the current default (inherited directly, with no duplicate role overrides) with the earlier cooler Lagoon. Current entry points are [identity](../identity.html), [Lagoon comparison](../palettes.html) and [embedded overlay](../overlay.html).

## Current refinement — lighter colors and 3D pose

The owner requested lighter colors, more options, clockwise rotation in the 15–30° range and a backward tilt. The mockup now defaults to Soft Lagoon (`color.brand` = `#619581`) on lighter ivory (`color.canvas` = `#faf8f3`), with Sage Lagoon and Sea Glass available as comparisons. Primary actions retain their distinct contrast-safe accent token. This adds one public semantic role, bringing the total to 100.

The default node mark is projected at 22.5° clockwise and 35° backward with a shallow lower layer. Geometry and standalone SVG exports share one source; no CSS 3D transform, raster image, animation or extra rendering framework is required. Interactive identity controls preview nine pose combinations and export the actual selected geometry. This continues to be a mockup candidate, not production adoption or a claim of final owner acceptance.

### Sculpted depth and extended color studies

The current shared SVG adds solid shaded sidewalls and a fine highlight. Default depth is 3, with 1/3/5 preview choices; rotation and tilt remain 22.5°/35°. Six palette studies share the existing semantic roles, and the identity controls apply the selected palette to the local preview and download. No new production theme or runtime dependency is introduced.

### Polished surface and multicolor node option

The default logo surface is now glossy, with a Satin alternative. Vector specular patches provide surface reflection independently of the cast shadow. The optional multicolor mode assigns four distinct outer-node colors from the palette studies, excluding the selected brand. Center and connections always keep the brand hue. Single-brand coloring remains the default; these remain mockup identity studies.
