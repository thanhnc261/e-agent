# Enterprise agent overlay: research and design

Date: 2026-10-08. Scope: the existing provider-neutral MVP UI. Implementation baseline: [ADR 0016](../docs/adr/0016-selectable-agent-surfaces.md).

## Research evidence

The following primary sources were reviewed on 2026-10-08. Vendor design guidance is evidence of design practice, not independent proof of usability or enterprise readiness. The recommendations below are project design decisions.

| Reference | Relevant guidance | Application to e-agent |
|---|---|---|
| [Microsoft 365 Copilot redesign](https://www.microsoft.com/en-us/copilot/blog/2026/05/28/introducing-a-new-design-for-microsoft-365-copilot/) (2026-05-28) | Task-aware workspaces, progressive disclosure, consistent entry points and returning to work | Keep the active task visible; offer compact and expanded surfaces without creating another session |
| [Carbon for AI](https://www.carbondesignsystem.com/building-blocks/foundations/carbon-for-ai) (updated 2026-08-12) | Consistent AI identity and contextual explainability; AI styling should communicate purpose | Give the Workbench a restrained accent and dedicated context panel; use actual evidence rather than decorative “thinking” effects |
| [Carbon AI Chat header](https://chat.carbondesignsystem.com/version/v1.19.0-rc.1/docs/documents/UI_customization.Header.html) | Header controls, minimization and customizable menus | Put the View selector beside existing appearance/language controls; retain work when minimized |
| [IBM explainability](https://www.ibm.com/design/ai/ethics/explainability/) | Make context and explanations understandable to users | Keep authorized evidence and event activity inspectable beside review |
| [SAP Joule Panel, Android v25-4](https://www.sap.com/design-system/fiori-design-android/v25-4/joule/components/joule-panel) | A panel provides an agent interaction surface with close/minimize controls | Support a persistent launcher and explicit reopening; this mobile reference does not establish a desktop web interaction standard |

The Carbon header reference is versioned release-candidate documentation. No vendor framework, artwork, trademark or AI chat runtime is introduced. Adoption/performance claims from vendor articles are not used as acceptance evidence.

## Recommended visual direction

**Workbench** is the expanded enterprise agent overlay: a floating task workspace with a primary task/review column and a secondary operational context column. Its identity comes from a clear task, authoritative state, exact proposed changes, explicit human approval and accessible evidence. Avoid invented execution plans, simulated reasoning, percent-complete meters and treating model prose as verified success.

| UI choice | Config value | Intended use |
|---|---|---|
| Compact | `overlay` | Quick requests while keeping the host page visible |
| Workbench | `workbench` | Longer tasks and detailed review with visible task overview, evidence and activity |
| Docked | `sidebar` | Persistent edge panel alongside host work |
| Workspace | `full-page` | Standalone focused work; excluded from embedded hosts |

The existing default remains unchanged. Workbench is selectable rather than forced on every user.

Desktop Workbench is at most 68rem wide, with a flexible task column and 17rem context column. The panel retains viewport margins and bounded height. Below 900px, context stacks after task content; below 760px, margins shrink. Grid rows retain content height so inspector content cannot cover task controls. Approval details have bounded scrolling; the exact review fields and action footer remain reachable.

Use existing shared typography, spacing, rounded surfaces and light/dark/high-contrast tokens. A thin accent at the header and task overview provides identity without adding decorative animation. Keep headings, exact business references and review controls more prominent than supporting activity. Long content wraps; no horizontal scrolling is required at the tested 390px viewport. EN/VI labels share the same controls.

## Interaction design

The header's labeled **View** selector changes presentation in place. One controller stays mounted above all layouts: the active run, snapshot, approval digest, task history, admission retry identity, locale and theme survive. An unsent composer draft lives in the framework-free controller and survives switching/minimizing. It is memory-only and is not promised to survive a browser reload.

Switching returns an open confirmation to the review step; the user must request and confirm approval again. Layout changes never send an approval, start another run, choose credentials or alter validation/policy. The selector is disabled while task admission is busy. Focus moves to the new View selector after switching. Escape backs out of confirmation first; a later Escape minimizes the nonmodal overlay and returns focus to the launcher. A minimized pending decision shows a review badge.

A validated presentation preference is stored in session storage. Explicit standalone `?layout=...` or embedded `layout` configuration overrides restoring that preference. Embedded preferences have a separate key scoped by element ID; hosts with multiple instances should provide distinct IDs. Only the layout identifier is stored by this feature. No business record or credential is written to the preference key.

The Workbench task overview presents the exact submitted task, authoritative run state and at most four supported recorded milestones. It explains that business changes require human approval. Evidence and activity use existing authorized data paths. No hidden chain-of-thought is collected or shown.

## Architecture and acceptance

L3 owns the draft and existing run/approval state. L5 exposes a narrow surface context and the `task-overview` slot. L6 renders controls and context. L7 owns available layouts, switching, local presentation preference and overlay focus. L8 restricts embedded modes and honors host configuration. There is no L6 import of L7, provider-specific UI logic, new server endpoint or duplicate enforcement inventory.

Acceptance covers identical canonical review fields across all surfaces, no implicit decision on switch, draft retention, confirmation reset, host preference precedence, Shadow DOM isolation, narrow-screen reachable controls, themes and keyboard interaction. Deterministic browser checks and screenshots demonstrate implementation behavior; representative user research and formal accessibility evaluation remain unperformed. Backend readiness findings and live model/ERP qualification remain separate.

See the [implementation handoff](../docs/handoffs/2026-10-08-enterprise-overlay.md) for actual verification and captured screens.
