# ADR 0016: Selectable enterprise agent surfaces

Date: 2026-10-08. Status: **Accepted** (implementation decision within the owner's requested selectable overlay design).

## Context

The owner requested research and an enterprise agent overlay that can be changed from the UI. [Research 11](../../research/11-enterprise-agent-overlay-design.md) recommends an expanded Workbench with task and operational context. ADRs 0011 and 0015 already separate presentation from shared run/approval authority.

## Decision

Add `workbench` alongside `overlay`, `sidebar` and `full-page`. Workbench reuses the nonmodal overlay and all existing semantic task/review components, with a responsive task/context grid. Add a concrete `task-overview` slot showing authoritative state and supported recorded milestones.

L3 owns the unsent in-memory composer draft so component remounts cannot lose it. L5 exposes only the available surface vocabulary and context. L6 renders the labeled View control; L7 owns switching, session-local presentation preferences and focus. L8 limits embedded hosts to Compact, Workbench and Docked; standalone also offers Workspace. Explicit URL/element layout configuration takes precedence over restoring a saved preference.

Keep the same controller above layout changes. A change backs out of an open confirmation to review and requires a fresh explicit confirmation. Minimization preserves the draft/run and returns focus to the launcher; pending review remains indicated. Changes do not submit tasks, grant approval, choose connections or change server authority. Presentation preferences contain only a validated layout identifier, scoped separately for standalone and embedded elements.

## Alternatives considered

A separate agent chat framework would duplicate the core and add unnecessary contracts. A theme-only switch would not provide the requested expanded operational workspace. Automatically widening every overlay would remove user control. Provider-specific enterprise branding would violate UI neutrality.

## Consequences

The configuration vocabulary gains one layout and one slot. Existing layouts/defaults remain valid. Appearance is independent of layout. Typed draft text survives in-session layout changes but is not persisted across reload. Embedded hosts must assign distinct element IDs to isolate preferences among multiple instances. No HTTP API or backend execution behavior changes; enterprise readiness and human usability remain separate evidence requirements.

## Verification

Unit coverage validates the new layout and controller draft. Playwright covers switching on standalone/embedded hosts, exact review continuity, confirmation reset, retained drafts, preference reload/explicit override, focus, minimization and narrow-screen controls. The shared conformance suite runs against Workbench as well as existing hosts. Opt-in fixture screenshots support visual inspection. Layer/provider-neutrality gates remain mandatory.
