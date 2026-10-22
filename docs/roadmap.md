# e-agent product roadmap

**Owner-approved direction (2026-10-12):**
- clean the repository;
- refactor to a clear structure first;
- build the core runtime around a typed **execution IR**;
- then cognition and conversation;
- then ERP breadth from ERP-Bench, with a development harness alongside.

Every new runtime feature ships **behind a toggle with a fallback** (see Rules).

This roadmap orders the work. Designs say *what* to build: [target architecture](design/target-architecture.md), [HLD](design/high-level-design.md), [MVP design](design/mvp-detailed-design.md) and the [ADRs](adr/README.md). Each phase has its own plan file. A phase starts only after its **detailed plan** has been written, linked here and reviewed.

## Rules for every phase

1. **Detailed plan before implementation.** Each phase gets a bite-sized plan in `docs/plans/` (specs in `docs/specs/`). Execution follows that plan with per-task review and end-to-end verification:
   - the full gate;
   - the Postgres run;
   - `make e2e`;
   - a live check on the `odoo19-learning` sandbox at the end of the phase.
2. **Design first.** A phase implements design sections and ADRs. A change to a contract or a boundary needs an ADR, and the phase merges only after the owner accepts it. If code and design disagree, fix the design or the code explicitly; never let them drift silently.
3. **Toggles and fallback.** Every new runtime feature (execution IR, ContextAssembler, conversation model, grounded answers, action plans) has a profile feature toggle with modes `off | shadow | on`.
   - **`shadow`**: computes and records the new path but acts on the existing one, so the two can be compared without risk. It needs a real consumer that compares the two paths.
   - **`on` with a fallback**: if the new path fails *before any write is reserved* (for example IR compilation or validation errors), the run falls back to the existing tested path and records a `feature.fallback` event with a reason code.
   - **After a write is reserved there is no fallback.** The run fails closed or goes to reconciliation. Fallback never bypasses approval, admission, verification or the transition table.
   - `/health/ready` reports the toggles, and the evidence bundle records them.
   - A seam ships with its first consumer. A toggle is not cover for a stub ([adoption review](reviews/2026-10-14-x-agent-adoption-review.md) XA-24).
4. **Trust anchor unchanged.** The run and action state machines, gateway, approval digests, admission and verification stay in the kernel. Model output is a proposal.
5. **Boundaries.** Only the `odoo19-learning` sandbox and containers e-agent creates are touched. `odoo-bench` and the lab experiments never are.

## Phases

| Phase | Name | Content | Plan | Status |
|---|---|---|---|---|
| 0 | Cleanup | Archive superseded plans, reports and mockups. Fix the `evidence/` ignore bug that hid UI source. Slug two research filenames. | done in `chore/cleanup-and-roadmap` | **Done** 2026-10-12 |
| 1 | Structure refactor | **1a** One layer-grouped code tree `src/e_agent/{contracts,sdk,kernel,erp,adapters/*,server}` with no repeated folder names. Per-distribution build configs in `dists/<name>/` (still independently releasable; spike-validated). Tests in `tests/unit/<part>/`. Editor hides caches. **1b** Docs into `docs/{design,plans,specs,adr,handoffs,reviews,runbooks}`, links rewritten, AGENTS.md and CLAUDE.md rewritten. **1c** Kernel split behind the `RunCoordinator` facade (SR-06) and server `worker`/`streaming` modules. No behaviour change. | [Phase 1 detailed plan](plans/2026-10-12-phase1-structure-refactor.md); [handoff](handoffs/2026-10-13-phase1-structure.md) | **Done** 2026-10-13; merged to `main` |
| 1d | Plugin boundary and reusable core | Follow-up to Phase 1 from the 2026-10-14 review. The core (contracts, sdk, kernel, server) installs and starts without any ERP package; ERP becomes the first plugin area under `src/e_agent/plugins/erp/{domain, odoo, simulator, …}` with room for many ERP providers. Manifest-driven auth and sandbox probe, task presets and the scripted driver from the domain pack, the fake ERP as a discovered provider plugin, no default profile in the server, an `e-agent-erp` bundle (ADR 0026). Run behaviour unchanged. | [Phase 1d detailed plan](plans/2026-10-14-phase1d-plugin-boundary.md) (approved 2026-10-15) | **Done** 2026-10-17: tasks 1d.1–1d.12 and the phase-review fix 1d.R1 (levels 1–4 pass; [handoff](handoffs/2026-10-16-phase1d-plugin-boundary.md)); merged to local `main`, not pushed |
| 1h | Hygiene | Five small checks from the [adoption review](reviews/2026-10-14-x-agent-adoption-review.md) (XA-04, XA-14 to XA-17): gates fail on zero cases, typed environment reads, supervised background tasks, a prompt golden file with every recording replayed, and a CI secret scan and dependency audit. No runtime feature. | [Hygiene plan](plans/2026-10-15-hygiene-gates-config-ci.md) (approved 2026-10-15) | **Done** 2026-10-17: tasks H.1–H.5 on `chore/hygiene-gates`, CI green on [PR #4](https://github.com/thanhnc261/e-agent/pull/4) ([handoff](handoffs/2026-10-17-hygiene-gates.md)); merged to `main` 2026-10-18 (`6f7ec70`) |
| 2 | Core runtime with execution IR | First task: feature-toggle infrastructure (`Profile.features`, `off/shadow/on`, `feature.fallback` events, `/health/ready`). Then a typed IR the runtime executes: **TaskDefinition** (C11: goal, acceptance spec, fixed capability set) → **ActionPlan** (ordered steps with dependencies, lineage and one approval digest; multi-write runs) → **StepRecord** (C8). The driver emits IR; the kernel validates, approves, dispatches step by step and verifies. Toggle `features.execution_ir: off/shadow/on`, falling back to today's single-action loop before any write is reserved. Design: target §6.4; ADRs 0024, 0025, 0027, 0028, 0029 (accepted 2026-10-18), including capability effect declarations (risk, reversibility, idempotency). | [Phase 2 detailed plan](plans/2026-10-14-phase2-execution-ir.md) (approved 2026-10-18) | **Done** 2026-10-19: tasks 2a.1–2d.2 (with 2c.5a and 2c.8a–2c.8c); levels 1–4 pass, live check on `odoo19-learning` ([handoff](handoffs/2026-10-18-phase2-execution-ir.md)); merged to `main` ([PR #6](https://github.com/thanhnc261/e-agent/pull/6)) |
| 3 | Cognition and context | Progress ledger (§6.2), ContextAssembler (C9; §7.2 layers, budgets, clearing, §7.4 rendering), a grounded answer contract (citations verified against recorded evidence), driver conformance suite, `KERNEL-REPEAT`, **explanation contract** (C18: `ProposalRationale` with checked EvidenceRefs and a deterministic explanation projection, Q5), and **run reconstruction from `run_events`** (U3, §5.1). **Data minimization** (ADR 0030: class-per-route rules, bounded results with truncation markers; the hosted-route startup rule lands first). Toggle `features.context_assembler`, falling back to the current driver history. | [Phase 3 detailed plan](plans/2026-10-19-phase3-cognition-context.md) (from the [core plan](plans/2026-10-12-core-conversation-cognition.md) Phases 3–4) | **Done** 2026-10-20: tasks 3a.1–3f.2 and the phase-review fix 3.R1, behind three toggles (`context_assembler`, `kernel_repeat`, `grounded_answers`), all `off` by default; levels 1–3 in the [handoff](handoffs/2026-10-20-phase3-cognition-context.md). The phase had a final check by two fresh-context Claude reviewers adjudicated by the advisor (owner ruling 2026-10-20) in place of Codex; its fix 3.R2 is committed (ADR 0033 §3 amendment accepted by the owner 2026-10-20). Live check 3g.2 ran 2026-10-20: readiness, context pack (`shadow`, `on`), grounded `open-pos` and `explain` passed live; the model proposed no draft PO, so no live write ran; live check partial: no live write (Level 4 in the handoff); merged to `main` ([PR #7](https://github.com/thanhnc261/e-agent/pull/7), `b52f979`) |
| 4 | Conversation and chat UX | Conversation model (ADR 0023: a thread of runs with carried context), chat defects (`status.undefined`, label noise, Context chip copy, sidebar), UI threads through the `ag-*` skills with owner gates. Toggle `features.conversations`, falling back to the per-run task view. | [Phase 4 detailed plan](plans/2026-10-20-phase4-conversation-chat.md) (approved by the owner 2026-10-20; from the [core plan](plans/2026-10-12-core-conversation-cognition.md) Phases 0–1) | **Implemented** 2026-10-22: tasks 4a.1–4f.1 (4e.6 deferred at G-A to a named follow-up; 4e.5 shipped), behind `features.conversations`, `off` by default. Levels 1–3 pass on fixtures and Postgres; the phase had a final check by two fresh-context Claude reviewers adjudicated by the advisor. Live check 4f.2 pending; not merged. |
| 5 | Odoo integration from ERP-Bench | Capability map. Read tools (SO, PO, MO, BOM, workcenters, products and stock, vendor offers, partners, invoices). Write tools as action-plan steps with lineage, rules and verifiers. Every new capability declares effect (ADR 0029) and data classes (ADR 0030). Evidence-export authorization before live evaluation. Planning support. Evaluation. ADR 0024 sets the approval model; the evaluation substrate is an owner decision. | [Odoo tools plan](plans/2026-10-12-odoo-tools-from-erp-bench.md); detailed per sub-phase | Planned; reads can start after Phase 2 |
| H | Development harness (parallel track) | Context manifest, task/plan/handoff/review contracts, scope and gate checks, engineering skills next to the `ag-*` UI skills, Claude subagents and hooks for protected paths. | [harness plan](plans/2026-10-12-dev-harness.md); last: [H4 adapters](plans/2026-10-13-harness-h4-adapters.md), [handoff](handoffs/2026-10-13-harness-h4.md) | H0–H4 done 2026-10-14 (CLI, `eng-*` skills, Claude Code hooks, permissions and subagents); piloted in Phase 1 (findings in `harness/state/1/harness-pilot-log.md`); H5 (measure and adopt) runs with Phase 2 |
| 6 | Concurrency, scale and request safety | Design P0/P1 remainder: run slots with per-tenant fairness (C1), LISTEN streaming (C2), durable writer lease (C3), API and worker process roles (C4), cross-process cancel, **correlation id on events and work** (C17 part 1 rest), **API request limits and bounded reads** (Q3, §12.4), load harness and capacity baseline (R1, R2, Q2). | to write | Deferred by owner priority |
| 7 | Security, tenancy and audit hardening | **Authorization bundle** (C16, Q1): role mappings, task and capability grants, approval scopes, run visibility. Tenancy: RLS with control and tenant roles, OIDC, vault (C15, U8). Audit: database-enforced append-only grants and access log for reads and exports (C17 part 2, Q4). Threat-model review per release. Retention, purge role, tenant offboarding and subject deletion (ADR 0030); telemetry. | to write | Later |
| 8 | Integration breadth and genericity | **MCP binding** (C12, U1, §10.2). **Event-triggered runs** (C13, R5): service principal, idempotent triggers, approver notification and inbox, per-task TTL. **Delegated connections** (ADR 0012/0013): `connect.required` finding, OAuth engine, admin and user integration pages. **Second, non-ERP domain pack** for a real use case, plus the G-criteria fitness tests (U8, U9, §2.2). UI host adapters and cross-origin embedding (ADR 0011). BigQuery read-only analytics adapter [C] (ADR 0001). | to write | Later |
| 9 | Knowledge and memory [C] | Knowledge service with canonical claims and hybrid projection (C14, U7); memory candidates and promotion path with `MemoryStore` port (C10, U5); graph projection only for named competency questions. Durable-engine substrate [C]. Each item starts only when its trigger fires (§8, §9). | to write | Conditional |
| Q | Release qualification (recurring) | ADR 0010 protocol on the frozen candidate: three live trials per enabled task, pass^3, unsafe outcomes block the release; evidence bundles and release report. Runs after Phase 5 and after every later phase that changes task behaviour. | to write | Recurring |

**Order and dependencies:**
- Phase 8 needs 2 (task definitions) and 7 (authorization bundle for triggered runs and delegated connections). Phase 9 starts only on its triggers.
- Phase 1 runs first.
- Phase 2 needs 1c (kernel split), and 1d (plugin boundary) if the owner approves it.
- Phase 3 needs 2.
- Phase 4 needs 3 (carried context uses the ContextAssembler); its chat defects (core plan Phase 0) may land early as small fixes.
- Phase 5 reads can begin after 2; its writes need 2 (action plans) and 3 (grounded answers).
- The harness track H runs alongside from Phase 1 and becomes the way later phases are executed.

## Design coverage

Every target-architecture ADR candidate and criterion maps to a phase. Status tags from the design: `[I]` implemented, `[Pa]` partial, `[P]` proposed, `[C]` conditional.

| Item | Phase | | Item | Phase |
|---|---|---|---|---|
| C1 run slots, fairness | 6 | | R1 scale, R2 concurrency | 6 |
| C2 LISTEN streaming | 6 | | R3 plugin-driven | [I]; kept in 1a |
| C3 write admission [I] + lease | 6 | | R4 reusable packages | [I]; layout preserved in 1a (`dists/`) |
| C4 API/worker roles | 1c (modules), 6 (processes) | | R5 event-driven | 8 |
| C5 FastAPI stays | decision, no work | | R6 HTTP framework | [I] |
| C6 run transition table | [I] (WP1) | | U1 explicit integration | 5 (native), 8 (MCP) |
| C7 swappable-runtime boundary | 1c, 3 (driver conformance) | | U2 swappable core | 3 |
| C8 step records, ledger, KERNEL-REPEAT | 2, 3 | | U3 traceable state | 2, 3 |
| C9 ContextAssembler | 3 | | U4 self-correction | 3 |
| C10 memory | 9 | | U5 memory | 9 |
| C11 task definitions, acceptance | 2 | | U6 context management | 3 |
| C12 MCP binding | 8 | | U7 knowledge graph | 9 |
| C13 triggers, approver inbox | 8 (sweeper [I] in WP1) | | U8 multi-domain production | 7, 8 |
| C14 knowledge service | 9 | | U9 generic core | 8 (G-criteria) |
| C15 RLS, OIDC, vault | 7 | | Q1 authorization | 7 (self-approval [I]) |
| C16 authorization bundle | 7 (self-approval [I]) | | Q2 high load | 6 |
| C17 audit integrity | actor [I]; 6 (correlation id); 7 (grants, access log) | | Q3 concurrent requests | paging [I]; 6 (limits) |
| C18 explanation contract | reason codes [I]; 3 (rationale, projection) | | Q4 auditing | 6, 7 |
| C20 conversation model ([ADR 0023](adr/0023-conversation-model.md), target §5.7) | 4 | | Q5 explainability | 3 |
| Execution IR / action plans (target §6.4) | 2, ADRs 0024, 0025, 0027–0029 | | ERP-Bench tools (design P3 adapted) | 5 |
| C19 data governance (target §13.3) | ADR 0030: 3, 5, 7 | | | |

Other design documents: HLD and MVP design are the baseline every phase keeps. The integration auth SDK and integration management docs are covered by 8. UI architecture (ADR 0011) is covered by 4 (chat) and 8 (host adapters). The threat model is reviewed in 7 and at every release (Q). The evaluation protocol (ADR 0010) is Q.

## Decisions waiting on the owner

| Decision | Phase | Default if no answer |
|---|---|---|
| Defer concurrency (P0) behind cognition | 6 | Deferred, as in this roadmap |
| Conversation shape (ADR 0023): thread of runs, or one long-lived run | 4 | Thread of runs |
| Approval model for multi-write plans (ADR 0024) | 2/5 | **Decided 2026-10-14:** approve the plan once; benchmark-only auto-approve for `read`/`write_low` only, never in live profiles; nothing modified after approval ([adoption review](reviews/2026-10-14-x-agent-adoption-review.md) D-3, D-4). ADR 0024 records it (Proposed) |
| ERP-Bench evaluation substrate: patterns ported to `odoo19-learning`, or owned bench containers | 5 | Ported patterns |
| ERP-Bench canonical URL (D7) | 5 | Needed before importing any concept |
| Harness: lean, built on Claude Code primitives (manifest, contracts, hooks, subagents); see the [harness plan](plans/2026-10-12-dev-harness.md) | H | Lean; decided 2026-10-12 |

## Done before this roadmap

- MVP kernel, adapters, eight ERP tasks and UI (see [README](../README.md)).
- WP1 correctness: [handoff](handoffs/2026-10-12-wp1-correctness.md).
- Real-agent part B (ADR 0022, live Odoo): [handoff](handoffs/2026-10-12-real-agent.md).
