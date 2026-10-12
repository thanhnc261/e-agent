# Conversation + workspace study

Current visual direction: [tilted connected nodes + Soft Lagoon](identity.html). The owner requested visible nodes and connections with a warmer Lagoon palette. Earlier explorations below remain history; the current mockup uses this revision.

Date: 2026-10-10. Candidate mockup, not product implementation.

The owner rejected study 03's dashboard hierarchy and permanent sidebar. This revision changes the information architecture: conversation is the primary surface; the right workspace holds the thing being worked on. The previous study is preserved, not endorsed by this revision.

## Open

From the repository root:

```sh
python3 -m http.server 4181 --bind 127.0.0.1 --directory research/mockups
```

Open http://127.0.0.1:4181/agentic-chat-v4/ . Open the [component catalog](http://127.0.0.1:4181/agentic-chat-v4/components.html) for themes, icons and interactive component states. The mockup uses local scenario and action presentation modules from study 03. Serve the parent directory as shown.

## What to evaluate

1. Start on an uncluttered conversation, with three optional examples and a composer. There is no catalog dashboard or secondary work list.
2. Expand/collapse left navigation. It starts as a 68px rail; conversation history is available when expanded. On mobile it is a drawer.
3. Select **Prepare a handoff**. Chat carries intent and explanation. The proposed document opens on the right at desktop widths; on mobile open it from the conversation's document card.
4. Close/reopen the workspace. Sources and activity are tabs within that workspace; they do not add permanent columns. Draft chat input and the selected task survive placement changes.
5. Review the exact action. Create the document and share its message with separate approvals and sample read-back. Activity contains clearly labelled prototype controls for stale and unknown outcomes.
6. Start another conversation and return through history. Thread-specific input, proposal and results remain separate for this page session.

All examples, access checks and results are fictional. Free-text submission opens a sample selector; follow-ups are preserved but do not invoke a model or change proposals. This is explicit in the interface. No persistent conversations, real integrations, authorization or writes are implemented.

## Research applied to the structure

This reuses the earlier [32-page source audit](../agentic-workspace-v3/source-coverage.html), not a new research or usability claim.

- [Chat interface patterns](https://agentic-design.ai/patterns/ui-ux-patterns/chat-interface-patterns): a persistent conversation with a structured document beside it. Chat is the entry and coordination surface, not the container for every complex review field.
- [Progressive disclosure](https://agentic-design.ai/patterns/ui-ux-patterns/progressive-disclosure-patterns): history, sources, activity and connection details appear when requested. Scope and material values stay in the document review; exact confirmation repeats the full action.
- [Enterprise UX](https://uxpilot.ai/blogs/enterprise-ux-design): prioritize the primary task, consistent navigation and familiar controls. The visual direction carries over a warm neutral canvas and restrained identity; page structure is substantially different.

These are design interpretations. Pattern coverage and a code review did not validate the previous layout with the owner; this revision must be assessed as a concrete interaction.

## Code and adoption boundary

`index.html` defines the shell; `styles.css` owns this composition; `app.js` implements local prototype transitions. Tokens, icons, composer and status views are shared with the new [design system](design-system/README.md). Fixtures and action records are imported from the preserved study 03. Production should map conversation, artifact, source, review and navigation into existing components/layouts and core state, not copy this string renderer or simulated transitions. Current production work remains paused. No ADR or backend contract changes are introduced.

## Checks

Run `node research/mockups/agentic-chat-v4/verify.mjs` with the server running and UI dependencies installed. See `QA.md` for actual results. Warm light, warm dark and high-contrast variants are included. Keyboard/screen-reader certification, user task testing and embedded host placement are not established by this candidate.

[Claude review](CLAUDE-REVIEW.md) and [response](REVIEW-RESOLUTION.md) record subsequent layout/context corrections. Neither is a substitute for owner assessment of the design.

## Warm canvas and conversation refinement

The current working palette uses soft ivory (`#f7f4ee`), warm paper surfaces, Warm Lagoon actions and neutral dividers, replacing the rejected navy/cream direction. This is an adaptation of the supplied Agentic Design reference, not a claim of exact color matching. Conversation details include selected material values, expandable sample-source citations and prepared follow-up exchanges. Suggestions prefill the composer for review before sending.

The composer grows with text, disables Send when empty, supports Shift+Enter, and lets an active conversation include/remove sample source references. References travel with the sent message and do not change source permissions or an existing proposal. New conversations expose connection context; sources become selectable after choosing a sample. `chat-content.js` holds authored replies separately from layout and transitions. Arbitrary free text remains explicitly unprocessed by a model.

## Component system and responsive coverage

The [interactive catalog](components.html) contains eight sections: foundations, identity/icons, controls, forms, conversation, work/evidence, feedback and navigation/overlays. Its 99 public tokens, 46 SVG icons, logo variants and shared composer/status views also drive the chat mockup. Theme changes therefore exercise the same sources. The [frontend specification](design-system/README.md) documents source ownership, component contracts, responsive rules and adoption into the existing FE packages.

Catalog checks cover widths from 320 to 1920px, tablets and short landscape. The chat checks include dark/high-contrast layouts and a reduced-height viewport. Standard controls are 44px, mobile uses one main view, and dialogs/tables remain contained. These are browser viewport tests, not physical-device certification.

The component system received a separate [Claude review](design-system/CLAUDE-REVIEW.md); [resolved findings](design-system/REVIEW-RESOLUTION.md) cover hover contrast, token reuse, focus and high-contrast boundaries.

## Default overlay foundation review

The refined [connected graph identity](identity.html) and [embedded foundation preview](overlay.html) are now available. The latter uses Shadow DOM and container sizing, supports hostile-host CSS testing and keeps the same design tokens and controls as the catalog. The [foundation contract](design-system/FOUNDATION.md) and [review](design-system/FOUNDATION-REVIEW.md) document findings, corrections, browser evidence and production adoption boundaries.

[Compare warm and original Lagoon](palettes.html). The latest owner direction supersedes the earlier charcoal, forest and espresso studies.

## Earlier identity restart — archived exploration

The owner rejected the earlier node/hexagon marks and the navy/cream and charcoal palettes. The then-current design exploration was [New identity directions](identity-directions.html): Bond, Orbit and Mesh, with independent Ember, Iris and Lagoon treatments. The main chat retained its earlier identity during that exploration; none of those three loop shapes was accepted. This comparison uses native radio controls, the shared composer and icons, and downloadable SVG symbols.

`design-system/identity-directions.json` owns the concept geometry and color values. `export-icons.mjs` generates their SVG downloads; `--check` verifies source/export parity. The lockup on this exploration uses the system font and is a typographic specimen, not a new outlined wordmark export. `identity-directions.js` applies scoped semantic overrides without adding production themes.

## Current identity and color direction

The owner clarified a preference for a modern, explicitly connected-node logo and a warmer Lagoon palette. The current [identity](identity.html) implements a five-node connection symbol with warm teal/ivory colors throughout the mockup, component catalog and embedded specimen. [Compare warm and original Lagoon](palettes.html). The earlier three-loop exploration is archived; its rejection and earlier visual evidence remain recorded above. This follows the requested direction and does not claim final logo acceptance or production adoption.

## Lighter palettes and 3D pose

The current mark rotates 22.5° clockwise and tilts backward 35°, with perspective-scaled nodes and a shallow depth layer. [Identity controls](identity.html) preview clockwise 15°/22.5°/30° and backward 20°/35°/45°; the SVG download matches the selected pose. [Color options](palettes.html) compare Soft Lagoon, Sage Lagoon and Sea Glass. Soft Lagoon is the mockup default.

A new semantic `color.brand` token keeps the logo lighter while primary actions retain readable contrast. The system now contains 100 public tokens. The pose is generated as standalone SVG in `brand.js`, shared by the chat, launcher and asset exports; there is no 3D runtime or canvas dependency.

### Sculpted logo and six color choices

The identity preview now includes Subtle, Sculpted and Deep extrusion, with solid sidewalls and a lit edge. Six selectable palettes update the local preview and SVG download: Soft Lagoon, Sage Lagoon, Sea Glass, Rose Clay, Dusty Iris and Linen Blue. The default remains Soft Lagoon at 22.5° clockwise / 35° backward, with Sculpted depth. Comparison cards link directly to the selected color. These choices remain mockup studies.

The identity preview also offers **Shadow: None / Soft / Raised**. Soft is the default; the selected shadow is included in the downloaded SVG.

The latest preview adds **Surface: Satin / Glossy reflection** and **Node colors: One brand color / Color per node**. The center and connections retain the chosen brand; the four outer colors come from the other palette studies. Open `identity.html?nodes=multicolor` to inspect this option directly.
