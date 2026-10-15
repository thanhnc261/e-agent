# Design and plan review against the product principles

Date: 2026-10-14. Reviewed candidate: branch `refactor/phase1-structure` at `036407b` (clean tree). Principles set by the owner: **scale, flexibility, plugin-driven, wide integration, data governance**.

Scope: the [roadmap](../roadmap.md), the [HLD](../design/high-level-design.md), the [MVP design](../design/mvp-detailed-design.md), the [target architecture](../design/target-architecture.md), [integration management](../design/integration-management.md), the [integration auth SDK](../design/integration-auth-sdk.md), the [threat model](../design/threat-model.md), the ADR index, and the core cognition, Odoo tools and Phase 1 plans in `docs/plans/`. The development-harness plans were left out because they are development tooling, not product architecture. Code was read to check design claims (file:line below). Nothing was run, no code or design document was changed, and no throughput or qualification result is claimed. Status tags follow the target architecture: [I] implemented, [Pa] partial, [P] proposed, [C] conditional.

## Verdict

**The architecture is sound and largely matches 2026 practice. Keep it.** The trust anchor and port split, the Postgres-first decision, connection-level write admission, the domain → capability → binding → connection model and the fitness-test discipline (G-criteria, R/U/Q matrix) hold up. Most designs do not get this far.

The weaknesses are uneven across the five principles:

| Principle | Design | Implementation | Plan | Main gap |
|---|---|---|---|---|
| Scale | Strong (§12: slots, fairness, LISTEN, lease, role split, capacity harness) | [Pa]: 1 run per process, 200 ms SSE polling, no rate limits | Phase 6, deferred by the owner | Load arrives in Phases 4–5 before Phase 6 (DR-07) |
| Flexibility | Strong (§4 swappable seams with conformance) | [Pa]: one driver, hardcoded policy, no toggles yet | Phases 2–3 | Phase 2 execution IR has no design section (DR-01) |
| Plugin-driven | Strong (discovery before import, admission, digests) | [Pa]: only the domain pack and the Odoo adapter are discovered; driver, store, validator and secret store are hard-wired in bootstrap | No phase | R3 is claimed [I] but covers two plugins (DR-04) |
| Wide integration | Good (manifests, OAuth engine, MCP binding, triggers) | [Pa]: the manifest `connection` section is unused; connections exist only in profile JSON; adding a capability touches 12–15 files | Phase 8, behind Phase 7 | The cost of each new capability grows with Phase 5 (DR-02, DR-03) |
| Data governance | **Weak** for run, evidence and model-context data; good for knowledge and memory (§8–§9) | [Pa]: tenant scoping, secret isolation and provenance exist; no classification, minimization, retention, deletion or export authorization | Scattered across Phases 7 and 9 | No design and no ADR (DR-05) |

The two highest-priority items:
1. **Phase 2 has no design.** Write a design section and an ADR before its detailed plan (DR-01).
2. **Data governance has no ADR.** Add one, and put its minimization part into the Phase 3 ContextAssembler, which is where it belongs (DR-05).

---

## 1. What already matches current practice

| Principle | Practice | Where |
|---|---|---|
| Scale | Postgres as the ledger, queue and event log; `SKIP LOCKED` leases with fencing; waits release slots; no broker until a named consumer exists | MVP §9, target §11–§12, ADR 0003 |
| Scale | Connection-level write admission as the backstop for a lost lock or lease | ADR 0020 [I], target §12.2 |
| Scale | Capacity claims need a load harness; fixture evidence is labelled as such | Target §12.3 |
| Flexibility | The trust anchor is fixed and everything around it is a port with a conformance suite; thinnest topology that passes evals | Target §4 |
| Flexibility | `off/shadow/on` toggles with pre-reservation-only fallback | Roadmap rule 3 |
| Flexibility | Revisit triggers on every deferred technology (graph, vector DB, bus, DBOS, OPA) | Target §14, HLD §10 |
| Plugin-driven | Metadata read without import; SDK range check; artifact digest inventory; disabled plugins never imported | `sdk/discovery.py:43-108`, `kernel/registry.py:126-147`, `sdk/manifest.py:35-57` |
| Plugin-driven | Independent wheels; import-linter boundaries | HLD §4, `dists/`, root `pyproject.toml` |
| Wide integration | Capability contracts named by business context; bindings carry the provider; ambiguity refused | ADR 0002, `kernel/registry.py:217-227` |
| Wide integration | Schema-driven connections; write-only secrets; RFC 9700 OAuth; user-delegated connections; MCP tools only when mapped to a contract | ADR 0012/0013, target §10.2 |
| Data governance | Lineage from goal to verified outcome; EvidenceRef provenance; no hidden reasoning persisted | MVP §11, target §5.5–§5.6, ADR 0004 |
| Data governance | Knowledge as canonical claims with rebuildable projections; ACL before rerank; deletion cascades into memory | Target §8–§9 |

---

## 2. Findings

### DR-01 — High: Phase 2 (execution IR, action plans) has no design section

**Evidence.** The roadmap coverage table lists "Execution IR / action plans (not in design) → 2, new ADR". The Odoo plan, Phase 0.3, sketches `ActionPlan(steps, depends_on, lineage)`. Today `Budgets.max_admitted_writes = 1`, and every write is "exactly one" (Odoo plan 0.3).

**Impact.** The action plan changes trust-anchor invariants that the rest of the design depends on:
- One approval digest now covers many writes.
- Each step needs its own reservation, and those reservations interact with the `CONNECTION_BUSY` rule (ADR 0020). A plan of N writes on one connection serializes, and one `UNKNOWN` step blocks the rest.
- There are partial-failure semantics: committed and verified steps remain, and the remainder must be reported.
- Lineage refs point to the result of an earlier step (for example, a PO `origin` that holds an SO name), so later steps' arguments are not known at approval time. The digest must define what it binds when an argument is only resolved at run time.
- The toggle rule says no fallback after a write is reserved. With a plan, "after the first step" is the normal state, so `shadow` and `on` need a per-feature definition. Shadow must not add model calls or reads that consume budget without saying so.
- Plan-level approval fatigue and step divergence from the approved plan are new threats that the threat model does not list.

The roadmap already names the gap and the new ADR, so the problem is order. Roadmap rule 2 ("a phase implements design sections and ADRs") would be broken if the Phase 2 detailed plan were written before the design section exists. The section and the ADR are therefore the phase's entry gate.

**Fix.** Before the Phase 2 detailed plan:
1. Add a target-architecture section, "Execution IR", covering `TaskDefinition → ActionPlan → StepRecord`, the digest scope (bound literals versus lineage placeholders with declared resolution rules), per-step admission and verification, partial failure and its run states, and the toggle semantics per mode.
2. Write the ADR (0025 in the Odoo plan's numbering) together with ADR 0024 (approval model).
3. Add threat-model entries T20 (plan approval fatigue) and T21 (step divergence).

**Phase.** 2, entry gate.

### DR-02 — Medium: the per-capability cost is high and grows with Phase 5

**Evidence.**
- Odoo dispatch is an `if/elif` chain on `contract_id` (`adapters/odoo/executor.py:103-166`, then `_read_more` at `:181-278`, ending in `UNSUPPORTED`). Writes use another chain (`:298-326`).
- One new read touches about 12–15 files. These include the domain constant, query model, `INPUT_SCHEMAS` (`erp/plugin.py:45-65`), two manifests, the executor, the bridge method, a bridge version bump (`addons/e_agent_bridge/__manifest__.py:3`, plus the `expected_bridge_version` pins), the fake ERP, three profiles' `bindings`, tests and re-pinned digests.
- Some reads pass bridge payloads through unchanged (`raw["orders"]`, `executor.py:255,266`). That contradicts the Odoo plan's rule of explicit keys with no pass-through.

**Impact.** Phase 5 adds about 40 capabilities (from about 18 to about 60). At the current cost, wide integration becomes a release-coordination problem between the adapter, the bridge and the profiles. Pass-through payloads also undermine field-level governance (DR-05).

**Fix.**
1. Make Phase 5 task 1 a refactor: replace the chain with a `contract_id → handler` registry inside the adapter, and give each capability a declarative output projection (an allowlist of keys, with types), checked by a test.
2. Decide in an ADR whether reads may use one generic, **allowlisted** bridge read. Its parameters would be model, field allowlist, domain template and limit, declared per capability in the adapter manifest. This keeps ADR 0005's "no generic execute", because it is read-only and allowlisted, and it turns most new reads into data instead of a bridge release. Writes stay bespoke bridge commands.
3. Derive profile `bindings` from the manifests by default, so that a new binding does not require editing every profile.

**Phase.** 5, before Phase 2 of the Odoo plan.

### DR-03 — Medium: the integration-management seams are declared but have no consumer

**Evidence.**
- The Odoo manifest declares `connection.auth_methods` and `test_connection` (`adapters/odoo/e_agent_plugin.json:141-171`), but no code reads `manifest.connection`.
- Auth placement is hardcoded by plugin ID (`server/bootstrap.py:38`, `AUTH_PLACEMENT = {"odoo19": …}`).
- `settings_schema` is never validated.
- Connections live in profile JSON (`server/profile.py:76`) and an in-memory `ConnectionCatalog`. None of the four migrations creates a connections table.
- `connection.version` exists and is part of the digest, but versions only change when the file is edited.

**Impact.** ADR 0012/0013 are accepted contracts with no consumer, so they will drift. The second integration has to edit bootstrap, which contradicts "a new provider is a new adapter plus manifest only" (U1/G3). Every new provider and every new connection needs a redeploy.

**Fix.**
- Move "bootstrap reads `manifest.connection` (auth placement, schema validation of settings)" into Phase 5, where bindings multiply. Remove `AUTH_PLACEMENT`.
- Add a G3 fitness test: a fixture adapter with a second auth method is wired without editing the server.
- Persisting connections (a table, versions, lifecycle and an audit row) can stay in Phase 8, but it needs a decision now on whether profile JSON remains a seed or the source of truth.

**Phase.** 5 (manifest consumption), 8 (persistence and admin).

### DR-04 — Medium: "plugin-driven" [I] is narrower than the design claims

**Evidence.**
- Only `dists/domain-erp` and `dists/adapter-odoo` register entry points.
- The driver, store, validator and secret store are imported directly and chosen by `kind` strings in bootstrap (`server/bootstrap.py:15-18,79,143`).
- The shared composition root imports the packaged fixture provider unconditionally (`bootstrap.py:21-25`: `FakeErp`, `SCENARIOS`, `ScriptedErpDriver`), including in live profiles.
- The target architecture's R3 row says [I].

**Impact.** HLD §4 allows bootstrap to choose implementations, so this is not a rule violation. It does mean that the second driver (G7), a second store or a vault `SecretStore` needs a server edit and a server release. The flexibility principle depends on those seams being swappable.

**Fix.**
- State R3 precisely: "[I] for domain packs and ERP adapters; [P] for drivers, stores, validators and secret stores".
- When the first second implementation arrives (most likely the driver conformance work in Phase 3, or a vault adapter in Phase 7), give these port kinds the same entry-point discovery and admission.
- Move the fixture wiring behind the fixture plugin, so that a live composition root never loads fixture code.

**Phase.** 3 (driver), 7 (secret store).

### DR-05 — High: data governance for run, evidence and model-context data is undesigned and unimplemented

**Evidence** (all "not found" unless a location is given):
- **Classification.** There is no sensitivity or PII label on capability outputs or fields. The only "classification" in the code is the run-outcome category (`kernel/evidence.py:45`).
- **Minimization toward the model.** Observation data reaches the model unchanged: `adapters/pydantic_ai/driver.py:403` sends `{"data": dict(obs.data), …}`. ADR 0021 leaves the data-egress review for a hosted upstream to the operator. The only cross-border control in the threat model is for BigQuery (T13).
- **Redaction.** There is no redaction function. Evidence counts as "redacted" only because the ledger stores no secrets (`evidence.py:3-6`), and `build_evidence` exports every run, action, approval, receipt and event as it is (`evidence.py:88-125`). `read.recorded` events hold only refs (`kernel/gateway.py:54-61`). Business values still reach the export through action arguments, outcomes and model text (`message.final`).
- **Persisted observation data.** Raw read results persist outside the event log, inside the driver continuation (the framework message history, ADR 0004). No retention applies to it.
- **Export authorization.** `GET /v1/runs/{id}/evidence` checks only that a session exists and scopes by tenant (`server/api.py:484-493`). HLD §9 requires authorization, and target §13.2 notes this gap.
- **Retention.** The only time limit is the approval TTL. Retention is listed as [P] in target §13 ("Data lifecycle"), with no design.
- **Deletion.** `RunStore` has no delete methods (`sdk/store.py:60-197`). There is no tenant offboarding and no data-subject deletion path. Continuations hold framework message history, including ERP data.
- **Data ownership.** HLD §8 assigns owners per data class. Nothing records a data owner or legal basis per connection, except T13's precondition for BigQuery.

**Impact.**
- Every principle except governance has a fitness-tested design.
- Phase 5 widens the data surface considerably: partner notes, credit limits, invoices and payment terms. Phase 4 carries context across runs. Phase 9 adds memory. Each of these makes governance more expensive to add afterwards.
- Vietnam PDPL (already cited in T13) and any GDPR-style regime need purpose, minimization, retention and deletion controls on the run ledger, not only on the knowledge store.

**Fix.** A new ADR candidate, **C19: data classification, minimization, retention and deletion**.
1. **Classification as pack data.** Each capability output schema marks fields with a sensitivity class (for example `public`, `internal`, `personal`, `sensitive-personal`, `secret`). The registry rejects unmarked fields in live profiles.
2. **Minimization in the ContextAssembler (C9, Phase 3).** `ContextPolicy` gains a dimension that says which classes may reach which model route (local versus hosted), with masking or dropping recorded in `ContextPack.dropped`. The same projection drives the evidence export. This puts the policy in the kernel, where target §7.1 already says "what may enter" belongs. The driver alone cannot do this, because `dict(obs.data)` is already too late.
3. **Model routes declare their data boundary.** For example `local`, `hosted:<region>`. A profile that sends `personal` data to a hosted route needs an explicit declaration of the data owner and legal basis, reported in `/health/ready` the way `self_approval_allowed` is.
4. **Retention per record class.** Classes include events, evidence payloads, continuations, idempotency rows and conversations. Retention needs a purge job that keeps the audit skeleton (IDs, digests, actors, states) and drops payloads. Decide how this interacts with append-only grants (C17): purge runs under a dedicated role.
5. **Deletion.** Tenant offboarding, plus a subject-deletion path that removes payloads in which a subject's identifier appears. It is tested like the §8 memory cascade.
6. **Export authorization and the access log** stay in C16/C17, but move export authorization ahead of Phase 5 live evaluation, because evidence will then hold real-looking partner data.
7. **Threat-model entries.** T22 covers personal data egress to hosted models. T23 covers the evidence export as an exfiltration channel.

**Phase.** ADR in Phase 3 (with C9), classification markers in Phase 5 (with each new capability), retention and deletion in Phase 7.

### DR-06 — Medium: ADRs 0018–0022 are implemented but still Proposed

**Evidence.** The ADR index shows 0018–0022 as **Proposed**. The target architecture tags their content [I] (run transition table, sweeper, self-approval, `CONNECTION_BUSY`, LiteLLM, conversational replies). The ADR index rule says "A proposed ADR does not change the baseline until accepted", and roadmap rule 2 says a phase merges only after its ADRs are accepted.

**Impact.** The code depends on a baseline that the documents say does not exist. The Phase 1 branch is also unmerged. Agents that follow AGENTS.md will treat this behaviour as non-baseline.

**Fix.** The owner accepts, amends or rejects 0018–0022. On acceptance, merge their content into the HLD and MVP design as the ADR index requires. ADR 0023 (conversations) is planned to amend 0022, so decide 0022 first.

### DR-07 — Medium: concurrency is deferred while Phases 4–5 add load

**Evidence.** The owner deferred C1, C2 and the C3 lease to Phase 6. Today a process runs one run at a time (`server/api.py:215-217`), SSE polls every 200 ms per viewer (`api.py:388-417`), and there are no request limits. Phase 4 adds conversation threads with more runs per user, and Phase 5 adds multi-write plans and live evaluation of about 29 patterns.

**Impact.** The deferral itself is accepted and not reopened here. The risk is that Phase 5's evaluation timings (tokens, time, ADR 0010 metrics) are measured on a runtime whose queueing behaviour then changes in Phase 6. Phase 5 latency numbers would then not carry over.

**Fix.** Keep Phase 6 where it is, but add a **Phase 5 live-evaluation entry gate**: the shared-singleton audit (target §12.2) and a recorded single-slot baseline from the fixture load harness. Then Phase 6 has a before/after comparison, and Phase 5 numbers are labelled single-slot.

### DR-08 — Low (accepted risk): genericity is proven only by a test fixture

**Evidence.** G2 relies on the "notes" fixture domain (`tests/unit/kernel/conftest.py`). The Odoo plan explicitly chooses depth over a second domain, and G2, G3 and G10 stay open until Phase 8.

**Impact.** With about 60 ERP capabilities, ERP assumptions can leak into the SDK and kernel unnoticed: per-contract `INPUT_SCHEMAS`, answer contracts, approval presentation and the bridge-version enum. The fixture domain cannot catch these, because it uses none of them.

**Fix.** Record this as accepted risk in the roadmap. Add a cheap guard in Phase 5: each new SDK or kernel change made for Phase 5 is checked against the notes fixture, and any change the fixture cannot exercise is listed for Phase 8.

### DR-09 — Low: compatibility checks detect change, not breakage

**Evidence.** The OpenAPI check is an exact-match "up to date" check (`scripts/export_openapi.py --check`, CI `ci.yml:41-42,84-86`), not a breaking-change diff. Plugin compatibility is only the `sdk_api` range (`manifest.py:35-57`). Event, contract and continuation versions exist (`events.py:39`, `capability.py:12`, `kernel/continuation.py:53`).

**Impact.** Independently released wheels and a replaceable UI (ADR 0011) need to know when a change breaks a consumer. An exact-match check forces regeneration but cannot say whether the regenerated contract is compatible.

**Fix.** Add an OpenAPI breaking-change diff against the last released snapshot (for example oasdiff), and a JSON Schema diff for event payloads and capability schemas. Treat the store and driver conformance suites as the consumer-driven contracts of the plugin API, and run them against the previous SDK minor version when `sdk_api` changes.

### DR-10 — Low: two roadmaps, and stale status lines

**Evidence.**
- Target-architecture §18 (P0–P5, concurrency first) and `docs/roadmap.md` (Phases 0–9, cognition first) give different orders.
- The HLD header says "Implementation status: research/design only".
- The MVP design says "not implemented".
- Integration management and the threat model say "nothing is implemented" and "No mitigation here is implemented yet", although parts are.

**Impact.** AGENTS.md tells agents to read these files first, so they get contradictory status and ordering.

**Fix.**
- Mark target §18 "superseded by docs/roadmap.md" and keep only its exit evidence, which the roadmap can reference.
- Replace the stale status lines with a pointer to the README status and the latest retest, plus the date of the last check.

### Not raised as findings (checked, adequate for now)

- **FastAPI.** Kept, with a trigger (C5).
- **No broker, graph or vector database yet.** Each has a trigger.
- **Single Postgres.** Accepted, with RLS role design in §13.1.
- **External policy engine deferred.** OPA and Cedar have a trigger (§13.2).
- **Backup, HA and DR.** The design never mentions them. They are outside the current scope ("no production SLAs"), but the ledger is the system of record for approvals and receipts. Phase 7 should state its recovery point and recovery time objectives (RPO and RTO) and a restore test, even for a single-node deployment.

---

## 3. ADR candidates from this review

| ID | Decision | Phase | Refines |
|---|---|---|---|
| C19 | Data classification, minimization toward model routes, retention per record class, deletion and offboarding (DR-05) | ADR in 3; implementation in 3, 5 and 7 | HLD §8–§9, ADR 0008, 0021; threat model T13 |
| C20 | Execution IR and action plans: digest scope with lineage placeholders, per-step admission, partial failure, toggle semantics (DR-01); this is the ADR the roadmap already expects | 2 (entry) | MVP §7–§9, ADR 0006, 0020 |
| C21 | Allowlisted declarative bridge reads, or a confirmation of bespoke bridge methods per read (DR-02) | 5 | ADR 0005 |
| C22 | Entry-point discovery for driver, store, validator and secret-store port kinds when a second implementation appears (DR-04) | 3 / 7 | HLD §4, MVP §6 |

## 4. Principle × phase coverage after this review

| Principle | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 |
|---|---|---|---|---|---|---|---|---|
| Scale | toggles | | | entry gate: singleton audit + baseline (DR-07) | C1–C4 | | | |
| Flexibility | IR design (DR-01) | driver conformance; port discovery (DR-04) | | | | policy bundles | | |
| Plugin-driven | | port discovery for drivers (DR-04) | | adapter handler registry (DR-02) | | secret-store discovery | MCP binding | |
| Wide integration | | | | manifest `connection` consumed (DR-03); declarative reads (DR-02) | | | persisted connections, OAuth, triggers, second domain | |
| Data governance | | **C19 ADR + minimization in ContextAssembler** | carried-context retention | field classification per capability; export authz before live eval | | retention, deletion, RLS, access log | | memory cascade (exists in design) |

## 5. Not verified

- Whether a live start with `profiles/live.example.json` (no `artifact_sha256`) is refused or supported by a runbook step that pins digests.
- Concurrency safety of the Odoo client, `PublicTextBus` and coordinator caches (target §12.2 lists them as still to check).
- Whether any UI path renders evidence payloads that would need the same minimization as the model path.
- Performance of any kind: no load was generated.

## 6. Sources

Repository: the documents listed under Scope, the [2026-10-11 scalability review](2026-10-11-scalability-architecture-review.md) and the code locations cited above.

External practice (accessed 2026-10-14; vendor and practitioner guidance, not standards):
- Data ownership, sensitivity labels, lineage and retention as core agent data-governance controls: [CData, AI agent data governance](https://www.cdata.com/blog/ai-agent-data-governance); [TechTarget, agentic AI governance strategies](https://www.techtarget.com/ai/tip/8-agentic-AI-governance-strategies-A-complete-guide).
- Access that outlives its purpose, and cross-agent PII leakage through intermediate outputs: [Promethium, AI agent data governance playbook 2026](https://promethium.ai/guides/ai-agent-data-governance-enterprise-playbook-2026/); [Diagrid, data governance for AI agents](https://www.diagrid.io/learn/data-governance-for-ai-agents).
- Consumer-driven contracts and breaking-change detection beyond schema diffs: [Gravitee, API contract testing and consumer-driven versioning](https://gravitee.io/corpus/gen-1143/api-management/api-contract-testing-and-consumer-driven-versioning-strategies.html); [Gravitee, OpenAPI contract testing](https://gravitee.io/contract-testing-gate.html).
