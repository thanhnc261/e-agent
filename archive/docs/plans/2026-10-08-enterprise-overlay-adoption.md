# Enterprise overlay adoption plan

**Date:** 2026-10-08. **Status:** implemented 2026-10-09 for FE-00 to FE-07 and API-01, against deterministic fixtures. This document remains the plan; the delivered behaviour, the checks that were actually run and the remaining gaps are in the [implementation results handoff](../../../docs/handoffs/2026-10-08-enterprise-overlay-implementation-results.md). Fixture success is not a live-release qualification and does not change the readiness claim in the README.

Apply the [enterprise-wide mockup](../../research/mockups/agentic-overlay/index.html) to e-agent in two deliveries: first improve the existing task experience and frontend maintainability, then introduce enterprise discovery and connection views backed by authorized server APIs. The product remains domain-neutral; available workflows must reflect implemented capabilities.

Read with [research 12](../../../research/12-agentic-overlay-ux-research.md), [research 14](../../../research/14-enterprise-wide-agent-experience.md), the accepted [UI architecture](../../../docs/ui-architecture.md), and the companion [frontend development guide](../../../docs/frontend-development-guide.md). ADRs [0011](../../../docs/adr/0011-layered-replaceable-ui.md), [0015](../../../docs/adr/0015-task-workspace-presentation.md) and [0016](../../../docs/adr/0016-selectable-agent-surfaces.md) remain the baseline. New discovery contracts need a focused ADR and corresponding design updates before implementation; this plan does not silently adopt them.

## 1. Recommended scope

**Delivery A — reusable overlay and workspace.** Apply the Calm visual direction, clearer task/review/evidence hierarchy, responsive placement, reusable components and consistent interaction states to real existing runs. Preserve current client/core/controller and approval behavior. Standalone Overview and session work navigation can ship with honest capability limits. Add AI Presence and Operator only after Calm passes the same gates.

**Delivery B — enterprise discovery.** Add an admitted task catalog and a member-safe Connections view after their API contracts and authorization tests exist. A durable cross-session work/review inbox is a separate backend increment. Procurement remains one domain; shipping these screens does not implement CRM, knowledge, people or IT workflows.

Do not port the prototype's simulated task engine, fixture integrations, fake status transitions or Design Study controls into production. Retain the research mockup unchanged as a reference. A request to connect an application must not be represented as access granted.

## 2. Repository assessment

| Current implementation | Implication for this change |
|---|---|
| Eight UI packages already separate client, headless state, tokens, React bindings, components, layouts, embedding and conformance. | Keep these boundaries and the current stack. Reorganize internals instead of adding another framework or package hierarchy. |
| Most L6 components are in `ui/packages/components/src/index.tsx`; L5 hooks and L7 layouts also share large entry files. | Extract cohesive modules, preserve public exports and keep entry files as composition/barrels. |
| Component code directly manages theme DOM attributes and uses viewport/ancestor queries for navigation and approval scrolling. | Move host DOM updates to L8 and shared presentation policy to L7. Use component/container sizing and explicit focus contracts. |
| `EvidencePanel` interprets an unstructured evidence response. | Normalize supported shapes at the client/core boundary; give views typed projections with explicit unknowns. Do not invent missing provenance. |
| One `RunController` supports active-run SSE, draft, approval and up to 20 session-history entries. | Keep its lifetime above layout changes. Inactive entries are last-known state, not a live tenant-wide inbox. |
| API supports per-run commands, snapshots, events, approvals, inputs, cancellation, reconciliation and evidence. | There is no implemented run-list API, task catalog, member connection inventory or proposal-edit API to reuse. |
| Shadow-DOM embedding and a non-React reference host already exist. | Preserve inline CSS bundling, keyboard/press behavior and lower-layer replaceability. Current cookie auth limits embedding to same-origin. |
| TypeScript, Vitest, Playwright, boundary and neutrality gates exist; a general formatter does not. | Use existing checks, add scoped formatting in its own change, and add tests for changed behavior. |

Assessment is from source inspection on the stated date, not a new test run. Existing live readiness limits remain in the [remediation retest](../../../docs/reviews/2026-10-07-mvp-remediation-retest.md).

## 3. Map the mockup to the product

| Mockup element | Delivery A behavior | Later dependency |
|---|---|---|
| Overview and task entry | Neutral welcome, actual composer, recent session work. Explain installed scope; no hard-coded five-workflow menu. | Server-admitted, requester-visible task catalog for discoverable workflow cards. |
| My work | Label as “This session”; display last-known state and refresh a selected run before offering a decision. | Authorized paginated run listing for durable, searchable, cross-device work. |
| Needs review | Bring the active run's authoritative review into view; session history may show clearly marked last-known hints. Do not show a fabricated global count. | Server-owned pending-review query, freshness and authorization semantics. |
| Connections | Keep out of production navigation until a useful authorized view exists. Distinguish integration availability from the existing SSE `ConnectionStatus`. | Member-safe connection/capability projection; administrative changes and OAuth remain Phase 2. |
| Floating / expanded / docked | Map to existing `overlay` / `workbench` / `sidebar`; retain `full-page` for standalone. | No new execution API. |
| Task, artifact, context and evidence columns | Compose existing trusted task overview, conversation, exact approval, verified outcome and evidence. | New artifact schemas only for a concrete capability; versioned server projection and fallback required. |
| Edit proposal | Hide when unsupported. Input for a new proposal must follow a defined host flow. | Host-supported re-proposal contract that invalidates prior approval; browser must not patch canonical arguments. |
| Cross-application progress | Show only recorded host events and action-specific results. | Real admitted domains/adapters, authorization, per-action approval and independent verification. |
| Partial result / unknown effect | Keep committed, verified, failed and unknown states distinct; offer existing authorized reconciliation where supported. | No automatic retry of possibly committed writes; future multi-action summaries need contract coverage. |

All user-visible integration names, icons and scopes must come from admitted server metadata. An enabled integration, configured connection, currently authorized capability and successful provider health check are different facts.

## 4. Frontend structure and ownership

Retain the dependency flow: host → layouts → components → React bindings → headless core → typed client. Tokens remain independent. Use feature folders **inside** the existing layers; do not create a second feature tree that bypasses them.

| Owner | Responsibilities |
|---|---|
| `@e-agent/client` | Generated DTOs, transport, command identity, typed errors and future discovery endpoints. |
| `@e-agent/ui-core` | Run state, draft, approval machine, pure presentation selectors, safe text, i18n and future discovery state when required. No React or provider business rules. |
| `@e-agent/tokens` | Semantic visual roles, themes, appearance and density tokens. Generated CSS/JSON remain build outputs. |
| `@e-agent/ui-react` | Narrow hooks, context and slot contracts over core; no second business store. |
| `@e-agent/components` | Accessible primitives, prop-driven views and small feature containers using L5 hooks. |
| `@e-agent/layouts` | Placement, responsive composition, shared presentation preferences and focus transitions. |
| `apps/web` / `overlay-element` | Bootstrap, route/attribute parsing, controller lifetime, host DOM attributes and embedding lifecycle. |

The [development guide](../../../docs/frontend-development-guide.md) defines the target folder tree, extraction rules and extension recipes. Keep current exported component names and slot IDs compatible during the migration. An existing consumer should not need to change imports merely because a file moved.

Separate these presentation dimensions:

| Dimension | Values and rule |
|---|---|
| Theme | Existing `light`, `dark`, `high-contrast`. High contrast takes precedence over decorative effects. |
| Appearance | Proposed `calm`, `presence`, `operator`. Changes emphasis and decoration; never approval rules, information completeness or capabilities. |
| Density | Proposed comfortable/compact spacing, within accessibility targets. |
| Surface | Existing `overlay`, `workbench`, `sidebar`, `full-page`. Embedded hosts exclude full page as today. |

Start with Calm plus existing themes and surfaces. Do not force Operator to mean dark mode or AI Presence to mean animation. Define validated defaults and precedence: explicit host configuration, scoped session preference, default. A host-controlled attribute/query value remains authoritative until that configuration changes.

## 5. Ordered work packages

Each row is a separately reviewable PR; every PR records its actual checks. Do not bundle repository-wide formatting, behavior changes and new APIs into one diff.

| ID | Change and main files | Dependencies | Completion gate |
|---|---|---|---|
| FE-00 | Capture current behavior/screens; inventory exports and slots. Pin a compatible Prettier dev dependency, add scoped format scripts and generated-file exclusions under `ui/`. | None | Existing gates recorded; baseline fixture states reproducible. Any pre-existing failure has its own record. No style-driven behavior change. |
| FE-01 | Extract L5 hooks/providers, L6 features/primitives and L7 surfaces from their entry files. Preserve exports, slot IDs, test selectors and aggregate CSS entrypoints. Extend dependency-cruiser rules. | FE-00 | Existing consumers build; conformance remains green; no feature cycles or deep cross-package imports. Format touched modules only. |
| FE-02 | Implement Calm semantic tokens, reusable button/status/surface/field/disclosure patterns and a development-only component gallery. Introduce presentation dimensions and a host callback for DOM attributes. | FE-01 | Three theme contrast checks; keyboard and disabled/loading states documented; CSS works both as normal import and shadow-root inline stylesheet. Gallery excluded from production builds. |
| FE-03 | Recompose TaskSurface: overview, conversation/composer, exact approval, outcome and evidence. Extract typed evidence/outcome selectors. Replace incidental viewport/ancestor DOM logic with explicit layout/focus behavior. | FE-02 | Existing action terms and all material fields stay visible; stale/expired/malformed approval fails closed; unknown result remains unknown. EN/VI and small-container review pass. |
| FE-04 | Apply shared TaskSurface to four layouts; add neutral standalone Overview and session-work navigation. Preserve draft and controller across route/placement changes. | FE-03 | No extra run/command on navigation; Back and focus work; inactive task refresh and active-run navigation safeguards preserved. Same-origin embedding and vanilla conformance still pass. |
| FE-05 | Add AI Presence and Operator token variants; evaluate the same task with representative users and keyboard/screen-reader checks. | FE-04 | No decorative effect obscures terms/status or increases required interaction; reduced motion works. Defer variants that are not ready. |
| API-01 | Specify admitted task catalog and member connection summaries in a focused ADR; update UI/integration/auth designs, implement bounded authorized APIs and regenerate OpenAPI/client types. | Can begin after FE-00; independent of Delivery A | Tenant/principal filtering, version/freshness semantics, safe metadata and missing/unknown states tested. No secret/admin response reused as a member DTO. |
| FE-06 | Render catalog and read-only Connections from those APIs; add loading/empty/denied/unknown/revoked states and neutral manifest fixtures. | FE-04 + API-01 | New provider metadata changes cards without UI source edits. No credential controls, fabricated health, silent identity fallback or unimplemented “connect” action. |
| FE-07 | Qualify and enable each delivery; publish screenshots, checks, usability findings and limitations. Remove temporary rollout switch after stabilization. | FE-04 for A; FE-06 for B; FE-05 only for enabled variants | Acceptance matrix below passed; actual live qualification remains separately identified. |

**First implementation slice:** FE-00 → FE-01 → FE-02 → FE-03 → FE-04. It produces a useful upgrade without waiting on new integrations. Future work/review inbox APIs and cross-domain adapters are separately estimated and qualified after their scope is defined.

### API-01 contract sketch, not an implemented API

Prefer alignment with the existing [Phase 2 auth API design](../../../docs/integration-auth-sdk.md#9-apis-and-pages-phase-2): a member-readable `GET /v1/me/connections` projection rather than granting access to admin endpoints. A proposed `GET /v1/me/task-catalog` would expose admitted task templates. Final routes, DTO names and compatibility/version policy belong in the ADR.

Connection summaries need stable opaque identity, allowed display metadata, ownership/acting-identity description when disclosable, permitted scope summary, available capabilities, revision and observation time. Configuration status and observed health must be separate; absent checks mean unknown. Icons require a host-controlled delivery policy, not automatic requests to arbitrary manifest URLs. Do not return credential material or hidden tenant connections to explain missing access.

Catalog entries need stable template identity, title/description, supported input intent, current availability/reason and required capabilities. These templates assist task entry; the server resolves bindings/connections and authorizes all actions again at execution. A template does not let the model select credentials. Neither endpoint performs provider-side health probes as a side effect of rendering; provider reads, if later requested, go through authorization and the action gateway.

Use generated wire types at L2; add bounded runtime validation and pure view-model mapping at the client/core boundary. Do not hand-maintain a second DTO schema in JSX. Server read models assemble admitted metadata through public application services; domain logic stays out of HTTP handlers.

## 6. Interaction and accessibility acceptance

| Area | Required behavior |
|---|---|
| Start/resume | Task entry retains draft after failed submission. Existing idempotency and active-run navigation protection remain intact. Reload/session behavior is accurately described. |
| Review | Complete exact material terms, changed values, identity/scope and rule findings precede confirmation. New revision resets review. Composer Enter, IME composition and layout switching cannot approve. |
| Status | Separate stream connectivity, task state, connection availability, committed effect and verified outcome. Use explicit unknown/unavailable language. |
| Context | Sources show only known provenance/freshness and authorized links. Long identifiers and missing evidence remain readable. No remote images or untrusted HTML from model output. |
| Overlay | Minimize/reopen preserves active run and in-memory draft. A pending decision can reveal the surface without confirming it. Escape backs out of confirmation before closing; focus returns to the trigger. |
| Responsive | Test 320 CSS-pixel width, 390×844 mobile and a narrow embedded container on a wide page. Sticky composer/review controls cannot cover focused terms or actions. Test zoom and a real mobile keyboard. |
| Accessibility | WCAG 2.2 AA target, semantic landmarks/headings, accessible control names, visible focus and non-color status. Aim for 44px comfortable controls; AA minimum target size is 24px or its specified spacing/exceptions. |
| Streaming | Announce meaningful state changes, not every token. Auto-follow only when the reader is near the end; offer “Jump to latest” after they scroll away. No artificial progress percentages. |
| Localization | All UI copy in existing EN/VI catalogs, locale-aware formatting, long translated labels, exact canonical values retained where approval requires them. |

Run small formative sessions with users from more than one business function. Ask them to start/resume work, explain the approved effect and actor, distinguish unknown from verified, inspect sources and recover without repeating a write. Record observations and blockers; a small study is not enterprise-readiness proof.

## 7. Verification and rollout

Use the repository's current commands from its root:

```bash
pnpm --dir ui check
pnpm --dir ui conformance
```

When contracts or token sources change, regenerate with `pnpm --dir ui gen`; follow the existing OpenAPI export workflow for server DTO changes. CI runs `pnpm --dir ui gen:check`. That command compares generated output with Git, so an already-dirty generated tree is not evidence of a regression. Review the intended generated diff and check a clean candidate. FE-00 adds formatting checks; do not claim those scripts already exist.

Add meaningful tests at the changed boundary:

- Vitest for new selectors, missing/malformed metadata, valid preference precedence, route parsing and command/state transitions. React component tests use the existing happy-dom support explicitly; the global test default is Node.
- Conformance for all approval-capable hosts, including adding docked mode to the shared target coverage. Keep the vanilla reference to detect accidental React dependence in core.
- Browser checks for focus and scrolling, Shadow DOM under hostile host CSS, multiple overlay instances, stream reconnect, unknown result, navigation/draft retention, EN/VI, reduced motion and theme contrast. Core safety scenarios cover every approval surface; visual combinations use a documented risk-based matrix rather than testing every possible cross-product.
- Reviewed screenshots of idle, gathering, review, stale review, verified, blocked and unknown states where real fixtures support them. Keep deterministic evidence separate from live system evidence. Automated accessibility checks supplement manual keyboard and screen-reader checks.
- Profile a representative long conversation and stream before adding subscription optimization or virtualization. Avoid remounting the controller; lazy-load only heavy secondary inspectors if measurements justify it. Approval content stays readily inspectable.

Delivery A can use a temporary build/host presentation switch to select old/new composition over the **same** controller and server contracts. The switch must not choose an execution, policy or approval path. Delivery B hides unsupported navigation when discovery APIs are absent, with typed handling of unsupported responses. Rolling back presentation must neither replay a command nor alter recorded task state.

## 8. Definition of done and handoff

A delivery is complete when its scoped views use real supported contracts; public exports/slots remain compatible; changed components have documented states and reuse examples; required UI checks pass; desktop/mobile/shadow-root behavior is reviewed; and README plus implementation notes describe the actual enabled behavior. The handoff names failed/skipped checks and remaining backend or live qualification work.

The mockup's wider integrations, durable inbox, proposal editing, administrative connection flows, delegated OAuth and cross-origin embedding remain unimplemented until their respective work lands. Applying this design must not change the current live-release readiness claim.
