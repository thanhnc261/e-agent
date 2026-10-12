# e-agent product roadmap

**Owner-approved direction (2026-10-12):**
- clean the repository;
- refactor to a clear structure first;
- build the core runtime around a typed **execution IR**;
- then cognition and conversation;
- then ERP breadth from ERP-Bench, with a development harness alongside.

Every new runtime feature ships **behind a toggle with a fallback** (see Rules).

This roadmap orders the work. Designs say *what* to build: [target architecture](target-architecture.md), [HLD](high-level-design.md), [MVP design](mvp-detailed-design.md) and the [ADRs](adr/README.md). Each phase has its own plan file. A phase starts only after its **detailed plan** has been written, linked here and reviewed.

## Rules for every phase

1. **Detailed plan before implementation.** Each phase gets a bite-sized plan in `docs/plans/`; the folder becomes current in Phase 1, and until then plans live in `docs/superpowers/plans/`. Execution follows that plan with per-task review and end-to-end verification:
   - the full gate;
   - the Postgres run;
   - `make e2e`;
   - a live check on the `odoo19-learning` sandbox at the end of the phase.
2. **Design first.** A phase implements design sections and ADRs. A change to a contract or a boundary needs an ADR, and the phase merges only after the owner accepts it. If code and design disagree, fix the design or the code explicitly; never let them drift silently.
3. **Toggles and fallback.** Every new runtime feature (execution IR, ContextAssembler, conversation model, grounded answers, action plans) has a profile feature toggle with modes `off | shadow | on`.
   - **`shadow`**: computes and records the new path but acts on the existing one, so the two can be compared without risk.
   - **`on` with a fallback**: if the new path fails *before any write is reserved* (for example IR compilation or validation errors), the run falls back to the existing tested path and records a `feature.fallback` event with a reason code.
   - **After a write is reserved there is no fallback.** The run fails closed or goes to reconciliation. Fallback never bypasses approval, admission, verification or the transition table.
   - `/health/ready` reports the toggles, and the evidence bundle records them.
4. **Trust anchor unchanged.** The run and action state machines, gateway, approval digests, admission and verification stay in the kernel. Model output is a proposal.
5. **Boundaries.** Only the `odoo19-learning` sandbox and containers e-agent creates are touched. `odoo-bench` and the lab experiments never are.

## Phases

| Phase | Name | Content | Plan | Status |
|---|---|---|---|---|
| 0 | Cleanup | Archive superseded plans, reports and mockups. Fix the `evidence/` ignore bug that hid UI source. Slug two research filenames. | done in `chore/cleanup-and-roadmap` | **Done** 2026-10-12 |
| 1 | Structure refactor | **1a** One layer-grouped code tree `src/e_agent/{contracts,sdk,kernel,erp,adapters/*,server}` with no repeated folder names. Per-distribution build configs in `dists/<name>/` (still independently releasable; spike-validated). Tests in `tests/unit/<part>/`. Editor hides caches. **1b** Docs into `docs/{design,plans,specs,adr,handoffs,reviews,runbooks}`, links rewritten, AGENTS.md and CLAUDE.md rewritten. **1c** Kernel split behind the `RunCoordinator` facade (SR-06) and server `worker`/`streaming` modules. No behaviour change. | [Phase 1 detailed plan](superpowers/plans/2026-10-12-phase1-structure-refactor.md) | Planned (detailed) |
| 2 | Core runtime with execution IR | First task: feature-toggle infrastructure (`Profile.features`, `off/shadow/on`, `feature.fallback` events, `/health/ready`). Then a typed IR the runtime executes: **TaskDefinition** (C11: goal, acceptance spec, fixed capability set) → **ActionPlan** (ordered steps with dependencies, lineage and one approval digest; multi-write runs) → **StepRecord** (C8). The driver emits IR; the kernel validates, approves, dispatches step by step and verifies. Toggle `features.execution_ir: off/shadow/on`, falling back to today's single-action loop before any write is reserved. ADRs C8, C11, plus a new ADR for the action-plan IR. | detailed plan written at phase start | Planned |
| 3 | Cognition and context | Progress ledger (§6.2), ContextAssembler (C9; §7.2 layers, budgets, clearing, §7.4 rendering), a grounded answer contract (citations verified against recorded evidence), driver conformance suite, `KERNEL-REPEAT`. Toggle `features.context_assembler`, falling back to the current driver history. | from [core plan](superpowers/plans/2026-10-12-core-conversation-cognition.md) Phases 3–4; detailed at phase start | Planned |
| 4 | Conversation and chat UX | Conversation model (ADR 0023: a thread of runs with carried context), chat defects (`status.undefined`, label noise, Context chip copy, sidebar), UI threads through the `ag-*` skills with owner gates. Toggle `features.conversations`, falling back to the per-run task view. | from [core plan](superpowers/plans/2026-10-12-core-conversation-cognition.md) Phases 0–1; detailed at phase start | Planned |
| 5 | Odoo integration from ERP-Bench | Capability map. Read tools (SO, PO, MO, BOM, workcenters, products and stock, vendor offers, partners, invoices). Write tools as action-plan steps with lineage, rules and verifiers. Planning support. Evaluation. ADR 0024 sets the approval model; the evaluation substrate is an owner decision. | [Odoo tools plan](superpowers/plans/2026-10-12-odoo-tools-from-erp-bench.md); detailed per sub-phase | Planned; reads can start after Phase 2 |
| H | Development harness (parallel track) | Context manifest, task/plan/handoff/review contracts, scope and gate checks, engineering skills next to the `ag-*` UI skills, Claude subagents and hooks for protected paths. | [harness plan](superpowers/plans/2026-10-12-dev-harness.md) | Planned; starts with Phase 1 |
| 6 | Concurrency and scale | Design roadmap P0/P1 remainder: run slots, LISTEN streaming, durable writer lease, worker role, cross-process cancel, load harness. | to write | Deferred by owner priority |
| 7 | Knowledge, memory and production hardening | Design roadmap P4/P5: knowledge service, memory candidates, RLS, OIDC, vault, retention, telemetry. | to write | Later |

**Order and dependencies:**
- Phase 1 runs first.
- Phase 2 needs 1c (kernel split).
- Phase 3 needs 2.
- Phase 4 needs 3 (carried context uses the ContextAssembler); its chat defects (core plan Phase 0) may land early as small fixes.
- Phase 5 reads can begin after 2; its writes need 2 (action plans) and 3 (grounded answers).
- The harness track H runs alongside from Phase 1 and becomes the way later phases are executed.

## Decisions waiting on the owner

| Decision | Phase | Default if no answer |
|---|---|---|
| Defer concurrency (P0) behind cognition | 6 | Deferred, as in this roadmap |
| Conversation shape (ADR 0023): thread of runs, or one long-lived run | 4 | Thread of runs |
| Approval model for multi-write plans (ADR 0024): approve the plan once, or auto-approve in a benchmark-only profile | 2/5 | Approve the plan once |
| ERP-Bench evaluation substrate: patterns ported to `odoo19-learning`, or owned bench containers | 5 | Ported patterns |
| ERP-Bench canonical URL (D7) | 5 | Needed before importing any concept |
| Harness: build a lean e-agent harness, or reuse concepts from the `onto-erp-agents` harness | H | Lean, concept reuse with provenance |

## Done before this roadmap

- MVP kernel, adapters, eight ERP tasks and UI (see [README](../README.md)).
- WP1 correctness: [handoff](handoffs/2026-10-12-wp1-correctness.md).
- Real-agent part B (ADR 0022, live Odoo): [handoff](handoffs/2026-10-12-real-agent.md).
