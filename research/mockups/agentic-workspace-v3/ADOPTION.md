# Applying this visual direction later

Date: 2026-10-09. Candidate implementation mapping only; application changes remain paused. Keep the existing [frontend guide](../../../docs/frontend-development-guide.md), [UI architecture](../../../docs/ui-architecture.md) and [adoption plan](../../../docs/plans/2026-10-08-enterprise-overlay-adoption.md) as the structural baseline. This mockup updates the proposed appearance, not execution contracts.

| Study asset or composition | Existing owner | Implementation rule |
| --- | --- | --- |
| Warm canvas, navy action, violet assistant, semantic status and spacing | `ui/packages/tokens` | Change source tokens and regenerate outputs; preserve light, dark and high-contrast roles. |
| Original logo and monoline icon paths | `ui/packages/components` primitives | One SVG renderer with decorative/labelled usage; server manifests still supply integration branding. |
| Buttons, fields, statuses, disclosures and confirmation | Existing component primitives | Retain accessible primitives, focus handling and disabled/loading behavior. Avoid copying global prototype styles. |
| Proposal, material values, source inspection, recovery and outcome | Component feature modules | Render typed authoritative projections; compose the same features across surfaces. Separate input evidence from observed results. |
| Compact, expanded and mobile placement | `ui/packages/layouts` | Change composition and responsive rules without remounting controller state. Preserve public slots and draft/context. |
| Workspace, work navigation and connections | Web app page composition | Use existing authorized catalog/connection APIs and honest session scope. Do not ship the six fictional workflows as available capabilities. |
| Visible task states and available actions | Existing core selectors and React bindings | Map actual host states into the study's labels. Never use `app.js` or the study selector as an execution state machine. |

## Suggested implementation slices

1. Apply approved identity and token roles in the existing component gallery. Validate all supported themes and ordinary/shadow-root rendering.
2. Update shared primitives, then proposal/confirmation/evidence compositions. Preserve exact material values, approval freshness, authorization and unknown outcomes.
3. Update workspace and responsive placements with those same components. Keep controller lifetime, navigation, source context and drafts intact.
4. Run declared UI checks and conformance, inspect desktop/narrow/embedded screenshots, and complete keyboard/screen-reader and intended-user task review. Record fixture checks separately from live qualification.

Keep feature styles beside feature components and public exports stable. Prefer prop-driven views and existing narrow hooks. Add a new shared abstraction only when a concrete second consumer needs it. User-facing copy belongs in the existing EN/VI catalogs. New provider names, forms or icons must come through server-admitted metadata, never UI conditionals.

The prototype is a specification and asset source, not production code to transplant. In particular, its string rendering, fixed sample times, simulated access checks, read-back records and study controls must not be carried over. Reviewer queues, delegation, persistent cross-session work, unsupported integrations and useful missing-access fallback flows need their own supported contracts and scoped designs.
