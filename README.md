# e-agent

A plugin-driven enterprise agent application designed for governed business actions, versioned domain knowledge and verifiable outcomes.

**Status: early implementation (milestone M1).** The workspace, contracts and a fixture-only walking skeleton exist; live integrations do not. The documents below define the implementation baseline.

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

| Work package | Status | Evidence |
|---|---|---|
| I00 Environment qualification | Ready to run locally | [runbook](docs/runbooks/i00-environment-qualification.md), `scripts/env_check.py` (needs the owner's machine) |
| I01 Workspace and CI | Done | uv workspace, ruff, mypy strict, import-linter, pytest, wheel clean-install gate, GitHub Actions |
| I02 Contracts and registration | Done (fixture walking skeleton) | Contracts, JCS digest + golden vectors, SDK ports, metadata-only discovery, registry admission, kernel coordinator, CLI demo |
| I03 Rule and ontology slice | Done | `e_agent.adapters.shacl` (pySHACL, SHACL 1.1 + SPARQL); procurement ontology and shapes packaged in `e_agent.erp`; rule matrix, parity and inventory tests |
| I04–I14 | Not started | See the [implementation plan](docs/implementation-plan.md) |

Validation is authoritative (SHACL). Driver and ERP are still **fixtures**: a scripted driver and a fake ERP exercise the real kernel. No model, Odoo, PostgreSQL or UI integration exists yet, and nothing here is evidence of live capability.

### Commands (verified in the development container)

```bash
uv sync                                   # Python 3.12+ and uv required
uv run e-agent demo --approve             # fixture procurement run, approve explicitly
uv run e-agent demo --driver-mode invalid-then-repair --approve   # blocked by PR-003, then repaired
uv run e-agent demo --fault lost-response --approve --reconcile   # UNKNOWN -> read-only reconcile
uv run e-agent demo --scenario zero-shortage                      # verified no-op
uv run e-agent plugins                    # discovered plugins (metadata only)

uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run lint-imports                       # architecture dependency gates
uv run pytest -q
uv run python scripts/check_wheels.py     # each wheel installs/runs outside the repo
```

Python packages share the `e_agent` namespace: `e_agent.contracts`, `e_agent.sdk`, `e_agent.kernel`, `e_agent.erp`, `e_agent.server`.

See the [implementation plan](docs/implementation-plan.md) for owner decisions, milestones and work packages.

## Contribution expectations

Follow [AGENTS.md](AGENTS.md), preserve package dependency direction, keep secrets out of source/evidence, and test policy and recovery behavior as well as successful tasks. Update design documents when contracts change. Report the scope and limitations of evidence; a working demo is not a claim of production readiness or enterprise certification.
