# MVP requirement and evidence matrix

Date: 2026-10-07. Candidate: `3ae9aafb13b112a207ea6474c006e74a3dc157d2`. Verdict: **NOT_READY**. Evidence root: `evidence/review/20261007-075816-3ae9aaf/`.

Use with the [review findings](2026-10-07-mvp-review-report.md) and [test report](2026-10-07-local-test-report.md). PASS is limited to the stated environment and assertion; BLOCKED is an unmet prerequisite; NOT_RUN is an unexecuted check; DEFERRED is outside this execution's required live scope. Implementation-authored historical results are not independent PASS evidence.

## Controls and presentation

| Requirement / baseline | Implementation | Independent evidence | Result / limitation |
|---|---|---|---|
| Portable contracts and dependency direction, HLD §4 | contracts/SDK/kernel; independent adapters | T01 imports 7/7; T04 forbidden-import mutation rejected | PASS for tested static imports |
| Independent artifacts/resources, MVP §13 | Ten Python distributions; packaged ontology/manifests/migrations | T04 wheels + exact local-wheel origin/closure JSON; neutral-cwd resources/demos | PASS; UI packages still consumed as workspace TS source |
| Non-ERP lifecycle without ERP installed | Notes fixture on public contracts/SDK | T12 clean venv: approve, create once, verify; only contracts/SDK/kernel installed | PASS generic seam; test fixture loaded from repository, not a new independently packaged domain plugin |
| Multiple scoped bindings/connections | Registry/catalog | Existing two-connection, duplicate-definition and ambiguous-resolution tests | PASS explicit kernel routing; live model multi-account routing NOT_RUN |
| Metadata before import; admitted code identity, MVP §6/T4 | Discovery and optional manifest digest | Disabled/version/SDK/manifest tests pass; altered code with unchanged pinned manifest imports | FAIL F07 for installed-content integrity |
| All reads/writes through host; no model approval | Deferred driver, gateway, policy/approval | Existing deterministic driver/kernel tests; UI composer cannot approve | PASS tested fixture cases; live eight-task competence unqualified |
| Exact approval digest, tenant/connection/credential/expiry | JCS digest, catalog and coordinator | Golden vectors; stale digest/revision/expiry/source/credential tests; PG kernel | PASS tested guards; freshness failures below remain |
| Changed policy invalidates approval, MVP §5 | `_staleness` checks permission only | R-final probes: one write under changed policy version, both stores | FAIL F01 |
| Material fact freshness without revision, MVP §5 | Revision equality only | Changed content with both revisions null creates once, both stores | FAIL F02; live adapter has unversioned observations |
| Required validator/rule freshness | Validation cached before approval | Validator changed to unavailable still allows one write, both stores | Gap F02 supplement; no live ontology-update exploit demonstrated |
| Mandatory admission/dispatch evidence, atomic store methods | Reservation/action/event CAS | T05 store/kernel; existing audit/validator failure cases | PASS covered boundaries; global run/continuation atomicity not established |
| UNKNOWN never blindly replayed | Reconcile by operation key | T03 lost response: one create, then reconcile; deterministic recovery suites | PASS tested injections; live Odoo UNKNOWN recovery BLOCKED |
| Committed receipt resumes after restart | Recovery requires run already VERIFYING | Separate processes on review ledger: COMMITTED receipt/run WAITING_APPROVAL/recover zero | FAIL F03 |
| No effect after pre-dispatch cancellation | Action CAS + cancel | Refined race probe, memory and PG: zero writes, CANCELLED, worker conflict | PASS tested race; stop during hung inference NOT_RUN |
| Worker lease/fencing and scheduler, ADR 0003 | In-process run locks; PG session writer lock | PG lock conformance passes; no scheduler/lease/fencing schema | Partial implementation F10; second-server recovery NOT_RUN |
| Active time/token/deadline bounds, MVP §10 | Turn/read/repair/write and model-request counts | Source inspection; no configured cumulative time/token fields/deadline enforcement | NOT_IMPLEMENTED portions F10; review outer timeout is not a product control |
| Independent exact business outcome | Domain verifiers, gateway read-back | Wrong requested PO date supplied in fresh read-back still SUCCEEDED/VERIFIED | FAIL F04; other tested fixture verifier negatives pass |
| Authoritative ontology inventory, ADR 0009 | ERP resources + SHACL adapter | Negative/parity/inventory tests and 21 fixture cases; clean resources | PASS bounded fixtures, not evidence of broad ontology effectiveness |
| Task clarification resumes same run, MVP §12 | WAITING_INPUT exists; no input API/coordinator/UI continuation | AskClarification fixture → WAITING_INPUT; inputs POST → 404 | FAIL F05 |
| Incremental safe model response, ADR 0001/I04/I08 | Final model `.run`; durable-event SSE | Source inspection: no text-delta producer/consumer | NOT_IMPLEMENTED F06; SSE replay PASS does not qualify text streaming |
| Session, CSRF, idempotency and SSE replay | Loopback session and typed API | Existing API tests; CLI/UI fixture runs | PASS covered tests; hostile Host/Origin/actual foreign-tenant tests incomplete |
| Theme/layout/component/whole-UI replacement, ADR 0011 | Tokens, layouts, slots, reference UI | 38 unit + 41 Chromium conformance tests, 3 recorded success traces | PASS fixture scope; independent UI publication NOT_RUN |
| Exact approval presentation/explicit confirmation | Shared approval state/digest checks | Wrong digest/expiry/stale/hidden slot/keyboard/Enter/confirmation tests | PASS tested fixture surfaces |
| Neutral embedding | Shadow DOM and generic HostContext | Hostile CSS and hint tests | PASS same-origin fixture host; cross-origin auth NOT_IMPLEMENTED; desktop deferred |
| No renderer exfiltration/reasoning/credential exposure | Sanitizer/CSP, thinking stripping, encrypted local store | Existing renderer, driver hygiene, credential/local-store tests | PASS covered synthetic tests; full live sentinel/export audit NOT_RUN |
| Sandbox target/marker/company before mutation, T14 | Startup marker; integration-group bridge check | Version endpoint only; source shows no exact marker check before each ordinary write | F09 source-observed; live denial probes BLOCKED |
| Trusted synthetic setup/owned cleanup | Admin seed/reset helpers | Source checked; no owner ERP seeding | BLOCKED live setup; fixture tests seed before runtime marker validation |
| ADR 0010 complete trial protocol | Three-scenario procurement script | T09 two smoke runs; F08 deterministic ERROR false-pass probe | FAIL qualification semantics/metadata; N≥10 and pass^3 NOT_RUN |
| Natural-language task routing and full binding profile | Scripted task selector; procurement live example | CLI constant prompt and manifest/profile inspection | Gap F11; API/user prompts required for integrated trials |
| BigQuery-specific extension | No analytics pack/BigQuery adapter | Generic notes/connection/reference-UI evidence only | DEFERRED; BigQuery-specific probe NOT_IMPLEMENTED, live credentials not requested |
| Governed knowledge/KG migrations | Design/contracts, no full platform | Design reviewed | DEFERRED; backend replaceability is not semantic/ACL/deletion migration evidence |

## Eight task families

| Task | Scripted fixture + memory | PostgreSQL | Scripted owner's Odoo | Live model + fixture | Live model + Odoo + UI |
|---|---|---|---|---|---|
| ERP-01 shortage | PASS correct and repaired answer | Generic kernel/store only; task NOT_RUN | BLOCKED DB/keys | No dedicated answer-task qualification; zero-shortage draft-PO scenario failed | BLOCKED |
| ERP-02 supplier recommendation | PASS fixture | Task NOT_RUN | BLOCKED DB/keys | Model may use answer tools during PO smoke; dedicated task NOT_RUN | BLOCKED |
| ERP-03 draft PO | PASS suite/CLI; wrong-date adversarial FAIL F04 | Generic kernel plus review probes; live task NOT_RUN | BLOCKED DB/keys | Valid 0/2 across smoke runs, zero creates; not qualified | BLOCKED safety/model/access |
| ERP-04 amend RFQ | PASS success/stale/confirmed negatives | Task NOT_RUN | BLOCKED DB/keys | NOT_RUN | BLOCKED |
| ERP-05 quotation | PASS success/price/product negatives | Task NOT_RUN | BLOCKED DB/keys | NOT_RUN | BLOCKED |
| ERP-06 late orders | PASS answer/correction | Task NOT_RUN | BLOCKED DB/keys | NOT_RUN | BLOCKED |
| ERP-07 CRM lead | PASS creation/team/lost-response cases | Task NOT_RUN | BLOCKED DB/keys | NOT_RUN | BLOCKED |
| ERP-08 overdue invoices | PASS answer/correction | Task NOT_RUN | BLOCKED DB/keys | NOT_RUN | BLOCKED |

The PostgreSQL kernel suite uses a non-ERP notes fixture. It does not establish integrated durable ERP task qualification. Browser tests use scripted procurement against fixture ERP; their “live fixture server” label means an actual HTTP server, not live Odoo or model inference. No task has the required N≥10 development sample, three consecutive integrated passing trials, or a live human approval trace in this review.
