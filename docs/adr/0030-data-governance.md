# ADR 0030: Data classification, minimization, retention and deletion for run data

Date: 2026-10-14. Amended 2026-10-19 again (owner, Task 3b.3): `data_classes` keys are instance paths. Status: Proposed; **the parts marked [Phase 3] were accepted by the owner on 2026-10-19 at gate G2** (Phase 3 Task 3a.2). Amended 2026-10-19 (Phase 3 Task 3a.1): the loopback rule and the boundary basis (Phase 3 plan D2), and field classes declared beside the schema instead of inside it. **At gate G2 (Phase 3 Task 3a.2) the owner accepts or amends the parts marked [Phase 3]**: the route boundary and startup rule, field and record classes, minimization and bounded results. The parts marked [Phase 5] (class markers on new capabilities, export authorization) and [Phase 7] (retention and deletion) stay Proposed after G2. Refines ADRs 0004, 0008, 0021; HLD §8, §9; MVP design §10, §11; [target architecture](../design/target-architecture.md) §7, §13.2, §13.3.

## Context

The [design principles review](../reviews/2026-10-14-design-principles-review.md) DR-05 found that data governance for run, evidence and model-context data is neither designed nor implemented. Re-checked at `51c6c15` (2026-10-19):
- There is no field classification.
- Observations reach the model unchanged (`adapters/pydantic_ai/driver.py:543`).
- The evidence export carries business values and checks only the tenant (`server/api.py:488-499`).
- The run store has no delete path (`RunStore`, `sdk/store.py:71-225`).
- No retention applies to continuations.
- ADR 0021 leaves data egress for a hosted upstream to the deployment.

Phase 5 widens the data surface (partners, invoices, credit limits), Phase 4 carries context across runs, and Phase 9 adds memory, so governance gets more expensive with each phase. Vietnam PDPL (threat T13) and GDPR-style regimes need purpose, minimization, retention and deletion controls on the run ledger.

The [adoption review](../reviews/2026-10-14-x-agent-adoption-review.md), approved by the owner on 2026-10-14, adds:
- XA-13: classes for stored records;
- AP-15: bounded results carry a truncation marker and are never labelled complete.

The first version of this ADR marked fields with an `x-data-class` keyword inside the capability JSON schemas. Those schemas are model-facing: the driver sends them as tool schemas, so a keyword inside them would change every model request, including the pinned `off` model requests (Phase 3 plan, "`off` is today"). The 2026-10-19 amendment moves the classes beside the schema.

## Decision

- **[Phase 3] Field classes are pack data, declared beside the schema.**
  - A capability declaration carries `CapabilityDescriptor.data_classes: Mapping[str, DataClass]`, with the classes `public`, `internal`, `personal`, `sensitive_personal` and `secret` (target §13.3).
  - Each key is an instance path: where the value sits in the capability's input or output data, written as an RFC 6901 pointer under `/input` or `/output`, with `items` standing for every array index. For example, `/output/partners/items/email` classes the email of every partner in the list. A value's class is the most restrictive class declared on its path or on any ancestor path; an undeclared value is `personal`. Keys of a dict-valued property are data, so a dict is classed by a declaration on the dict property itself. Admission refuses a path that does not resolve to a property through at least one branch of the schema; resolution only checks the path exists and never decides a class. (Owner decision 2026-10-19, Phase 3 Task 3b.3: the earlier schema-pointer keys let one value be reached through several schema paths, and three review rounds found ways to lower a class through them.)
  - The schemas themselves are unchanged, so the model-facing tool schemas, the approval digest and the `off` model requests do not change.
  - An unmarked property counts as `personal`. Readiness reports unmarked counts per capability.
  - The field is part of `sdk_api` 1.2 (ADR 0032) and has an empty default, so an existing declaration still loads.
- **[Phase 3] Stored record classes.** Each stored record kind declares a record class (`audit_skeleton`, `business_payload`, `infra`) and a retention class in a store-neutral registry, `contracts/data_classes.py`. A contract test fails when a declaration is missing; both stores inherit it (ENG-STORE-1).
- **[Phase 3] Model routes declare a data boundary.**
  - The driver route declares `data_boundary: local | hosted:<region>`. The declared value decides.
  - An undeclared `ollama` route whose base URL host is a loopback address (`localhost`, `127.0.0.0/8`, `::1`, compared literally, with no DNS lookup) is `local`. Any other undeclared route, `litellm` included, is `hosted:unknown`. Being undeclared is never refused for that alone; the rules below apply to the resulting boundary.
  - Readiness reports each boundary with its **basis**: `verified` for an `ollama` route on a loopback host (whether or not the profile also declares `local`), `declared` for an operator assertion, and `default` for an undeclared route that resolves to `hosted:unknown`. A LiteLLM route's boundary is never `verified`, because its upstream is outside e-agent: it is `declared` when the profile declares it and `default` otherwise. The scripted driver makes no model call; it reports `local`, basis `verified`.
  - `local_only: true` refuses non-local routes at startup.
  - A hosted route that may receive `personal` data needs a profile `data_processing` declaration (data owner, legal basis, region), reported in `/health/ready`.
  - **Startup rule:** a route that is not `local` and has no `data_processing` declaration fails startup while `features.context_assembler` is not `on`. The exemption for `on` lands together with the masking it relies on (Phase 3 Task 3d.5); until then the rule refuses such a route whatever the toggle says, so `on` never covers an unbuilt path (ADR 0027). No committed profile uses a hosted route, and the owner's live profile uses a loopback Ollama, so it needs no edit.
  - The route is not pinned per run, so the startup rule alone cannot protect a run that resumes on another route. The per-call route check of ADR 0032 (`ROUTE_BOUNDARY_UNMET`) covers it.
  - This refines the sentence in ADR 0021's Consequences that leaves egress review to the deployment. ADR 0021 is not edited; on acceptance it gets a one-line pointer to this ADR.
- **[Phase 3] Minimization is a kernel concern.**
  - The ContextAssembler (ADR 0032) applies a class-per-route rule from `ContextPolicy`, masks values a route may not receive and records each one in `ContextPack.dropped`.
  - Tool output is bounded in the context pack (Phase 3 plan D3). A bounded or masked observation is `PARTIAL` with a `truncated` or `masked` marker. An error is never an empty result.
- **[Phase 5] Evidence export is a class-aware projection.** `personal` and `sensitive_personal` values are masked unless the exporter has auditor visibility. Export authorization (target §13.2 rule 4) is implemented before Phase 5 live evaluation, with the minimal visibility model. In local session mode the profile operator holds auditor visibility. `secret` values never enter the ledger, the context or the export (unchanged).
- **The approval card is never masked.** Classes govern model context, exports and any enabled telemetry content capture (ADR 0008), never the approval presentation (ADR 0006, T9).
- **[Phase 7] Retention and deletion:**
  - per-class retention periods in the profile;
  - a purge job that keeps the audit skeleton and runs under a dedicated purge role;
  - tenant offboarding after an authorized export;
  - subject deletion over `personal` fields, tested like the memory deletion cascade;
  - a data owner and legal basis declared on each live connection.
- **Threats:** T23 (personal data egress to a hosted model) and T24 (evidence export as an exfiltration channel).

## Alternatives considered

- Minimization inside the driver adapter: rejected because the adapter already holds the full observation, and every new driver would re-implement it. Target §7.1 puts "what may enter" in the kernel.
- Classes in the profile instead of the pack: rejected because the meaning of a field belongs to the domain that defines it. Profiles choose routes and bases, not field meaning.
- Classes inside the JSON schema (`x-data-class`, this ADR's first version): replaced on 2026-10-19 because the schema is sent to the model as the tool schema, so the keyword would change every model request and the pinned `off` requests.
- Required classes with refusal of unmarked fields: rejected for now because every existing capability would fail at once. The conservative `personal` default gives the same protection on hosted routes.
- Resolving the route host through DNS to decide loopback: rejected because the answer can change after startup; a literal loopback host is checkable, and any other host can be declared.
- Deleting whole runs for retention: rejected because approvals, receipts and reason codes are the audit record. Only payloads expire.
- An external data-catalog or DLP service: deferred until a deployment needs cross-system lineage or regulated-data scanning.

## Consequences

- Code:
  - `data_classes` declarations in the ERP pack and the notes test pack (Phase 3 Task 3b.3);
  - registry reading of classes and unmarked counts;
  - readiness fields (`data_boundary`, `data_boundary_basis`, `data_processing_declared`, unmarked counts);
  - a `data_boundary` setting on the driver route, plus `local_only` and `data_processing` profile settings, and the effective-boundary function (Task 3b.1);
  - the startup rule (Task 3b.1) and its `on` exemption (Task 3d.5);
  - `ContextPolicy` class rules and bounded-result markers (Tasks 3d.1, 3d.2);
  - the evidence projection and export authorization (before Phase 5 live evaluation);
  - the purge job, purge role, offboarding and subject deletion (Phase 7).
- Tests and evidence:
  - an unmarked property is treated as `personal`;
  - a `data_classes` instance path that resolves to no property fails admission;
  - an undeclared loopback Ollama route is `local` with basis `verified`; an undeclared remote or LiteLLM route is `hosted:unknown` with basis `default`;
  - startup is refused for a hosted route without `data_processing` and for `local_only` with a hosted route;
  - a masked value is recorded in `dropped`;
  - a bounded result is `PARTIAL` with its marker;
  - the export masks personal values for a non-auditor;
  - every table has a record class;
  - purge keeps the audit skeleton;
  - the subject-deletion cascade.
- Operations: profiles that use LiteLLM with a hosted upstream must add `data_processing` or switch to `local_only`. `/health/ready` shows the boundary and basis of every route.

## Gates

- Phase 3, first task (Task 3b.1): the route boundary, the startup rule and readiness fields, gate `full`.
- Phase 3 (Task 3b.3): field and record classes, gates `full` and `pg`.
- Phase 3 (Tasks 3d.1–3d.5): minimization and bounded results with the ContextAssembler, gates `full` and `pg`.
- Phase 5: class markers on each new capability, and export authorization before live evaluation.
- Phase 7: retention, purge role, offboarding and subject deletion, gates `full` and `pg`.
