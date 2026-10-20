# ADR 0033: Explanation contract, citations and grounded answers

Date: 2026-10-19. Status: Accepted (2026-10-19, owner, gate G2, Phase 3 Task 3a.2). At G2 the owner chose the digest-only rationale storage (section 4). Amended 2026-10-20 (Phase 3 review, owner accepted; Task 3.D1): section 1's value at the pointer, number rendering and length caps; section 4's rule-inventory seam, id shapes and at-rest form of model-authored refs (Task 3.R1); the CQ06 row; the unsalted-digest consequence. Amended 2026-10-20 (owner decision; Task 3.D2): the CQ07 row records the Skip of `rule_bundle_version` (ADR 0031 §3). Refines ADRs 0004, 0018, 0027 and 0028 (section 3 adds `AcceptanceSpec.grounded_answer` to the accepted ADR 0028 contract); [target architecture](../design/target-architecture.md) §5.6, §17 C18. Plan: [Phase 3](../plans/2026-10-19-phase3-cognition-context.md) D4, D5, D6, D10, Tasks 3c.3, 3e.1–3e.4.

## Context

Target §5.6 names three readers of an explanation (the approver, the requester, the auditor) and three rules: an explanation is never chain-of-thought, structured rationale is model-authored data that is checked and never a gate by itself, and facts in explanations come from the ledger. At `51c6c15` no `rationale` or citation field exists in the contracts, the driver or the evidence export, and the explanation is the event list plus `run.reason` and `ReasonCode`.

Two kinds of answer exist today. A typed answer (`EffectKind.ANSWER`, for example the ERP shortage answer in `plugins/erp/domain/*/api.py`) is verified by its domain verifier through fresh, independent reads (`_handle_answer`, then in `kernel/proposals.py`, now in `kernel/grounding.py`); an answer capability without a verifier fails (`KERNEL-VERIFIER`). A plain text reply after reads is not accepted: the kernel returns `KERNEL-VERIFICATION` and asks for a structured answer (`kernel/run_loop.py:179-203`). A read-only question that has no typed answer contract therefore cannot succeed. The core plan asked for such answers to be `verified`; PR-19 reserves that word for an independent read-back.

Research 03 §5 lists competency questions the knowledge layer must answer ([research 03](../../research/03-knowledge-and-cognitive-ontology.md), lines 91-100, in Vietnamese). Some of them concern one run's decisions and can be answered from its events alone.

## Decision

### 1. `Citation` and its envelope (D4, Task 3e.1)

- `Citation(evidence_id, pointer, value)` (`contracts/grounding.py`): `pointer` is an RFC 6901 JSON pointer into the `data` of the observation with that evidence id, and `value` is the value the model claims is there.
- The record caps `evidence_id` at 128 characters (`EVIDENCE_ID_MAX`) and `pointer` at 1024 (`POINTER_MAX`), and requires `value` to be a JSON value. Within the caps it accepts any text: a pointer that is not RFC 6901, or names nothing, is an unresolved citation the kernel returns as a repair, never a refused proposal.
- Citations travel in a kernel envelope beside the answer arguments: `ActionProposal.citations: tuple[Citation, ...] = ()`. The field is left out of serialization when empty. The domain answer models (`plugins/erp/domain/*/api.py`) and the notes test answer are unchanged, and the answer arguments reach the domain model without `citations`.
- A citation **resolves** when its `evidence_id` names an observation of **this run** (the kernel continuation's observations, looked up by evidence id and scoped by run, never by tenant alone; Review Focus 5, threat T6), the pointer exists in that observation's data, and the canonical value at the pointer equals the cited value. Equality is the equality of `jcs-sha256-v1` digests (ADR 0006, `contracts/digest.py`), with every JSON number of both values first written as its canonical decimal string, as the context pack renders it (`value_digest` in `kernel/grounding.py`, `number_text` in `contracts/context_pack.py`). A cited value outside the digest profile digests to `invalid` and is `mismatched`.
- **The value at the pointer** is read from the observation's raw data, except in a run pinned `context_assembler: on`, where it is read from the data as the pack's class walk shows it to the model (`ClassView`, `kernel/grounding.py`; ADR 0032 §5). There a masked value or a removed key is unresolved, exactly like a key that does not exist, and a cited masking marker never resolves, so the check is no oracle on what the pack withheld (PR-26). Evidence replaced by a later re-read of the same request is no longer in the continuation, so a citation to it does not resolve.
- The check reads only the continuation: it makes no provider read and no model call.
- **At rest** a citation is stored as `value_digest`, never the value (PR-26). Its `evidence_id` and `pointer` are stored as written only when the citation named a real value: the pointer found a value in an observation of this run with that evidence id, whether the citation then resolved or mismatched. Otherwise they are stored only as `evidence_id_digest` and `pointer_digest` (`citation_at_rest`, `kernel/at_rest.py`, Task 3.R1). The stored form goes in the `proposal.created` payload as the key `citations`, only for a run pinned `shadow` or `on` with at least one citation, so an `off` event is unchanged. `ActionRecord` gains no field.
- Citations are not in the approval digest: `digest_input` (`kernel/approval.py`) enumerates its fields, so a new proposal field is outside it by construction. A citation never grants approval, changes policy or marks anything verified (PR-13).

### 2. Citations on typed answers

- With `grounded_answers: on`, the kernel checks the citations of a typed answer before the answer's action is created and before its verifier reads. An unresolved or mismatched citation, or a pointer that does not exist, gives the repair finding `KERNEL-CITATION`, recorded in `validation.completed` with no action id and returned to the driver within `max_validation_repairs`, as `KERNEL-PLAN-CAPABILITY` is today (`kernel/ir_on.py`, `_repair_finding`). The finding names the citation's evidence id and pointer, never a value. The driver gets them as written, so the model can correct them; as recorded (in `validation.completed` and the stored continuation), a finding for a citation that named no real value holds the pointer's digest as `observed` and no evidence id (`finding_at_rest`, `repair_at_rest`, Task 3.R1). When every citation resolves, the answer takes today's path and its verifier decides whether it is verified (PR-19).
- A typed answer with no citations is not refused for that alone in Phase 3; its verifier decides as today.

### 3. The generic grounded answer `grounded.answer.v1` (D5, Task 3e.2)

- A core answer contract owned by the kernel, with arguments `{summary}` and citations in the envelope. It answers a read-only question for which no typed answer contract exists. It never stands in for a typed verifier (PR-19).
- It reads nothing and writes nothing, so it has no connection, binding or verifier. A connection named on it is ignored (model output never selects a connection, PR-12), and it creates no `ActionRecord`, so the action table and its states are unchanged.
- It is **not a registry capability**. It is outside the host tool specs and the registry `surface_digest`, so a run that is not pinned `on` never sees it and a toggle flip does not stale an in-flight approval (threat T17). The driver offers it as an extra tool, the way it offers `propose_plan` (`adapters/pydantic_ai/driver.py`).
- The kernel recognizes it in `_handle_proposal` **before** the task-set check (`_outside_task_set`) and the capability lookup, so a task definition's tool set does not refuse it and the no-verifier rule (`KERNEL-VERIFIER`) does not apply.
- When every citation resolves (at least one is required), the run ends `SUCCEEDED` with the new reason code `GROUNDED` (`grounded`, `contracts/run.py`). The `message.final` event carries the summary as its `text` and gains the keys `contract_id` and `citations` (the at-rest form). The evidence bundle labels the summary `unverified` model text and each citation `grounded`. A grounded answer is never `verified`, never has an outcome report and never satisfies a task definition's acceptance item that requires a verified answer.
- An unresolved citation is `KERNEL-CITATION`, within `max_validation_repairs`.
- **Admission.** The kernel admits the generic answer for a run only when all three hold, and the result is fixed for the run because its tool set and task definition are:
  1. the run is pinned `grounded_answers: on`. In `shadow` the kernel would have no existing path to act on when the model calls it (ADR 0027: `shadow` acts on nothing), so it is not offered there. This narrows D5's "not `off`"; the owner confirms or changes it at G2;
  2. the run's offered tool set contains no typed answer contract (no capability with `EffectKind.ANSWER`): the definition's capabilities on a bound run, every agent-visible capability otherwise. Where a typed answer exists, its verifier decides, and the generic answer cannot bypass it;
  3. the run is not bound to a task definition, or its definition's acceptance spec admits a grounded answer explicitly (below).
- A run that does not admit it is never offered it, and a call to it anyway is the fixed repair finding `KERNEL-GROUNDED-ANSWER`, recorded in `validation.completed` with no action id, within `max_validation_repairs`.
- **Acceptance (refines ADR 0028).** `AcceptanceSpec` gains `grounded_answer: bool = False` (Task 3e.2). It is valid only when `required_effects` and `required_answer` are both empty, so a definition that names a typed answer or an effect can never be met by a grounded one. The acceptance gate (`_acceptance_gap`, `kernel/ir_on.py:408-440`) reads only `VERIFIED` actions and verifier reports today; with `grounded_answer: true` it also accepts the run's `GROUNDED` end, read from the kernel's own citation-check record (the `message.final` it wrote with `contract_id` and the at-rest `citations`), never from model output (ENG-TRUST-1). With `false`, a grounded end never meets the spec. No task definition sets the flag today.
- **Counting.** A grounded run writes no `outcome.reported`, so the release report (`scripts/release_report.py`, which reads `outcome.reported` statuses) and model qualification (ADR 0010) count `GROUNDED` as its own category, never as `VERIFIED`. Task 3e.2 changes the release report.

### 4. `ProposalRationale` (D6, Task 3e.3)

```python
class ProposalRationale(Record):            # contracts/grounding.py
    goal_ref: RefId                          # "run", or the run's task definition task_id@task_version
    cited_evidence: tuple[RefId, ...]        # evidence ids of this run
    rules_considered: tuple[RefId, ...]      # rule ids from the admitted rule inventory (ADR 0009), or kernel finding ids
    alternatives: tuple[RejectedAlternative, ...]  # proposal digest, ReasonCode, one line
    summary: str                             # at most 400 characters, shown as model-authored
```

- `ActionProposal.rationale` and `ActionPlan.rationale` are `ProposalRationale | None`, left out of serialization when `None`. Rationale belongs to write and plan proposals; answers carry citations instead.
- **Id shapes.** Every id field is a `RefId` (`contracts/grounding.py`): 1 to 128 characters of letters, digits and `_.:@#/+-`, so no whitespace and no prose. The record refuses any other shape (Task 3e.3). An id of the right shape that names nothing is never refused by the record; the check returns it as a repair.
- **The admitted rule inventory** is the union of every admitted plugin's `PluginContribution.rule_inventory` (rule id to rule version, `sdk_api` 1.2, read from the plugin's packaged inventory resources; ADR 0009). The registry refuses a rule id that two plugins declare (PR-09) and a rule id with the kernel prefix `KERNEL-` (`kernel/registry.py`). It is never sent to a model.
- With `grounded_answers: on`, the rationale is checked before the proposal is validated and before an action is created. An evidence id that is not an observation of this run, or a rule id that is not in the admitted rule inventory and does not start with `KERNEL-`, gives the repair finding `KERNEL-RATIONALE` (one per id), returned like `KERNEL-CITATION`. The driver gets the id as written; as recorded (in `validation.completed` and the stored continuation), the finding holds only the id's digest as `observed` and no evidence id (`finding_at_rest`, Task 3.R1). A rationale that resolves changes nothing: validation, policy, approval and dispatch are today's. A rationale can only add a finding; it can never make a proposal pass.
- A `summary` over 400 characters is refused by the record.
- `goal_ref` is recorded and shown, not checked or refused, in Phase 3. The kernel knows two goal refs for a run (`known_goals`, `kernel/at_rest.py`): `run`, and the run's task definition `task_id@task_version` when it is bound to one. No acceptance-item suffix is recognised.
- Rationale is never an approval input and never enters the approval digest (target §5.6). The approval card shows the canonical proposal first and the rationale second, labelled model-authored (threat T9); the card UI is later work (D10).
- At rest the rationale is stored in the `proposal.created` payload under `rationale` (and a plan's step rationales under `step_rationales`) as codes and a `jcs-sha256-v1` digest of each model-authored text (`summary_digest`, and each alternative's `proposal_digest`, `reason_code` and `line_digest`), never the texts themselves (owner, G2). A model-authored ref is model text and can hold a value, so it is stored as written only when the kernel resolved it (Task 3.R1, `kernel/at_rest.py`):
  - `goal_ref` as written only when it is one of the run's known goal refs, otherwise only `goal_ref_digest`;
  - `cited_evidence` and `rules_considered` hold only the ids that resolved, in order, and a `KERNEL-*` rule id only when the kernel emits it (`KERNEL_FINDING_IDS`), although the check resolves any `KERNEL-*` id by its prefix;
  - the digest of every other evidence id and rule id goes under `unresolved_evidence_digests` and `unresolved_rule_digests`, left out when empty and never mixed into the id lists.

  This keeps the plan's ids-only payload rule (PR-26) without an exception. Events written before `24d6878` (Task 3.R1) keep the refs as written; no migration rewrites them (they predate the Phase 3 merge).
- **Rationale text is transient.** The texts live only in the run's continuation, like observation values. The approval card shows the rationale text while the continuation holds it; the explanation and the evidence export show the evidence ids, rule ids and text digests. Storing the texts as `business_payload`, masked by the Phase 5 class-aware export, was the alternative the owner declined at G2. Thinking parts stay stripped (ADR 0004, PR-28).

### 5. Toggle `features.grounded_answers` (D1)

| Mode | Behaviour |
|---|---|
| `off` | Today. Answer tools offer no `citations`, write and plan tools offer no `rationale`, and `grounded.answer.v1` is not offered. Citations or rationale that a driver sends anyway are dropped and not stored. |
| `shadow` | Citations and rationale are offered. The kernel checks them from the continuation and records `grounding.compared` (resolved, unresolved and mismatched counts for citations and for rationale refs). Typed answers go to their verifier and write proposals to validation as today. Real consumer: `test_grounding_shadow_agrees_with_on` over the authored grounded replays asserts that shadow's verdicts equal `on`'s and its case count (Task 3e.4); the release report shows the counts. A shadow error records `grounding.shadow_failed` and changes nothing else. |
| `on` | Sections 2–4: `KERNEL-CITATION`, `KERNEL-RATIONALE` and `KERNEL-GROUNDED-ANSWER` repair findings, and `grounded.answer.v1` where section 3 admits it. |

- `DriverInput.grounding` is a `GroundingOffer` (`off`, `cite`, `cite_and_answer`; default `off`) that the kernel derives per call from the run's pinned mode and section 3's admission: pinned `off` gives `off`; pinned `shadow` gives `cite`; pinned `on` gives `cite_and_answer` when the run admits the generic answer and `cite` otherwise. The driver offers `citations` and `rationale` unless it is `off`, and `grounded.answer.v1` only for `cite_and_answer`. The driver never reads the profile (D8). With `off`, both `off` model-request goldens (notes and ERP) stay byte-identical.
- **Failure handling (ADR 0027):** before the run's first reservation, `feature.fallback` with `GROUNDING_CHECK_FAILED`; a typed answer then goes to its verifier and a write proposal to validation as today. A `grounded.answer.v1` has no existing path, so its check failure fails the run closed with `GROUNDING_UNAVAILABLE`. After a reservation every check failure fails closed with `GROUNDING_UNAVAILABLE`, or goes to `NEEDS_RECONCILIATION` when a reservation is unresolved.

### 6. The explanation projection (Task 3c.3)

- `explain(ledger, reconstructed) -> Explanation` (`kernel/explain.py`) is pure and deterministic over the progress ledger and the reconstruction (ADR 0031). It makes no model call. It renders: goal → source facts (evidence ids and revisions) → validation findings by rule id → proposal (digest, then the rationale once Task 3e.3 lands) → approval (actor, policy version) → receipt → verified or grounded outcome.
- It holds no observation values and no model reasoning. Model-authored text (the grounded summary) is labelled as such and shown after the facts; a rationale appears as its evidence ids, rule ids and text digests.
- It is an additive `explanation` key of the evidence bundle and `e-agent explain <run_id>` on the CLI (D10). A run whose events predate ADR 0031's keys gives a `partial` explanation.
- It answers these research 03 §5 competency questions (translated from the Vietnamese table, research 03 lines 96-100), each for one run:

| ID | Question | Answered from |
|---|---|---|
| CQ06 | Which missing data does the draft-creating action still need? | the open findings by rule id, rule version and status, and the requests for input by event id and status; a finding's message and its expected and observed values are left out because they can echo read data (PR-26) |
| CQ07 | Which sources, and which tool, model and ontology versions, was the decision based on? | evidence ids and revisions, capability and binding ids, rule and policy versions (each finding's `rule_version`; no event records the rule bundle version, and the explanation does not name the bundle: owner decision 2026-10-20, Skip, ADR 0031 §3; the bundle is traceable through the profile's `artifact_sha256` pin), and the driver id; the model name comes from the bundle's `versions`, not from the events |
| CQ08 | If source R3 is withdrawn, which claims, summaries and decisions are affected? | the proposals, approvals and citations of this run that name the evidence; across runs this needs the knowledge layer (target §9) |
| CQ09 | Has a draft already been created for this logical operation? | the action's logical operation id, its reservation, its receipt and its outcome |
| CQ10 | Is the value an extraction, an inference, a hypothesis or an authoritative record? | the label of each value: provider read, verified outcome, grounded citation or model-authored text |

CQ01–CQ05 (entity mapping, valid time, conflicting sources, viewing rights) need the knowledge layer and are not answered here.

## Alternatives considered

- **Citations inside the domain answer models:** rejected (D4). Every domain model would change, and the `off` tool schemas with them.
- **Storing the cited value:** rejected (PR-26). The digest lets an auditor check a citation against the evidence without copying the value into the log.
- **`verified` for the generic answer:** rejected (D5, PR-19). Resolving citations against this run's evidence is not an independent read-back.
- **An action record and a new action state for the generic answer:** rejected. It has no connection, binding or effect, and a new state widens the ADR 0018 table for a record that changes nothing outside the run.
- **Validating a proposal whose rationale does not resolve, and returning both findings:** rejected for Phase 3. It calls validators and creates an action for a proposal the kernel already knows it will block, and the pre-check matches the existing `_repair_finding` pattern. The owner may choose it at G2.
- **Rationale as an approval input:** rejected (target §5.6). It is model-authored and would let model text influence what the approver binds.

## Consequences

- Code: `contracts/grounding.py`, `ActionProposal` and `ActionPlan` fields, `kernel/at_rest.py` (Task 3.R1), `AcceptanceSpec.grounded_answer` (`contracts/task.py`) and its acceptance-gate branch, `kernel/grounding.py`, `kernel/grounded_answer.py`, `kernel/explain.py`, the `GROUNDED` reason code, the release report's grounded count, `grounding.compared` and `grounding.shadow_failed`, the driver's conditional fields and tool, the scripted driver, the evidence bundle and the CLI command.
- Tests and evidence: Tasks 3c.3 and 3e.1–3e.4; an authored grounded replay recording (provenance "authored", not live evidence).
- The UI for citations, rationale and the explanation is later work (D10).
- Known gap: every digest stored by this ADR (`value_digest`, the text digests, `goal_ref_digest` and the unresolved ref digests) is an unsalted `jcs-sha256-v1` digest. A short or guessable value, such as a cited quantity or a short id, can be confirmed offline by hashing candidates against the stored digest (3e.1). No fix is decided.

## Verification

- 3e.1: `test_citation_to_another_run_is_unresolved`, `test_citation_value_is_not_stored`, `test_grounded_off_drops_citations_and_action_record_unchanged`, `test_verifier_still_decides`, and the post-reservation test.
- 3e.2: `test_grounded_is_never_reported_as_verified`, `test_free_text_answer_is_labelled_unverified`, `test_grounded_answer_not_offered_unless_pinned_on`, and the admission tests `test_grounded_answer_not_offered_beside_a_typed_answer`, `test_grounded_answer_refused_on_bound_run_without_admission` and `test_release_report_counts_grounded_separately`.
- 3e.3: `test_rationale_never_changes_the_approval_digest`, `test_rationale_holds_no_hidden_reasoning`.
- 3c.3: `test_explanation_answers_competency_questions`, with one case per question above and its case count; `test_explanation_makes_no_model_call`; `test_explanation_holds_no_observation_values`.
- Revisit when a citation must point into a document span rather than structured data (knowledge layer), or when a grounded answer is proposed as an acceptance item.

## Gates

Accepted at gate G2 (Task 3a.2, 2026-10-19). Tasks 3c.3 and 3e.1–3e.4 implement it; gates `full` and `pg`, plus `e2e` for 3e.4.
