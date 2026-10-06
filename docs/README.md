# Design documentation

These documents define the implementation baseline for e-agent. They describe planned behavior; the repository currently contains research and design, not a runnable application.

| Document | Purpose |
|---|---|
| [High-level design](high-level-design.md) | Product boundaries, components, dependencies, trust, knowledge architecture, evolution and delivery phases |
| [MVP detailed design](mvp-detailed-design.md) | Procurement workflow, contracts, plugin registration, persistence, execution states, recovery, APIs and acceptance gates |
| [Implementation plan](implementation-plan.md) | Task catalog, work packages, gates and local/CI test policy |
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
