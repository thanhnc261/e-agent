# e-agent

A plugin-driven enterprise agent application designed for governed business actions, versioned domain knowledge and verifiable outcomes.

**Status: research and design.** No runnable product, package workspace or completed MVP is present yet. The documents below define the implementation baseline.

## Start here

| Document | What it provides |
|---|---|
| [High-level design](docs/high-level-design.md) | Architecture, package boundaries, multi-domain support, knowledge evolution and deployment |
| [MVP detailed design](docs/mvp-detailed-design.md) | Procurement workflow, contracts, state machines, persistence, approvals, recovery and acceptance tests |
| [Implementation plan](docs/implementation-plan.md) and [ADRs](docs/adr/README.md) | Accepted scope and decisions (ADRs 0001–0013) and work packages |
| [Documentation index](docs/README.md) | Design reading order and decision conventions |
| [Research](research/README.md) | Industry sources, ontology research, enterprise controls and architecture reviews |
| [AGENTS.md](AGENTS.md) / [CLAUDE.md](CLAUDE.md) | Instructions for coding agents working on this project |

## First MVP

A real model-driven agent will read synthetic procurement facts, propose a purchase order, validate it against versioned ontology constraints, request human approval, create a draft PO in an isolated Odoo sandbox and independently verify the result.

The demo must expose successful execution, blocked invalid proposals and safe handling of changed approvals or uncertain external results. It must distinguish live ERP outcomes from deterministic fixtures and scripted fault injection.

Procurement is the first vertical slice. [ADR 0001](docs/adr/0001-local-mvp-scope.md) extends the MVP to a local Pydantic AI + Ollama driver, 5–10 common Odoo 19 tasks, a streaming overlay UI for task interaction and approval, and read-only BigQuery analytics. Order confirmation, stock receipt, posted accounting, payments, external CRM providers and Google integrations remain out of scope. Evidence-explanation/governance UI and a governed knowledge graph follow once the execution and evidence foundations work.

## Architecture

```text
CLI / API
    -> application + kernel: policy, approval, actions, evidence
        -> agent driver: model interaction and proposals
        -> domain packs: capabilities, ontology, rules, outcome criteria
        -> provider adapters: authorized execution and source reads
        -> storage adapter: durable run/action records
```

- **Monorepo, modular monolith:** simple initial deployment with independently packaged adapters.
- **Domain-neutral kernel:** ERP and future CRM/document domains register capabilities through public contracts.
- **Provider and connection separation:** Google Workspace/Odoo adapters are distinct from business domains and tenant accounts.
- **Host-controlled execution:** frameworks propose actions; the application owns permission, approval and verification.
- **Replaceable knowledge implementations:** preserve evidence, provenance and semantic contracts while evolving ingestion, retrieval and graph projections.

The product is independent of the separate `enterprise-agent/experiment` research system. That system is a reference, not a runtime dependency.

## Development status and next steps

Only `docs/`, `research/` and project guidance exist at this stage. The package tree in the MVP design is planned, not created.

Implementation starts with workspace/contracts and architecture gates, then a framework execution spike, persisted approvals/recovery, the live Odoo draft workflow and complete demo evidence. Python 3.12+, uv, PostgreSQL, an isolated Odoo environment and a model provider are proposed prerequisites; exact supported versions and setup commands will be documented after bootstrap verification.

There are no installation, server or test commands to run yet. See the [implementation plan](docs/implementation-plan.md) for owner decisions, the proposed toolchain, milestones and work packages, and the [MVP readiness review](docs/reviews/2026-10-06-mvp-readiness-review.md) for what must be decided before coding starts.

## Contribution expectations

Follow [AGENTS.md](AGENTS.md), preserve package dependency direction, keep secrets out of source/evidence, and test policy and recovery behavior as well as successful tasks. Update design documents when contracts change. Report the scope and limitations of evidence; a working demo is not a claim of production readiness or enterprise certification.
