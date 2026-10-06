# MVP implementation plan

**Date:** 2026-10-06. **Status:** actionable planning baseline; implementation has not started. User decisions are recorded in [ADR 0001](adr/0001-local-mvp-scope.md). Read with the [HLD](high-level-design.md) and [detailed design](mvp-detailed-design.md). ADRs 0002–0013 ([index](adr/README.md)) were accepted on 2026-10-06 (decisions D1–D5); D6/D7 remain open. §0 lists what must be decided before development starts; the [MVP readiness review](reviews/2026-10-06-mvp-readiness-review.md) records how this was checked. The scoped [threat model](threat-model.md) defines security tests used by I05–I09 and I12.

## 0. Readiness: decisions and Day-1 checklist

**Owner decisions (D).** D1–D5 were approved by the project owner on 2026-10-06; ADRs 0002–0013 and the toolchain baseline are accepted. D6 and D7 remain open.

| ID | Decision | Gates | Default if accepted as proposed |
|---|---|---|---|
| D1 | Accept/reject ADRs 0008 (observability) and the toolchain baseline below | I01 | OTel with content capture off; toolchain as listed |
| D2 | Accept/reject ADRs 0002, 0006, 0013 (contract parts) | I02 | Business-context capability IDs; JCS digest; `ownership`/`credential_subject` in contracts |
| D3 | Accept/reject ADRs 0003, 0004, 0009, 0010 | I03–I05 | Kernel-owned durability; deferred-only writes; rule engines; pass^k protocol |
| D4 | Accept/reject ADR 0005; permit adding `addons/e_agent_bridge` to the external `odoo19-learning` compose addons path and creating a dedicated integration user + API key there | I00 (user/API key), I06 | JSON-2 + transactional bridge |
| D5 | Accept/reject ADRs 0007, 0011, 0012 | I08 | SSE contract; layered system-neutral UI; schema-driven connections |
| D6 | BigQuery project/dataset/region/purpose and data permission | I12/I13 only | Synthetic data only until decided |
| D7 | ERP Bench exact repository/revision/licence | Optional input to I03 | I03 proceeds from Odoo 19 semantics without it |

Nothing else blocks the critical path through I09. D6/D7 never block I00–I11.

**Proposed toolchain baseline (confirm in I01; record exact versions in the lockfiles and README):**

| Area | Baseline |
|---|---|
| Python | 3.12+ (prefer latest stable supported by all dependencies), uv workspace, `uv_build` backend, ruff (lint/format), mypy with the Pydantic plugin (strict for contracts/kernel/SDK), pytest + pytest-asyncio, import-linter |
| Server | FastAPI + uvicorn; native `EventSourceResponse` for SSE; httpx for outbound HTTP |
| Persistence | PostgreSQL (separate instance or database/role from Odoo); psycopg 3; Alembic migrations owned by `adapter-postgres` |
| Agent | Pydantic AI 2.x (exact pin), Ollama via its OpenAI-compatible or native provider as qualified in I04 |
| Validation | pySHACL + rdflib (SHACL 1.1 + SHACL-SPARQL) |
| TypeScript | Node 24 LTS (or 26 once promoted to LTS), pnpm workspace, TypeScript, React 19, React Aria Components, Vite, Vitest, Playwright, ESLint + dependency-cruiser, openapi-typescript, Style Dictionary (DTCG tokens) |
| CI | GitHub Actions: Python and TS lint/type/test/build, PostgreSQL service container, wheel clean-install job; no live services or credentials |

**Day-1 local prerequisites (I00):** Docker with the `odoo19-learning` stack running; a separate PostgreSQL for e-agent; Ollama with candidate models pulled; uv and Node/pnpm installed; a dedicated Odoo integration user and API key created in the sandbox (D4) and stored outside the repository; sandbox marker record created in the Odoo DB.

**Milestones:**

| Milestone | Work packages | Demonstrates |
|---|---|---|
| M0 Ready | D1–D5, I00 | Decisions recorded; environment manifest |
| M1 Walking skeleton | I01, I02 | Fake driver + fake ERP + real kernel + CLI, CI green |
| M2 Safe core | I03, I04, I05 | Rules, durable approvals/recovery, qualified local model (rescope checkpoint) |
| M3 Live procurement slice | I06, I07 | The three required MVP demonstrations via CLI against the Odoo sandbox |
| M4 Live UI | I08, I09 | Same slice in standalone web app and embedded overlay; conformance suite |
| M5 Five tasks | I10 | ERP-01..05 |
| M6 MVP release | I11–I14 | Eight Odoo tasks (+ BigQuery if D6 decided), release qualification |

## 1. Confirmed choices and open inputs

| Item | Baseline |
|---|---|
| Machine | Current local development machine; local-first testing |
| Runtime/model | Pydantic AI 2.x (exact pin in I01) + Ollama first; no automatic cloud fallback; deferred-only writes and thinking hygiene per ADR 0004 |
| ERP | Odoo 19 `odoo19-learning`, independent of experiment; customization allowed |
| Scope | 5–10 common ERP tasks; proposed catalog below has eight Odoo tasks plus two BigQuery tasks |
| UI | Streaming overlay UI in MVP; small CLI uses the same services; layered default UI that can be re-themed, re-laid-out or replaced ([UI architecture](ui-architecture.md), ADR 0011) |
| Analytics | Real BigQuery connection in MVP; purpose and project/dataset pending |
| Ontology | ERP Bench may inform concepts/rules; exact repository/revision pending |
| CI | Simple deterministic checks and builds; local live tests |
| Schedule/cost | Not fixed; do not reuse the earlier narrow-demo estimate |

Open inputs do not prevent implementation of the core. They do block their dependent external behavior: BigQuery scope/credentials/data permission and the exact benchmark source. Overlay placement is resolved by ADR 0011: the UI is system-neutral, shipped as a standalone web app plus an overlay embeddable in any web page. Host adapters for specific systems are optional and outside the MVP. Assume synthetic fixtures for design only; do not export existing ERP data or run billed queries until destination/scope is defined.

### Read-only environment observations

Observed during planning, not integration-tested:

- `odoo19-learning-odoo-1` uses image `odoo:19.0`, host port 8069; its DB container uses `postgres:16-alpine`.
- Compose metadata points to `/Users/thanhnguyen/dev/study/erp/docker-compose.yml`. No configuration values, credentials or business records were read.
- Separate `odoo-bench` is on port 8071. Never select it by searching for the first Odoo container.
- `ollama list` reports local models including `qwen3.8:27b`, `qwen3-coder:30b` and `qwen2.5-coder:7b`. Availability is not evidence of correct tool use. Select a default only after qualification; record model digest, context settings and runtime version.

No model inference, installation, database mutation, cloud query or benchmark answer inspection occurred during planning.

## 2. Proposed task catalog

Each row is a distinct user task, not five variants of the same procurement case. Freeze the catalog after checking installed Odoo modules and seed data. Read-only tasks require no human write approval; every business mutation requires explicit approval.

| ID | User task | Initial scope and ontology | Independent acceptance |
|---|---|---|---|
| ERP-01 | Check product availability for a demand | Stock, Product, Warehouse, units, freshness | Answer matches scoped ERP snapshot; identifies shortage or no-op |
| ERP-02 | Compare supplier offers and recommend one | Supplier, Offer, approval, price, delivery, budget | Evidence covers eligible options; chosen offer meets declared bounds or reports none |
| ERP-03 | Create a draft RFQ/PO for a shortage | Procurement spine, quantity/offer/reference constraints | Exactly one matching draft order after approval; no confirmation |
| ERP-04 | Amend quantity or date on a draft RFQ | Draft-only state and optimistic resource version | Only approved fields change; stale/non-draft target rejected |
| ERP-05 | Create a customer quotation | Customer, SaleQuotation, Product, currency/price | Correct draft quotation/lines; no confirmation, email or delivery |
| ERP-06 | Summarize late sales orders or deliveries | Order, promised date, delivery status, explicit as-of time | Result set matches independent scoped query; no workflow mutation |
| ERP-07 | Create a CRM lead/opportunity | Lead, Contact, owner/team and source | Correct new record and fields; duplicate command does not duplicate lead |
| ERP-08 | Summarize unpaid/overdue invoices | Invoice, due date, residual amount, company/currency | Correct scoped totals/list with as-of time; never post/pay/write off |
| BQ-01 | Summarize ERP-related metrics in BigQuery | Approved metric/query template, dataset/snapshot provenance | Aggregates match independent deterministic query on approved data |
| BQ-02 | Explain an ERP versus analytics discrepancy | Entity mapping, metric definition, snapshot watermark | Distinguishes stale snapshot from inconsistent values; no automatic correction |

ERP-01..05 form the first five-task gate. ERP-06..08 extend to eight Odoo tasks. BigQuery is an additional integration gate, not a substitute for five real Odoo tasks. If a required module is unavailable, install/configure it in the designated sandbox or explicitly revise the catalog; do not silently count a stub as live coverage.

Demo mutations remain bounded to draft documents and lead creation. Manufacturing execution, order confirmation, stock movement, posted accounting and payments are excluded. Existing procurement restrictions (single currency/unit and tax-free fixture) apply to its first slice; any broader monetary behavior must get explicit fixtures and rules before activation.

## 3. Implementation work packages

All work packages below are **not started**. Each implementation change should cite its ID and report its gate. Small sequential commits are preferred; the dependency list is execution order, not a requirement to spawn agents.

| ID | Dependencies | Deliverables / affected paths | Definition of done |
|---|---|---|---|
| I00 Environment qualification | None | Local environment manifest/runbook; proposed non-secret profile; sandbox checks | Exact Odoo DB/company/module inventory and supported auth/API known (JSON-2 reachable with a dedicated API-key user); e-agent PostgreSQL is a separate database/role from Odoo's; target marker excludes benchmark; Ollama endpoint/model digests recorded; BigQuery open input tracked; dedicated Odoo integration user/API key created and stored outside the repo (D4); sandbox marker present |
| I01 Workspace and CI | I00 for runtime versions | `pyproject.toml`, lockfile, package skeletons with real tests, frontend tooling when selected, CI | Python lint/type/unit/build/import gates pass; independent wheel install works; CI uses no live credentials or model downloads |
| I02 Contracts and registration | I01 | contracts, SDK, registry/bootstrap; fixtures | Typed action/evidence/binding/stream records, including the initial `RunEvent` catalog (MVP design §4.1), `ConnectionDescriptor.ownership`/`credential_subject` and digest fields; metadata-only discovery; incompatible/disabled plugins rejected; two connections of one capability resolve safely; digest golden vectors (ADR 0006). **Exit = walking skeleton:** fake driver + fake ERP + real kernel services + CLI complete one procurement run end to end with no network |
| I03 Rule and ontology slice | I02 (ERP Bench source D7 needed only before importing benchmark content) | domain-erp resources, SHACL adapter, competency fixtures, provenance inventory | Procurement rules pass positive/negative/missing cases; resource loading from wheel works; public domain specs mapped to Odoo 19; no evaluator answers enter prompts/assets |
| I04 Local model qualification | I02 | Pydantic driver, Ollama configuration, local qualification report | Real model can request typed tools, defer to host, resume with results, stream safe text and stop within bounds; no bypass/raw ERP client; no thinking content persisted; record failures and timings with ADR 0010 metadata. **Rescope checkpoint:** if no local model reaches pass@1 ≥ 0.8 (N ≥ 10) on the deferred-write scenario, stop and revise tool surface/model/scope before I06+ task work |
| I05 Durable kernel | I02 | kernel, PostgreSQL adapter/migrations, deterministic recovery tests | Proposal/approval/reservation/event atomicity; stale approval blocked; cancel/restart/UNKNOWN paths verified; no blind write replay |
| I06 Odoo bridge and adapter | I00, I02, I05, D4 | `addons/e_agent_bridge`, adapter-odoo with manifest `connection` schema and `test_connection`, SDK `auth` module MVP subset (`api_key`, `service_account_jwt`, `AuthContext`; ADR 0013), `SecretStore` local-encrypted adapter, sandbox seed/reset tooling | Odoo API key stored only via `SecretStore` (profile holds `secret_ref`); connection versioned; Dedicated scoped account; approved command executes via narrow RPC; operation key uniqueness and payload conflict handled in same ERP transaction; duplicate concurrent requests yield one effect |
| I07 Procurement vertical slice | I03, I04, I05, I06 | Application workflow, minimal CLI, independent verifier | ERP-01..03 real local runs verified; invalid plan blocked; approval changes and timeouts demonstrated; all attempts exported |
| I08 Streaming API and UI layers | I02, I05 | server SSE endpoint + `ApprovalPresentation` + local session auth (MVP design §12); `apps/web` and a neutral test host page served from the server origin; TS workspace with `@e-agent/client`, `ui-core`, `tokens`, `ui-react`, `components`, layouts; `apps/web`; `<e-agent-overlay>` element; `ui-conformance` skeleton | Generated TS types match OpenAPI snapshot; layer boundary rules pass; mock and persisted events render in `overlay` and `full-page` layouts; theme swap needs no component change; reconnect/replay/dedup work; token text never grants approval; unauthorized streams denied |
| I09 Live UI workflow | I07, I08 | Plan/evidence/rule cards, approval diff from `ApprovalPresentation`, cancellation and unresolved state views; generic `HostContext` resolution; non-React reference custom UI fixture | User can complete/reject procurement in the standalone app and in the overlay embedded on a neutral test page; refresh/reconnect does not execute twice; host context hints are resolved/authorized by the server or dropped; default UI **and** reference custom UI pass `ui-conformance` |
| I10 Five-task gate | I07, I09 | ERP-04/05 capabilities, shapes, fixtures and verifiers | Five Odoo tasks run through same driver/gateway/UI; stale draft amendment and invalid quotation cases blocked |
| I11 Eight-task expansion | I10, module inventory | ERP-06/07/08 domain modules/capabilities and acceptance | Each has real seeded Odoo checks and negative cases; no raw provider types in kernel; no accounting side effects |
| I12 BigQuery integration | I02, I05, confirmed cloud scope | domain-analytics API, adapter-bigquery, approved templates, cost/scoping tests | Actual dataset/location and credentials configured outside repo; dry-run/bytes limit; deterministic job IDs/retrieval; read-only allowlisted queries; BQ-01 succeeds live |
| I13 Cross-source evidence | I07, I12, approved snapshot/mapping | Application workflow, lineage/watermark metadata, metric fixtures | BQ-02 identifies intentional stale/mismatched snapshot; does not claim BigQuery is live ERP truth or send automatic corrections |
| I14 Release qualification | I09, I10, I11, I12, I13 | Local integration/eval report, demo/reset/recovery runbooks, CI checks | All enabled task gates met; complete failure report; repeatable demo; independent artifacts/ontology packaged; no unsupported production-readiness claim |

Initial critical path: I00 → I01 → I02 (walking skeleton) → I03/I04/I05 → I06 → I07. Do not start I10/I11 task families until I07 and I09 pass. Build UI contracts/shell alongside the core once I02/I05 exist. Complete I09/I10 before adding more task families. BigQuery can be designed independently, but do not connect, provision or export data while its scope is unresolved.

## 4. Local driver qualification

Pydantic AI is selected; the spike qualifies its configuration rather than reopening the framework comparison. Test installed Ollama models on: valid JSON/schema output; one/multiple read requests; invalid argument repair; deferred write; approval resume; streaming; cancellation and budget exhaustion. Reject fabricated tool results and unsupported tool patterns. Record cold-load versus warm latency separately.

Prefer one qualified default model and a smaller fallback only if it passes the same safety tests. Model changes stay explicit in profile/evidence. If no local model passes, record the concrete blocker and tune model/context/tool surface; do not replace Ollama with a cloud provider without a scope change. The former 120-second active budget is provisional and must be recalibrated from local measurements; deterministic safety tests do not depend on model speed.

Use the 2.x deferred-tool mechanics: read tools call the gateway via injected dependencies; effectful tools raise `CallDeferred`; the kernel resumes the agent with `DeferredToolResults.calls`. Do not use `requires_approval` or framework durability for business actions (ADRs 0003/0004). Pydantic's [Ollama integration](https://pydantic.dev/docs/ai/models/ollama/) and [deferred tools](https://pydantic.dev/docs/ai/tools-toolsets/deferred-tools/) are the implementation references. Pin a tested version and use its supported API, rather than copying an unverified current snippet into the design.

## 5. Odoo integration and operation identity

Prefer the Odoo 19 JSON-2 surface after verifying it against this local installation and account. JSON-2 runs each call in its own SQL transaction and the legacy XML-RPC/JSON-RPC endpoints are deprecated, so each bridge command must perform ledger check, uniqueness and business mutation inside one call; uniqueness uses Odoo 19 `models.Constraint` ([ADR 0005](adr/0005-odoo-integration-transport.md)). Validate its dynamic API/module availability before choosing transport; a compatible scoped custom endpoint is possible if needed. Odoo's [JSON-2 documentation](https://www.odoo.com/documentation/19.0/developer/reference/external_api.html) is the starting reference, not proof of installed capabilities.

The bridge owns narrowly named methods for approved draft/lead operations. It must not provide unrestricted `execute(model, method, args)` to the agent. An operation ledger keyed by namespace/company/operation ID binds the payload digest and external result. Use a unique DB constraint plus transaction-safe concurrency handling: reservation and business mutation commit together; duplicate same-payload requests return the existing result; different-payload reuse returns conflict. Validate transaction behavior under simultaneous requests and lost responses.

The local kernel still records approval and dispatch before network invocation. ERP-side idempotency reduces duplicate effects; it does not remove UNKNOWN during outages. Reconcile by operation ID, not fuzzy search. Dedicated Odoo permissions/company rules remain enforced inside the bridge. The user permits customization but the plan does not authorize resets of arbitrary existing learning data; seed/reset commands operate only on marked e-agent fixtures or an explicitly designated disposable DB.

## 6. Overlay UI and event transport

The UI is layered per [UI architecture](ui-architecture.md) (ADR 0011): a generated typed client and a framework-free `ui-core` are shared by every UI. On top of them sit the default React components (React Aria primitives), DTCG design-token themes, `overlay`/`sidebar`/`full-page` layouts, and the hosts: `apps/web` and a Shadow-DOM `<e-agent-overlay>` custom element that embeds in any web page. No layer is tied to Odoo or another system. Custom themes, layouts, components or whole UIs reuse the lower layers and must pass the UI conformance suite. Proposed web implementation: TypeScript with React/Vite and a pnpm workspace. A later system-specific host adapter (for example inside Odoo or an intranet portal) would only mount the same element and supply a generic `HostContext`. Validate the chosen host/asset approach before adopting it. No desktop wrapper or browser extension is assumed.

Required UI: expandable overlay, task/chat input, streamed response, live status timeline, evidence/rule links, exact proposal diff, explicit approve/reject, stop/cancel, reconnect indicator, final verified/failed/unresolved state. It is not a graph-governance authoring UI.

Use an authenticated SSE endpoint for server-to-client progress and POST commands for input/approval/cancel ([ADR 0007](adr/0007-run-event-stream-contract.md)). Pydantic AI's AG-UI/Vercel AI adapters may only be read-only presentation adapters; they never carry approvals. Apply the [threat model](threat-model.md) T11 rendering controls (no remote images, strict CSP). Map provider events to project DTOs; no Pydantic internals in UI contracts. Persist state/approval/action events before publishing. Text deltas are transient and tagged by message/offset; they are not business truth and need not replay after a crash. Final safe text is persisted. Durable events use sequence IDs; reconnect resumes after the last durable sequence, deduplicates events, and fetches a snapshot if the retained cursor expired.

Disconnecting the browser does not cancel or rerun an action. Closing a draft card is not rejection; stop after dispatch can still leave reconciliation pending. Slow clients may lose transient text deltas but must resync durable state. Never display internal model thinking streams. Sanitize rendered content and links.

If embedded on another application's origin, validate identity mapping and CSRF/session behavior server-side. If cross-origin, constrain allowed origins and authenticated session exchange; do not pass bearer secrets in URLs or infer permissions from iframe/postMessage payloads. Page model/record IDs are untrusted hints until reauthorized.

## 7. BigQuery boundary

Default proposal, pending clarification: a read-only analytical provider using approved parameterized metric queries, not an agent-controlled SQL console. `domain-analytics` owns QuerySpec/MetricDefinition semantics; the BigQuery adapter depends on that public API. ERP↔analytics mappings belong to application/domain mapping assets, not to adapter-to-adapter imports.

Allowlist project/dataset/tables/location and templates; use a scoped identity with query-job permission plus only necessary data read access. Reject DDL/DML, scripts, exports, remote functions and arbitrary destinations. Apply dry-run estimation and a configured maximum-bytes-billed before real query submission; LIMIT alone is not a cost boundary. [BigQuery cost controls](https://docs.cloud.google.com/bigquery/docs/best-practices-costs).

Query jobs are billed external operations even when business data is read-only. Persist intent and deterministic scoped job ID, then poll/recover the existing job on timeout rather than submitting another one. Capture job ID, source snapshot/watermark, query-template version, parameters digest and processing statistics in evidence. Data copied to BigQuery may be a cross-border transfer under Vietnam's PDPL (Law 91/2025/QH15, effective 2026-01-01); use synthetic data until data owner, region and legal basis are recorded (threat model T13). Dataset provisioning/upload requires a separately defined destination/scope; this plan does not create a cloud ETL pipeline by implication.

Without an approved BigQuery project/dataset, unit/contract work can proceed, but the BigQuery release gate stays incomplete. It is not replaced by a local mock or BigQuery-like SQL engine.

## 8. ERP Bench to ontology workflow

There are multiple similarly named projects. Confirm the user's exact repository, revision and license before copying assets. Treat ERP Bench as a source of domain/task concepts, not an authoritative ready-made enterprise ontology.

1. Record source URL/revision/license and the specific public task/specification sections used.
2. Identify concepts, relationships, preconditions, effects and competency questions without reading held-out answers or privileged evaluator state into the agent knowledge base.
3. Map concepts to actual Odoo 19 fields/state transitions, marking custom benchmark semantics separately.
4. Author versioned vocabulary/shapes and synthetic fixtures; record rule-to-source and rule-to-task mappings.
5. Build independent outcome verifiers from approved domain requirements. Keep verifier expected values inaccessible to agent context.
6. Label reused tasks as development examples, not held-out evaluation. Use new synthetic variants for product regression and keep the separate experiment evidence unchanged.

Repository runtime imports must never point into a benchmark checkout or the experiment. Any permitted reused assets must be packaged with provenance/license and checked into this product deliberately.

## 9. Test, CI and release policy

Simple GitHub Actions: Python lint/types, deterministic unit/conformance/architecture checks, PostgreSQL transaction tests using an ephemeral service where needed, wheel/resource installation checks; frontend type/lint/build and focused component tests after frontend exists. No live Ollama, Odoo credentials, BigQuery jobs or cloud model fallback in default PR CI.

Local gates: model qualification; Odoo module/transaction tests; all task runs; browser streaming/approval/reconnect checks; BigQuery authorized integration. Track `not-run`, `blocked`, `failed` and `passed` distinctly. Use a test harness/fixture for mechanisms, and real services for capability claims.

Metrics follow [ADR 0010](adr/0010-evaluation-protocol.md): pass@1 with N during development; pass^3 on consecutive trials of the frozen release candidate; unsafe outcomes block release regardless of pass rate. For the frozen release catalog, run three live trials per enabled task on resettable synthetic data (read tasks use a pinned snapshot). Require all deterministic safety gates and three verifier-passing trials for each claimed task. Record all failures and subsequent reruns; do not cherry-pick. Small-sample success is not proof of broad reliability. An early five-task milestone can be demonstrated, but does not count as completion of the full eight-task-plus-BigQuery target without an explicit scope revision.

UI gate includes keyboard/focus behavior, scroll/expand state, long output, empty/error/loading, approval expiry, network loss and no duplicate action on reconnect. Include Vietnamese input and Vietnamese business labels in at least one local task run; code/design remain English.

## 10. Out of MVP (Phase 2 backlog)

Recorded so MVP work keeps the seams but does not build these: admin *Integrations* and user *My integrations* pages, user-delegated connections, OAuth engine and app registrations, Google Workspace adapter (ADRs 0012/0013); system-specific UI host adapters and cross-origin embedding with OIDC (ADR 0011); AG-UI output adapter; agent-generated UI (A2UI/MCP Apps); MCP integration type; OpenBao/Vault/cloud `SecretStore` adapters; knowledge ingestion/graph (HLD §7); production identity, multi-tenant hosting, HA/DR.

No deadline or cost promise is made yet. Estimate remaining work after I04/I07 measure model reliability, ERP mapping effort and recovery behavior. Publish a status table with actual commands, pinned versions, package artifacts, test results and remaining gaps when implementation begins.
