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
| I05 Durable kernel | Done | `e_agent.adapters.postgres`: ledger schema, checksummed migrations, CAS, unique reservations, gapless events + NOTIFY, advisory writer lock, persisted continuation, startup `recover()`; kernel suite and store conformance pass on PostgreSQL 16 |
| I04 Local model qualification | Driver done; live qualification pending on the owner's machine | `e_agent.adapters.pydantic_ai` (Pydantic AI 2.54, Ollama): all tools deferred to the kernel, thinking stripped, snapshot/restore; FunctionModel end-to-end tests; `scripts/qualify_model.py` (needs local Ollama) |
| I06 Odoo bridge and adapter | Done (sandbox from source); owner install pending | `addons/e_agent_bridge` (operation ledger with `models.Constraint`, draft-only commands, narrow reads, sandbox seed/reset), `e_agent.adapters.odoo` (JSON-2, API key via `AuthContext`), local envelope-encrypted secret store, credential service. 7 live tests passed against real Odoo 19 (idempotency, 6-way race → 1 PO, lost response → reconcile, marker check). [Runbook](docs/runbooks/i06-odoo-bridge.md) |
| I07 Procurement vertical slice | Done with scripted driver on live Odoo; live-model runs pending | ERP-01 shortage and ERP-02 recommendation as verified structured answers (new `answer` effect: no approval, independent recomputation from fresh reads), ERP-03 draft PO; all three verified against live Odoo 19; redacted evidence bundles (`--evidence-out`, `e-agent evidence`) |
| I08 Streaming API and UI layers | Done | `e-agent serve`: FastAPI API v1 (loopback session + CSRF, `Idempotency-Key`, typed snapshots, native SSE with `Last-Event-ID`/`after_sequence` resume, `ApprovalPresentation` with changed-field marking); `ui/` pnpm workspace: `@e-agent/client` (types generated from the checked-in OpenAPI), `ui-core` (run store, approval state machine, JCS digest check on the shared golden vectors, sanitizer, vi/en), `tokens` (DTCG → CSS, contrast gates), `ui-react`, `components` (React Aria), `layouts` (overlay/sidebar/full-page), `apps/web`, `<e-agent-overlay>` (Shadow DOM); dependency-cruiser layer rules and a provider-neutrality gate |
| I09 Live UI workflow | Done on the fixture server | `ui-conformance` (Playwright): the 8 §6 checks plus theming/embedding, run against the default app, the overlay on a hostile neutral host page and a non-React reference UI; live flows complete/reject/reload against the real kernel. Generic `HostContext` hints are resolved through connection mappings or dropped |
| I10–I14 | Not started | See the [implementation plan](docs/implementation-plan.md) |

Validation is authoritative (SHACL); the ledger is PostgreSQL; the Odoo adapter has been exercised against a real Odoo 19 sandbox built from source. Live model runs (Ollama) are not done yet; fixture runs are labelled `environment=fixture` and are not evidence of live capability. The UI has been exercised against the fixture server, not against live Odoo.

### Commands (verified in the development container)

```bash
uv sync                                   # Python 3.12+ and uv required
uv run e-agent demo --approve             # fixture procurement run, approve explicitly
uv run e-agent demo --driver-mode invalid-then-repair --approve   # blocked by PR-003, then repaired
uv run e-agent demo --fault lost-response --approve --reconcile   # UNKNOWN -> read-only reconcile
uv run e-agent demo --scenario zero-shortage                      # verified no-op
uv run e-agent demo --task shortage                               # ERP-01 verified answer
uv run e-agent demo --task recommend                              # ERP-02 verified answer
uv run e-agent demo --approve --evidence-out run.json             # redacted evidence bundle
uv run e-agent plugins                    # discovered plugins (metadata only)

# Live model qualification (owner's machine with Ollama; fixture ERP)
uv run python scripts/qualify_model.py --model qwen3-coder:30b --trials 10 --out evals/reports/qualification.json

uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run lint-imports                       # architecture dependency gates
uv run pytest -q
uv run python scripts/check_wheels.py     # each wheel installs/runs outside the repo

# HTTP API + web UI (loopback only; Node 22.12+/24 and pnpm 10 for ui/)
(cd ui && pnpm install && pnpm build)
uv run e-agent serve --static ui/dist/web # http://127.0.0.1:8787/ (app), /host.html (overlay), /reference/
uv run python scripts/export_openapi.py   # after API changes; then (cd ui && pnpm gen)
(cd ui && pnpm check && pnpm conformance) # types, unit tests, layer rules, neutrality, build, Playwright

# PostgreSQL ledger (profile store.kind=postgres; DSN only via environment)
export E_AGENT_PG_DSN=postgresql://user@host:5432/e_agent   # e-agent's own database, never Odoo's
uv run e-agent --profile my-profile.json migrate
uv run e-agent --profile my-profile.json recover
E_AGENT_TEST_PG_DSN=$E_AGENT_PG_DSN E_AGENT_TEST_STORE=postgres uv run pytest -q packages/kernel
```

Python packages share the `e_agent` namespace: `e_agent.contracts`, `e_agent.sdk`, `e_agent.kernel`, `e_agent.erp`, `e_agent.server`.

See the [implementation plan](docs/implementation-plan.md) for owner decisions, milestones and work packages.

## Contribution expectations

Follow [AGENTS.md](AGENTS.md), preserve package dependency direction, keep secrets out of source/evidence, and test policy and recovery behavior as well as successful tasks. Update design documents when contracts change. Report the scope and limitations of evidence; a working demo is not a claim of production readiness or enterprise certification.
