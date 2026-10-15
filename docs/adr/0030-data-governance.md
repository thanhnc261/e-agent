# ADR 0030: Data classification, minimization, retention and deletion for run data

Date: 2026-10-14. Status: Proposed. Refines ADRs 0004, 0008, 0021; HLD §8, §9; MVP design §10, §11; [target architecture](../design/target-architecture.md) §7, §13.2, §13.3.

## Context

The [design principles review](../reviews/2026-10-14-design-principles-review.md) DR-05 found that data governance for run, evidence and model-context data is neither designed nor implemented:
- There is no field classification.
- Observations reach the model unchanged (`adapters/pydantic_ai/driver.py:403`).
- The evidence export carries business values and checks only the tenant (`server/api.py:484-493`).
- The run store has no delete path (`sdk/store.py:60-197`).
- No retention applies to continuations.
- ADR 0021 leaves data egress for a hosted upstream to the deployment.

Phase 5 widens the data surface (partners, invoices, credit limits), Phase 4 carries context across runs, and Phase 9 adds memory, so governance gets more expensive with each phase. Vietnam PDPL (threat T13) and GDPR-style regimes need purpose, minimization, retention and deletion controls on the run ledger.

The [adoption review](../reviews/2026-10-14-x-agent-adoption-review.md), approved by the owner on 2026-10-14, adds:
- XA-13: classes for stored records;
- AP-15: bounded results carry a truncation marker and are never labelled complete.

## Decision

- **Field classes are pack data.** Capability input and output schemas mark properties with `x-data-class`: `public`, `internal`, `personal`, `sensitive_personal` or `secret` (target §13.3). An unmarked property counts as `personal`. Readiness reports unmarked counts per capability.
- **Stored record classes.** Each stored record kind declares a record class (`audit_skeleton`, `business_payload`, `infra`) and a retention class in a store-neutral registry, `contracts/data_classes.py`. A contract test fails when a declaration is missing; both stores inherit it (ENG-STORE-1).
- **Model routes declare a data boundary.**
  - The driver route declares `local` or `hosted:<region>`; an undeclared route is `hosted:unknown`.
  - `local_only: true` refuses non-local routes at startup.
  - A hosted route that may receive `personal` data needs a profile `data_processing` declaration (data owner, legal basis, region), reported in `/health/ready`.
  - While `features.context_assembler` is not `on`, a non-local route without that declaration fails startup. No committed profile uses a hosted route.
  - A LiteLLM route's boundary is an operator assertion (its upstream is outside e-agent), reported as `declared`, not `verified`.
  - This refines the sentence in ADR 0021's Consequences that leaves egress review to the deployment. ADR 0021 is not edited; on acceptance it gets a one-line pointer to this ADR.
- **Minimization is a kernel concern.**
  - The ContextAssembler (C9, Phase 3) applies a class-per-route rule from `ContextPolicy`, masks or drops values and records them in `ContextPack.dropped`.
  - Tool output is bounded per capability. A bounded or masked observation is `PARTIAL` with a `truncated` or `masked` marker. An error is never an empty result.
- **Evidence export is a class-aware projection.** `personal` and `sensitive_personal` values are masked unless the exporter has auditor visibility. Export authorization (target §13.2 rule 4) is implemented before Phase 5 live evaluation, with the minimal visibility model. In local session mode the profile operator holds auditor visibility. `secret` values never enter the ledger, the context or the export (unchanged).
- **The approval card is never masked.** Classes govern model context, exports and any enabled telemetry content capture (ADR 0008), never the approval presentation (ADR 0006, T9).
- **Retention and deletion** (Phase 7):
  - per-class retention periods in the profile;
  - a purge job that keeps the audit skeleton and runs under a dedicated purge role;
  - tenant offboarding after an authorized export;
  - subject deletion over `personal` fields, tested like the memory deletion cascade;
  - a data owner and legal basis declared on each live connection.
- **Threats:** T23 (personal data egress to a hosted model) and T24 (evidence export as an exfiltration channel).

## Alternatives considered

- Minimization inside the driver adapter: rejected because the adapter already holds the full observation, and every new driver would re-implement it. Target §7.1 puts "what may enter" in the kernel.
- Classes in the profile instead of the pack: rejected because the meaning of a field belongs to the domain that defines it. Profiles choose routes and bases, not field meaning.
- Required classes with refusal of unmarked fields: rejected for now because every existing capability would fail at once. The conservative `personal` default gives the same protection on hosted routes.
- Deleting whole runs for retention: rejected because approvals, receipts and reason codes are the audit record. Only payloads expire.
- An external data-catalog or DLP service: deferred until a deployment needs cross-system lineage or regulated-data scanning.

## Consequences

- Code:
  - schema annotations in the ERP pack and the notes domain;
  - registry reading of classes;
  - readiness fields;
  - a `data_boundary` setting on the driver route, plus `local_only` and `data_processing` profile settings;
  - the startup rule;
  - `ContextPolicy` class rules and bounded-result markers (Phase 3);
  - the evidence projection and export authorization (before Phase 5 live evaluation);
  - the purge job, purge role, offboarding and subject deletion (Phase 7).
- Tests and evidence:
  - an unmarked property is treated as `personal`;
  - startup is refused for a hosted route without `data_processing` and for `local_only` with a hosted route;
  - a masked value is recorded in `dropped`;
  - a bounded result is `PARTIAL` with its marker;
  - the export masks personal values for a non-auditor;
  - every table has a record class;
  - purge keeps the audit skeleton;
  - the subject-deletion cascade.
- Operations: profiles that use LiteLLM with a hosted upstream must add `data_processing` or switch to `local_only`. `/health/ready` shows the boundary of every route.

## Gates

- Phase 3, first task: the startup rule and readiness fields, gate `full`.
- Phase 3: minimization and bounded results with the ContextAssembler, gates `full` and `pg`.
- Phase 5: class markers on each new capability, and export authorization before live evaluation.
- Phase 7: retention, purge role, offboarding and subject deletion, gates `full` and `pg`.
