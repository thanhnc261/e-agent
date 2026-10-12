# Frontend development guide

**Date:** 2026-10-08, status updated 2026-10-09. **Status:** in force for `ui/`. The folder structure, reuse boundaries, state ownership and extension recipes below were adopted by work packages FE-00 to FE-07 and API-01; see [UI architecture §11](ui-architecture.md#11-enterprise-overlay-adoption-2026-10-09) for what was actually built and the [implementation results](handoffs/2026-10-08-enterprise-overlay-implementation-results.md) for the checks. Folders are created when a real implementation needs them, so the tree below is still the target shape rather than a file listing. Accepted dependency and trust boundaries remain in the [UI architecture](ui-architecture.md).

## 1. Organize by layer, then by feature

Keep existing packages. Within a package, put code that changes together beside each other. Separate a feature when it has its own behavior, visual contract or tests; do not make one file per trivial expression. Entry files export supported APIs and compose defaults instead of containing implementations.

```text
ui/
  apps/web/src/
    main.tsx                       # create services/controller; mount once
    app/                           # routes, host composition, DOM preferences
    pages/                         # Overview and session work composition
  packages/
    client/src/                    # generated schema + typed transport
    ui-core/src/
      controller.ts                # run lifecycle and commands
      store.ts                     # event/snapshot state
      approval.ts                  # existing approval state machine
      presentation.ts              # exact display/canonical checks
      selectors/                   # pure evidence/outcome/task projections
      i18n.ts                      # existing catalogs; split only as needed
      index.ts
    tokens/
      tokens/                      # authored semantic token sources
      src/generated/               # generated CSS/JSON, never hand-edited
    ui-react/src/
      providers/RunProvider.tsx
      hooks/                       # useRun, useComposer, usePendingApproval...
      slots/                       # names, types, provider and Slot
      presentation/                # context contract; owner remains L7/L8
      index.tsx
    components/src/
      primitives/                  # Button, IconButton, Surface, StatusBadge...
      features/
        composer/
        conversation/
        task-navigation/
        task-overview/
        approval/
          ApprovalPanel.tsx        # connected public slot component
          ApprovalReview.tsx       # prop-driven rendering
          MaterialFields.tsx
          RuleFindings.tsx
          ApprovalConfirmation.tsx
          approval.css
        evidence/
        outcome/
      defaults.ts                  # built-in slot map
      components.css               # public aggregate stylesheet
      index.tsx                    # stable public exports
    layouts/src/
      config.ts                    # validated public layout configuration
      presentation/                # preferences and focus transitions
      shared/TaskSurface.tsx       # shared task composition, not task logic
      overlay/
      workbench/
      sidebar/
      full-page/
      layouts.css                  # public aggregate stylesheet
      index.tsx
    overlay-element/src/           # custom-element lifecycle/attributes
    ui-conformance/                # shared browser contract suite
```

Create only modules used by the implementation. Connections/catalog feature folders come with their real contracts, not as empty placeholders. Keep unit/component tests under each package's existing `test/` directory, mirrored by feature, so current Vitest discovery continues to work. Development gallery examples use neutral fixture data and a separate Vite entry excluded from production inputs; do not import demo behavior from production components.

## 2. Choose the right reuse boundary

| Kind | Allowed responsibilities | Example |
|---|---|---|
| Primitive | Semantics, interaction and styling; props only, no run hooks or transport. | Button, field, status badge, disclosure. |
| Feature view | Render a typed view model and callbacks; local disclosure/focus state is acceptable. | MaterialFields, OutcomeSummary. |
| Feature container | Read L5 hooks, bind commands and compose views. | ApprovalPanel, EvidencePanel. |
| Layout | Arrange slots, responsive regions and focus transitions. | Workbench with task and evidence columns. |
| Host/page | Controller lifecycle, routing, environment/configuration and page composition. | Standalone Overview, embedded element. |

Start with a specific component. Extract a shared primitive when it has a stable repeated role or needs one consistent accessibility behavior. Prefer children and a small typed variant API over dozens of boolean switches. Keep helpers near their feature until a second actual consumer needs them; avoid catch-all `utils`, `common` and `services` folders.

Wrap React Aria where the wrapper adds a consistent product contract. Preserve refs, accessible names, keyboard behavior, slots and merged event handlers; do not replace a button with a clickable `div`. Use the library's composition facilities rather than swallowing consumer props. [React Aria customization](https://react-aria.adobe.com/customization).

Public feature components retain existing names and slot IDs during extraction. Export public types with the component; keep internal parts private until a concrete customization needs them. Within-package implementation imports use direct module paths to avoid barrel cycles. Across packages, use declared public exports; never reach into a sibling's `src/`.

Extend architecture checks to prevent primitives importing feature hooks, feature-to-feature cycles, upper-layer imports and private cross-package paths. Feature composition belongs in a container/layout, not through two features importing one another. Keep the existing provider-neutrality gate across `ui/`, including examples and tests.

## 3. State has one owner

| State | Owner | Rule |
|---|---|---|
| Run/action/approval/evidence authority | Server; represented in L3 | Browser state cannot promote a result to verified, grant permission or approve implicitly. |
| Active run, submission identity, draft, run history | L3 controller | Do not mirror in React state. Preserve existing storage scope and lifetime. |
| Derived status, summary, display rows | Pure L3 selectors | Derive from authoritative state; do not synchronize a second copy through effects. |
| React subscription | L5 hooks | Keep `useSyncExternalStore`, stable subscriptions and immutable stable snapshots. |
| Surface, appearance, density and preference validation | L7 presentation owner | Share through a narrow L5 context; no business state in that context. |
| Host attributes, document/shadow-root integration | L8 | Receive explicit preference callbacks. L6 must not discover and mutate its host document. |
| Selected standalone page/route | L8 | Preserve controller across navigation. No secrets or task text in the URL. |
| Expanded disclosure, tooltip, local focus | Nearest component/layout | Keep transient UI state local. Approval phase remains in the core machine. |

React recommends deriving values rather than storing redundant or contradictory state. Component position and keys determine state lifetime, so a layout remount must not own the task draft or execution controller. [State structure](https://react.dev/learn/choosing-the-state-structure), [state lifetime](https://react.dev/learn/preserving-and-resetting-state).

The existing external store supports both React and vanilla hosts. Keep it; adding Redux, Zustand or a query cache is not part of this migration. If profiling reveals broad streaming rerenders, introduce a tested selector subscription in L5 with stable cached snapshots. Merely wrapping a fresh object in a hook will not solve it. [useSyncExternalStore](https://react.dev/reference/react/useSyncExternalStore).

Standalone navigation can start with validated hash routes, avoiding a new server history-fallback requirement. Define a small typed route union, Back/Forward behavior and invalid-route fallback; preserve existing layout/lang/theme query parameters. A route containing a run ID is only a navigation request: attach through the authorized controller, respect unfinished-task safeguards and handle denied/deleted runs. Embedded mode stays independent of the host page's router.

## 4. Contracts and presentation data

Generate wire types from server OpenAPI. Components consume typed projections, not raw `Record<string, unknown>` parsing spread throughout JSX. Validate unsupported or malformed response shapes at the boundary and map them with pure functions in core. Keep generated types, normalized view models and component props distinct when they have different responsibilities.

Use discriminated unions where different states permit different interactions, such as loading/ready/denied/error. Do not encode the same state with several independent booleans. Preserve unknowns, source references, observed times and revisions. A missing value must not turn into an empty string, zero, connected status or permission granted.

Approval is a protected feature: keep exact canonical/display validation, material-field completeness, findings, freshness and explicit confirmation in the existing controller/machine path. A reusable card may arrange terms but cannot reinterpret them. Current supported canonical values are bounded; arrays or new artifact types require contract and validation work, not a permissive visual fallback that enables approval.

For a future domain-specific artifact, first define a versioned host-owned presentation contract, then add a trusted renderer keyed by schema/type. Provide a safe unsupported-type state. Do not build an arbitrary JSON-to-UI framework, runtime plugin loader or model-generated approval renderer. Provider identifiers never select a UI implementation.

Connection, catalog and result views are display projections. They cannot resolve credentials, choose an acting identity, enforce independent business policy or authorize a command. All API access goes through L2 and the controller/application state layer; no `fetch`, provider SDK or raw privileged client inside a component.

## 5. Styling and responsive behavior

Retain React Aria and namespaced plain CSS with the existing DTCG compiler. Add semantic roles for canvas/surface, text, border, accent, status, spacing, type, radius, shadow and motion as consumed by actual components. Components use tokens rather than repeated hex values or appearance-specific colors. The DTCG format is a community specification; keep the compiler's supported subset documented. [DTCG 2025.10](https://www.designtokens.org/tr/2025.10/format/).

Co-locate feature styles and aggregate them through the existing exported `components.css` and `layouts.css`. Verify that Vite resolves the aggregate into a complete `?inline` stylesheet for the shadow root; no unresolved runtime imports or dependence on page-global CSS. Keep primitives responsible for internal styling and layouts responsible for geometry. Avoid selectors that reach into another feature's private DOM.

Use React Aria state attributes for focus, pressed, selected and disabled styling. Prefer a small explicit `variant`/`size` contract over per-call inline CSS. Adding Tailwind, CSS-in-JS or a second component framework is not necessary for this work. [React Aria styling](https://react-aria.adobe.com/styling).

Base layout on available container width, not just window width: a sidebar can be narrow on a large monitor. Use grid/flex with sensible minimum sizes and scoped scrolling; reserve JavaScript size observation for behavior that CSS cannot express. Derive a semantic compact/wide presentation value if behavior needs it instead of scattering `window.innerWidth` checks. Honor reduced motion, forced colors and long translated content. Confine decorative presence effects to nonessential regions.

## 6. Accessible interaction is part of the API

Define component states and focus behavior before styling. Every interactive component needs a name, keyboard operation, visible focus, disabled/pending behavior and recovery from errors. For dialogs, explicitly choose modal or nonmodal semantics. A floating assistant is not automatically modal; only genuinely modal confirmation traps focus. In the embedded host, portals must stay inside the intended shadow-root styling/focus boundary.

Aim for 44px controls where space allows. WCAG 2.2 AA's target-size minimum is 24×24 CSS pixels or its specified spacing/exceptions, not a universal 44px requirement. Sticky controls must not obscure focused content. Reflow checks include 320 CSS-pixel width, zoom and text scaling, with appropriate handling of genuinely two-dimensional content. [Target size](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html), [focus visibility](https://www.w3.org/WAI/WCAG22/Understanding/focus-not-obscured-minimum.html), [reflow](https://www.w3.org/WAI/WCAG22/Understanding/reflow.html).

Use polite announcements for meaningful run-state changes. Do not announce every streamed token or steal focus on each update. Preserve reader scroll position and offer a jump-to-latest control. Errors belong next to the relevant field/action and include a supported next action. Toasts cannot be the only record of failure, an approval requirement or an unknown external effect.

## 7. Development and reuse workflow

For each meaningful component, document its purpose, props, slots, states, focus behavior and one reuse example in the development gallery. Cover realistic long values, missing data, EN/VI, disabled/loading/error and each supported theme. Keep scenario data independent of production controllers. The gallery should reuse production views rather than maintain a second styled implementation.

Use the existing Vite toolchain for this bounded gallery initially. Evaluate Storybook only when independent component browsing and team workflows justify its maintenance; it is not a runtime dependency or prerequisite. Accessibility automation can detect some defects but does not replace human checks. [Storybook accessibility testing guidance](https://storybook.js.org/docs/writing-tests/accessibility-testing).

| Change requested | Preferred edit path | Relevant verification |
|---|---|---|
| Brand, spacing or appearance | Authored token sources, regenerate output | Token resolution/contrast and reviewed surfaces. |
| New placement or panel arrangement | Layout/configuration and slots | Same-controller retention, focus, sizing and approval conformance. |
| New reusable control | Primitive with typed props and React Aria behavior | Interaction test and gallery states. |
| New existing-contract feature | Core selector if needed → L5 hook → feature view/container → slot/layout | Selector/state cases and meaningful user journey. |
| New enterprise capability | Server domain/adapter + authorized contracts first → generated client → generic UI projections | Backend authorization/verification plus UI contract tests. |
| Replace default UI | Public core/client contracts and shared conformance | No dependency on React or default layout internals. |

Pin new tooling only when introduced, inspect its compatibility with the lockfile and document the actual command. Use the existing strict TypeScript settings, test runner and boundary gates. Add focused tests for changed behavior and high-risk reuse boundaries; avoid snapshotting every wrapper or mirroring its implementation in tests.

Before merging a feature, verify that its data has an authoritative owner, extension does not require provider conditions, alternate surfaces reuse the same behavior, localization/accessibility states exist, and no sensitive browser persistence or telemetry was added casually. Profile performance before adding caching, memoization or virtualization. Record actual results and limitations in the PR rather than copying historical test counts.

## 8. Default overlay visual foundation candidate (2026-10-10)

The owner requested careful treatment of the warm styling as the default overlay foundation. The current [foundation contract](../research/mockups/agentic-chat-v4/design-system/FOUNDATION.md), [identity study](../research/mockups/agentic-chat-v4/identity.html), [embedded specimen](../research/mockups/agentic-chat-v4/overlay.html) and [review evidence](../research/mockups/agentic-chat-v4/design-system/FOUNDATION-REVIEW.md) define the candidate values and behavior. The specimen reuses the authored token/control sources and verifies container sizing and Shadow DOM isolation. It is not the production custom element.

Adoption must use the existing layer/primitive/layout boundaries above, preserve appearance/density/theme preference precedence and controller lifetime, and reconcile the candidate sRGB-object inputs with the production token compiler. The candidate’s browser evidence must not be reported as live qualification.

**Status 2026-10-12: adopted in production.**
- **What is in production:** the owner-approved Sage Lagoon multicolour logo (`BrandMark`), the warm Sage Lagoon light, dark and high-contrast tokens, theme-safe motion, and the conversation-first overview (EA-10).
- **Where to look:** the adoption record, rulings and remaining blocked items are in [the results handoff](handoffs/2026-10-12-ui-foundation-adoption-results.md).
- **What changed for implementers:** this section no longer describes paused work. New UI follows the production tokens.
