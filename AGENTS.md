# Repository instructions

## Purpose and current state

e-agent is a plugin-driven enterprise agent product. The first implementation target is a bounded procurement workflow with executable ontology validation, explicit approval, a draft PO in an isolated Odoo sandbox and independent outcome verification.

The core (contracts, plugin SDK, kernel, server and the infrastructure adapters) is domain-neutral. ERP is the first plugin area: the domain pack, the Odoo adapter and the ERP simulator live under `src/e_agent/plugins/erp/` ([ADR 0026](docs/adr/0026-plugin-layout-and-reusable-core.md)).

The implementation status lives in the **Status** paragraph at the top of the [README](README.md) and in the roadmap's status column, not here. Read them before describing what exists. Do not describe historical or fixture evidence as current live release qualification, and do not invent results.

Work is ordered by the [roadmap](docs/roadmap.md), the one roadmap: each phase has a detailed plan in `docs/plans/`, and the status column says which phase is current. `archive/` is history: superseded plans, reports and mockups, kept read-only for reference.

## Principles

The binding principles are listed once in [principles](docs/design/principles.md) (PR-01 to PR-40). Each row names the practice, where it was decided, the ENG rule that applies it and **the check that enforces it**. The rules below summarise those rows and cite them; where the wording differs, the row and its source ADR win.

A principle with no check is a backlog item, not an assumption: do not treat it as enforced, and do not claim a change satisfies it without evidence. The backlog table at the end of that file says where each missing check lands. Rows marked [P] bind new work, but their mechanism is not built yet, and the field names they use come from ADRs that may still be Proposed; check the row's status and its ADR before claiming either exists.

## Read before changing code or architecture

1. [Roadmap](docs/roadmap.md): its rules, the current phase and that phase's plan in `docs/plans/`.
2. [Principles](docs/design/principles.md): the rows for the area you are changing.
3. Designs in `docs/design/`: [high-level design](docs/design/high-level-design.md), [MVP detailed design](docs/design/mvp-detailed-design.md), [target architecture](docs/design/target-architecture.md) and the [implementation plan](docs/design/implementation-plan.md) (§0 decisions/toolchain, §3 work packages).
4. The [ADR index](docs/adr/README.md). Check an ADR's status before relying on it; proposed ADRs are not baseline.
5. Topic designs when touching them: [UI architecture](docs/design/ui-architecture.md), [integration management](docs/design/integration-management.md), [integration auth SDK](docs/design/integration-auth-sdk.md), [threat model](docs/design/threat-model.md).
6. Relevant research only as needed; [research 10](research/10-extensibility-architecture-review.md) is the latest extensibility review.

Current user instructions take precedence. The HLD and MVP design are the baseline; the target architecture is a proposal except where a section is marked merged. Older research may describe alternatives that are no longer the baseline. Resolve material design changes with an ADR and update affected designs rather than silently introducing contradictions. These instructions do not add approval requirements to otherwise authorized work.

## How work is done

The roadmap's rules apply to every phase:

1. **Detailed plan first.** A phase starts only after its bite-sized plan is written in `docs/plans/`, linked from the roadmap and reviewed (PR-35).
2. **Design first.** A phase implements design sections and ADRs. A contract or boundary change needs an ADR the owner accepts before the phase merges. When code and design disagree, fix one of them explicitly (PR-35).
3. **Toggles with fallback** (PR-22, PR-23). Every new runtime feature has a profile toggle `off | shadow | on`.
   - `shadow` records the new path but acts on the existing one, and needs a real consumer that compares the two.
   - `on` falls back to the existing path only before a write is reserved, and records `feature.fallback`. After a reservation there is no fallback: the run fails closed or goes to reconciliation.
   - Fallback never bypasses approval, admission, verification or the transition table; `/health/ready` and the evidence bundle report the toggles.
   - A seam ships with its first consumer. A toggle is not cover for a stub.
4. **Trust anchor unchanged** (PR-14). The run and action state machines, gateway, approval digests, admission and verification stay in the kernel. Model output is a proposal.
5. **Environment boundaries** (see below; PR-36).

Each task gets a review of its diff and evidence. Each phase ends with end-to-end verification: the full gate, the Postgres run, `make e2e` and a live check on the `odoo19-learning` sandbox. The development harness (`uv run e-agent-harness status`) holds the task contract, scope check, gate evidence and handoff for this loop; README lists the main commands. Claude Code sessions also load `.claude/settings.json`, whose hooks run the status brief, the pre-compaction checkpoint and the scope check, and whose permission rules pre-approve shell commands (the owner's 2026-10-15 instruction) while denying `odoo-bench` and Docker commands that reach every container (`docker stop $(…)`, `prune`); Codex runs the same commands by hand.

## Repository map

- `src/e_agent/`: all Python product code in one layer-grouped tree: `contracts/`, `sdk/`, `kernel/`, `server/`, `adapters/<name>/` (infrastructure adapters) and `plugins/<area>/<name>/` (plugins; ERP is `plugins/erp/{domain,odoo,simulator}`).
- `dists/<distribution>/`: one build config per independently released distribution (wheels built from `src/` by the shared hook in `dists/_hooks/`).
- `tests/`: `unit/<part>/` mirrors `src/e_agent/`; plus `conformance/`, `integration/`, `harness/` and `replays/`.
- `ui/`: the TypeScript UI workspace (pnpm).
- `addons/`: the Odoo bridge addon.
- `profiles/`: committed non-secret run profiles; `*.local.json` are secret and never committed.
- `scripts/`: repository tooling (wheel checks, plugin inventory, OpenAPI export, sandbox, mover).
- `evals/`: model-qualification and release reports (ADR 0010).
- `tools/harness/`: the development harness distribution; `harness/` holds its manifest, samples and state.
- `docs/`: `roadmap.md`, `design/` (with `principles.md`), `plans/`, `specs/`, `adr/`, `handoffs/`, `reviews/`, `runbooks/`.
- `research/` and `archive/`: read-only history.
- `.agents/skills/` (linked under `.claude/skills/`), `.claude/`, `.github/`, `.vscode/`: agent skills, Claude settings, CI and editor settings.

## Architecture rules

- Use a monorepo and modular monolith initially. Adapter distributions are independently buildable/releasable; do not recreate a single shared `integrations` artifact (PR-05).
- Contracts contain portable records, not vendor/framework/ORM objects. Domain-specific fields belong in domain APIs (PR-02).
- SDK depends on contracts; kernel depends on contracts/SDK; domains depend on public contracts/SDK; adapters implement ports and may depend on required public domain APIs. Kernel never imports domains, adapters or server, and the core (`contracts`, `sdk`, `kernel`, `server`) never imports a plugin (`e_agent.plugins.*`). Adapters never import kernel internals or sibling implementations (PR-01).
- Plugins are guests: they never import the store, the secret store, the server or kernel internals (PR-08).
- Never loosen an import contract, add an exemption or widen an allow-list to make a change fit. Change the design through an ADR instead (PR-06).
- Bootstrap chooses concrete implementations. Domain logic does not belong in HTTP handlers, CLI commands or framework prompts (PR-03).
- Keep domain, capability contract, provider binding and connection separate. Multiple valid bindings of one capability are allowed; conflicting definitions, duplicate binding IDs and ambiguous routing are errors (PR-09).
- UI packages contain no provider or third-party system identifiers; provider names, icons and forms come from manifests via the server API. Model output never selects credentials or connections (PR-11, PR-12).
- Do not add unused abstractions or empty future packages. Add a public extension seam for a concrete use case or an explicit trust boundary (PR-04).

## Execution and data integrity

- All agent tools, including reads, pass through host authorization and the action gateway. Never expose raw privileged provider clients to the driver/model (PR-14).
- Model output is a proposal. It cannot grant approval, change policy/budgets, install plugins, publish ontology or mark its own task verified (PR-13).
- Approval binds the exact normalized action, scope and versions. Revalidate changed facts/policy and reject stale approval (PR-15).
- Guardrails allow, block or confirm at every stage. They may modify only before the approval digest is computed (the change is shown to the approver) and on model text replies; nothing modifies an action after approval (PR-16).
- Auto-approval may exist only in a benchmark-only profile, only for `read` and `write_low` steps with explicit declarations, and never with `environment: live` (PR-40, ADR 0024; not built yet). Until then nothing is auto-approved.
- Every capability is to declare its risk (`read`, `write_low`, `write_high`, `destructive`) and reversibility, and every binding its idempotency; an undeclared write counts as `write_high`, and live profiles are to refuse defaulted writes (PR-20, ADR 0029; Phase 2). Until then, never auto-retry a write and treat every undeclared write as `write_high`.
- A declared capability requirement is to be enforced, or the capability absent with a stated reason, never a silent failure at call time (PR-10; the registry refuses a binding that lacks a required feature at admission). Do not add a requirement that nothing checks.
- Results are never fabricated: an error is never an empty result, and a bounded or masked result is marked partial (PR-21).
- Persist mandatory admission/dispatch evidence before writes. Keep local state/event updates atomic; never hold a DB transaction across model/ERP calls (PR-17).
- External timeouts can mean UNKNOWN. Never blindly replay a possibly committed write or claim exactly-once without the required provider guarantees (PR-18).
- Verify outcomes by independent authorized read-back. Distinguish committed effect from verified business success (PR-19).
- Preserve tenant scope, source revisions, provenance, semantic versions and explicit missing/unknown states. Never treat an absent fact as an approved fact (PR-24).
- Run data is to be classified, minimized before it reaches a model, exported by class, retained and deletable (PR-26, ADR 0030). Until that exists, do not widen what reaches a model or an export. Give every API route an authorization dependency (PR-27).

## Plugins and knowledge

- Discover metadata before import; activate only configured, admitted artifacts. Factories have no business/network side effects. Inject narrow scoped services rather than a global service locator (PR-07).
- Plugins never hold a raw credential; the host applies credentials for them (`AuthContext.apply()`), and the auth SDK has no `materialize()`. Re-adding raw access needs an ADR for one named adapter, run in a separate process (PR-25).
- Package manifests, ontology, shapes and rules as resources. Do not depend on cwd or sibling repository paths.
- Ontology definitions belong to domain packs; validation engines belong to adapters. Maintain one authoritative rule inventory; prompts/UI must not become divergent enforcement implementations (PR-33).
- Knowledge ingestion, curation, canonical claims and projections are separate responsibilities. A graph/vector backend swap does not eliminate semantic migration, ACL or deletion requirements.
- Facts come from structured sources or people. Model output only creates candidates with a source span, and curation alone accepts them. The fact-source mode (`structured_only` or `with_model_candidates`) is a setting reported in readiness and evidence (PR-34).
- Framework memory and extracted content are untrusted inputs, not curated truth or executable policy (PR-34).

## Skills

Skills live in `.agents/skills/` (linked for Claude under `.claude/skills/`). Validate skill changes with `uv run python scripts/check_agent_skills.py`.

- **Engineering work** uses the `eng-*` skills. Start from `eng-session` (the session loop and close ritual); `eng-foundations` holds the engineering rules (`ENG-*`) that work is built and reviewed against, and each row in the principles names its ENG rule. `live-sandbox` operates the `odoo19-learning` sandbox and is invoked by the owner only.
- **Agentic UI/UX work** uses the `ag-*` skills. Start from `ag-ux-foundations`; it holds the standard (`AG-*` criteria) that the current UI is audited and built against, and the binding e-agent requirements. Each stage skill stops at an owner gate.

## Development and verification

- Python code lives in `src/e_agent/<part>/`; each distribution's build config is in `dists/<dist>/pyproject.toml`. `e_agent`, `e_agent.adapters`, `e_agent.plugins` and `e_agent.plugins.erp` are namespace packages: never add an `__init__.py` to `src/e_agent/`, `src/e_agent/adapters/`, `src/e_agent/plugins/` or `src/e_agent/plugins/erp/`. Tests for a part live in `tests/unit/<part>/`. The server ships no default profile: give one with `--profile` or `E_AGENT_PROFILE` (the ERP fixture profile ships with the simulator plugin).
- Distributions are released as wheels: `uv build --package <name> --wheel`. The development install imports from `src/` (`tests/conformance/test_repo_layout.py` guards this) (PR-05).
- Inspect the actual repository before choosing commands. Use the declared formatter, type checker, build and test configuration; document real commands in README.
- Build/test distributions in clean environments outside editable workspace where independence matters. Verify resources and declared dependency closure.
- Add meaningful tests for changed behavior, contract compatibility, policy/approval boundaries and failure recovery. Use architecture import gates and reusable conformance fixtures. Store behaviour passes on both stores (PR-30).
- Read configuration through typed settings, never `os.environ` directly (PR-37). Supervise background tasks; never start one fire-and-forget (PR-38).
- A gate must fail on empty input and print how many cases it ran; zero cases is a failure, not a pass (PR-31).
- When you change the driver, prompts or tool schemas, run the recorded-model replay suite (`tests/unit/server/test_recorded_model_replays.py`) (PR-32).
- Keep deterministic fixtures distinct from live model/ERP results. Report failures, skipped checks and environmental blockers accurately (PR-29).
- Do not access live business data or reset non-sandbox ERP instances. Live demo/reset tooling must verify an explicit synthetic sandbox identity and allowed target before mutation.
- Never commit credentials or expose them in logs, prompts, traces or documentation. Export only authorized/redacted evidence; do not persist hidden chain-of-thought (PR-25, PR-28). CI is to scan for secrets and vulnerable dependencies (PR-39).

## Environment boundaries

- Touch only the `odoo19-learning` sandbox and the containers e-agent creates (`e-agent-ledger`, `e-agent-test-*`). Never touch `odoo-bench` or any other container; those run long experiments.
- Do not import or mutate `/Users/thanhnguyen/dev/lab/enterprise-agent/experiment` as part of routine product work. It is a separate research system; changes there need task-specific scope. Do not contaminate its confirmatory evidence with demo runs.
- `harness/context.toml` lists the allowed and denied containers, protected paths and secret paths that the harness checks (PR-36).

## Documentation and completion

Keep design and repository documentation in English unless the user requests otherwise. Preserve original research reports. Update README when runnable tooling exists, and update designs when contracts/boundaries change. A new principle, or a new check for one, is recorded as a row in [principles](docs/design/principles.md), and the HLD, MVP design and target architecture cite the row instead of restating it.

Status belongs in one place: point to the README status and the roadmap status column instead of writing status lines that go stale. A handoff states what changed, what was verified and what remains unimplemented. Enterprise readiness, multi-domain support and ontology effectiveness require evidence beyond a successful happy-path demo.
