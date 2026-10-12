# MVP remediation and readiness plan

Date: 2026-10-07. Status: **approved 2026-10-07; source and fixture retests complete; owner live qualification blocked**. Reviewed source: `3ae9aafb13b112a207ea6474c006e74a3dc157d2`.

Authority: the user's request to review and plan fixes while retaining the design principles. Inputs: [independent findings](2026-10-07-mvp-review-report.md), [requirement matrix](2026-10-07-mvp-requirement-matrix.md), [test results](2026-10-07-local-test-report.md), [HLD](../high-level-design.md), [MVP design](../mvp-detailed-design.md), [implementation plan](../implementation-plan.md) and accepted [ADRs](../adr/README.md).

The target is a qualified local Odoo MVP covering ERP-01..08 with Ollama, durable PostgreSQL and replaceable web/overlay presentation. Desktop implementation, production authentication, full knowledge governance and live BigQuery remain outside this readiness gate. A generic extension seam does not count as BigQuery-specific evidence. Writing the plan itself performed no implementation or ERP installation. Approved source changes and observed retests are now recorded in the [remediation retest](2026-10-07-mvp-remediation-retest.md); owner installation remains unqualified.

## 1. What `addons/e_agent_bridge` means

`addons/` is this repository's directory for modules that are installed **inside Odoo**. It is separate from the e-agent Python distributions under `packages/`. The reviewed `addons/e_agent_bridge` was one custom Odoo module, version `19.0.0.2.0` (remediation source is now `19.0.0.3.0`; installed status remains unverified), declared in its [manifest](../../addons/e_agent_bridge/__manifest__.py). The repository contains its source; that does not establish that it is installed in the owner's database.

| Component | Runs where | Responsibility |
|---|---|---|
| Kernel | e-agent application | Authorize, validate, bind human approval, persist dispatch intent, recover and verify |
| `adapter-odoo` | e-agent application | Translate portable capability calls into narrow Odoo requests using host-scoped credentials |
| `e_agent_bridge` addon | Odoo server | Check Odoo permissions/target/preconditions; atomically record operation identity and perform a bounded ERP change |
| Odoo ORM and database | Odoo server | Apply Odoo access rules and commit/roll back the local ERP transaction |

Example: a user approves a draft PO. The kernel persists the approved action and dispatch intent. The adapter calls `create_draft_purchase_order` through JSON-2. Inside that Odoo call, the bridge reserves an operation key, creates a draft order and stores its result reference in one transaction. A unique `(namespace, company, operation_key)` constraint protects operation identity. An existing matching digest can return the recorded result; a conflicting digest is rejected; concurrent in-flight duplicates can require reconciliation. The kernel then reads the result independently before declaring it VERIFIED.

There are two ledgers with different purposes: e-agent's PostgreSQL ledger records authority and workflow state; Odoo's `e_agent.operation` records which ERP operation committed. They cannot share one cross-system transaction. If a response is lost, e-agent records UNKNOWN and consults the ERP operation record without blindly creating another PO. A missing record during an ambiguous/in-flight call remains unresolved unless authoritative no-effect evidence exists.

The bridge is selected by [accepted ADR 0005](../adr/0005-odoo-integration-transport.md). Retain it for this MVP. Replacing it with separate standard create/search calls would lose the selected atomic operation semantics. Other providers can implement the same public ports using their own guarantees; the kernel and UI must not acquire Odoo dependencies.

The bridge also contains administrator-only synthetic seed/reset helpers. Those are test setup operations, not agent tools. Some seed helpers post synthetic invoices; therefore install/setup and fixture cleanup must remain separate from the agent's draft-only business permission. Installation is only into the designated learning sandbox, following the [I06 runbook](../runbooks/i06-odoo-bridge.md), after identifying the exact permitted database. This plan does not install it.

## 2. Review judgement and constraints

The existing package/UI layering and deterministic walking skeleton provide a useful foundation. A framework replacement or new orchestration platform is not justified by the findings. Priority is correctness at the already selected boundaries, then real interaction and qualification.

Confirmed failures include stale policy approval, unversioned fact changes, receipt-boundary recovery, PO date verification, missing clarification API, admission of modified code and qualification false-pass logic. Text streaming, target rechecks, execution bounds and worker ownership are source-observed gaps. Do not describe those gaps as demonstrated live exploits. Cached-validator behavior requires tests for actual rule/version drift; engine unavailability alone does not prove a live ontology-publishing bypass. Two failed valid smoke attempts do not prove that the installed model is intrinsically incapable.

Implementation must preserve these invariants:

1. Monorepo/modular monolith; independently released adapters and Odoo addon. No shared integration artifact or unused future packages.
2. Portable contracts and SDK ports. Kernel never imports domains, adapters or server; provider-specific URL/company/marker logic belongs in the provider implementation and composition configuration.
3. Model output proposes. The host selects usable bindings/credentials and owns policy, budgets, approval and dispatch; every read, including verification, uses the gateway.
4. Approval binds normalized arguments, scope, source identity and semantic/policy/connection versions. Changed material inputs need revalidation and explicit reapproval.
5. Mandatory local state/evidence commits before external writes. Short PostgreSQL transactions; no transaction held across model/ERP calls. UNKNOWN is never automatically replayed.
6. Domain packs own rules and acceptance criteria; adapters own validation engines and transport. Prompts, API handlers, CLI and UI do not become parallel rule engines.
7. UI remains provider-neutral and replaceable over generated API/client/core contracts. Safe transient text cannot grant authority or become verification evidence.
8. Preserve baseline failures, record each fixed candidate/configuration, and qualify fixture/model/ERP/UI environments separately. No automatic cloud fallback or benchmark answer leakage.

## 3. Ordered work packages

Each package should be a reviewable change with meaningful regressions. Add only public seams needed by the concrete correction. Update the affected designs/schema versions with contract changes. Preserve the original review rather than rewriting its failures as passing.

| Package | Scope / findings | Dependencies | Completion evidence |
|---|---|---|---|
| FIX-01 | Trustworthy reproduction and qualification reporting, F08/F11 | None | ERROR/no-effect/wrong-task/undersized trials cannot qualify; original failures replay |
| FIX-02 | Approval/fact/rule freshness, F01/F02 | FIX-01 test foundation | Stale inputs cause zero writes and fresh approval; memory/PG/domain regressions |
| FIX-03 | Atomic local transitions, crash recovery and work ownership, F03/F10 | FIX-01; align dispatch with FIX-02 | Process exits at every boundary recover without duplicate effect; fenced ownership tests |
| FIX-04 | Exact independent business verification, F04 | FIX-01 | Wrong/missing material fields never VERIFIED across all eight task families |
| FIX-05 | Installed-artifact integrity and exact sandbox targeting, F07/F09 | FIX-01; integrate with FIX-02/03 | Tampered code/resources rejected before import; target changes blocked before mutation |
| FIX-06 | Clarification, safe model text streaming and execution budgets, F05/F06/F10 | FIX-02/03; portable contract updates | Same-run input/resume, incremental safe text, bounded cancel/time/token behavior |
| FIX-07 | Local model development qualification and task/profile routing, F08/F11 | FIX-01..06 safety/interaction gates | Frozen model/settings, N≥10 per claimed task, checkpoint and failure classifications |
| FIX-08 | Owner Odoo + persistent API/UI qualification | Safety gates, procurement model checkpoint, exact access preflight | Scripted live provider safety; eight integrated tasks, release streaks and human approval evidence |
| FIX-09 | Documentation and readiness decision, F12 | Updated alongside each package; final after FIX-08 | Current requirement matrix and bounded release verdict backed by new evidence |

### FIX-01: make failures reproducible and measurements honest

Promote corrected private review reproductions into appropriate kernel/domain/SDK/server tests, retaining original logs. Keep actual-process crash probes on isolated PostgreSQL. The current cancellation race correctly blocks dispatch through CAS; test that result rather than expecting a normal worker return. Remove review-helper authoring errors from the regression specification while preserving their evidence history.

Refactor the model harness's outcome classification: infrastructure/driver ERROR is failure, not business refusal; SUCCEEDED without the requested effect does not pass a write task; VERIFIED must refer to the required task/action, not any unrelated answer event. Distinguish smoke, development and release modes; require positive trial counts and reject unknown scenarios. A smoke can pass its own explicit checks but cannot set a development/release-qualified flag.

Record per-trial model digest, actual runtime/context/sampling, driver version, profile digest, scenario seed/snapshot, timing, approvals, expected effect and independent checks. Save each completed trial incrementally using distinct result/command filenames. Apply a whole-trial timeout and preserve incomplete/cancelled trials. Exit nonzero when that mode's qualification criteria fail; report unsafe counts separately.

Fix CLI natural-language input so the requested task actually reaches the driver. Build a complete live example from admitted manifest bindings for ERP-01..08, with private values supplied separately. Validate required capability closure at startup and fail closed on ambiguous routing. Do not let model output choose credentials to resolve ambiguity.

### FIX-02: revalidate the approved action at dispatch

Compare current policy/rule/surface/connection/credential versions with the approved canonical input, including resume after process restart. Domain normalizers remain responsible for portable canonical business facts; adapter observations preserve source revisions/provenance/completeness. Use provider revisions or a versioned canonical material-fact digest when revisions are missing. Exclude incidental observation timestamps; do not invent source revisions or treat two missing values as unchanged truth.

Refresh required observations through the authorized gateway and retain the results. Re-evaluate current policy and required validators against the fresh facts and exact proposal. If arguments, material facts or bound versions differ, block the old action, produce a linked new proposal and require new approval. ERROR/UNKNOWN or missing required facts prevent dispatch. Normalization and rule inventory stay in domain code/resources, not coordinator branches for supplier/price/company semantics.

Tests: policy version changes with permission still allowed; rule-bundle change; missing/failed validator; changed pricing/contact/team facts with absent revisions; partial observations; credential rotation/revocation; unchanged facts with new observation timestamps; restart and expiry during revalidation. Assert zero external effects before valid new approval.

### FIX-03: close crash windows and implement accepted work ownership

Extend RunStore with focused atomic operations for the actual local transitions requiring action/run/events/continuation consistency. Implement the same behavior in memory and PostgreSQL, with forward-only checksummed migrations. Do not expose ORM/database objects in contracts or hand domain plugins unrestricted storage handles.

Recovery must derive next work from authoritative action, receipt and outcome records even when run state/continuation lag. COMMITTED without a finished outcome schedules read-only verification; VERIFIED without a terminal run finishes without redispatch; DISPATCHING/uncertain receipt enters reconciliation; interrupted undispatched work revalidates authority before any future dispatch. No action should be stranded behind an obsolete approval screen.

Implement ADR 0003's durable work claim/lease/fencing in the existing storage/kernel boundaries. Claim/renew/commit use short transactions; stale workers cannot commit current local state. Lease expiry cannot cancel an ERP call already accepted, so external uncertainty still requires provider reconciliation. Never add model/framework automatic write replay. Provider uniqueness continues to protect operation identity.

Tests: real process termination before/after reservation, dispatch intent, external commit, receipt persistence, outcome persistence and terminal transition; DB/audit failure before write; verifier outage; concurrent claims; expired worker; second-server startup while a worker is active; API idempotency claimed before run creation; cancellation at each boundary. Verify recovery by independent reads and exact effect counts.

### FIX-04: verify every approved material field

For draft PO, require and compare requested date, line count, parties, product, quantity, unit, currency, unit price, subtotal, draft state and operation correlation. Extend provider-neutral domain read-back DTOs only where these concrete checks require fields. Make fake and live adapters return consistent complete views; absent/partial read-back cannot pass.

Audit amendments, quotations and leads against their exact approved fields. Audit answer tasks against independently recomputed scoped facts/as-of dates/completeness. Verifiers stay in domain packs and receive only scoped reads; model statements and provider receipts alone cannot mark business success.

Tests independently corrupt each material field, omit required fields, return two effects, change target state or truncate the source. Verify the distinction between a committed effect, FAILED business acceptance and UNKNOWN read-back.

### FIX-05: verify actual artifacts and the target inside the write boundary

Generate a trusted build inventory that covers installed plugin code, manifests and semantic resources. Bind it to the approved deployment artifacts; verify contents before loading factories, including module parents. A self-reported or locally rewritten wheel RECORD is not the trust root. Live release profiles require verified installed artifacts; editable development fixtures are explicitly labelled and cannot silently satisfy the live integrity gate. No runtime installation/marketplace or plugin process sandbox is added.

Keep exact Odoo endpoint/database/company/marker/addon-version constraints in host configuration and the Odoo adapter/bridge. Validate them at startup and before writes. For the marker/company precondition, check it within the bridge command's ERP transaction so a separate preflight cannot introduce another unchecked gap. Trusted target values must not be chosen from model arguments. Scope operation lookup/result reads and dedicated-user ACL/rules by company; review direct access to custom operation/demand models as well as bridge methods.

Validate operation key reuse against command identity and payload identity; audit both same-key/same-payload and different-payload/command races. Same-payload retries must return/reconcile the original effect, never create a second one. A missing operation during uncertainty stays unresolved until the host has authoritative no-effect evidence.

Seed/reset require the same exact sandbox preflight before fixture setup, explicit owned namespaces and ownership inventory. Tests must not seed first and validate a marker afterward. Inspect cleanup leftovers, including seeded partners/products/stock/team/source records, not just draft documents. No reset of unrelated learning data or Odoo benchmark resources.

Tests: tampered Python/resource/manifest files with zero import side effects; mismatched artifact inventory; wrong DB/marker/company; marker changed after startup; unauthorized admin seed; custom-model cross-company reads; concurrent duplicates; digest/command conflict; business failure rolling back both ERP effect and operation row; lost response and reconciliation. Source-observed target concerns become confirmed/fixed only after these tests actually run.

### FIX-06: complete interaction without changing authority

Add revision-checked, authenticated clarification input and resume of the same persisted run. Persist input-request/input-received events and continuation atomically where needed, and serialize through durable ownership. Scope input to its requester/run, bound size, handle duplicate submission, and treat its content as untrusted user data. Clarification cannot approve an action, change budgets or select hidden connections.

The driver adapter emits safe text through a narrow public SDK event/sink, without importing kernel/server. The application maps it to provider-neutral transient message/offset deltas; the client/headless core and all UI hosts consume those deltas. Durable events retain their replay cursor; text deltas have separate transient identity and cannot manufacture durable business state. Persist only safe final text. Slow/reconnected clients resync durable state and receive a defined partial/final-text behavior.

Enforce model/provider deadlines and cumulative active-time/token limits at the trusted runtime, excluding human wait. Account for usage across resumed turns and restarts. Stop interrupts cancellable inference/read work, blocks new actions and preserves honest reconciliation after possible dispatch. No long-lived DB transaction surrounds inference or transport.

Tests: clarification success/stale/duplicate/foreign tenant/restart; all three UI hosts; text visible before final completion; thinking in structured/provider/text channels never persisted or emitted; secret canaries; malicious source/rendered text; stream gaps/duplicates/slow clients; hung inference; cumulative usage and cancellation/restart. Regenerate OpenAPI/TS and preserve UI layer/provider-neutrality gates.

### FIX-07: qualify the local model and actual task intent

First diagnose the recorded failures with safe, sanitized replay: tool schema/argument coercion, domain guidance, available task facts, expected outcome, answer-versus-write selection and continuation correlation. Improve the existing Pydantic AI/Ollama adapter and task surface where evidence identifies a defect; do not substitute scripted completion for model competence or load verifier answers into model context.

After deterministic safety/interaction gates pass, freeze one installed model digest and explicit context/sampling/budget settings. Run sequential procurement smoke then N≥10 development trials. Meet the accepted ≥0.8 deferred-write checkpoint with zero unsafe outcomes before extending live effectful task qualification. A failed series requires diagnosis and a separately recorded candidate/settings change; preserve all failures. Other installed local models can be evaluated explicitly if needed, with no automatic cloud fallback.

Qualify each of ERP-01..08 with its actual natural-language task and expected independent outcome. Record N≥10 per claimed task and classified failures under ADR 0010; the explicit ≥0.8 threshold is the procurement rescope checkpoint, not an invented universal threshold in that ADR. Generic SUCCEEDED, an unrelated verified answer, or a green exit cannot satisfy a task. Passing safe response replays become deterministic CI fixtures, without hidden reasoning.

### FIX-08: execute owner-machine provider and integrated gates

Access prerequisite: identify the exact authorized learning database/company/marker and private credential configuration. Existing sandbox customization authorization covers bridge installation and a dedicated integration account; ask only for missing target/access facts. Never print keys or place them in profiles. Inspect/preserve actual compose configuration before adding the addon path/installing the versioned bridge, and verify actual module/user/company permissions afterward.

Use disposable isolated PostgreSQL for truncating/migration suites. Use a separate persistent review ledger for integrated runs. Keep stable review-only secret storage across restart. Seed only validated owned synthetic namespaces; retain before/after inventory and independently read results before cleanup.

Run scripted live Odoo safety tests first, then real-model procurement through persistent API and browser, then ERP-04/05, then ERP-06/07/08. Include all prior failures and three consecutive verifier-passing frozen-candidate live trials per claimed task. Record development N≥10 separately; a three-trial release streak does not replace it.

At least one real-model browser run per task and explicit human approval evidence for each effectful task are required. Automatic harness approvals are labelled and do not replace that evidence. Both standalone and overlay must complete/reject writes and recover from stale approval/reload/reconnect. Verify clarification/text streaming, foreign scope/CSRF/hostile Origin/Host handling, secrets/reasoning hygiene and process recovery against the integrated stack. Fault injection must affect only owned processes/proxies/namespaces.

### FIX-09: publish an accurate readiness decision

Update README, AGENTS/CLAUDE status text, implementation/design status and runbooks to distinguish existing implementation from tested environments. Preserve historical reports. Align the current task scope and BigQuery clarification in affected design documents. Update contract/version inventories and generated artifacts with their implementation changes; retain semantic rule resources as the authority.

Publish a new dated report, requirement matrix, all trial outcomes, artifact/environment metadata and cleanup inventory for the fixed candidate. No historical or baseline failure is overwritten to imply a retest passed. Any unavailable access gate is BLOCKED; complete independent work without manufacturing results.

## 4. Decision consistency checks

The default path implements the accepted baseline. These are specific documentation/contract decisions to resolve during the corresponding package, not permission requirements added to routine fixes:

- **Lock semantics (FIX-03):** ADR 0003 says transaction-scoped serialization; RunStore forbids a transaction across ERP calls and implements a session lock. Claims/fencing must commit before the external call. Clarify when an optional session lock is used versus reliance on bridge uniqueness; do not hold a transaction open to satisfy inconsistent wording. Document a material decision with an ADR and update affected designs.
- **Uncertain absence (FIX-05):** ADR 0005's consequence that no operation row means no effect needs qualification for calls still running/unavailable reads. Preserve the AGENTS/MVP UNKNOWN/no-blind-replay rule. Document authoritative no-effect criteria rather than turning a single negative read into retry permission.
- **Scope (FIX-09):** eight Odoo tasks remain required. Record the user's clarified BigQuery extension/deferred-live scope consistently. Removing bridge guarantees, narrowing worker ownership, dropping streaming or reducing task count would be a material scope/design change requiring an explicit decision, not an implicit workaround.

## 5. Release checklist and first implementation slice

Assign `READY_FOR_LOCAL_MVP_DEMO` only when:

1. All P1 findings affecting the claimed scope are fixed and retested; source-observed safety gaps have executable evidence or an explicitly accepted design resolution.
2. Python/UI/import/OpenAPI/artifact gates, memory/PG conformance and the expanded safety/crash matrix pass; required checks are not silently skipped.
3. The exact owner sandbox and dedicated credentials are verified; scripted live ERP races, denial, rollback and UNKNOWN tests pass.
4. ADR 0010 development metadata/sample requirements and procurement checkpoint are met; every claimed task has the recorded three-trial live release streak and no unsafe outcomes.
5. Persistent real-model/API/UI runs demonstrate all eight tasks, human approvals, independent read-back, clarification, genuine incremental safe text and restart/reconnect behavior.
6. Evidence and owned cleanup are complete; deferred desktop/BigQuery/KG work and local-only identity limits are stated accurately.

First code slice: FIX-01 regression/measurement foundation, followed by FIX-02 approval freshness and FIX-04 exact PO verification, then FIX-03 receipt-boundary recovery with ownership. These directly address known failures before spending further live-model trials. Continue FIX-05/06 before live qualification. No new framework, broad abstraction layer or extra domain package is required to begin.

## 5. Approved remediation outcome

The [retest report](2026-10-07-mvp-remediation-retest.md) records implemented source corrections, 317 passing Python checks and nine recorded-call regressions, independent wheel closure, 47 browser checks and the frozen eight-task fixture/model series. FIX-01..06 are source-tested; FIX-07's local fixture checkpoint is met. FIX-08 requires the exact owner target and integrated human-approved live evidence. FIX-09 has current documentation, archived candidate inputs, retained failures, hashes and cleanup records; final live readiness remains open. None of the fixture gates upgrades the owner's live MVP verdict from NOT_READY.
