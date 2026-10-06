# ERP agent MVP: demonstration, evidence, and an extensible product boundary

Date: 2026-10-06. Status: delivery proposal after a targeted inspection of `/Users/thanhnguyen/dev/lab/enterprise-agent/experiment`. Updated direction following the user's clarification: develop the product MVP independently in `/Users/thanhnguyen/dev/projects/personal/e-agent`; keep the experiment as a reference/evaluation system without cross-repository imports. See [package organization](07-package-and-plugin-organization.md) and [architecture verification](08-architecture-decisions-and-fitness.md) for the proposed implementation structure.

## 1. Product goal

Demonstrate a real model-driven agent completing bounded ERP tasks, with ontology validation affecting execution, independent verification of the resulting ERP state, and a plugin architecture that can support later applications. Modern explainable UI and a governed enterprise knowledge graph are the next phase. Minimal evidence visibility belongs in the MVP so the demonstration is inspectable.

Keep three claims separate:

1. **Mechanism:** an invalid plan is rejected by executable ontology constraints, a corrected plan passes, and violations identify their rule and evidence.
2. **Task capability:** a live agent produces the correct terminal state on explicitly scoped ERP tasks.
3. **Comparative benefit:** ontology improves measured outcomes over suitable controls. This requires repeated, controlled trials; a successful demo alone cannot establish it.

## 2. Existing experiment: verified reuse opportunities and gaps

| Component | Inspected state | Delivery implication |
|---|---|---|
| Agent loop | `loop/agent.py` accepts model, ERP and validator ports; validation consultation/repair and receipts already exist | Preserve these boundaries rather than replacing the system with another agent framework |
| Validation | SHACL consumes shared PlanFacts, constructs RDF and returns canonical violations with provenance | Use the existing mechanism as a reference; keep procedural controls free of RDF dependencies |
| ERP integration | Odoo provider exposes capability/read/execute interfaces and committed/failed/unknown receipts | Verify real final state; audit restart/timeout semantics before claiming durable idempotency |
| Demo profile | `configs/profiles/demo.toml` enables `approval`, but resolving it raises `UnknownPlugin` because its module is absent | Declared configuration is not a working approval workflow; close the seam explicitly |
| Plugin registry | Static registry resolves module availability; digest is calculated from a registered source string | Do not advertise the existing digest as verification of actual installed plugin code |
| Run service | UI-triggered runs exist and are distinguished from confirmatory runs | Keep demo orchestration and its outputs outside confirmatory evaluation |
| UI | Chat, run inspector, comparison and timeline files already exist | Inspect behavior before reusing; modern redesign is not required for the first milestone |
| Measurement | Ledger reports prior local pilots with no verifier-passing task | Prior runs do not establish successful ERP capability; collect fresh scoped evidence |
| Documentation | README still describes early scaffolding despite substantial implementation | The new demo needs its own accurate runbook and explicit readiness statement |

This was a targeted code/configuration review, not a full audit. No external ERP-Bench solutions, hidden tests, credentials or reward files were inspected. No Odoo/Docker/model process was started and no ERP data was changed.

## 3. First demo scope

Use an isolated synthetic Odoo database. Establish one task family first; add the next family only after the first passes end to end.

| Scenario | Agent task | Constraints to expose | Independent outcome checks |
|---|---|---|---|
| Procurement | Read stock and supplier offers, then prepare/execute procurement for a specified demand | Purchase only the shortage; approved supplier/offer; quantity, budget and delivery bounds | Correct PO lines, quantities, supplier, totals and links; no unwanted extra orders |
| Order acceptance | Read a customer request and decide whether to accept it under explicit policy | Quantity range, lead time, price/budget and required references | Correct SO state and lines; rejected requests cause no downstream write |
| Failure demonstration | Recover or stop after invalid plan, missing data, changed approval or uncertain tool outcome | Validation fail-closed; approval binds exact action; no blind retry | No unauthorized effect; explicit blocked/unknown state; evidence explains the reason |

Begin with procurement as the delivery spine. Keep manufacturing scheduling and invoice posting outside the first scope because they introduce additional transactional and optimization complexity. These can become later domain packs.

## 4. MVP architecture

```text
CLI / thin existing UI
         |
Demo application service
         |
Model-driven loop ---- Model adapter
         |
Typed proposed plan
         |
Validator port ------- Ontology/SHACL plugin
         |             (procedural control in evaluation only)
Execution/approval gate
         |
Action ledger -------- ERP capability adapter -------- isolated Odoo
         |
Receipts + independent read-back verifier
         |
Versioned evidence bundle
```

Core contracts: TaskContext, CapabilityDescriptor, CandidatePlan, ValidationResponse, ApprovalRecord, ExecutionReceipt, RunEvent and OutcomeReport. Reuse compatible contracts where implementation location permits; do not introduce cross-imports between repositories or the experiment's two subprojects.

The model proposes actions. It cannot declare itself approved, override a violation or mark its own action verified. The action gateway enforces these decisions independently.

## 5. MVP work packages and acceptance

| Package | Deliverable | Acceptance |
|---|---|---|
| M0 — Scope and isolation | Demo profile/run namespace, synthetic ERP setup, a fixed task set and model configuration | Run cannot target protected evidence/seed databases; demo outputs cannot enter confirmatory analysis |
| M1 — Contracts and registry | Versioned plugin/capability contracts, explicit enabled set, working module resolution and real artifact fingerprint | Unknown/disabled plugin fails closed; add one sample capability through registration without editing the loop |
| M2 — Ontology pack | Entity vocabulary, constraints, source references, plan-to-facts/graph projection | Conforming and deliberately invalid cases produce inspectable rule IDs, observed values and provenance |
| M3 — Live agent | Bounded read → propose → validate → repair loop using a real model provider | Completion cannot rely on a hardcoded successful plan; missing data leads to clarification or a safe stop |
| M4 — Controlled execution | Approval bound to canonical plan digest, receipt persistence and explicit uncertain outcomes | Changed plan invalidates approval; writes cannot bypass the gate; restart/retry does not silently replay an unknown effect |
| M5 — ERP outcome verification | Separate read-back checks of business state | A model's success message is insufficient; wrong/partial state is reported as failure or incomplete |
| M6 — Evidence and evaluation | Replayable run transcript, rule/plan changes, final-state diff and test report | Report distinguishes scripted fault injection, live model run, infrastructure failure and verified success |
| M7 — Demo packaging | One documented startup path, health checks, resettable synthetic workspace and a five-minute script | A second developer can reproduce setup and all three demonstration paths |

Offline deterministic fixtures are useful for CI and explaining constraint behavior. They must be labeled as such and must not be reported as live model capability or Odoo execution evidence.

## 6. How to demonstrate ontology value honestly

The mechanism demo presents the same ERP state and candidate plan to validation. A rejected plan shows a concrete business violation; a repair is revalidated before execution. Display the plan version, rule ID, source reference, expected/observed values, repair and final receipt.

For comparative evaluation, use the experiment's existing four conditions: no policy, policy as text, procedural validation, and SHACL validation. Hold model, task instances, seeds where available, budgets, tools and evaluation constant. The primary comparison must follow the experiment's declared design; do not change it to favor the demo.

Procedural and SHACL implementations of identical rules should agree. Parity is desirable. It is not reasonable to promise SHACL beats an equivalent procedural validator merely because it uses RDF. Potential additional ontology benefits—schema extensibility, provenance, reuse and maintainability—need separate engineering measurements.

Use a small development set across the selected task families, with multiple trials per case, before choosing showcase examples. Record all failures and keep a held-out set for later evaluation. The showcase demonstrates a capability; the complete report limits the claim to its tested scope.

## 7. Phase 2: explainable UI and governed knowledge graph

| Area | Phase 2 deliverable | Foundation required in MVP |
|---|---|---|
| Agent workspace | Modern chat/task interface with streaming progress and resumable actions | Stable run/event/action IDs and explicit states |
| Explanation view | Goal → evidence → constraint → plan → action → outcome; source/rule drill-down | Structured decision records and provenance, not hidden chain-of-thought |
| Human review | Action diff, approver identity, expiry and changed-resource warnings | Persisted approval contract and canonical digests |
| Knowledge graph | Business entities, claims, relationships, valid/recorded time and source lineage | Stable domain IDs and versioned claim/projection contracts |
| Ontology governance | Propose → validate → review → publish → deprecate, with migrations and competency questions | Versioned vocabulary/shapes; no direct model-published changes |
| Data governance | Source ownership, ACL propagation, conflict handling, correction/deletion and projection rebuild | Source revisions, policy references and reverse lineage |
| Operational UX | Quality dashboard, failed/unknown-action queue and run comparison | Outcome verifier results, failure classes and traceable receipts |

Do not build a graph visualization over ungoverned extracted triples and call it ontology governance. Publish/review/version/invalidation behavior is the feature; visualization supports it.

## 8. Delivery estimate and completion definition

Preliminary estimate after model/environment are confirmed: 2–3 weeks for a tightly scoped implementation with 1–2 engineers, assuming the Odoo development environment and model access are available. This estimate has not been validated against the additional architecture gates in document 08. The previous local ERP success failures make a shorter promise unsafe; investigate the first full task before committing to the remaining schedule.

The MVP is ready when a reproducible live run completes a scoped ERP task, a constraint violation is visibly blocked and repaired, a rejected/changed approval prevents writing, terminal state is independently checked, plugin extension is demonstrated without loop changes, and evidence explicitly states the model, rules, scenario and limitations. UI polish and full enterprise knowledge governance remain Phase 2.
