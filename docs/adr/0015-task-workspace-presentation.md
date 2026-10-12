# ADR 0015: Task workspace and host-owned presentation metadata

Date: 2026-10-08. Status: **Accepted** (implementation decision within the owner's requested UI change).

## Context

The [layer/component review](../reviews/2026-10-07-layer-component-ui-review.md) reproduced lost drafts, hidden unfinished tasks, misleading status labels, unsupported event-version handling and unreadable approval/mobile surfaces. The [UI redesign specification](../reviews/2026-10-07-ui-redesign-spec.md) defines the product direction. ADR 0011's replaceable UI layers and ADRs 0006/0007's approval/event authority remain the baseline.

## Decision

- L3 owns submission admission/retry identity, current-session task navigation, conversation/status selectors and presentation integrity. L6 renders business review/result cards; L7 composes a navigation rail, task column and contextual inspectors. Overlay/sidebar reuse the same semantic components with bounded review scrolling. Inspectors use native disclosure controls, not a new drawer framework.
- Starting another task while a run is unfinished requires explicit New task navigation. Navigation retains at most 20 session-local task references and never cancels server work. Server snapshots remain authoritative. Session storage is scoped to API origin, tenant and principal; no server-wide task-list endpoint is added.
- Submission returns a boolean admission result. Failed admission retains the draft and a stable idempotency key; lost snapshot responses retain the admitted run ID. Same-run clarification uses the existing revision-checked input command. This does not authorize replay of external writes.
- Extend the server-owned `ApprovalPresentation` with `display_title`, `expected_effects`, and optional material-field `label`, `comparison` and `proposal_previous_value`. Titles/labels and field order come from the admitted input schema's existing title/property annotations/order. No provider identifiers or domain field lists are added to UI code. Generated OpenAPI/TypeScript change together.
- A concrete amendment seam uses domain schema annotation `x-presentation.baseline_reference`. Kernel presentation matches that argument to exactly one host-retained approved observation. `comparison=current` identifies the actual baseline; absent/ambiguous baselines remain unknown. `proposal_previous_value` separately retains a superseded proposal. Other actions preserve the original proposal comparison. These annotations do not alter validation, canonical action arguments or approval digest computation.
- UI core checks a complete, unique displayed argument set against canonical values, scope identifiers and expected effects, in addition to the digest. Supported values follow the bounded string/boolean/null/object profile; unsupported shapes fail closed. FAIL/UNKNOWN/ERROR findings disable approval. These are presentation/safety checks, not a duplicate domain rule inventory. The host still revalidates every command.
- Unknown event types **or schema versions** are retained as unsupported activity and trigger read-only snapshot recovery; their payloads never mutate conversation/outcome state.
- Verified result values come from a VERIFIED action correlated with its host outcome report. External record references come from the same action's COMMITTED receipt; observation evidence IDs are not mislabeled as business object references. Model text remains supplementary. Evidence is inspectable during review and can be refreshed/exported through the existing authorized endpoint.

## Alternatives considered

A cosmetic restyle would preserve the reproduced interaction/integrity problems. Provider-specific screens would violate neutrality and require parallel enforcement. A generic plugin renderer, task-history service or modal/drawer framework would exceed this concrete MVP use case.

## Consequences

Existing clients can ignore added response fields; new clients use regenerated contracts. The prior generic material-field/digest command remains authoritative. Browser history is bounded to the current session and does not claim cross-device or comprehensive unfinished-task recovery. Names unavailable in authorized observations remain exact references. The UI does not invent subtotals, resource names or progress percentages.

This change does **not** resolve the separate missing SHACL-shape failure, task completion acceptance, driver-independent recovery, immutable export provenance, plugin admission or readiness/telemetry findings. It does not establish live model/ERP qualification or enterprise readiness. See the [implementation handoff](../handoffs/2026-10-08-ui-redesign.md) for verification and remaining limits.

## Verification

Unit checks cover canonical/display drift, conflicting paths/scope, unsupported versions, retry identity across reload, admission-refresh failure, active-task protection, session identity, outcome correlation and actual-versus-proposal baseline. Playwright covers all three UI hosts, stale/expired approval, explicit keyboard confirmation, dropped streams, lost submission responses, history navigation, narrow review scrolling and themes/Shadow DOM. Real-kernel fixture journeys approve, reject and reload without duplicate effects. Opt-in screenshots support visual inspection; human usability and owner live qualification remain separate gates.
