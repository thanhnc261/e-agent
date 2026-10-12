# MVP implementation review plan

Date: 2026-10-07. Executor: Sol 6.1. Status: **plan prepared; independent review and local qualification not executed by this document's author**.

Source baseline inspected: `3ae9aafb13b112a207ea6474c006e74a3dc157d2` (`feat: MVP implementation I03–I14 (#3)`). Record the actual candidate SHA at execution time; do not assume it still matches. Companion documents: [local test plan](../../archive/docs/testing/2026-10-07-local-test-plan.md), [handoff](../handoffs/2026-10-07-sol-6.1-mvp-review.md).

## 1. Objective and authority

Determine whether the implemented MVP satisfies its declared scope and works on the owner's machine with Pydantic AI, Ollama, the independent `odoo19-learning` Odoo 19 stack, durable storage and replaceable presentation. Deliver reproducible findings and an evidence-based release verdict, not a restatement of the implementation author's report.

Review and qualification are the assignment. Add focused regression/reproduction tests where needed; do not silently redesign the application or fix production code before preserving a failing baseline. Report fixes as separate candidate changes and rerun affected gates. Never change acceptance assertions simply to make the suite pass.

User requirements take precedence over older documents. In particular:

- Presentation supports CLI/web and an extension path for desktop; the default web UI/overlay can be themed, rearranged or replaced without changing business enforcement. A native desktop application is not a required MVP deliverable.
- Ollama first; no automatic cloud-model fallback.
- There are eight implemented Odoo task families to qualify, not merely eight variants of procurement.
- BigQuery was clarified as an architecture-extension probe; no project/dataset is selected. Assess the seam and identify missing BigQuery-specific evidence, but do not demand credentials or provision cloud resources as a prerequisite to Odoo qualification.
- ERP Bench input, if used, must match the version already referenced by `experiment`. Read metadata/public specifications only; no benchmark answer leakage, runtime cross-import or mutation of experiment data.
- Additional enterprise data requirements are deferred. Use synthetic sandbox records and bounded scope for qualification.

Consult AGENTS.md, HLD, MVP design, accepted ADRs, UI architecture, threat model and integration/auth designs. Distinguish accepted MVP requirements from Phase 2 aspirations. Source code and new observations determine what exists; old status paragraphs do not.

## 2. Planning observations to investigate first

These are source/document observations, **not completed vulnerability findings or local test results**.

| ID | Observation at the inspected SHA | Review consequence |
|---|---|---|
| O01 | README/AGENTS/CLAUDE/docs index still contain M1 or documentation-only statements, while the status table and source cover I03–I14 | Reconcile inventory and qualification claims; don't trust stale summaries |
| O02 | `docs/release/mvp-qualification-report.md` reports scripted live Odoo on a source-built sandbox, fixture-only UI, and pending owner-machine/model gates | Reproduce each environment separately; none proves live model + owner's ERP + web end-to-end |
| O03 | That report states no model text deltas and no endpoint to answer `AskClarification` | Reproduce actual UI/API behavior; determine blocking gaps for requested streaming and conversational task completion |
| O04 | `scripts/qualify_model.py` covers only valid/zero-shortage/over-budget procurement against fixture ERP; its exit code checks unsafe counts rather than all success gates | Parse metrics and trial records; a zero exit is not model qualification or eight-task coverage |
| O05 | The qualification script's over-budget pass expression accepts zero creates and no VERIFIED, including some ERROR outcomes | Require an explicit distinction between safe business refusal and infrastructure/driver failure; preserve raw results |
| O06 | CLI `demo` always starts with a hardcoded procurement task string; `--task` is supplied separately to runtime construction | Check that real-model non-procurement tests use actual task prompts via API/harness rather than assuming `--task` changes the model's request |
| O07 | `profiles/live.example.json` lists only initial procurement bindings | Construct a complete profile from installed manifests; reject missing bindings, never replace live tools with fixtures |
| O08 | PostgreSQL fixtures truncate ledger tables; migration tests drop/create the fixed database `e_agent_migration_test` and replace `/e_agent_test` in the DSN string | Use a dedicated disposable PostgreSQL server, not the application ledger or Odoo cluster; review helper robustness |
| O09 | Live Odoo test fixtures call admin seed helpers before runtime marker checks in some tests | Validate the exact target and marker independently before running any live tests; an expected-mismatch test may still seed records first |
| O10 | `seed-tasks` posts synthetic invoices and prepares non-draft example records using admin privileges; reset has nontrivial cancellation/deletion behavior | Review fixture mutation/cleanup independently of the agent's draft-only policy |
| O11 | Current UI docs disclose same-origin-only overlay auth and TypeScript source consumption inside the workspace | Do not claim arbitrary cross-origin embedding or independently published UI artifacts without additional evidence |
| O12 | Env checker returns a JSON manifest/exit zero even when dependencies are unavailable; it only reports PostgreSQL configuration, not connectivity | Treat manifest fields as evidence to assess, not a ready/pass signal |

## 3. Review work packages

Order safety and measurement checks before live mutations. Every package produces a checked/not-checked coverage entry and findings, even when no defect is found.

| ID | Focus and source entry points | Questions and adversarial checks | Required evidence |
|---|---|---|---|
| R01 | Scope/inventory: README, plan, ADRs, release report, tests | Which claims are authored reports versus reproduced? Do skipped checks disappear in summaries? Are Phase 2 items misclassified? | Requirement → implementation → test → environment matrix |
| R02 | Layers/packages: root pyproject, SDK discovery, kernel registry, adapter manifests, wheel script, UI boundary config | Does core run without ERP/provider packages? Do imports/dynamic loading bypass boundaries? Does artifact admission cover actual installed code or only manifest bytes? Do independent installs use intended artifacts rather than a registry version? | Dependency map, isolated installation logs, mutation tests for important gates |
| R03 | Host safety: coordinator, policy, approval, connections, credentials, API | Read/write authorization; tenant/principal/context spoofing; digest, revision, expiry, credential subject and capability drift; model cannot grant itself authority | Trust-flow trace from request to dispatch; focused denied-action tests with zero side effects |
| R04 | Durability: store ports, memory/PostgreSQL stores, migrations, coordinator recovery | CAS, reservation scope, state/event atomicity, API idempotency, cancellation races, advisory lock behavior, startup recovery; no resend from UNKNOWN | Fault table and reproduction for each commit boundary; PostgreSQL-specific evidence |
| R05 | Odoo bridge: addon models/security, adapter client/executor, seed/reset scripts | ERP transaction atomicity, operation key/payload conflict, canonical digest trust, company/namespace scope, stale updates, dedicated-user ACLs, bounds on reads, cleanup of only owned data | Real sandbox before/after read-back, duplicate race result, reset inventory; no real business records |
| R06 | Ontology/domain: rules, TTL/shapes, normalizers, verifiers across procurement/sales/CRM/receivables | Missing/null/bool/decimal/date semantics; rule coverage; stale/truncated facts; no authoritative rules solely in prompt; verifier independence from proposed answer | Rule/CQ matrix and negative fixtures; incorrect state/answer cannot be VERIFIED |
| R07 | Driver: Pydantic adapter, tool specs, snapshots, model qualification harness | Every effect deferred; read gateway respected; parallel calls and malformed JSON; thinking strip, snapshot compatibility, budgets/cancellation, clarification, real task routing | Deterministic conformance plus explicitly labelled live-model trials |
| R08 | API/session/SSE: server API and generated OpenAPI, UI client/store | Loopback-only auth, Origin/CSRF boundary, foreign run access, idempotency restart, event resume/gaps, slow/disconnected consumers, safe errors | API adversarial tests; inspect final states as well as status codes |
| R09 | Presentation: ui-core, react bindings, components/layouts/hosts, CLI | Theme/layout/component/whole-UI overrides preserve approval semantics; non-React host; overlay isolation and same-origin limitation; keyboard/vi/en; draft versus verified messaging | Automated conformance plus screenshots/traces and live browser task evidence |
| R10 | Secrets/evidence: local encrypted store, exports, continuation, server errors | Secret lifecycle and permissions; keys absent from model/events/errors/traces; no thinking capture; no tenant leakage; provenance sufficient to reproduce | Synthetic sentinel checks and sanitized artifact audit |
| R11 | Extensibility probes: non-ERP notes fixture, connection bindings, knowledge API, BigQuery seam | Can a separately built fixture plugin and alternative UI work without edits to kernel? Which KB/KG migrations are still only design? Does BigQuery have any actual adapter/contract evidence? | Separate verdicts for generic seam, BigQuery-specific probe and live BigQuery; no equivalence claim |
| R12 | Measurement/runbooks: qualify_model, release_report, CI, runbooks | Exit status versus semantic pass; fixture/live labels; complete trial metadata; fresh namespace, no stale files; repeatable setup/recovery | Audited evaluation method and corrected interpretation of reports |

Inspect public host/addon methods for arbitrary model/method access and `sudo` use. Test out-of-scope access directly through API/bridge, not only through a well-behaved model. Permission-negative tests must establish that the forbidden operation was actually attempted and denied before side effects.

## 4. Severity and finding format

| Severity | Definition | Examples |
|---|---|---|
| P0 | Immediate data integrity/security failure requiring live writes to stop | Unauthorized dispatch, cross-tenant data exposure, wrong ERP target, duplicate financial/business effect |
| P1 | Blocks a required MVP capability or safe recovery | Stale approval accepted, falsely VERIFIED result, unrecoverable uncertain write, required interaction impossible |
| P2 | Material limitation with a bounded workaround | Incomplete supported UI override, weak qualification reporting, setup/runbook defect |
| P3 | Maintainability or documentation issue without immediate correctness impact | Stale summary, minor naming/UX inconsistency |

Do not assign severity by keyword alone. Record impact, reachability, affected scope and whether reproduced. A known limitation can still block a claimed feature; a missing future feature is not automatically a defect.

Each finding: ID, severity, status (`confirmed`, `source-observed`, `hypothesis`, `fixed-retested`), candidate SHA, file/line, requirement, trigger/preconditions, reproduction command or test, expected versus observed behavior, sanitized evidence path, smallest proposed remedy, and regression test. Preserve original failure evidence after any fix.

## 5. Review outputs and stop rules

Write dated outputs under `docs/reviews/`:

- `2026-10-07-mvp-review-report.md`: summary, prioritized findings, coverage, unresolved questions.
- `2026-10-07-mvp-requirement-matrix.md`: requirements and evidence by environment; include streaming text, clarification, UI replacement and BigQuery seam explicitly.
- Link the local test report and raw evidence produced by the companion plan.

Stop the affected live-write stage on unauthorized scope, missing marker, duplicate effect, secret disclosure, unknown fixture ownership or unexpected data mutation. Preserve evidence and continue independent read-only/deterministic work. Missing keys/services mark dependent gates BLOCKED, never PASSED. Do not repeatedly request approvals already covered by the user's sandbox/customization authorization; ask only for genuinely missing access/target information.

Do not launch another model/agent automatically. This is a handoff to Sol 6.1; it does not require subagents or use of cloud inference. No commit/push/deployment is implied by executing this review plan.
