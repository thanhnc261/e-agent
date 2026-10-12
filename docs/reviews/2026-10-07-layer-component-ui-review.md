# Layer, component and UI/UX review

Date: 2026-10-07. Candidate: current uncommitted remediation working tree, baseline `3ae9aafb13b112a207ea6474c006e74a3dc157d2`. This extends the [architecture alignment review](2026-10-07-architecture-alignment-review.md), preserving its AR-01–08 findings. Review authority: HLD, MVP detailed design, implementation plan, UI architecture, integration designs and accepted ADRs 0001–0014.

## Assessment

**Keep the package/layer architecture. Substantially redesign the product presentation and complete the missing host invariants.** The current UI implements a useful conformance fixture, but presents low-level execution records directly to a business user. Its weak hierarchy, fragmented workflow and misleading state messages are observable problems, not just a preference about colors. Passing the existing safety conformance tests does not demonstrate a usable MVP.

Two additional high-priority integrity findings emerged: the validation adapter can report unevaluated rules as passing, and approval display values are not checked against the canonical arguments. The eight-task domain implementation and the layered UI do not need to be discarded.

## New findings, ordered by importance

### LC-01 — P1: missing executable shapes can become PASS

Location: `packages/adapter-shacl/src/e_agent/adapters/shacl/engine.py:86`, especially the loop over `dataset.expected_rules` after validation; `packages/plugin-sdk/src/e_agent/sdk/validation.py:43`; procurement dataset builder's separately declared `SHACL_RULES`.

The engine assigns PASS to any expected rule without a reported violation when `dataset.complete` is true. It does not establish that the expected rule exists in the loaded shape graph or targets the proposal. Completeness describes available facts; it does not prove rule execution.

**Reproduced:** build a real procurement dataset with quantity `0` and subtotal `0`. With the packaged shapes, status is FAIL. With the dataset's `shapes` tuple empty, status is PASS, including “PR-004: satisfied.” No source asset was changed and no write was sent. Current packaged shapes reject the invalid proposal; this finding concerns a missing host check when a dataset/asset binding is incorrect.

Fix: validate the domain inventory's engine-specific coverage against the admitted shape assets, rule IDs/versions and required proposal targets before activation/evaluation. Reject absent/empty shape bindings for a shape-enforced contract. Require explicit applicable target/focus coverage for the bounded dataset. Report ERROR/UNKNOWN when evaluation coverage cannot be established. Never infer execution from absence of violations. Keep domain semantics in domain resources and SHACL execution in the adapter.

Acceptance: remove an expected rule, remove its target, bind an empty graph or drift its version; validation blocks and never says “satisfied.” Current positive, negative and missing-fact scenarios still behave correctly.

### LC-02 — P1: the human-visible approval can disagree with the checked proposal

Location: `ui/packages/ui-core/src/controller.ts:251` checks the digest of `canonical_proposal`; `ui/packages/components/src/index.tsx:184` renders separate `material_fields`. Python presentation generation is in `packages/kernel/src/e_agent/kernel/approval.py:100`.

**Reproduced with a synthetic API response:** canonical quantity `40`, valid digest, displayed quantity `999999`. The UI renders `999,999` and enables “Approve.” Existing conformance tests tamper with canonical arguments, but do not tamper with the presentation values while retaining a valid canonical digest.

The current server derives fields from arguments correctly for existing flat commands. This is a missing display-integrity check, not proof that an attacker can alter the server's response today. The human must nevertheless review the same normalized action that the command approves.

Fix: derive review values from canonical arguments through a shared, versioned renderer, or verify exact complete path/value correspondence before enabling approval. Separately validate that presentation metadata targets the same action/contract/connection as the canonical envelope. Label/format metadata must not substitute another value, omit material fields or alter decimals. Keep canonical arguments and the approval digest unchanged by cosmetic formatting.

Acceptance: mismatched, omitted, duplicated and extra fields; nested paths and nulls; metadata mismatch; locale formatting; all three UI hosts. Safe failures visibly explain that approval details could not be validated.

### LC-03 — P2: starting another task hides an unfinished run

Location: controller `start`/`attach`, `ui/packages/ui-core/src/controller.ts:126`; single `storageKey`; composer and hosts.

`busy` covers only a command request, not the active run. While waiting for approval, the composer can create another run. `attach` replaces the only remembered run ID, messages, approval and stream. There is no default history/switcher control.

**Reproduced:** first run remains `WAITING_APPROVAL` on the server after the second becomes the only visible/remembered run. There are zero history controls. It was not cancelled and cannot be reached through the default screen after replacement.

Fix: explicitly separate “answer this task,” “new task” and “switch task.” For MVP, retain one visible active task and expose a compact task list/resume affordance before supporting concurrency. Never infer cancellation from navigation; keep unfinished task IDs reachable and scope remembered IDs to server/session identity.

Acceptance: new task during approval, running, verification and reconciliation; reload; switching away/back; overlay close/open; no unintended extra runs.

### LC-04 — P2: failed submission destroys the user's draft; retry has unstable identity

Location: composer `ui/packages/components/src/index.tsx:66`; controller `start` catches errors then resolves; a fresh key is generated at line 137 on each attempt.

**Reproduced:** abort a submission request. UI displays `TypeError: Failed to fetch`, and the entered task becomes empty because `submit(...).then(() => setTask(""))` runs after the controller swallowed the error.

A separate source-observed risk: if the server admitted the run but its response was lost, manually retrying generates another idempotency key. The server's same-key safeguard cannot recognize that logical retry. This accepted-response-loss case was not executed in this review.

Fix: return a typed submission result or propagate a handled error to the component. Clear the draft only after confirmed admission. Persist the pending request's key/payload until its outcome is resolved; reuse that key for transport retries. Surface action-specific retry/help text without technical exception names. Clarification responses use the same run and need an “Answer” label.

Acceptance: failed request retains text, lost admitted response resolves to the same run, changed task creates a new request identity, clarification never creates another run or approval.

### LC-05 — P2: outcome wording is false in several states

Locations: `ui/packages/ui-core/src/i18n.ts`, `store.ts:149`, `approval.ts:70`, components' approved status.

**Reproduced:** `outcome.reported` with status UNKNOWN renders “Outcome verified · UNKNOWN.” That label is unconditional. After a real fixture run succeeds, the approval card still says “Approved. Waiting for the outcome.” `CLEARED` deliberately retains approved/rejected phases, but the component does not reconcile decision history with task completion.

Fix: derive a user-facing status from run/action/outcome together. Distinguish approval recorded, operation committed, outcome checking, verified, failed and unresolved. Keep prior decision as a compact audit item; remove obsolete waiting/expiry copy. UNKNOWN must never carry verified language or a success icon.

Acceptance: FAILED/UNKNOWN/VERIFIED outcomes; approved then verifying/succeeded/failed; rejection; expired/stale; cancel before and after dispatch; reconnect and reload show the same truth.

### LC-06 — P2: unknown event schema versions are interpreted as current

Location: `ui/packages/ui-core/src/store.ts:79`; client `stream` casts JSON; `RunEvent.payload` is an untyped mapping in Python contracts and generated TS.

**Reproduced:** a known `run.state_changed` type with `schema_version="999"` changes the displayed state to SUCCEEDED and does not request a snapshot. Unknown types are handled, but unknown versions are ignored.

Fix: validate event envelopes and known version/type payloads at the client/core boundary. Quarantine unsupported versions, preserve the cursor deliberately and request a compatible authoritative snapshot. Add typed payload DTOs/discriminated event fixtures for supported events so generated contracts constrain interpretation. Do not let model/provider data masquerade as a state transition.

Acceptance: unsupported version of a known type, malformed enum/payload, mixed replay versions, unknown type; no guessed success, crash or replay loop.

### LC-07 — P2: approval lacks a business-readable presentation contract

Location: kernel `MaterialField`/`ApprovalPresentation`; components approval table; formatter's field-name regex. UI design §4.2 specifies display metadata and label keys, but the actual DTO has only paths/string values and technical IDs.

Users must decipher `procurement.purchase-order.create-draft.v1`, `supplier:approved-co`, `requested_date`, and a credential-subject string. The table allocates a blank “Previously” column even for a new object. There is no decision summary, unit-aware money/quantity presentation, readable resource name or clear statement of what will happen. “Approve…” does not name its effect.

For amendments, `previous_value` is based on the superseded proposal, not the current authorized ERP baseline. That can explain an agent repair but does not show the actual before/after business change.

Fix: a host-owned, provider-neutral presentation projection with capability/action display labels, resource name plus stable reference, field label/kind/unit/currency, expected effect, current baseline for amendments, and distinct proposal-revision diff. Domain packs supply business vocabulary; adapters supply authorized resource labels; bootstrap/application presentation composes them. HTTP handlers must not acquire ERP rules; UI must not infer provider behavior or approved facts from the model.

Acceptance: create and amendment show exact normalized material values; current-state versus repaired-proposal comparisons are clearly different; missing labels fall back honestly to references; every material field remains inspectable before approval.

### LC-08 — P2: hierarchy and responsive behavior obstruct the task

Locations: `ui/packages/layouts/src/index.tsx`, `layouts.css`, components and token styles; screenshots in review evidence.

Desktop uses three permanent columns with equal-weight panels, including empty Approval/Evidence/Timeline. The empty approval panel has the most prominent blue border. Conversation and task entry are small and detached from the central decision. A verbose audit list dominates the page after completion.

On a 390×844 viewport, the approval button's measured document position is **y=1069px**. Raw names split across lines (`requested_date`, resource refs), the empty previous-value column consumes scarce space, and the verified outcome appears after the long approval and audit sections. Horizontal overflow avoidance alone does not make that usable.

Fix: one primary task/conversation surface, a contextual decision/result card, and progressive disclosure for activity/evidence. Make approval review a dedicated mobile sheet with an accessible fixed action area and scrollable complete details; never overlap or truncate required fields. Collapse completed proposals and put the verified result first. Full page, sidebar and overlay share semantic components but use appropriate navigation/scroll containment.

Acceptance: mobile 390px, desktop, overlay and sidebar; 200% zoom; long English/Vietnamese; all decision fields and actions reachable; no nested scroll trap or misleading empty prominence.

### LC-09 — P2: result/evidence surfaces expose diagnostics instead of supporting decisions

Locations: `OutcomePanel`, `EvidencePanel`, `Timeline`; API `RunSnapshot` (`apps/server/src/e_agent/server/api.py:103`).

Outcome shows technical state/capability lists rather than a structured created object or answer. Evidence becomes a raw JSON `<pre>` and is offered only after terminal/unresolved states. A user reviewing approval cannot inspect a normal source-evidence view. Snapshot actions include arguments but do not provide a rich independently verified outcome/check/resource presentation. Most structured evidence is in events/export, so the UI would otherwise have to reconstruct business meaning from generic dictionaries.

Fix: server-owned outcome/evidence projections separate from raw audit export. Show scope/source/freshness/completeness and the relevant validation evidence during review. Show verified resource/reference and acceptance checks after completion; retain full JSON as an operator download. Links, if available, must be authorized and explicitly sanitized; no model-generated URL grants access.

Acceptance: inspect source facts before approval, understand failed/unknown checks, copy/export safe evidence, distinguish stale/partial/missing facts, no secrets/remote images/raw hidden reasoning.

### LC-10 — P3: UI customization and accessibility claims exceed current coverage

Layouts support preset/visibility/side, not designed slot ordering; sidebar uses a stack, not tabs; overlay approval/evidence are inline, not the specified modal/drawer. Only a panel styling part exists. The React Aria shadow behavior uses a private import, a known upgrade coupling. Token tests check contrast and distinct hex values; distinct values do not establish perceptual distinguishability. Screen-reader behavior, reduced motion, zoom and realistic long-task/mobile flows are not established by current browser assertions.

Fix: document a bounded supported customization API, finish needed slot/part/navigation affordances and maintain a shadow-DOM upgrade test. Use text/icons in addition to color. Add focused keyboard/screen-reader/zoom/responsive review, meaningful accessible names, unique IDs per mounted instance and restrained streaming announcements. Do not claim a full accessibility standard certification from the present checks.

## Backend layer and component audit

### Contracts distribution

Portable `Record`, decimal strings, UTC dates, identities, capability/binding/connection, run/action/receipt/outcome and work claims form a sound boundary. Unknown fields are rejected; vendor/framework/ORM objects stay outside. Approved facts are opaque portable data owned by the host. Keep this foundation.

Gaps: generic event payload dictionaries do not provide the designed typed event catalog (LC-06); immutable execution inventory and task acceptance specification are missing (AR-01/05). Proposal display records currently live in kernel and are generated into OpenAPI; that can remain host-owned, but their versioned presentation semantics need to be explicit before adding richer summaries. Add only the contracts required by concrete fixes, not a universal business-object schema.

### Plugin SDK

Driver steps distinguish reads, proposals, questions and final text. Verifiers receive only `ScopedReader`; executors receive an admitted action; scoped credentials avoid an unrestricted service locator. Store methods express atomic business operations. Validation datasets carry library-neutral statements/resource refs. These boundaries align with HLD §6 and MVP §5.

Gaps: continuation snapshot/restore/token reporting/text-sink hooks are used via `getattr` rather than explicit optional typed capabilities. Type the concrete persistence/usage seam when addressing AR-02, including incompatible continuation errors. `PluginServices.credentials` and dataset-builder contributions use `Any`; narrow these where the implemented use is known. Manifest declarations need host enforcement (AR-03/04). Do not add unused lifecycle classes; add bounded setup/cleanup only to implemented resources.

### Kernel registry, connection catalog and policy

Registry rejects duplicate/conflicting definitions, checks artifact identity before factory import, and refuses ambiguous routing. Connection catalog enforces tenant, active state, scope and delegated ownership; default policy requires requester scope and explicit approval for writes. Surface digests support stale-approval rejection.

Required changes: semantic admission/feature routing (AR-03/04). Current connections live in profile-backed memory; PostgreSQL migrations do not contain the connection/credential metadata tables promised in integration design MVP seams. For the single-operator local profile this is a bounded configuration choice, but it is a design deviation to resolve explicitly. Do not describe an audited persistent integration registry as implemented. Future credential/admin updates need a distinct owner and atomic metadata audit, not mutable in-memory catalogs shared ad hoc with handlers.

### Kernel coordinator and gateway

Authorization, reads, validation, approval freshness, reservation, dispatch, receipt, verification, cancellation and recovery remain centralized in the trusted host. Reads and verifier reads use the same gateway. Required dispatch evidence precedes writes; external ambiguity remains UNKNOWN. This is the appropriate trust boundary.

Required changes: whole-task completion and framework-independent recovery (AR-01/02); richer exact approval presentation (LC-02/07). The 1,506-line coordinator concentrates several responsibilities, making shared invariants easy to omit in alternative paths. Extract cohesive internal approval/admission, effect/reconciliation and completion operations while fixing behavior, with one authoritative state-transition path. Keep them inside kernel and keep domain rules outside. Line count alone is not a reason to introduce services or abstractions.

### Kernel approval, credentials and evidence

Canonical digest binds normalized action/scope, semantic versions, authority, source revisions/fact digests and credential revision. Credentials resolve at invocation and reject rotation. Mandatory ledger evidence is separate from optional telemetry. These are strengths.

Required changes: distinguish actual-state amendment diff from repaired-proposal diff (LC-07), verify human-visible correspondence (LC-02), freeze execution provenance (AR-05), and provide authorized evidence projections (LC-09). Define retention for framework continuation and evidence; do not imply exporting full JSON is a retention policy.

### PostgreSQL and memory stores

The public store defines admission, waiting approval, approval/action, reservation, receipt/outcome and continuation/work transactions. PostgreSQL uses compare-and-swap, parent-run locks, work leases/fencing and notifications with short transactions. Per-connection writer locking does not claim external exactly-once. Memory store provides deterministic conformance behavior. Prior real process-death/PG evidence remains relevant; no PG service was started in this review.

Source gaps/limits: no persistent connection metadata or retention/pagination policy; session advisory-lock use needs capacity awareness when a pool has multiple external calls. SSE presently polls events every 200ms even though the store publishes notifications. That is acceptable for one local client but should be declared instead of implying notification-driven streaming. Event paging/cursor expiration becomes necessary before retention or large histories are introduced. Do not widen the MVP to HA/production multitenancy to solve a local usability problem.

### Pydantic AI adapter and local model boundary

The adapter maps deferred tool calls to host requests/proposals, holds framework continuation, strips reasoning and tool/provider details, emits narrow public text and accounts for usage. Reads are also deferred, a documented stricter version of ADR 0004. Ollama selection and no cloud fallback preserve scope.

Required changes: typed optional continuation/usage capabilities and framework-independent recovery (AR-02); immutable model/configuration fingerprint (AR-05). Qualification traces do not establish UI human approval behavior. The model's final text should never be the primary business outcome card; that card comes from independent verifier records. Prompts remain explanatory rather than enforcement.

### ERP domain pack and its task components

| Component | Current boundary | Remaining concern |
|---|---|---|
| Inventory availability | Typed quantity/unit observations used by shortage verifier | Present stock/shortage with scope/freshness; no implication of stock reservation. |
| Procurement normalization/validation | Constructs facts/dataset; packaged inventory and shapes enforce positive quantity, reference/offer/budget/date bounds | Engine coverage LC-01; keep any human-readable rule descriptions sourced from this inventory. |
| Shortage answer | Recomputes demand/current stock/inbound through authorized reads | Verified availability can be intermediate; task completion AR-01. |
| Offer recommendation | Recomputes eligible choice from independent demand/stock/offers | Same completion distinction; present eligible options/evidence without another UI rule implementation. |
| Draft PO verifier | Checks resulting order, material fields, draft state, single line and correlation | Source code/fixture proof does not prove installed Odoo mapping; integrate structured result presentation. |
| Draft RFQ amendment | Optimistic source revision; retained host baseline verifies unchanged fields | Approval needs baseline business diff, not only revision/blocked-proposal difference (LC-07). |
| Customer quotation | Public DTO/dataset/shape/verifier; draft only | Display customer/product, units, currency and effect; no confirmation/email promise. |
| Late sales orders | Domain-defined as-of semantics and independent exact result set | Provide date/count/list in a verified answer card; retain incomplete-list negative tests. |
| CRM lead | Contact/team/owner/source validation and independent lead read-back | Present authorized contact/team/owner names plus refs; future contact consent/production workflows are not implied. |
| Overdue invoices | Domain recomputes posted unpaid overdue set/totals per currency | Show as-of and currency-separated totals; never aggregate unlike currencies or imply payment/posting. |

All five bounded contexts use public contracts/SDK, with concrete provider mapping outside. Preserve that separation. Full semantic migration, multidomain effectiveness and governed knowledge ingestion remain beyond this slice.

### SHACL adapter

RDF conversion and pySHACL belong here; resource loading is independent of cwd and the adapter does not import ERP implementation code. LC-01 is a correctness gap in execution coverage. Findings also commonly contain no source-evidence references, and PASS uses version `1` rather than deriving the evaluated rule version; connect canonical findings to admitted inventory/version/evidence without exposing RDF objects.

Source-observed scheduling risk: async `validate` immediately runs synchronous pySHACL work. The surrounding `asyncio.timeout` cannot preempt CPU work blocking the event loop, which can also delay text streaming and lease renewal. Current small fixture latency does not demonstrate a failure. Bound dataset size and run CPU validation in an appropriate controlled worker/thread strategy; if hard interruption is required, a cancellable process is needed. Treat this as an adapter execution concern, not a new platform service requirement.

### Odoo adapter and Odoo addon

Client chooses narrow JSON-2 methods, target context and credential placement; executor maps public domain DTOs, returns completeness/revisions and handles receipt/reconciliation identity. The addon owns ERP transaction-local operation uniqueness, exact target checks and bounded business changes. Fixture ownership/reset uses a separate admin-only inventory; normal business operations preserve user permissions.

This split is justified: the client cannot atomically combine multiple ERP RPCs with its local ledger. Keep provider-specific company/marker/ORM behavior in the addon/adapter. Remaining evidence gates are installed bytes/version, ORM ACLs/company rules, race/lost-response semantics and owned seed/reset on the exact allowed owner sandbox. Do not describe source/AST/mock checks as live proof.

### Local secret store

Envelope encryption, reference-bound authenticated data, non-secret revisions and expected-version reads satisfy the local credential boundary. Secret values do not enter normal profiles/driver/UI. The JSON file remains a single-process local storage choice: `_load`/`_save` has no multiprocess serialization and uses a fixed temporary path. Before admin or multiple writer processes are supported, add tested atomic concurrency and rotation/retention ownership or use an appropriate new adapter. No production vault/admin console is required to improve the current UI.

### Server bootstrap, API, worker and CLI

Bootstrap chooses concrete adapters/domain/provider implementations and an exact live sandbox target. Profile validation and local loopback/CSRF session handling preserve the scoped development boundary. API commands enter durable work; worker leases fence local writes; CLI is another host. Keep business semantics out of HTTP and CLI.

Required changes: current readiness/telemetry/provenance (AR-05/06/07), authoritative presentation projections for approval/results/evidence (LC-07/09), and structured command results for the UI (LC-04). `api.py` holds DTOs, local identity, text bus, scheduling, SSE and routing in one module; split by these existing responsibilities when modifying them. Keep composition and application presentation distinct from transport handlers. Production auth/cross-origin embedding remain deferred.

## UI architecture audit, layer by layer

| Layer | Keep | Change |
|---|---|---|
| L1 Application API | One host-authorized command/snapshot/SSE surface and exact `ApprovalPresentation` | Typed/versioned projections for display, outcomes/evidence and task list; authoritative facts, no model approval or domain rules in handlers. |
| L2 Generated client | Generated types, centralized auth/CSRF, event resume, injectable transports | Runtime payload/version validation; stable logical-request retry identity; safe typed errors; bounded retry policy. No rendering. |
| L3 Headless UI core | Shared reducer/controller, approval machine/digest, text sanitization, locale/decimal helpers | LC-02–06 invariants; typed submission outcomes; active-task navigation, conversation/input history, presentation selectors, resource-aware formatting from metadata. No business eligibility rules. |
| L4 Tokens | Semantic themes and contrast assertions | Stronger type/spacing/surface hierarchy and component states; responsive sizing; distinguish statuses using text/icons too. Theme alone cannot fix the workflow. |
| L5 React bindings | `useSyncExternalStore`, shared state, component override slots | Narrow hooks for task/status/decision/result/evidence; stable callback/selectors where measured; semantic slots for redesigned composition. UI-only draft/focus/overlay state may remain local. |
| L6 Components | React Aria controls and safe text nodes | Replace raw record panels with task header, transcript, decision card, result card, activity summary and evidence inspector. Meaningful loading/error/empty/action states. |
| L7 Layouts | Host-neutral presets and mandatory decision visibility | Task-focused full page; mobile review sheet; compact tabbed overlay/sidebar; configurable supported order and correct scroll/focus containment. |
| L8 Hosts | Same-origin app/overlay and vanilla conformance reference | Task URL/resume/navigation, identity-scoped storage, locale/theme controls, embed lifecycle; private shadow import upgrade check. No provider-specific system UI or permission assumptions. |

The existing 51-module dependency graph is a useful foundation. No React framework migration, third-party chat kit, desktop shell or system-specific embed is justified by these findings. The vanilla reference UI remains a compatibility fixture; it is not evidence of an attractive second product UI.

## UI component audit

| Current component | Concrete problem | Required replacement/behavior |
|---|---|---|
| Header / ConnectionStatus | Raw state plus stream “Live” confuses transport with business state; cancellation is undifferentiated | Task title, human-readable authoritative phase, discreet connection notice; state-aware stop wording. |
| Composer | Single-line input, no task context; erases failures; labels clarification as a new run | Autosizing task input; retain draft; explicit answer/new-task mode; keyboard help; no chat Enter approval. |
| Messages | One task, one current question and final string; no clarification transcript | Chronological authorized user/public-agent messages, timestamps only when useful, structured decision/result alongside conversation. No reasoning content. |
| ApprovalPanel | Raw IDs, path table, empty diff column, rule boilerplate, vague button | Exact business-readable decision summary, complete details, actual change diff, review/confirm actions, validation/source inspector. |
| Timeline | Every implementation event and full timestamp at equal weight | Short meaningful progress milestones; expandable full audit log retaining sequence and technical IDs. |
| OutcomePanel | Technical state/capabilities without usable resource/list/check result | Verifier-owned result with object reference, scope/as-of, checks and next permitted actions. Explicit unknown/failed states. |
| EvidencePanel | Post-run JSON only; no pre-approval source inspection | Human-readable authorized evidence drawer available during review; raw export secondary. |
| Footer | Empty | Optional operational context only when useful; no permanent decorative panel. |
| Layout / Overlay | Permanent grids/stacks, approval buried on mobile, repeated empty panels | Phase-aware primary surface and contextual inspector; reachable decision controls; keyboard focus and scroll return. |

## Verification and artifacts

Fresh review evidence: `evidence/architecture/20261007-layer-ui/`.

- Three Playwright Chromium **counterexample/capture cases passed**: actual fixture UI desktop/mobile/task replacement/submission failure; mocked UNKNOWN label; mocked approval display mismatch. Passing means the undesirable behavior was reproduced, not fixed. The first two use `playwright.log`; integrity case uses `display-integrity.log` and saved `display-integrity.spec.ts`.
- `pnpm --dir ui test`: **42 passed**, comprising the existing 41 tests plus one temporary event-version counterexample. Its source/output are retained as `event-version.test.ts`/`event-version.json`; temporary repository test files were removed.
- `validation-probe.py`/`.json`: invalid quantity fails with actual shapes but passes with no shape bindings. Fixture/read-only host operations only.
- Screenshots: `01-empty-desktop.png`, `02-approval-desktop.png`, `03-approval-mobile.png`, `04-completed-mobile.png`, `05-submit-error.png`, `06-display-mismatch.png`. Visually inspected empty/mobile/completed views.
- Prior same-session architecture checks: seven Python import contracts, 71 focused Python tests and UI boundary/neutrality checks passed. Full prior 317-test/47-browser/live-model evidence was not rerun here.

No product code changed. No owner Odoo/PG data or containers were accessed, no live model inference ran, and no baseline remediation archive was modified. The screenshot/test server used memory storage and synthetic ERP; mocked API probes are labeled above.

The [UI redesign specification](2026-10-07-ui-redesign-spec.md) translates this review into phase-specific screens, presentation contracts, work packages and acceptance criteria. Implement LC-01/02 and the earlier P1 host gaps before declaring the redesigned interface MVP-ready.
