# ADR 0011: layered, themeable and replaceable UI over a shared headless core

Date: 2026-10-06. Status: Accepted (project owner, decisions D1–D5, 2026-10-06). Refines ADR 0001 (streaming overlay UI) and builds on ADR 0007 (event stream contract).

## Context

The user wants the MVP to ship a default overlay/web UI, and wants deployers to change its theme or layout, or build a different UI entirely, while reusing the layers underneath. The current plan describes one React/Vite overlay with no internal layering, which would make every customization a fork.

Research (details in [UI architecture](../ui-architecture.md) §2):

- Headless UI practice separates behaviour from presentation: Zag.js/Ark UI state machines, React Aria behaviour hooks.
- The W3C DTCG Design Tokens format reached a stable 2025.10 version with theme and multi-brand support.
- CSS custom properties and `::part()` form a styling API through Shadow DOM.
- Agent UI protocols (AG-UI event streams, A2UI declarative UI v0.9 preview, MCP Apps iframes) are evolving and describe conversations or agent-generated UI, not governed business approval.

## Decision

1. Structure the frontend into downward-only layers:
   - L1 server API (single BFF);
   - L2 `@e-agent/client` (generated typed client + resumable SSE);
   - L3 `@e-agent/ui-core` (framework-free run store, selectors, approval state machine, sanitizer, i18n, formatters, digest check);
   - L4 `@e-agent/tokens` (DTCG themes);
   - L5 `@e-agent/ui-react` (hooks + slot registry);
   - L6 `@e-agent/components` (default design system on accessible headless primitives);
   - L7 layouts (`overlay`, `sidebar`, `full-page`);
   - L8 hosts (`apps/web` and the `<e-agent-overlay>` custom element, embeddable in any web page). Integrations into one particular system's UI are optional host adapters, not part of the core.
2. Support four customization tiers: theme (tokens only), layout (config), component override (slots), custom UI (any framework on L3 or L2).
3. **System neutrality.** No UI layer depends on Odoo or any other business system. Host pages contribute only a generic, untrusted `HostContext` hint, which the server resolves through provider connection mappings.
4. The server owns `ApprovalPresentation` (canonical proposal, material fields, findings, digest). Every UI renders approval from it, and ui-core verifies the digest before enabling approval.
5. Any UI that offers approval, default or custom, must pass the shared `@e-agent/ui-conformance` suite.
6. The default UI uses React with React Aria Components as the headless primitive layer, chosen for accessibility and internationalization breadth. This choice is confirmed by a short spike in I08; Ark UI is the fallback.
7. TypeScript types are generated from the Pydantic contracts (OpenAPI 3.1 / JSON Schema). Hand-written duplicate types are not allowed.
8. Not in the MVP: system-specific host adapters (e.g. an Odoo systray item), agent-generated UI (A2UI, MCP Apps), runtime-loaded third-party UI components, and AG-UI output. When agent-generated UI is added later, it may only use a host-trusted catalog and never covers approval or policy surfaces.

## Alternatives considered

- **Single React app with CSS overrides.** Fastest start, but a layout change or a custom UI means forking it, and safety-critical approval logic would be duplicated in every fork.
- **Adopt a chat UI kit (assistant-ui, CopilotKit) as the core.** These cover conversation well but not the run/approval/evidence domain. They remain options inside L6 for the message pane, connected through ui-core.
- **AG-UI or A2UI as the UI contract.** Rejected for the canonical path (ADR 0007): approval must stay a kernel concept, and A2UI is still preview.
- **Web Components for all default components.** Good for embedding, but ecosystem accessibility primitives are richer in React. Instead, only the outer overlay is a custom element.

## Consequences

- There are more TypeScript packages, and a pnpm workspace is needed next to the uv workspace.
- I08 grows: client, ui-core, tokens and the conformance skeleton come before visual polish.
- Custom UIs get a stable public surface (L2/L3 APIs, tokens, slots, parts) that needs semantic versioning and changelogs.

## Verification

- Boundary rules: ui-core has no React or DOM imports; packages import only from lower layers.
- A non-React reference custom UI built on ui-core passes the conformance suite.
- A theme swap produces zero component diff, and contrast checks on safety tokens pass.
- The overlay element is unaffected by hostile host-page CSS.
- Revisit if A2UI or AG-UI become stable standards that can represent governed approval, or if a second production UI shows the layer split is too fine or too coarse.
