# e-agent

A plugin-driven enterprise agent application designed for governed business actions, versioned domain knowledge and verifiable outcomes.

**Status: MVP remediation candidate; local live release is NOT_READY.** Phase 2 (execution IR) is done and merged to `main`. Phase 3 (cognition and context) is done and merged to `main` ([PR #7](https://github.com/thanhnc261/e-agent/pull/7)), verified on fixtures behind three toggles that are all `off` by default (`context_assembler`, `kernel_repeat`, `grounded_answers`; see [Phase 3 toggles](#phase-3-toggles-cognition-and-context)). Its final check by two fresh-context Claude reviewers adjudicated by the advisor (owner ruling 2026-10-20) in place of Codex found one design tightening, fixed in task 3.R2 (the ADR 0033 §3 amendment was accepted by the owner 2026-10-20). Its live check (task 3g.2, 2026-10-20) passed for readiness, the context pack in `shadow` and `on`, a grounded `open-pos` answer and `explain`; the live model did not propose the draft PO, so no live write ran and the write path with the pack stays fixture evidence. See the [Phase 3 handoff](docs/handoffs/2026-10-20-phase3-cognition-context.md) and the [roadmap](docs/roadmap.md) status column. The Phase 4 (conversation and chat UX) [plan](docs/plans/2026-10-20-phase4-conversation-chat.md) is a draft awaiting owner approval. Kernel, adapters, PostgreSQL storage, eight ERP tasks and replaceable UI are implemented. The approved review fixes have passed local source, persistent-ledger and UI checks; frozen Ollama qualification is recorded separately. The owner's exact Odoo sandbox, upgraded bridge and integrated model/API/UI runs with human approval still need qualification. The requested UI redesign is documented in the [2026-10-08 handoff](docs/handoffs/2026-10-08-ui-redesign.md), and the enterprise overlay adoption in the [2026-10-09 implementation results](docs/handoffs/2026-10-08-enterprise-overlay-implementation-results.md); both were verified against deterministic fixtures only and do not change this readiness claim. See the [remediation retest](docs/reviews/2026-10-07-mvp-remediation-retest.md); earlier implementation reports are historical evidence for their stated environments.

Work is ordered by the [roadmap](docs/roadmap.md). Its status column shows the current phase, and each phase has a detailed plan in [docs/plans](docs/plans/).

## Start here

| Document | What it provides |
|---|---|
| [Roadmap](docs/roadmap.md) | Phase order, rules for every phase, current status and the plan for each phase |
| [Current remediation retest](docs/reviews/2026-10-07-mvp-remediation-retest.md) | Implemented corrections, observed checks, retained failures and owner release gates |
| [Approved MVP fix plan](docs/reviews/2026-10-07-mvp-fix-plan.md) | Corrections, design boundaries, bridge explanation and remaining release gates |
| [Independent MVP review (2026-10-07)](docs/reviews/2026-10-07-mvp-review-report.md) | NOT_READY verdict, reproduced findings, requirement matrix and newly observed local test results |
| [Review and local test handoff for Sol 6.1](docs/handoffs/2026-10-07-sol-6.1-mvp-review.md) | Independent review plan, staged owner-machine tests, evidence and readiness criteria |
| [High-level design](docs/design/high-level-design.md) | Architecture, package boundaries, multi-domain support, knowledge evolution and deployment |
| [MVP detailed design](docs/design/mvp-detailed-design.md) | Procurement workflow, contracts, state machines, persistence, approvals, recovery and acceptance tests |
| [Implementation plan](docs/design/implementation-plan.md) and [ADRs](docs/adr/README.md) | Accepted scope and decisions (ADRs 0001–0017) and work packages |
| [Documentation index](docs/README.md) | Design reading order and decision conventions |
| [Research](research/README.md) | Industry sources, ontology research, enterprise controls and architecture reviews |
| [AGENTS.md](AGENTS.md) / [CLAUDE.md](CLAUDE.md) | Instructions for coding agents working on this project |

## Agentic overlay design prototype

The [adoption plan](archive/docs/plans/2026-10-08-enterprise-overlay-adoption.md) maps this design into the existing application in staged, testable changes, and the [frontend development guide](docs/design/frontend-development-guide.md) covers reusable components, folder structure, state ownership, tokens and accessibility.

Work packages FE-00 to FE-07 and API-01 are implemented (2026-10-09): module extraction with pinned public exports, Calm semantic tokens with independent theme/appearance/density dimensions, a shared task surface across the four placements, standalone Overview / Session work / Connections routes, and the member-readable `GET /v1/me/task-catalog` and `GET /v1/me/connections` read models ([ADR 0017](docs/adr/0017-member-discovery-read-models.md)). Verified against deterministic fixtures: `pnpm --dir ui check` (146 unit tests) and 135 browser conformance cases, after correcting five defects found by an [independent check](docs/reviews/2026-10-09-overlay-implementation-check.md). No cross-session work inbox, proposal editing, administrative connection management, delegated OAuth or cross-origin embedding exists, and no human usability or screen-reader study has been run. See the [implementation results](docs/handoffs/2026-10-08-enterprise-overlay-implementation-results.md).

The [enterprise-wide research and mockup study](research/14-enterprise-wide-agent-experience.md) presents a neutral workspace for customer handoffs, knowledge answers, IT support, onboarding and procurement, with connection scope and separate action approvals. Calm, AI Presence and Operator appearances remain available. All integrations and results are synthetic; this is a product-vision prototype, not implemented cross-domain support. The [original procurement prototype](archive/research/mockups/procurement-overlay-v1/index.html) is preserved.

Run `python3 -m http.server 4178 --bind 127.0.0.1 --directory research/mockups/agentic-overlay` from the repository root, then open `http://127.0.0.1:4178`. Choose a workflow from Overview, inspect Connections, and use the assistant header for appearance and placement. The bottom Design Study controls preview synthetic task states. See [QA notes](archive/research/mockups/agentic-overlay/QA.md) for reproducible checks.

## First MVP

A real model-driven agent will read synthetic procurement facts, propose a purchase order, validate it against versioned ontology constraints, request human approval, create a draft PO in an isolated Odoo sandbox and independently verify the result.

The demo must expose successful execution, blocked invalid proposals and safe handling of changed approvals or uncertain external results. It must distinguish live ERP outcomes from deterministic fixtures and scripted fault injection.

Procurement is the first vertical slice. [ADR 0001](docs/adr/0001-local-mvp-scope.md) extends the MVP to a local Pydantic AI + Ollama driver, 5–10 common Odoo 19 tasks, a streaming overlay UI for task interaction and approval, and read-only BigQuery analytics in the original scope. The approved remediation gate retains all eight ERP tasks and defers live BigQuery, desktop and full knowledge governance. Order confirmation, stock receipt, posted accounting, payments, external CRM providers and Google integrations remain out of scope. Evidence-explanation/governance UI and a governed knowledge graph follow once the execution and evidence foundations work.

## Architecture

```text
CLI / API
    -> application + kernel: policy, approval, actions, evidence
        -> agent driver: model interaction and proposals
        -> domain packs: capabilities, ontology, rules, outcome criteria
        -> provider adapters: authorized execution and source reads
        -> storage adapter: durable run/action records
```

- **Monorepo, modular monolith:** simple initial deployment with independently packaged adapters. All Python code is one layer-grouped tree, `src/e_agent/{contracts,sdk,kernel,server,adapters/*,plugins/*}`: a domain-neutral core, the infrastructure adapters under `adapters/`, and plugin areas under `plugins/`, of which ERP (`plugins/erp/{domain,odoo,simulator}`) is the first ([ADR 0026](docs/adr/0026-plugin-layout-and-reusable-core.md)). Contracts, SDK, kernel and server never import a plugin (import-linter); each of the 12 distributions has its build config in `dists/<name>/` and is released as a wheel. The core (contracts, plugin SDK, kernel, server and the infrastructure adapters) installs and starts without any ERP distribution; the code-less `e-agent-erp` bundle installs the ERP product (server, ERP domain, Odoo adapter and simulator).
- **Domain-neutral kernel:** ERP and future CRM/document domains register capabilities through public contracts.
- **Provider and connection separation:** Google Workspace/Odoo adapters are distinct from business domains and tenant accounts.
- **Host-controlled execution:** frameworks propose actions; the application owns permission, approval and verification.
- **Replaceable knowledge implementations:** preserve evidence, provenance and semantic contracts while evolving ingestion, retrieval and graph projections.

The product is independent of the separate `enterprise-agent/experiment` research system. That system is a reference, not a runtime dependency.

## Historical implementation milestones

This table summarizes the 2026-10-06 implementation report. Its live Odoo results used the previous bridge in a development sandbox. Current acceptance, model results and owner blockers are recorded in the [remediation retest](docs/reviews/2026-10-07-mvp-remediation-retest.md).

| Work package | Status | Evidence |
|---|---|---|
| I00 Environment qualification | Ready to run locally | [runbook](docs/runbooks/i00-environment-qualification.md), `scripts/env_check.py` (needs the owner's machine) |
| I01 Workspace and CI | Done | uv workspace, ruff, mypy strict, import-linter, pytest, wheel clean-install gate, GitHub Actions |
| I02 Contracts and registration | Done (fixture walking skeleton) | Contracts, JCS digest + golden vectors, SDK ports, metadata-only discovery, registry admission, kernel coordinator, CLI demo |
| I03 Rule and ontology slice | Done | `e_agent.adapters.shacl` (pySHACL, SHACL 1.1 + SPARQL); procurement ontology and shapes packaged in `e_agent.plugins.erp.domain`; rule matrix, parity and inventory tests |
| I05 Durable kernel | Done | `e_agent.adapters.postgres`: ledger schema, checksummed migrations, CAS, unique reservations, gapless events + NOTIFY, advisory writer lock, persisted continuation, startup `recover()`; kernel suite and store conformance pass on PostgreSQL 16 |
| I04 Local model qualification | Driver done; live qualification pending on the owner's machine | `e_agent.adapters.pydantic_ai` (Pydantic AI 2.54, Ollama): all tools deferred to the kernel, thinking stripped, snapshot/restore; FunctionModel end-to-end tests; `scripts/qualify_model.py` (needs local Ollama) |
| I06 Odoo bridge and adapter | Done (sandbox from source); owner install pending | `addons/e_agent_bridge` (operation ledger with `models.Constraint`, draft-only commands, narrow reads, sandbox seed/reset), `e_agent.plugins.erp.odoo` (JSON-2, API key via `AuthContext`), local envelope-encrypted secret store, credential service. 7 live tests passed against real Odoo 19 (idempotency, 6-way race → 1 PO, lost response → reconcile, marker check). [Runbook](docs/runbooks/i06-odoo-bridge.md) |
| I07 Procurement vertical slice | Done with scripted driver on live Odoo; live-model runs pending | ERP-01 shortage and ERP-02 recommendation as verified structured answers (new `answer` effect: no approval, independent recomputation from fresh reads), ERP-03 draft PO; all three verified against live Odoo 19; redacted evidence bundles (`--evidence-out`, `e-agent evidence`) |
| I08 Streaming API and UI layers | Done | `e-agent serve`: FastAPI API v1 (loopback session + CSRF, `Idempotency-Key`, typed snapshots, native SSE with `Last-Event-ID`/`after_sequence` resume, `ApprovalPresentation` with schema labels and current/proposal comparison); `ui/` pnpm workspace: `@e-agent/client` (types generated from the checked-in OpenAPI), `ui-core` (run store, approval state machine, JCS digest check on the shared golden vectors, sanitizer, vi/en), `tokens` (DTCG → CSS, contrast gates), `ui-react`, `components` (React Aria task workspace, readable exact approvals, verified-result/source inspectors), `layouts` (overlay/sidebar/full-page), `apps/web`, `<e-agent-overlay>` (Shadow DOM); dependency-cruiser layer rules and a provider-neutrality gate |
| I09 Live UI workflow | Done on the fixture server | `ui-conformance` (Playwright): the 8 §6 checks plus theming/embedding, run against the default app, the overlay on a hostile neutral host page and a non-React reference UI; live flows complete/reject/reload against the real kernel. Generic `HostContext` hints are resolved through connection mappings or dropped |
| I10 Five-task gate | Done with scripted driver on live Odoo; live-model runs pending | ERP-04 amend draft RFQ (quantity/date at the read revision; stale or non-draft blocked by AM-001/AM-002 and re-checked atomically by the bridge), ERP-05 draft quotation (archived customer, unsaleable product and off-list price blocked; never confirmed or sent) |
| I11 Eight-task expansion | Done with scripted driver on live Odoo; live-model runs pending | ERP-06 late sales orders and ERP-08 overdue invoices as verified read-only answers at an explicit as-of date; ERP-07 CRM lead (owner must be a team member; repeated commands never duplicate). New `sales`, `crm`, `receivables` bounded contexts; 10 live tests against Odoo 19 (`test_odoo_live_tasks.py`) |
| I12–I13 BigQuery | Deferred from the approved local ERP readiness gate | Original D6 project/data permission remains unresolved |
| I14 Release qualification | Done for the repository scope; owner gates open | [Qualification report](archive/docs/release/mvp-qualification-report.md), `scripts/release_report.py` (21-case matrix), [demo](docs/runbooks/demo.md) and [recovery/reset](docs/runbooks/recovery-and-reset.md) runbooks; T16/T17 mitigations implemented. Open: live model qualification, owner's `odoo19-learning` install, BigQuery (D6) |

Validation is authoritative (SHACL); the ledger is PostgreSQL; the Odoo adapter has been exercised against a real Odoo 19 sandbox built from source. Current live-model/fixture-ERP qualification is tracked in the [remediation retest](docs/reviews/2026-10-07-mvp-remediation-retest.md); the [2026-10-06 qualification report](archive/docs/release/mvp-qualification-report.md) predates the independent review. fixture runs are labelled `environment=fixture` and are not evidence of live capability. The UI has been exercised against the fixture server, not against live Odoo.

### Commands (verified in the development container)

For manual end-to-end testing, run `make dev` from the repository root. It builds the UI assets, starts the backend at `http://127.0.0.1:8787` and starts the Vite frontend at `http://127.0.0.1:5173`. Open the frontend for hot reload, `/host.html` for the overlay, or `/reference/` for the reference UI. API/SSE and built embedded assets are proxied through the frontend origin. Ctrl+C stops both owned processes; either process exiting also stops its sibling. The default backend is the real agent: `profiles/dev-ollama.json` runs the Pydantic AI driver on local Ollama (model `e-agent-mvp-qwen3-coder-20261007`, see below) against the fixture ERP data and an in-memory ledger, so the model interprets what you type. `make dev PROFILE=` uses the ERP simulator's fixture profile (`src/e_agent/plugins/erp/simulator/fixture_profile.json`) with the deterministic scripted driver, which ignores the text and always proposes the same draft PO.

```bash
make setup                    # first use: locked Python and frontend dependencies
make browser-install          # first use: Chromium for Playwright
make dev                      # backend + frontend for manual testing
make backend                  # backend with built app, independently
make frontend                 # Vite frontend, independently; requires the backend
make e2e                      # build + Playwright using its own isolated fixture server
make dev BACKEND_PORT=8887 FRONTEND_PORT=5174
make dev PROFILE=profiles/my.local.json  # explicitly use your configured backend profile
make dev PROFILE=                        # scripted fixture driver (deterministic demo, ignores the typed task)
make help
```

Secret scan and dependency audit (the CI `security` job runs the same checks; PR-25, PR-39). Install [gitleaks](https://github.com/gitleaks/gitleaks/releases) 8.28.0 from a verified release first:

```bash
gitleaks git --redact -c .gitleaks.toml .         # full history; prints "N commits scanned", never the secret
uv export --frozen --format requirements-txt --no-hashes --no-emit-workspace -o /tmp/requirements.txt
uvx --from pip-audit==2.9.0 pip-audit -r /tmp/requirements.txt --no-deps --disable-pip
pnpm --dir ui audit --prod                         # production UI dependencies
```

A finding fails the run. Allowlist an entry only for a test fixture string, in `.gitleaks.toml` with its reason, or with `--ignore-vuln <id>` and a comment giving the reason.

Use the header **View** selector to choose **Compact**, **Workbench**, **Docked**, or **Workspace** (standalone only). To open the expanded enterprise overlay directly, use `http://127.0.0.1:5173/?layout=workbench`, then open its launcher. Embedded hosts also accept `layout="workbench"`. Switching retains the active task and unsent draft and returns any open confirmation to review. See [overlay research and design](research/11-enterprise-agent-overlay-design.md).

`make e2e` always uses the fixture backend and its own port (`E2E_PORT=8791` by default), independent of `PROFILE` or a running dev session. It does not perform live ERP/model qualification. Frontend source changes hot-reload in the standalone app; rebuild/restart `make dev` after changing embedded overlay/reference sources to refresh their built assets. A fixture backend restart loses its in-memory runs.

```bash
uv sync                                   # Python 3.12+ and uv required
export E_AGENT_PROFILE="$PWD/src/e_agent/plugins/erp/simulator/fixture_profile.json"  # the server ships no profile (or pass --profile)
uv run e-agent demo --approve             # fixture procurement run, approve explicitly
uv run e-agent demo --driver-mode invalid-then-repair --approve   # blocked by PR-003, then repaired
uv run e-agent demo --fault lost-response --approve --reconcile   # UNKNOWN -> read-only reconcile
uv run e-agent demo --scenario zero-shortage                      # verified no-op
uv run e-agent demo --task shortage                               # ERP-01 verified answer
uv run e-agent demo --task recommend                              # ERP-02 verified answer
uv run e-agent demo --approve --evidence-out run.json             # redacted evidence bundle
uv run e-agent demo --task amend-rfq --driver-mode invalid-then-repair --approve  # ERP-04: stale revision blocked, repaired
uv run e-agent demo --task quotation --approve                    # ERP-05 draft quotation
uv run e-agent demo --task late-orders                            # ERP-06 verified answer
uv run e-agent demo --task crm-lead --approve                     # ERP-07 lead
uv run e-agent demo --task overdue-invoices                       # ERP-08 verified answer
uv run e-agent plugins                    # discovered plugins (metadata only)
uv run e-agent --profile my-profile.json explain <run_id>  # a stored run's explanation as JSON (ids, versions, digests, statuses only; no model call)

# Local model + fixture ERP qualification; pin existing weights/context explicitly
ollama create e-agent-mvp-qwen3-coder-20261007 -f profiles/ollama-mvp.Modelfile
uv run python scripts/qualify_model.py --model e-agent-mvp-qwen3-coder-20261007:latest --task draft-po --mode release --trials 10 --out evals/reports/draft-po.json
# Repeat --task for shortage, recommend, amend-rfq, quotation, late-orders, crm-lead, overdue-invoices
# Fixture/harness approval results do not satisfy the live human-approved release gate.
uv run python scripts/release_report.py --out evals/reports/fixture-release.json   # 21-case fixture matrix: repair_rate, ends, per-case repairs and model_tokens
uv run python scripts/release_report.py --context-assembler shadow --out shadow.json # adds the context columns (context.compared); fixture evidence
uv run python scripts/release_report.py --kernel-repeat shadow --out shadow.json     # adds the repeat columns and repeat_disagreements
uv run python scripts/release_report.py --grounded-answers shadow --out shadow.json  # adds the grounding columns and grounding_unresolved
uv run python scripts/context_ablation.py --out evals/reports/phase3-context-ablation.json  # the corpus with context_assembler off and on; fixture only

uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run lint-imports                       # architecture dependency gates
uv run pytest -q
uv run python scripts/check_wheels.py     # each wheel installs/runs outside the repo
uv run python scripts/check_core_only.py # core wheels + a non-ERP test pack, no ERP wheel; server answers /health/ready
uv build --package e-agent-erp --wheel      # the code-less ERP bundle: server, ERP domain, Odoo adapter, simulator
uv build --package e-agent-kernel --wheel   # one distribution (wheels only; dists/<name>/ builds from src/)
uv run pytest -q tests/conformance/test_harness_context.py  # dev-harness manifest and contract samples
uv run e-agent-harness status                 # dev-harness brief: state, boundaries, one next action
uv run e-agent-harness validate-context       # manifest vs checkout
uv run e-agent-harness gate quick --package tests/unit/kernel   # evidence under harness/state/evidence/ (committed)
uv run e-agent-harness gate core             # runs scripts/check_core_only.py
uv run e-agent-harness gate pg               # needs E_AGENT_TEST_PG_DSN with its own database name; every gate refuses the live ledger's name
uv run e-agent-harness new-task <phase> <id> --feature <F-id> --paths <glob>   # task contract
uv run e-agent-harness check-scope            # changed paths inside the task contract
uv run e-agent-harness close-check --session <id>   # close ritual: clean tree, progress, evidence, handoff
uv run e-agent-harness refresh-task [--from-features]   # new digests for the active task; base and scope kept
uv run e-agent-harness amend-scope --add <glob> --reason <why>   # widen the active task's scope, recorded
uv run e-agent-harness add-feature <phase> <F-id> --category <c> --description <d> --step <s>
uv run e-agent-harness validate <schema> <file>   # check a contract file (features, task, handoff, review, ...)
uv run python scripts/check_agent_skills.py  # validates the ag-* (UI) and eng-* (engineering) skills; start engineering work from eng-session
uv run e-agent-harness tidy                  # format and lint the whole change once, before the commit
# Claude Code: .claude/settings.json runs the harness hooks; .claude/agents/ holds explorer, verifier, reviewer, sandbox-operator

# HTTP API + web UI (loopback only; Node 22.12+/24 and pnpm 10 for ui/)
(cd ui && pnpm install && pnpm build)
uv run e-agent serve --static ui/dist/web # http://127.0.0.1:8787/ (app), /host.html (overlay), /reference/
uv run python scripts/export_openapi.py   # after API changes; then (cd ui && pnpm gen)
(cd ui && pnpm check && pnpm conformance) # types, unit tests, layer rules, neutrality, build, Playwright

# PostgreSQL ledger (profile store.kind=postgres; DSN only via environment)
export E_AGENT_PG_DSN=postgresql://user@host:5432/e_agent   # e-agent's own database, never Odoo's
uv run e-agent --profile my-profile.json migrate
uv run e-agent --profile my-profile.json recover
E_AGENT_TEST_PG_DSN=$E_AGENT_PG_DSN E_AGENT_TEST_STORE=postgres uv run pytest -q tests/unit/kernel
```

### Execution IR toggle (Phase 2)

`features.execution_ir` in a profile is `off` (default, today's single-action loop, byte-identical), `shadow` (records `ir.plan_compiled` beside the old path and acts on the old path) or `on` (the admitted task definition sets the tools; a validated proposal runs as a 1-step plan; a multi-step plan is approved once and dispatched step by step). `/health/ready` and the evidence bundle report the toggle and any defaulted effect declarations. A `live` profile refuses `budgets.max_admitted_writes > 1`, so multi-step writes run only against fixtures until Phase 5 ([ADR 0025](docs/adr/0025-execution-ir.md), [target §6.4](docs/design/target-architecture.md#64-execution-ir-i)).

A two-step plan on the fixture simulator. This is a lineage demonstration: two draft POs for one demand, not a procurement scenario.

```bash
uv run python - <<'PY'
import json
from e_agent.plugins.erp.simulator import fixture_profile_path
p = json.load(open(fixture_profile_path()))
p["features"]["execution_ir"] = "on"; p["budgets"] = {"max_admitted_writes": 2}
json.dump(p, open("/tmp/plan-fixture.json", "w"))
PY
uv run e-agent --profile /tmp/plan-fixture.json demo --driver-mode two-step-plan            # prints every step, waits for approval
uv run e-agent --profile /tmp/plan-fixture.json demo --driver-mode two-step-plan --approve  # one approval, two verified steps
```

### Phase 3 toggles (cognition and context)

Three profile toggles under `features`, each `off | shadow | on`, all `off` in every committed profile ([ADR 0031](docs/adr/0031-progress-ledger-and-reconstruction.md), [ADR 0032](docs/adr/0032-context-assembler.md), [ADR 0033](docs/adr/0033-explanation-and-grounded-answers.md)):

- `features.context_assembler`: the kernel builds a budgeted, masked and fenced context pack for each driver call. `shadow` records `context.compared` (kernel token estimates of the pack against the same inputs unbounded) and the driver keeps its own history. `on` makes the driver render the pack; before the first write reservation a failure falls back to the driver history with `feature.fallback`, and after it the run fails closed (`CONTEXT_UNAVAILABLE`).
- `features.kernel_repeat`: a write proposal whose digest equals an earlier validation-blocked one in the run, with the same facts, gets `KERNEL-REPEAT` without being validated again. `shadow` records `repeat.compared` and validates as today.
- `features.grounded_answers`: answers carry citations and proposals a rationale, both checked against this run's recorded evidence and the rule inventory. `shadow` records `grounding.compared`; `on` makes a bad citation or rationale a repair finding (`KERNEL-CITATION`, `KERNEL-RATIONALE`) and admits the generic answer `grounded.answer.v1` for read-only questions, in a run that cannot write (ADR 0033 §3). Such a run ends `SUCCEEDED` with reason code `GROUNDED`: grounded, not verified (PR-19).

Each run pins its three modes when it starts, in the kernel continuation, so a profile change affects new runs only. Nothing is pinned when all three are `off`. `/health/ready` reports all four toggles under `features`, plus `data_boundary`, `data_boundary_basis` and `data_processing_declared` for the model route. The evidence bundle reports the same, plus the run's pinned `modes` (only when a mode is not `off`), `context` (the pack digest and drop log per driver turn, only for a run pinned `context_assembler: on`), `explanation` (every run) and `grounded_answer` (only after a `GROUNDED` end; free text outside the citations is labelled `unverified`).

**Model route data boundary ([ADR 0030](docs/adr/0030-data-governance.md)).** The route's boundary is `local`, `hosted:<region>` or `hosted:unknown`, and readiness gives its basis:
- `verified`: the scripted driver, or an `ollama` route on a literal loopback host (`localhost`, `127.0.0.0/8`, `::1`), also when the profile declares `local`;
- `declared`: the operator set `driver.data_boundary` and it could not be verified (a LiteLLM route is never verified);
- `default`: nothing declared and not loopback, so `hosted:unknown`.

At startup a route that is not `local` is refused unless the profile has `data_processing` (`data_owner`, `legal_basis`, `region`) or sets `context_assembler: on`, so the route gets only the masked pack. `local_only: true` refuses every route that is not `local`, whatever the toggles say. A run not pinned `on` that resumes on such a route makes no model call and fails closed (`ROUTE_BOUNDARY_UNMET`).

**Explanation.** `e-agent explain <run_id>` prints a stored run's explanation as JSON: goal, source facts, rules evaluated, proposal digest, approval, receipt and outcome, as ids, versions, digests and statuses only, with no observation values and no model call. It reads the run from the profile's store, so it needs a durable-store profile (Postgres); the fixture profile's in-memory store loses its runs when the process exits.

**Fixture reports.** `scripts/release_report.py` writes `repair_rate` (the kernel's repair counter over attempts), `ends` (a `GROUNDED` end is counted apart from `verified`) and, per case, `repairs`, `model_tokens` (`unknown` with the scripted driver, never 0) and `reason_code`. `--context-assembler`, `--kernel-repeat` and `--grounded-answers` take `off` or `shadow` and add that toggle's columns. `scripts/context_ablation.py` runs the same corpus with `context_assembler` `off` and `on`. All of it is fixture evidence: the scripted driver proposes the same thing whatever its context, so equal outcomes show that the `on` path keeps the host safety path, not that typed state helps a model. That needs a qualified model run (ADR 0010).

### Model provider: Ollama (default) or LiteLLM (optional)

A `pydantic-ai` driver profile uses Ollama unless it names another provider: `{"kind": "pydantic-ai", "model": "<ollama model>"}` reads `E_AGENT_OLLAMA_URL` (default `http://localhost:11434/v1`).

LiteLLM is an explicit opt-in ([ADR 0021](docs/adr/0021-litellm-model-provider.md), Proposed):

```json
{"kind": "pydantic-ai", "provider": "litellm", "model": "<proxy model name>", "api_key_env": "E_AGENT_LITELLM_KEY"}
```

- The proxy URL comes from `E_AGENT_LITELLM_URL` (default `http://localhost:4000`); it must be loopback (`localhost`, `127.0.0.1`, `::1`) over http or https.
- `api_key_env` names the environment variable holding the proxy key; the profile never contains the key. Without `api_key_env`, a fixed placeholder is sent and no other environment key (such as `OPENAI_API_KEY`) is read.
- There is no fallback between providers: a missing model, a refused endpoint or an unset key variable rejects startup.
- Which upstream model the proxy routes to is the operator's LiteLLM configuration. Qualification evidence is per provider and model; no LiteLLM-routed model has been qualified, and an Ollama qualification does not carry over.
- Evidence runtime metadata records `model_provider` next to `model`.

### Live agent against the `odoo19-learning` sandbox (owner machine)

Prerequisites (one-time, see [runbook I06](docs/runbooks/i06-odoo-bridge.md)): the `e_agent_bridge` addon (19.0.0.4.0) installed in the sandbox, the `e-agent-integration` user and API keys, the integration key in the local secret store, a dedicated PostgreSQL ledger, and a gitignored live profile (`profiles/*.local.json`) with `artifact_sha256` pins from freshly built wheels (`scripts/plugin_inventory.py`). Keep secret-store and ledger settings in a private env file outside the repository (for example `~/.config/e-agent/live.env` with `E_AGENT_PG_DSN`, `E_AGENT_SECRET_KEY_FILE`, `E_AGENT_SECRETS_PATH`).

```bash
set -a; . ~/.config/e-agent/live.env; set +a
make dev PROFILE=profiles/live-odoo19-learning.local.json
```

A real model with all ERP tools uses far more tokens per run than the fixture: the committed profiles (`dev-ollama.json`, `live.example.json`) already set `max_model_tokens` 200000 and `max_validation_repairs` 4. A real model with the default budgets (32000 tokens, 2 repairs) ends with `budget exhausted: model usage`. After changing domain or adapter code, rebuild the wheels and refresh the pins; after changing the bridge addon, upgrade it in the sandbox (`-u e_agent_bridge`) before starting the stack.

Python packages share the `e_agent` namespace: `e_agent.contracts`, `e_agent.sdk`, `e_agent.kernel`, `e_agent.server`, `e_agent.adapters.<name>` and the ERP plugins `e_agent.plugins.erp.domain`, `e_agent.plugins.erp.odoo` and `e_agent.plugins.erp.simulator`. `e_agent`, `e_agent.adapters`, `e_agent.plugins` and `e_agent.plugins.erp` are namespace packages without `__init__.py`.

See the [implementation plan](docs/design/implementation-plan.md) for owner decisions, milestones and work packages.

## Contribution expectations

Follow [AGENTS.md](AGENTS.md), preserve package dependency direction, keep secrets out of source/evidence, and test policy and recovery behavior as well as successful tasks. Update design documents when contracts change. Report the scope and limitations of evidence; a working demo is not a claim of production readiness or enterprise certification.
