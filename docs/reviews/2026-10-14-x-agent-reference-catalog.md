# Reference catalogue: X-agent architecture review (research/dx)

Date: 2026-10-14. Source: 16 screenshots, kept only on the owner's machine and not in the repository (`research/dx/` is git-ignored), taken from an architecture and engineering-practice review of **X-agent**, another enterprise agent platform. The screenshots mix two documents: a Vietnamese practice review (cards rated *Tốt* = good, *Chưa enforce đủ* = not enforced enough, *Cần cải thiện* = needs improvement, *Đơn giản* = simple / acceptable for now) and an English architecture overview (sections 02–14).

This file only records what the screenshots say, translated to English, with a stable ID per practice (`AP-NN`). It makes no claim about e-agent; the comparison is in the [adoption review](2026-10-14-x-agent-adoption-review.md). Evidence tags (`OBSERVED`, `INFERRED`) and file references are X-agent's, copied as shown; none of them were checked by us. Numbers (package counts, file counts) are X-agent's and are kept only where they explain the practice.

## Image index

| File | Content | Practices |
|---|---|---|
| `image.png` | Structure and boundaries (module, package, plugin) | AP-01 – AP-06 |
| `image (1).png` | Identity, authorization and data (identity, tenancy) | AP-07 – AP-12 |
| `image (2).png` | AI and agent safety (runtime, tools, knowledge) | AP-13 – AP-18 |
| `image (3).png` | Operations and process (config, errors, logs, release) | AP-19 – AP-24 |
| `image (4).png` | Diagrams: five import tiers; one chat turn through the tool executor | AP-03, AP-40 |
| `image (5).png` | Patterns: ports and adapters, DI, plugin SDK, outbox, repository, LLM abstraction, prompts, Temporal, tenancy | AP-25 – AP-33 |
| `image (6).png` | In-memory state, flags and event versions; table of tool-enforced checks | AP-34 – AP-36 |
| `image (7).png` | §02 Product and scope; §03 Design principles | AP-37 |
| `image (8).png` | §04 System context; §05 Runtime topology | AP-38, AP-39 |
| `image (9).png` | §06 Layered architecture; §07 Agent runtime: a chat turn end to end | AP-03, AP-40 |
| `image (10).png` | §07 cont.: progressive disclosure, executor chain, durable turns, typed transcript; models and routing; tool risk and approvals | AP-41 – AP-44 |
| `image (11).png` | §08 Integration platform: catalog compiler, connections, credentials, sync, plugin portfolio | AP-45 – AP-48 |
| `image (12).png` | §09 Knowledge and data | AP-49, AP-50 |
| `image (13).png` | §10 Durable work and events; §11 Identity and security | AP-51, AP-52 |
| `image (14).png` | §12 UI, clients and downstream products; §13 Delivery and operations | AP-53, AP-54 |
| `image (15).png` | §14 Technology decisions | AP-55 |

## 1. Structure and boundaries (`image.png`, `image (4).png`, `image (9).png`)

**AP-01 Apps wire, packages own, plugins are guests.** *Good.* The app is the final composition root: settings, bootstrap, router, engine, plugin discovery, error mapping. Packages hold reusable logic. Plugins may depend only on the plugin SDK and approved leaves. Checked by import contracts `apps-are-terminal-composition-roots` and `plugin-isolation`; a plugin cannot reach the database or secrets. The isolation contract forbids plugin imports of db, auth, identity, credentials, runtime, Temporal and API internals.

**AP-02 Packages must earn their boundary.** *Good.* A new package is created only when there is a real second consumer, when both API and worker need it, or when the host must be able to drop its dependency. "Grab-bag" packages and packages created for the future are forbidden. Why good: prevents the package fragmentation many monorepos suffer; every package has a checkable reason to exist.

**AP-03 Five tiers, import only same tier or lower.** *Good.* `host › domain › platform › foundation › kernel` over 44 packages:

| Tier | Members (examples) | Role |
|---|---|---|
| host | `x-agent-host` | One-call assembly for both composition roots |
| domain | runtime, chat, chat-persistence, connections, automations, connector-sync, content-host, knowledge, sheet, artifacts, command-center, scheduled-agents, tenant-mcp, notifications, document-worker | Product behaviour |
| platform | guardrails, db, events, identity, fastapi, catalog, worker-core, evals core | Policy and infrastructure every domain uses |
| foundation | plugin-sdk, tabular, documents, config, observability, audit, auth, credentials, jobs, mcp, temporal, worldsim | Leaves with no database, identity or runtime imports |
| kernel | `x-agent-core`, `x-agent-ir` | Stdlib and Pydantic only |

Apps sit above host under composition-root contracts; plugins sit outside the tiers under `plugin-isolation`. The `workspace-tiers` contract runs in the required "Quality gates" check; a violation fails CI. "Do not loosen a boundary to make a change fit."

**AP-04 Contracts live with their producer.** *Good.* No shared top-level contracts folder; wire files live in the owning package's `wire/` directory, and the set of top-level folders is closed. Why good: whoever changes a schema owns it; 9 `wire/` folders carry 154 fixtures used as contract tests.

**AP-05 Durable state has one owner.** *Good.* Each kind of durable data belongs to exactly one package or adapter; history is kept where correctness needs it (bitemporal facts, versioned transcript). ADR "Aggregate caches are not schema authorities" reinforces it. Why good: no two places write the same table.

**AP-06 FastAPI only at the app root.** *Not enforced enough.* The rule says packages must not import FastAPI or raise `HTTPException`; in practice the chat package has 19 files importing FastAPI and 146 `raise HTTPException`, and the `fastapi-app-only` contract skips it. To do: record the exception in AGENTS.md or move chat's transport layer into the app.

## 2. Identity, authorization and data (`image (1).png`, `image (13).png`)

**AP-07 Identity is not authorization; three-plane authorization.** *Good.* OIDC only confirms the realm and returns a principal. Permissions resolve to capabilities, and queries still filter by tenant and resource. The three planes, verb (capability), tenancy (tenant clamp) and resource (classification, ownership, grants), are checked independently; passing one never implies another, so a fault in one plane does not open the data.

**AP-08 Roles are capability sets, not ranks.** *Good.* Code asks "does the actor have capability X", never "is role A above role B". Roles never widen visibility of PERSONAL data. Explicit deny wins. The staff realm matches its audience byte for byte; staff and customer realms are separated by exact issuer and audience, with tests proving disjointness. Why good: no "admin sees everything" escalation.

**AP-09 Three data classes, three closed cross-user paths.** *Good.* Every user-data table is classified (PERSONAL, TENANT_SHARED, OPERATIONAL, plus INFRA in the overview), and gates enforce that the classification exists. Only three paths let one user see another's personal data: an explicit share grant; audited, read-only, time-bounded impersonation; and a sealed view-only capability widening. A fourth path is forbidden. Gates `check_authz_registry` and `check_resource_scoping` run strict.

**AP-10 Every route has a capability, every query is clamped to a tenant.** *Not enforced enough.* The tenant filter is checked by an AST lint (`check_tenant_filter --strict`), but no gate checks that every route carries a capability, and the authz registry only scans tables with an owner-like column. To do: a test that enumerates all OpenAPI routes and asserts each has a capability dependency (a test, not a new gate).

**AP-11 Fail closed.** *Good.* Unknown identity, account, permission or model source is refused. A hidden row looks exactly like a nonexistent row. A crashing plugin breaks only that integration. Model routing fails closed when a source disappears. Why good: errors do not leak the existence of data; local failures stay local.

**AP-12 Secrets stay inside the host trust boundary.** *Good.* A plugin receives an authenticated client (SSRF-protected, IP-pinned), never a raw credential. Credentials are envelope-encrypted with AES-256-GCM; the AAD binds tenant and connection; the KEK is in KMS. Why good: a third-party plugin cannot exfiltrate tokens; ciphertext copied to another tenant fails to decrypt.

## 3. AI and agent safety (`image (2).png`)

**AP-13 The model sees a narrowed operation surface.** *Good.* Before the model is called, tools are filtered by availability, policy, account semantics and routing. The model starts with only `find_capabilities` and `query_dataset` (progressive disclosure). Why good: fewer tokens, fewer wrong tool choices, smaller prompt-injection surface.

**AP-14 Model output is untrusted input ("a model cannot authorize itself").** *Good.* Write tools must declare risk, approval, reversibility and idempotency. Approval is bound to the payload hash and a fingerprint and survives restart. The approval summary is structured; the model does not "narrate" consent. Why good: the model cannot change parameters after the user approves; every call leaves exactly one audit record.

**AP-15 Do not fabricate results.** *Good.* A failed tool does not return a fake empty result. A truncated result is not labelled complete. The UI never parses prose to recover a tool call. Why good: blocks the error class that makes ERP agents dangerous, reporting "no invoices" when the API actually timed out.

**AP-16 Facts come from structure or people.** *Good.* Knowledge facts come only from a connector's structured fields or from human input; the model never extracts facts from text. Facts are bitemporal and carry evidence. Text is only chunked, embedded and retrieved with citations. Why good: the knowledge base is not contaminated by hallucination; the reviewer found no violating path.

**AP-17 No assumptions about the customer's instance.** *Good.* "Customer-agnostic read-surface doctrine": do not hard-code assumptions about the tenant's system into tools when they can be discovered at runtime, or refuse honestly. Ten rules, for example "Writes are always typed operations". Why good: Odoo and NetSuite plugins work across differently configured ERPs without silent breakage.

**AP-18 Agent behaviour changes need evals.** *Not enforced enough.* AGENTS.md requires adding an eval case and running `uv run dev eval`, but the CI `agent-evals` lane is path-triggered and not a required check; the full deterministic suite runs only nightly. To do: make the deterministic core eval (temperature 0) required when a PR touches the runtime, prompts or tool schemas.

## 4. Operations and process (`image (3).png`)

**AP-19 Typed config, never `os.environ`.** *Good.* Typed settings (pydantic-settings, 80 classes); Ruff TID251 bans `os.environ` and `os.getenv`. Startup fails before serving if the trust boundary is not configured; an unconfigured feature is absent from the tool surface. Why good: bad config shows up at deploy time, not while a customer is using it.

**AP-20 Errors have a shape; the transport owns HTTP.** *Good.* Domain errors inherit from one base error (633 subclasses); user-facing messages go through `messages.py` modules. Caveat: 1,604 `raise ValueError` and 199 `RuntimeError` remain in `src/`; how many reach users is unknown.

**AP-21 Libraries emit telemetry, the app configures it.** *Good.* structlog everywhere, plus OpenTelemetry, Prometheus, Sentry. The final error is logged once; retries log at WARNING. Background tasks use `create_supervised_task` (Ruff bans `asyncio.create_task`). Why good: no duplicate logs and no tasks that die silently.

**AP-22 The integration branch is always production-ready ("never merge unfinished code").** *Good.* A change must show its path to an effect. A seam ships with its first consumer. A flag is not cover for a stub. A hotfix changes urgency, not safety. Why good: `dev` can always cut a release; reduces "dead code behind a flag".

**AP-23 Hosted defaults are preserved ("downstream products compose supported seams").** *Good.* Downstream products pin one SHA and extend only through supported seams. A core change made for a downstream product must be platform-neutral or sit behind a typed setting whose default keeps hosted behaviour. Why good: one core serves several products without forks.

**AP-24 New rules are enforced by type, lint or test.** *Good.* Prefer types, constructors, Ruff, Pyrefly, import-linter or tests. Do not add new `dev check` gates or exemption tables. A gate that cannot parse its input fails and prints the number of files scanned. Why good: avoids "garbage gates" that pass vacuously; a gate that scans 0 files and stays green is a common failure.

## 5. Patterns (`image (5).png`, `image (6).png`)

**AP-25 Ports and adapters with `typing.Protocol`.** *Good.* 769 Protocols outside tests; a package declares its port locally and provides SQLAlchemy and in-memory adapters. Easy to test and to swap infrastructure (the stream buffer already has a seam for Redis). Small fix: the `_SyncDatabase` Protocol is redeclared in at least 9 packages.

**AP-26 Manual DI at the composition root.** *Good.* `create_app(overrides)` plus a `wiring.py` per feature; startup order managed by `x-agent-bringup` (Phase, Policy). No DI container. Explicit wiring is readable; the cost is a fat root.

**AP-27 A strongly typed plugin SDK.** *Good.* Entry point `xagent.plugins`; `build_manifest(ctx)` is a pure factory (no I/O); `ToolSpec[In, Out]`, 4 `RiskClass`, about 10 `AuthShape`, `RetryPolicy`, `RateLimiter`, a circuit breaker per plugin, tool and connection. Why good: a new ERP is a new manifest, not a core change; the host keeps scope, credentials and approval.

**AP-28 Transactional outbox plus LISTEN/NOTIFY.** *Good.* Events are written in the business transaction; Postgres NOTIFY wakes a dispatcher on each pod to push SSE; retention applies. No event loss on a crash; cross-pod fan-out goes through the database, not pod memory.

**AP-29 Repositories; the caller owns the transaction.** *Good.* 116 repository classes; the transaction is opened with `Database.async_scope()`; exactly one `commit()` lives in the repository layer. Clear transaction boundaries let the outbox and the business change commit together.

**AP-30 LLM provider abstraction.** *Good.* 12 factories (Anthropic, OpenAI, Azure, Bedrock, Vertex, …) on pydantic-ai. The gateway is infrastructure, not a `ProviderKind`. Raw model calls are banned by Ruff, forcing the metered path. Switch models or run air-gapped (`LLM_LOCAL_ONLY`) without touching business logic.

**AP-31 Prompts are code.** *Good.* Prompts are assembled by Python "prompt contributors" and locked with golden files in tests; no prompt is edited outside the repository. Every prompt change goes through a PR with a diff. Missing: no A/B or per-tenant prompt rollout.

**AP-32 Durable work on Temporal.** *Good.* The `BoundJob` contract is engine-neutral; automations and scheduled agents use the job's own permissions, not personal preferences. The Command Center runs AI by activity; an inactive actor has zero runs. (Rest of the card is cut off in the screenshot.)

**AP-33 Tenancy only at the application layer.** *Needs improvement.* No Postgres RLS and no global SQLAlchemy filter (documented in a docstring). Each repository writes `.where(tenant_id == …)`; the AST lint checks only within one function; 83–89 `# noqa: TID-tenant` suppressions. One wrongly written query is enough to leak (card cut off).

**AP-34 In-memory state per pod.** *Needs improvement.* `InMemoryTurnStreamBuffer` is the only implementation; the rate limiters (3 kinds), circuit breaker and OAuth state store default to process memory. Infrastructure needs sticky sessions for streaming routes. Why fix: reconnecting to another pod loses replay; real limits become N × configured with N pods; a pod restart loses in-flight streams. The chat-turn diagram calls this the weak point for horizontal scale.

**AP-35 Feature flags and event versions.** *Simple.* Flags are 18 deploy-time booleans `XAGENT_*_ENABLED` plus a DB kill switch. Events carry only `payload_version: int`; there is no upcaster registry. Acceptable at current scale; per-tenant flags and an upcaster are needed before large customers or long-lived events. (`INFERRED`.)

## 6. What the tooling actually enforces (`image (6).png`)

"This section counts only what machines check, not advice in documents." **AP-36** Required checks on `dev`:

| Required check | What it checks |
|---|---|
| Validate PR title | Conventional commit; branch format `<type>/<ticket-key>/<desc>` |
| Quality gates | 21 pre-commit hooks; cognitive complexity ≤ 15 on changed code; `dev check` 12 gates (ruff, pyrefly, import-linter, deptry, tenant filter, authz registry, resource scoping…); ESLint 0 warnings |
| Backend tests | pytest by shard, migration topology, Temporal local, Playwright e2e on Chromium |
| UI tests | vitest in 12 shards, Storybook build, axe a11y checks on stories |
| Migration safety | Destructive-migration policy, upgrade/status, integrity, knowledge-engine conformance |
| Detect secrets baseline · Trivy | Secrets scan on changed files; vulnerabilities, misconfiguration, licences |
| Sonar gate (+ merge queue) | Thresholds configured on the Sonar server, not in the repository |

## 7. Architecture overview (`image (7).png` – `image (15).png`)

**AP-37 Product scope and principles (§02–§03).** Documented user journey: sign in through the organisation IdP; choose or configure an agent; ask in chat or start an automation; the runtime selects authorised operations; approve sensitive actions; receive a response, artifact, notification or durable job result.
- Users: workspace users in a customer tenant; tenant administrators who configure integrations, policies and tool classifications; platform operators in a separate staff realm; downstream product teams that pin and extend the platform.
- Surfaces: chat with tool activity, approvals and artifacts; artifacts (documents, dashboards, reports, forms, files, sheets); automations and scheduled agents; Command Center and Daily Brief; knowledge, integrations, admin, sharing, voice.
- Products built on it: the hosted product; two downstream products (a spatial-awareness product and an export-controlled workspace product); one named external distribution.
- Research repositories feed ideas rather than run inside: an intent-to-IR lowering project, a provenance-first knowledge graph and an ontology evaluator in Rust.
- Principles are binding rules in AGENTS.md and 53 decision records in `docs/decisions/`, each row giving principle, practice and source: apps wire / packages own / plugins are guests; three-plane authorization; model output is untrusted input; facts come from structure or people; fail closed; hosted defaults are preserved.

**AP-38 System context (§04).** Actors: workspace user, tenant admin and downstream product team reach a hosted or downstream product (which pins one SHA); platform operators reach the platform through the staff realm. The platform validates tokens against OIDC IdPs (Okta, Entra, Auth0, Keycloak), makes actor-scoped calls to business systems (ERP, CRM, docs, data), sends narrowed prompts and tools to model providers and gateways, and is an MCP client to tenant-installed remote MCP servers. "Identity providers assert identity but never define X-agent roles; model providers generate candidates but never authorize calls."

**AP-39 Runtime topology (§05).** Clients (browser SPA; iOS, macOS and Android shells; Rust terminal client) → GKE Autopilot per environment → Gateway API and Cloud Armor → `x-agent-api`, `x-agent-worker`, `x-agent-platform-api`; supporting `x-agent-embeddings`, self-hosted Temporal, OTel collector with Phoenix and Prometheus; Cloud SQL Postgres for the platform and a separate Postgres for knowledge (pgvector, PostGIS).

**AP-40 A chat turn end to end (§07, `image (4).png`, `image (9).png`).** ChatSurface `POST /turn/stream` → turn router admits the turn, attachments and budgets → TurnExecutor builds context, routes, executes → RuntimeGraph prompts the model with kernel tools only → the model issues a `find_capabilities` query → typed tools are mounted from the actor's snapshot → tool call → operation executor validates, authorizes, runs guardrails and previews → approval card if required → `POST /confirm` → invoke with a guarded client → typed result, bounded or stored as an artifact → exactly one audit record → stream events → SSE frames, then the `TranscriptDocument` is persisted. Review note: the tool-executor control chain is the strongest point; the in-memory stream buffer is the weakest under horizontal scale.

**AP-41 Progressive disclosure, one executor chain, durable turns (§07).**
- *Progressive disclosure:* `find_capabilities` and `query_dataset` search the actor's immutable catalog snapshot; only selected operations are mounted with full typed schemas, so tools the actor cannot use never reach the model.
- *One executor chain:* snapshot resolve, input validation, connection resolve, policy authorization, guardrails, effect preview, approval bound to operation ID plus payload hash plus fingerprint, invocation with timeout and retry, result bounding, exactly one audit record.
- *Durable turns:* turn control and thread state persist in Postgres; a detached producer survives client disconnect; approvals pause the turn durably; send receipts deduplicate retries by client request ID.

**AP-42 Typed transcript (§07).** One versioned `TranscriptDocument` per conversation. Content is never silently dropped; omissions are explicit parts.

**AP-43 Models and routing (§07).** Eleven model sources (Anthropic, OpenAI, Azure OpenAI, Bedrock, Vertex, Vertex MaaS, OpenRouter, Cerebras, Ollama, LiteLLM, Bifrost); default `claude-sonnet-5-5`. Fast, balanced and deep response profiles. A workspace egress stance can force gateway-only routing; `LLM_LOCAL_ONLY` restricts to Ollama for air-gapped installs. Gateway-fronted models start with image, thinking and native-tool flags off until tenant-scoped behavioural evidence enables them.

**AP-44 Tool risk and approvals (§07).**

| Mechanism | Behaviour |
|---|---|
| Risk classes | `READ`, `WRITE_LOW`, `WRITE_HIGH`, `DESTRUCTIVE` on every tool. Write tools must declare idempotency. |
| Remote MCP tools | Server hints never set risk. Unruled tools are treated as `WRITE_HIGH` and ask first. A tenant admin rules per schema fingerprint; a ruled read runs, a ruled write asks. |
| Standing approvals | Always-allow and never-allow preferences, except tools marked non-clearable, which always need fresh approval. |
| Unattended runs | Automations carry their own job-scoped permission set. User preferences never apply. Retries follow declared idempotency. |
| Guardrails | Input, tool and output stages returning allow, block, confirm or modify. Fail closed on timeout. |

**AP-45 Integration platform and catalog compiler (§08).** Each integration is a plugin wheel registering `build_manifest(ctx)` under the `xagent.plugins` entry point; the factory is pure (no network or database I/O). The manifest declares auth shape, connection shapes, capabilities, typed tools, datasets with optional query pushdown, jobs, content sources, webhooks, health, lifecycle hooks and UI metadata. The host compiles all manifests, platform stores and remote MCP servers into one catalog of operation, dataset and content-source descriptors → per-actor catalog snapshot → agent runtime → plugin handler (with a guarded, SSRF-pinned client whose credential comes from the vault) → external provider API.

**AP-46 Connections (§08).** One row per tenant, actor, plugin, profile and instance; user- or tenant-owned; seven lifecycle states from `PENDING` to `DEAD`. Multi-account addressing resolves an explicit argument, then a conversation pin, then the user default, then the unique eligible account; ambiguity asks the user.

**AP-47 Credentials (§08).** A per-record data key wrapped by a key-encryption key (env, file, systemd-creds or GCP KMS). AAD binds tenant and connection, so ciphertext cannot be replayed on another row. OAuth 2 code, device and client-credentials flows; OAuth 1 TBA; API keys; service accounts.

**AP-48 Sync and content (§08).** Connector sync jobs page through sources with watermarks that advance only after every sink accepts. Records keep provider provenance. Access re-checks withhold records rather than delete them. Content sources are live or synced; indexes are projections, never authority. Plugin portfolio: 30 plugins (ERP and finance: NetSuite with OAuth 1 TBA and confirmation-gated writes, Odoo; CRM/HR/contracts; collaboration; engineering; data platforms).

**AP-49 Knowledge and data stores (§09).**
- *Platform database:* PostgreSQL 18, SQLAlchemy, one Alembic tree (643 revisions); boot preflight asserts the schema is applied.
- *Knowledge database:* a separate Postgres with pgvector, PostGIS and pg_trgm; owner and least-privilege app roles; plain SQL migrations owned by the knowledge engine.
- *Tabular compute:* agents emit a typed IR; plans run on ephemeral DuckDB (512 MB cap) or push down to provider SQL through sqlglot and Ibis, with exact decimal semantics. No free-form code execution.

**AP-50 Knowledge pipeline (§09).** Connector structured records and people (or agents on explicit request) → bitemporal facts with evidence rows. Documents → chunks with section, page and character spans → embedding job (768-dim) → pgvector HNSW, plus `tsvector` → hybrid search (vector top 50 + text top 50, RRF fusion) → passages with citations, filtered by reader principals. Facts are never overwritten: each has a valid-time range, recorded and superseded timestamps, a status (accepted, candidate, rejected, outranked, …) and evidence rows. Visibility is enforced in the query by reader-principal arrays. Documents are parsed by a MIME-routed pipeline (Docling in an isolated child process, per-page OCR when needed).

**AP-51 Durable work and events (§10).**

| Mechanism | Use | Implementation |
|---|---|---|
| BoundJob | Any background unit of work declared by a package or plugin | Engine-neutral contract; in-memory runner for dev and tests, Temporal in production via one generic dispatch workflow |
| Bespoke workflow | Multi-step orchestration that needs its own workflow | Registered through the worker's extra-workflow seam |
| Schedules | Recurring jobs | Translated to Temporal Schedules |
| Events | Reporting committed outcomes to other components and the UI | Transactional outbox, at-least-once publisher with dead letters, LISTEN/NOTIFY feeding SSE |
| Automations | User-authored procedures of operation and agent steps | One installation kind with versions, compare-and-swap edits and job-scoped permissions |
| Scheduled agents | Unattended agent steps inside automations | Frozen identity, structured output, model-failure circuit breaker |

**AP-52 Identity and security (§11).** Customer OIDC (customer audience) → public API; staff OIDC (staff audience, groups claim) → platform API; both → identity (actor scope) → three planes: verb → capability check, tenancy → tenant clamp, resource → classification and grants → tenant and personal data.
- Authentication: stateless OIDC bearer validation per request against per-tenant JWKS; staff and customer realms separated by exact issuer and audience, tests prove disjointness.
- Authorization: code-defined roles are capability sets; explicit deny wins; every user-data table classified PERSONAL, TENANT_SHARED, OPERATIONAL or INFRA, gates enforce that the classification exists.
- Personal data: exactly three cross-user paths (AP-09); admin roles never widen personal visibility.
- Audit: a seven-category audit taxonomy with an initiator axis and a coverage ledger; each tool invocation emits exactly one audit record.
- Network: Cloud Armor, private GKE nodes, NetworkPolicies, Kyverno, secrets from GCP Secret Manager through External Secrets.

**AP-53 UI, clients and downstream products (§12).** Web shell `@x-agent/ui-shell` (React 19, Vite 8, Tailwind 4, TanStack Query, Vercel AI SDK and AI Elements, i18next) builds both an SPA and a library that downstream overlays consume. One chat implementation: every conversational surface mounts the same `ChatSurface`; parallel chat stacks need architecture-owner approval. Native shells (SwiftUI, Compose) embed the SPA in a web view and add push, location, Live Activities and a meeting HUD (experimental). Terminal client: Rust TUI with chat and approval cards plus staff commands. Downstream model: product repositories pin one SHA for Python and UI, contribute capability packs, routers, plugins and overlays, and keep their own migration table.

**AP-54 Delivery and operations (§13).** Feature PR → merge queue (squash) → `dev` (auto-deploys shared dev) → freeze a tested SHA → `release/YYYY-MM-DD` → PR, merge commit → `main` → digest pair, GitOps commit → staging via Argo CD → protected manual promote of the same digests → production via Argo CD; release tag merged back to `dev` by ancestry. GitHub Actions publish image digests and desired state; Argo CD owns rollout and health.

**AP-55 Technology decisions (§14).**

| Area | Choice | Alternatives | Why it fits, and the trade-off |
|---|---|---|---|
| Agent loop | pydantic-ai inside a custom sequential RuntimeGraph | LangGraph, OpenAI Agents SDK, Claude Agent SDK | Typed tools, provider neutrality; the team owns orchestration, checkpointing and streaming code |
| Durable execution | Temporal (self-hosted) behind an engine-neutral job contract | Cloud Tasks, Celery, Step Functions | Replayable, durable, schedulable; Temporal operations burden and workflow-determinism discipline |
| Data | PostgreSQL for everything, including vectors and events | Dedicated vector DB, Kafka | One operational system, transactional outbox; vector scale ceiling on one Postgres |
| Retrieval | Hybrid pgvector and full text with RRF, citations | Vector-only, external search | Strong precision with provenance; no reranker observed |
| Embeddings | Self-hosted sentence-transformers, 768 dims | Hosted embedding APIs | Data stays in-cluster, works air-gapped; lower model-quality ceiling |
| Tool protocol | Native plugin manifest, MCP as a client | MCP-only | Richer contracts (risk, preview, datasets) than MCP alone |
| Deployment | GKE Autopilot, Argo CD, Terraform | Cloud Run, managed PaaS | GitOps control and environment parity |
| UI | React 19, Vite, Tailwind 4, Vercel AI Elements | Next.js | Embeddable library for overlays and native shells |
