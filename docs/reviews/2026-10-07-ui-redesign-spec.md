# UI redesign specification for the bounded MVP

Date: 2026-10-07. Status: **proposed follow-up**, not implemented or an accepted baseline change. Based on the [component/UI review](2026-10-07-layer-component-ui-review.md). Preserve ADRs 0006/0007/0011/0014, exact approval and independent verification. Any new public presentation/acceptance contract requires an ADR and synchronized OpenAPI/client changes.

## Product direction

Build a focused task workspace: the user states a task, sees understandable progress, reviews one exact decision and receives a verified result. The default view answers four questions: what is happening, what the agent found, what needs my decision, and what was actually verified.

Technical records remain inspectable through an activity/evidence inspector. The primary surface uses business language and authoritative structured data. Provider names and resource labels come from admitted server metadata, never hard-coded UI identifiers. Final model prose is supplementary; it does not authorize or certify an outcome.

## Full-page composition

Use a centered readable task/conversation area and an optional contextual inspector. A compact navigation rail contains New task and reachable recent/unfinished tasks; keep the initial implementation bounded to current-session tasks plus a supported server resume/list API. Do not build an unrestricted conversation-history product or admin console.

```text
┌──────────────────────────────────────────────────────────────────────┐
│ e-agent     Restock Widget A          Review needed          Settings │
├──────────────┬────────────────────────────────┬──────────────────────┤
│ New task     │ User request                   │ Task details         │
│              │                                │ Sources · Checks     │
│ Recent tasks │ Checked demand and stock.      │                      │
│ • Restock…   │ 7 units are needed.            │ Demand    12 units   │
│ • Late…      │                                │ Available  5 units   │
│              │ ┌ Review draft purchase order┐ │ Scope / observed time│
│ Unfinished   │ │ Supplier  Approved Co      │ │                      │
│ • Review…    │ │ Product   Widget A         │ │ View source evidence │
│              │ │ Quantity  7 units          │ │                      │
│              │ │ Subtotal  700 VND          │ │ Activity details     │
│              │ │ Requested 20 Oct 2026      │ │                      │
│              │ │ See all exact fields       │ │                      │
│              │ │ [Review and approve]       │ │                      │
│              │ │ [Reject proposal]          │ │                      │
│              │ └────────────────────────────┘ │                      │
│              │ [Ask a question / task input]  │                      │
└──────────────┴────────────────────────────────┴──────────────────────┘
```

Values above are synthetic examples. The entire exact field set must be accessible during review, with human-readable names and stable references. A compact summary must not hide material terms or allow confirmation before the review surface is available. UI cards are host-rendered components; the model cannot generate an approval interface.

## Screen and state requirements

| State | Primary content | Permitted action and behavior |
|---|---|---|
| Empty | Clear purpose, task input, a few safe task examples | Start a task. Examples come from admitted task metadata; do not promise unsupported work. Hide empty approval/evidence/audit panels. |
| Starting / reading | Echo request, brief progress such as “Checking availability” | Stop if safe; preserve draft on request failure. No fabricated progress percentages. |
| Clarification | Question in the transcript, answer input with “Send answer” | Resume same run. Retain prior questions/user answers; separate new-task action. |
| Validation blocked | Specific business issue and source/check details | Agent repair or clarification within budget; no approval of FAIL/UNKNOWN/ERROR. |
| Waiting approval | Readable exact decision, scope, expected effect, source/check availability and expiry | Review → explicit confirm; reject separate. No silent field truncation or automatic approval. |
| Confirming | Same reviewed proposal plus effect-specific confirmation | Separate user action, exact identity/revision/digest. New revision interrupts confirmation and requires review again. |
| Approved / dispatching | “Approval recorded” then actual operation phase | Prevent extra decisions. Stop text explains possible committed effects; never imply rollback. |
| Verifying | “Operation completed; checking the result” only when COMMITTED is known | Do not use success language until independent checks pass. |
| Verified result | Created object/structured answer, scope/as-of, completed checks | View details/evidence; new task. Decision collapses into history. |
| Failed | Specific failure, what is known about effects, safe next step | Retry only when host establishes eligibility. Preserve context and user input. |
| Unresolved | “The result is not confirmed”; known effect/receipt state | Host-authorized check status/reconcile; no generic replay button. Keep task reachable. |
| Cancelled / rejected | Accurate stopped/rejected result and any known effects | New task if appropriate. Navigation away never counts as stop/rejection. |
| Disconnected | Visible connection notice while keeping last authoritative state | Automatic read-only reconnect; no duplicate admission/decision; preserve draft and review state safely. |

## Approval review

Business title and action-specific confirmation come from trusted presentation metadata, for example “Review draft purchase order” and “Approve draft creation.” Keep universal confirmation fallback for capabilities without metadata; do not infer effect from a model sentence.

The review exposes product/supplier/customer/contact names with reference details, exact quantities and units, money with currency and explicit subtotal basis, requested dates, scope/connection and acting identity. More technical binding/digest/version information is available through Details. No secret appears.

For creation, use grouped label/value details; omit the empty previous-value column. For amendment, show **Current → Proposed** from authorized baseline facts and separately expose **Previous proposal → Revised proposal** when the agent repaired something. Unknown baselines are stated as unknown; the renderer cannot invent prior values.

Checks show concise business outcomes with expandable rule IDs, versions, expected/observed values and evidence. Preserve separate PASS/FAIL/UNKNOWN/ERROR semantics. Passing rules do not grant approval.

A mismatch between displayed values and canonical proposal disables approval. New action/digest/revision invalidates review. Expiry clearly states the remaining eligible time and the host-supported next step; no client-only renewal. Confirm remains an explicit second action and retains exact server revalidation.

## Results, activity and evidence

Verified result cards use `OutcomeReport` and authorized read-back data, including external reference, material values, independent checks and provenance. Read tasks show meaningful stock/offer/order/invoice summaries with scope and as-of. Money totals stay separated by currency. Never use model text to choose a resource link, populate verified fields or declare completion.

Activity shows a short sequence of user-relevant milestones. “Technical activity” retains complete event ordering and implementation details. Source evidence is available during approval review, not only after completion: source/reference, observation time, revision/digest and explicit freshness/completeness. Downloads retain the complete authorized redacted audit bundle. Evidence inspector and raw export are different presentations of the same authoritative records.

## Mobile, sidebar and overlay

- Full-page mobile: one primary column; compact task header; contextual details open in a sheet. Approval gets a dedicated review sheet with all exact fields and a reachable action bar. Avoid a three-column table on a narrow screen.
- Overlay: compact conversation/task view with a review badge; dedicated review/detail navigation, predictable close/open and scroll position. Closing never cancels. Overlay messages do not require scrolling past a full audit list to answer a question.
- Sidebar: shared semantic components with task/details navigation appropriate to width. It is not simply the desktop grid squeezed into a strip.
- Keep same-origin authentication for MVP. Cross-origin/OIDC/system-specific hosts remain outside scope.
- Tab/focus order follows visual reading order. Focus returns to the invoking control after a sheet closes. Do not auto-focus the confirmation button. Use unique instance IDs for mounts and correct nonmodal/modal semantics.

At 390×844 and 200% zoom, required fields/actions must be reachable without horizontal scrolling, clipped controls or nested scroll traps. A fixed footer may not obscure the final rows. Respect reduced motion and announce semantic state changes; do not reread a whole streaming paragraph on every token.

## Presentation data and ownership

| Data | Owner | Required boundary |
|---|---|---|
| Task acceptance and allowed completion branches | Domain/application definition, admitted by host | Portable specification consumed by kernel; model cannot redefine it. |
| Canonical action/digest/approval state | Kernel | Existing normalized records remain authoritative. |
| Field labels, kinds, grouping, units and business titles | Domain presentation metadata | Versioned admitted schema; never an independent UI rules engine. |
| Resource names/provider connection display | Authorized provider observations and admitted manifests | Non-secret; name plus exact scoped reference; no unrestricted extra reads. |
| Current amendment baseline | Host-retained approved observations | Same facts used by freshness/verification; unknown stays unknown. |
| Structured outcome and evidence | Host verifier/evidence services | Authoritative typed BFF projection; no generated model success claims. |
| Display formatting/status/interaction state | Shared UI core | Exact string decimals, locale, safe links, version checks and review identity. |
| Visual composition/focus/theme | Components/layouts/hosts | May change appearance; cannot weaken approval or scope checks. |

Implement a narrow renderer metadata vocabulary for existing eight tasks. Avoid a generic workflow/form engine, arbitrary renderer code loaded from plugins, or model-generated UI. Generate OpenAPI/TypeScript together and test presentation/canonical consistency.

## Work packages and acceptance

| Package | Changes | Completion evidence |
|---|---|---|
| UX-00 Integrity prerequisites | LC-01/02/06 plus AR-01/02 | Missing rules/display drift/unknown event versions fail safely; incomplete task cannot succeed; ledger recovery independent of driver. |
| UX-01 Presentation contracts | LC-07/09, immutable provenance AR-05 | Admitted display metadata, baseline diffs, typed result/source projections; unchanged exact approval digest semantics; generated client current. |
| UX-02 Headless interaction | LC-03/04/05 | Typed submission result, retained draft and stable retry key; same-run clarification/history; accurate derived task/decision/outcome state. |
| UX-03 Primary components | Task header/input/transcript/decision/result/activity/evidence | State matrix above implemented with human-readable copy and all exact fields inspectable; operator details secondary. |
| UX-04 Layouts and themes | Full page, mobile, sidebar, overlay | Same core/components; supported slots/config; visually reviewed desktop/mobile/zoom/light/dark; Shadow-DOM behavior intact. |
| UX-05 Qualification | Replace/extend conformance with task journeys and presentation safety | All three hosts pass; no unsafe/repeated effects; required fields/focus/reconnect/error scenarios verified; owner live trials still separate. |

Add meaningful regressions for the reproduced counterexamples; screenshot comparison alone cannot verify authority or recovery. Use deterministic Playwright/fixture runs for mechanism/UI checks, then integrated local model + persistent API + exact approved sandbox with human decisions for live claims. Test accepted-response loss, stale review, rejected proposal, ambiguous dispatch, verification failure, clarification transcript and reload/switching tasks.

Review the finished screens against the state matrix with another operator. Record whether they can explain the proposed action, find its source, identify the outcome and recover from interruption. Do not equate aesthetic improvements, test counts or three successful live examples with enterprise readiness.
