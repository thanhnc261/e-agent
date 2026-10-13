# Repository instructions

## Purpose and current state

e-agent is a plugin-driven enterprise agent product. The first implementation target is a bounded procurement workflow with executable ontology validation, explicit approval, a draft PO in an isolated Odoo sandbox and independent outcome verification.

The kernel, adapters, PostgreSQL store, eight ERP tasks and UI are implemented. The approved 2026-10-07 remediation candidate has separate fixture, persistent-ledger, UI and local model evidence. Owner Odoo installation and integrated human-approved live qualification remain open; consult the README and latest remediation retest. Do not describe historical or fixture evidence as current live release qualification, or invent results.

Work is ordered by the [roadmap](docs/roadmap.md): each phase has a detailed plan in `docs/plans/`, and the roadmap's status column says which phase is current. `archive/` is history: superseded plans, reports and mockups, kept read-only for reference.

## Read before changing code or architecture

1. [Roadmap](docs/roadmap.md): its rules, the current phase and that phase's plan in `docs/plans/`.
2. Designs in `docs/design/`: [high-level design](docs/design/high-level-design.md), [MVP detailed design](docs/design/mvp-detailed-design.md), [target architecture](docs/design/target-architecture.md) and the [implementation plan](docs/design/implementation-plan.md) (§0 decisions/toolchain, §3 work packages).
3. The [ADR index](docs/adr/README.md). Check an ADR's status before relying on it; proposed ADRs are not baseline.
4. Topic designs when touching them: [UI architecture](docs/design/ui-architecture.md), [integration management](docs/design/integration-management.md), [integration auth SDK](docs/design/integration-auth-sdk.md), [threat model](docs/design/threat-model.md).
5. Relevant research only as needed; [research 10](research/10-extensibility-architecture-review.md) is the latest extensibility review.

Current user instructions take precedence. The MVP design specializes the high-level design; older research may describe alternatives that are no longer the baseline. Resolve material design changes with an ADR and update affected designs rather than silently introducing contradictions. These instructions do not add approval requirements to otherwise authorized work.

## How work is done

The roadmap's rules apply to every phase:

1. **Detailed plan first.** A phase starts only after its bite-sized plan is written in `docs/plans/`, linked from the roadmap and reviewed.
2. **Design first.** A phase implements design sections and ADRs. A contract or boundary change needs an ADR the owner accepts before the phase merges. When code and design disagree, fix one of them explicitly.
3. **Toggles with fallback.** Every new runtime feature has a profile toggle `off | shadow | on`. `shadow` records the new path but acts on the existing one. `on` falls back to the existing path only before a write is reserved, and records `feature.fallback`. After a reservation there is no fallback: the run fails closed or goes to reconciliation. Fallback never bypasses approval, admission, verification or the transition table; `/health/ready` and the evidence bundle report the toggles.
4. **Trust anchor unchanged.** The run and action state machines, gateway, approval digests, admission and verification stay in the kernel. Model output is a proposal.
5. **Environment boundaries** (see below).

Each task gets a review of its diff and evidence. Each phase ends with end-to-end verification: the full gate, the Postgres run, `make e2e` and a live check on the `odoo19-learning` sandbox. The development harness (`uv run e-agent-harness status`) holds the task contract, scope check, gate evidence and handoff for this loop; README lists the main commands. Claude Code sessions also load `.claude/settings.json`, whose hooks run the status brief, the pre-compaction checkpoint and the scope check, and whose permission rules deny `odoo-bench` and ask before `git push`, `merge`, `rebase` and `reset --hard`; Codex runs the same commands by hand.

## Repository map

- `src/e_agent/`: all Python product code in one layer-grouped tree: `contracts/`, `sdk/`, `kernel/`, `erp/`, `adapters/<name>/`, `server/`.
- `dists/<distribution>/`: one build config per independently released distribution (wheels built from `src/` by the shared hook in `dists/_hooks/`).
- `tests/`: `unit/<part>/` mirrors `src/e_agent/`; plus `conformance/`, `integration/`, `harness/` and `replays/`.
- `ui/`: the TypeScript UI workspace (pnpm).
- `addons/`: the Odoo bridge addon.
- `profiles/`: committed non-secret run profiles; `*.local.json` are secret and never committed.
- `scripts/`: repository tooling (wheel checks, plugin inventory, OpenAPI export, sandbox, mover).
- `evals/`: model-qualification and release reports (ADR 0010).
- `tools/harness/`: the development harness distribution; `harness/` holds its manifest, samples and state.
- `docs/`: `roadmap.md`, `design/`, `plans/`, `specs/`, `adr/`, `handoffs/`, `reviews/`, `runbooks/`.
- `research/` and `archive/`: read-only history.
- `.agents/skills/` (linked under `.claude/skills/`), `.claude/`, `.github/`, `.vscode/`: agent skills, Claude settings, CI and editor settings.

## Architecture rules

- Use a monorepo and modular monolith initially. Adapter distributions are independently buildable/releasable; do not recreate a single shared `integrations` artifact.
- Contracts contain portable records, not vendor/framework/ORM objects. Domain-specific fields belong in domain APIs.
- SDK depends on contracts; kernel depends on contracts/SDK; domains depend on public contracts/SDK; adapters implement ports and may depend on required public domain APIs. Kernel never imports domains, adapters or server. Adapters never import kernel internals or sibling implementations.
- Bootstrap chooses concrete implementations. Domain logic does not belong in HTTP handlers, CLI commands or framework prompts.
- Keep domain, capability contract, provider binding and connection separate. Multiple valid bindings of one capability are allowed; conflicting definitions, duplicate binding IDs and ambiguous routing are errors.
- UI packages contain no provider or third-party system identifiers; provider names, icons and forms come from manifests via the server API. Model output never selects credentials or connections.
- Do not add unused abstractions or empty future packages. Add a public extension seam for a concrete use case or an explicit trust boundary.

## Execution and data integrity

- All agent tools, including reads, pass through host authorization and the action gateway. Never expose raw privileged provider clients to the driver/model.
- Model output is a proposal. It cannot grant approval, change policy/budgets, install plugins, publish ontology or mark its own task verified.
- Approval binds the exact normalized action, scope and versions. Revalidate changed facts/policy and reject stale approval.
- Persist mandatory admission/dispatch evidence before writes. Keep local state/event updates atomic; never hold a DB transaction across model/ERP calls.
- External timeouts can mean UNKNOWN. Never blindly replay a possibly committed write or claim exactly-once without the required provider guarantees.
- Verify outcomes by independent authorized read-back. Distinguish committed effect from verified business success.
- Preserve tenant scope, source revisions, provenance, semantic versions and explicit missing/unknown states. Never treat an absent fact as an approved fact.

## Plugins and knowledge

- Discover metadata before import; activate only configured, admitted artifacts. Factories have no business/network side effects. Inject narrow scoped services rather than a global service locator.
- Package manifests, ontology, shapes and rules as resources. Do not depend on cwd or sibling repository paths.
- Ontology definitions belong to domain packs; validation engines belong to adapters. Maintain one authoritative rule inventory; prompts/UI must not become divergent enforcement implementations.
- Knowledge ingestion, curation, canonical claims and projections are separate responsibilities. A graph/vector backend swap does not eliminate semantic migration, ACL or deletion requirements.
- Framework memory and extracted content are untrusted inputs, not curated truth or executable policy.

## Skills

Skills live in `.agents/skills/` (linked for Claude under `.claude/skills/`). Validate skill changes with `uv run python scripts/check_agent_skills.py`.

- **Engineering work** uses the `eng-*` skills. Start from `eng-session` (the session loop and close ritual); `eng-foundations` holds the engineering rules (`ENG-*`) that work is built and reviewed against. `live-sandbox` operates the `odoo19-learning` sandbox and is invoked by the owner only.
- **Agentic UI/UX work** uses the `ag-*` skills. Start from `ag-ux-foundations`; it holds the standard (`AG-*` criteria) that the current UI is audited and built against, and the binding e-agent requirements. Each stage skill stops at an owner gate.

## Development and verification

- Python code lives in `src/e_agent/<part>/`; each distribution's build config is in `dists/<dist>/pyproject.toml`. `e_agent` and `e_agent.adapters` are namespace packages: never add `src/e_agent/__init__.py` or `src/e_agent/adapters/__init__.py`. Tests for a part live in `tests/unit/<part>/`.
- Distributions are released as wheels: `uv build --package <name> --wheel`. The development install imports from `src/` (`tests/conformance/test_repo_layout.py` guards this).
- Inspect the actual repository before choosing commands. Once tooling exists, use its declared formatter, type checker, build and test configuration; document real commands in README.
- Build/test distributions in clean environments outside editable workspace where independence matters. Verify resources and declared dependency closure.
- Add meaningful tests for changed behavior, contract compatibility, policy/approval boundaries and failure recovery. Use architecture import gates and reusable conformance fixtures.
- Keep deterministic fixtures distinct from live model/ERP results. Report failures, skipped checks and environmental blockers accurately.
- Do not access live business data or reset non-sandbox ERP instances. Live demo/reset tooling must verify an explicit synthetic sandbox identity and allowed target before mutation.
- Never commit credentials or expose them in logs, prompts, traces or documentation. Export only authorized/redacted evidence; do not persist hidden chain-of-thought.

## Environment boundaries

- Touch only the `odoo19-learning` sandbox and the containers e-agent creates (`e-agent-ledger`, `e-agent-test-*`). Never touch `odoo-bench` or any other container; those run long experiments.
- Do not import or mutate `/Users/thanhnguyen/dev/lab/enterprise-agent/experiment` as part of routine product work. It is a separate research system; changes there need task-specific scope. Do not contaminate its confirmatory evidence with demo runs.
- `harness/context.toml` lists the allowed and denied containers, protected paths and secret paths that the harness checks.

## Documentation and completion

Keep design and repository documentation in English unless the user requests otherwise. Preserve original research reports. Update README when runnable tooling exists, and update designs when contracts/boundaries change. A handoff states what changed, what was verified and what remains unimplemented. Enterprise readiness, multi-domain support and ontology effectiveness require evidence beyond a successful happy-path demo.
