# Design documentation

These documents define the implementation baseline for e-agent. They describe planned behavior; the repository currently contains research and design, not a runnable application.

| Document | Purpose |
|---|---|
| [High-level design](high-level-design.md) | Product boundaries, components, dependencies, trust, knowledge architecture, evolution and delivery phases |
| [MVP detailed design](mvp-detailed-design.md) | Procurement workflow, contracts, plugin registration, persistence, execution states, recovery, APIs and acceptance gates |
| [Research index](../research/README.md) | Supporting research, alternatives and source registers |
| [Agent instructions](../AGENTS.md) | Repository conventions for implementation agents |

Read the high-level design first, then the MVP design. The MVP design specializes the high-level design. Research records explain decisions but may contain superseded alternatives, such as the earlier combined `integrations` distribution. Neither document is evidence that implementation or tests already exist.

Record later material architecture changes as ADRs under `docs/adr/` when the decisions are made. Include context, decision, alternatives, consequences, compatibility/migration impact and verification. Update these designs when an ADR changes their baseline; avoid maintaining contradictory descriptions.
