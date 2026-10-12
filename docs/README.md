# Design documentation

These documents define the implementation baseline and qualification process for e-agent. Implementation and tests now exist; design intent and historical implementation-reported results are not substitutes for independent local qualification.

| Document | Purpose |
|---|---|
| [Enterprise overlay adoption plan](plans/2026-10-08-enterprise-overlay-adoption.md) | Proposed phased migration of the enterprise mockup; reusable frontend structure, API dependencies and acceptance gates |
| [Frontend development guide](frontend-development-guide.md) | Proposed component organization, state ownership, tokens, accessibility and extension conventions for that migration |
| [UI redesign implementation](handoffs/2026-10-08-ui-redesign.md) | Task workspace, presentation boundary, verified checks/screenshots and remaining live/backend limits |
| [Remediation retest](reviews/2026-10-07-mvp-remediation-retest.md) | Current candidate changes, observed retests and remaining owner release gates |
| [MVP fix and readiness plan](reviews/2026-10-07-mvp-fix-plan.md) | Ordered corrections, design-boundary ownership, Odoo bridge explanation and release gates |
| [Independent MVP review](reviews/2026-10-07-mvp-review-report.md) | Reproduced safety/interaction findings and NOT_READY verdict for the local live MVP |
| [Requirement/evidence matrix](reviews/2026-10-07-mvp-requirement-matrix.md) | Fixture, PostgreSQL, UI, live model and blocked ERP coverage kept separate |
| [Local test results](reviews/2026-10-07-local-test-report.md) | Newly observed commands/results, trial failures, evidence limitations and cleanup |
| [Sol 6.1 review handoff](handoffs/2026-10-07-sol-6.1-mvp-review.md) | Entry point for independent implementation review and owner-machine qualification |
| [MVP review plan](reviews/2026-10-07-mvp-review-plan.md) | Risk-prioritized source review, known evidence gaps, findings and coverage requirements |
| [Local test plan](testing/2026-10-07-local-test-plan.md) | Staged commands, isolated databases, live Ollama/Odoo/UI checks and evidence/cleanup requirements |
| [High-level design](high-level-design.md) | Product boundaries, components, dependencies, trust, knowledge architecture, evolution and delivery phases |
| [MVP detailed design](mvp-detailed-design.md) | Procurement workflow, contracts, plugin registration, persistence, execution states, recovery, APIs and acceptance gates |
| [Implementation plan](implementation-plan.md) | Task catalog, work packages, gates and local/CI test policy |
| [Target architecture (v2)](target-architecture.md) | Post-MVP target design: swappable runtime, traceable state, self-correction, memory, knowledge, event-driven scale, authorization, audit and explanation; status-tagged against the tree |
| [WP1 correctness plan](superpowers/plans/2026-10-12-target-architecture-wp1-correctness.md) | Bite-sized implementation plan for the verified kernel defects (run transitions, self-approval, event actor, reason codes, approval sweeper, paged events, write admission) and the WP2–WP5 map |
| [Core: conversation, context and cognition plan](superpowers/plans/2026-10-12-core-conversation-cognition.md) | Proposed phased plan (roadmap P1 C11 + P2 C8/C9): visible chat defects, conversation model (ADR 0023), task definitions, step records, progress ledger, ContextAssembler, grounded answers, driver conformance |
| [Odoo tools from ERP-Bench plan](superpowers/plans/2026-10-12-odoo-tools-from-erp-bench.md) | Proposed phased plan (roadmap P3): ERP-Bench-derived Odoo read/write capabilities, action plans (multi-write), approval model (ADR 0024), evaluation substrate; depends on the core plan |
| [ADR index](adr/README.md) | Architecture decisions (all current ones accepted) and template |
| [UI architecture](ui-architecture.md) | Layered default UI with theme, layout, component and whole-UI replacement; conformance suite |
| [Integration management](integration-management.md) | Generic connections, credentials, OAuth and admin pages with no provider-specific UI |
| [Integration auth SDK](integration-auth-sdk.md) | Auth methods, SDK API, tenant app registrations, user-delegated connections, OAuth and API-key flows |
| [Threat model](threat-model.md) | MVP-scoped threats mapped to OWASP Agentic Top 10, with tests |
| [MVP readiness review](reviews/2026-10-06-mvp-readiness-review.md) | Consistency check of all designs/ADRs/plan; blocking decisions and fixes |
| [Architecture review 2026-10-06](reviews/2026-10-06-architecture-review.md) | Findings, quality scenarios, risks and ADR gating |
| [Research index](../research/README.md) | Supporting research, alternatives and source registers |
| [Agent instructions](../AGENTS.md) | Repository conventions for implementation agents |

Read the high-level design first, then the MVP design, then the implementation plan (start with §0). Topic designs (UI, integration management, auth SDK, threat model) refine specific areas. The MVP design specializes the high-level design. Research records explain decisions but may contain superseded alternatives, such as the earlier combined `integrations` distribution. Neither document is evidence that implementation or tests already exist.

Record later material architecture changes as ADRs under `docs/adr/` when the decisions are made. Include context, decision, alternatives, consequences, compatibility/migration impact and verification. Update these designs when an ADR changes their baseline; avoid maintaining contradictory descriptions.
