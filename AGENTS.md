# Repository instructions

## Purpose and current state

e-agent is a plugin-driven enterprise agent product. The first implementation target is a bounded procurement workflow with executable ontology validation, explicit approval, a draft PO in an isolated Odoo sandbox and independent outcome verification.

The repository currently contains research and design documents. There is no runnable application, package workspace or verified test command yet. Do not describe planned behavior as implemented or invent setup commands/results.

## Read before changing code or architecture

1. [High-level design](docs/high-level-design.md).
2. [MVP detailed design](docs/mvp-detailed-design.md).
3. Relevant research only as needed; [research 10](research/10-extensibility-architecture-review.md) is the latest extensibility review.

Current user instructions take precedence. The MVP design specializes the high-level design; older research may describe alternatives that are no longer the baseline. Resolve material design changes with an ADR and update affected designs rather than silently introducing contradictions. These instructions do not add approval requirements to otherwise authorized work.

## Architecture rules

- Use a monorepo and modular monolith initially. Adapter distributions are independently buildable/releasable; do not recreate a single shared `integrations` artifact.
- Contracts contain portable records, not vendor/framework/ORM objects. Domain-specific fields belong in domain APIs.
- SDK depends on contracts; kernel depends on contracts/SDK; domains depend on public contracts/SDK; adapters implement ports and may depend on required public domain APIs. Kernel never imports domains, adapters or server. Adapters never import kernel internals or sibling implementations.
- Bootstrap chooses concrete implementations. Domain logic does not belong in HTTP handlers, CLI commands or framework prompts.
- Keep domain, capability contract, provider binding and connection separate. Multiple valid bindings of one capability are allowed; conflicting definitions, duplicate binding IDs and ambiguous routing are errors.
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

## Development and verification

- Inspect the actual repository before choosing commands. Once tooling exists, use its declared formatter, type checker, build and test configuration; document real commands in README.
- Build/test distributions in clean environments outside editable workspace where independence matters. Verify resources and declared dependency closure.
- Add meaningful tests for changed behavior, contract compatibility, policy/approval boundaries and failure recovery. Use architecture import gates and reusable conformance fixtures.
- Keep deterministic fixtures distinct from live model/ERP results. Report failures, skipped checks and environmental blockers accurately.
- Do not access live business data or reset non-sandbox ERP instances. Live demo/reset tooling must verify an explicit synthetic sandbox identity and allowed target before mutation.
- Never commit credentials or expose them in logs, prompts, traces or documentation. Export only authorized/redacted evidence; do not persist hidden chain-of-thought.
- Do not import or mutate `/Users/thanhnguyen/dev/lab/enterprise-agent/experiment` as part of routine product work. It is a separate research system; changes there need task-specific scope. Do not contaminate its confirmatory evidence with demo runs.

## Documentation and completion

Keep design and repository documentation in English unless the user requests otherwise. Preserve original research reports. Update README when runnable tooling exists, and update designs when contracts/boundaries change. A handoff states what changed, what was verified and what remains unimplemented. Enterprise readiness, multi-domain support and ontology effectiveness require evidence beyond a successful happy-path demo.
