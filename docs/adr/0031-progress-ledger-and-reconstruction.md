# ADR 0031: Progress ledger, repeat detection and run reconstruction

Date: 2026-10-19. Status: Accepted (2026-10-19, owner, gate G2, Phase 3 Task 3a.2). Refines ADRs 0007, 0018, 0025 and 0027; [target architecture](../design/target-architecture.md) §5.1 item 2, §6.2, §6.3, §17 C8. Plan: [Phase 3](../plans/2026-10-19-phase3-cognition-context.md) D7, D9, Tasks 3c.1, 3c.2, 3d.6.

## Context

Target §5.1 item 2 says the event log is the audit truth, but the current-state rows are not reconstructable from it today (fitness row U3). Reading the event writers in `src/e_agent/kernel/` at `51c6c15` shows why:

- `run.created` (`kernel/coordinator.py`, `_prepare_run`) carries `task`, `driver` and `host_context`, but not the run's `requester_id`, `logical_operation_id`, `created_at` or its task definition link. The event `actor` comes from a context variable whose default is `system:kernel` (`sdk/store.py:24`), so it is not the requester.
- `proposal.created` (`kernel/proposals.py:143` and `:331`, `kernel/plan_flow.py` `_proposal_event`) carries `contract_id`, `arguments`, `supersedes` and, for answers, `kind`. The action's binding, connection, credential subject and version, digest, logical operation id and plan link are only in the `actions` row.
- An action's state is implied by the event type for most writes, but not for all:
  - `validation.completed` is written with an action id both when the action moves (to `VALIDATED` or `BLOCKED`) and when it does not (`kernel/dispatch.py` `_arguments_refused`, a later plan step that has no `BLOCKED` transition).
  - `outcome.reported` with status `UNKNOWN` leaves the action unchanged in the write path (`kernel/verification.py:80`, `:127`), but moves an answer to `VERIFICATION_FAILED` (`kernel/proposals.py:365`).
  - Five action writes carry no event at all: the answer's `PROPOSED → VALIDATED` (`kernel/proposals.py:348`), and `→ BLOCKED` in `kernel/dispatch.py:84` (revalidation deadline on a first step), `kernel/dispatch.py:323` (`_block_if_allowed`, connection busy or duplicate operation), `kernel/recovery.py:86` (cancel) and `kernel/recovery.py:220` (startup recovery before dispatch).
- `approval.decided` (`kernel/approval_flow.py:213`) carries `decision`, `actor_id` and `digest`, but not the approval record's `approval_id`, `policy_version`, `issued_at` or `expires_at`.
- `run.state_changed` has two shapes: `{from, to, reason, reason_code}` from `_set_run_state` (`kernel/transitions.py:67`) and `wait_for_approval` (`kernel/proposals.py:271`), and `{state}` from `accept_input` (`kernel/run_loop.py:257`).
- Receipts are already complete: `action.receipt_recorded` and `action.unknown` carry `receipt.model_dump(mode="json")` (`kernel/dispatch.py:409`).
- A 1-step plan link in execution IR `on` is set on the action after `proposal.created` (`kernel/ir_on.py`, `_on_plan`) and stored by `wait_for_approval`; `ir.plan_compiled` with an action id is written in `shadow` too, where nothing is linked.

Target §6.2 asks for a kernel-computed progress ledger, and §6.3 for a `KERNEL-REPEAT` finding. Today the kernel only short-circuits a repeated *verified* answer (`kernel/proposals.py:303-314`, in `_handle_answer`); a repeated blocked write proposal is validated again.

ADR 0027 requires that `off` is exactly today's behaviour, proved by a golden event stream. Adding payload keys changes that stream. Plan decision D7 refines the proof instead of re-recording it.

## Decision

### 1. The progress ledger is a projection

- `ProgressLedger` (`contracts/progress.py`) is computed by a pure kernel function `project_progress(events, steps)` over `RunStore.list_events` and `list_steps`. It is never stored, never a source of truth, and writes nothing.
- Fields:
  - `goal`: the run's task text and its task definition ref (`task_id@task_version`, or none);
  - `facts`: one entry per `read.recorded` (`evidence_id`, `contract_id`, `revision`), never the observation data;
  - `done` and `pending`: completed and open stages (reads, proposals, validation, approval wait, dispatch, verify), from step records where they exist and from events otherwise; `pending` names a wait for approval, input or reconciliation;
  - `open_findings`: rule id, rule version, status and message of the findings of the latest `validation.completed` that no later proposal has superseded;
  - `repair_turns`: the event ids of plain-text repair turns (`KERNEL-VERIFICATION`), never their text;
  - `budgets_used`: what the events and step records show (reads, failed validations, admitted writes). A budget they do not show, such as driver turns or tokens without step records, is `unknown`, never zero (PR-24).
- The ledger holds no model text (no `message.final`, no `input.requested` question, no thinking; PR-28, ADR 0004).
- Plan updates proposed by the model (`plan.proposed`, target §6.2) are not decided here. The `plan` items in the ledger are only the run's compiled plan steps and their kernel-observed status. A model plan-update variant of `DriverStep` needs its own ADR and `sdk_api` change.
- The ContextAssembler (ADR 0032) renders the ledger into the dynamic suffix of the context pack; the explanation projection (ADR 0033) reads it.

### 2. Reconstruction from `run_events`

- `reconstruct(events) -> Reconstructed` (`kernel/reconstruct.py`) rebuilds the run, its actions, its approvals and its receipts from the run's events alone. Each field is `known`, `partial` or `unknown`; reconstruction never fills a field with a guess (PR-24).
- **Outside reconstruction:**
  - `revision` on runs and actions: a compare-and-swap token, not an audit fact (target §5.1 item 2 keeps the rows authoritative for concurrency control);
  - the `data` of `ActionRecord.approved_facts`: observation values, which never enter an event (PR-26). Reconstruction gives the facts' evidence ids, so the field is `partial` by design;
  - outcome reports, steps and plans: they have their own rows and events (`outcome.reported`, step records, `ir.*`); reconstructing them is not required for U3.
- **Action state** is read from the events of each action id:

| Event | State after it |
|---|---|
| `proposal.created` | `PROPOSED` |
| `validation.completed` | the new key `action_state` (`VALIDATED`, `BLOCKED`, or null when the write left the action unchanged) |
| `approval.requested` | `AWAITING_APPROVAL` |
| `approval.decided` | `APPROVED` for `approved`; `BLOCKED` for `rejected`, `expired`, `surface_changed` |
| `action.reserved` | `RESERVED` |
| `action.dispatching` | `DISPATCHING` |
| `action.receipt_recorded` | `COMMITTED` or `FAILED`, from the receipt `status` |
| `action.unknown` | `UNKNOWN` |
| `outcome.reported` | the new key `action_state` (`VERIFIED`, `VERIFICATION_FAILED`, or null when unchanged) |
| `run.state_changed` | `BLOCKED` for every id in the new key `blocked_action_ids` |

- An answer action whose `proposal.created` has no later `outcome.reported` is `PROPOSED` or `VALIDATED`; its state is `partial`.
- A run is reconstructed in full only when its `run.created` carries the keys below. For a run whose events predate them, every field that depends on a listed key is `partial` or `unknown`, and the run as a whole is marked `partial` (D7).

### 3. The event payload keys reconstruction needs

These keys are added to existing events only. No event is added, removed or reordered, and no existing key or value changes. Every key is an id, a digest, a version, a count, a code or a timestamp, never an observation value (PR-26).

| Event type (writer) | New keys |
|---|---|
| `run.created` (`kernel/coordinator.py` `_prepare_run`) | `requester_id`, `logical_operation_id`, `created_at`, `task_id`, `task_version` (null when the run has no task definition) |
| `run.state_changed` from `accept_input` (`kernel/run_loop.py:257`) | `from`, `to`, `reason` (null), `reason_code` (null); the existing `state` key stays |
| `run.state_changed` from `_set_run_state` (`kernel/transitions.py`) | `blocked_action_ids`, only on the state change that the same kernel call writes after one of the four event-less `BLOCKED` writes (`kernel/dispatch.py:84`, through `_exhausted`; `kernel/dispatch.py:323`; `kernel/recovery.py:86`; `kernel/recovery.py:220`) |
| `proposal.created` (`kernel/proposals.py:143`, `:331`; `kernel/plan_flow.py` `_proposal_event`) | `binding_id`, `connection_id`, `connection_version`, `credential_subject`, `credential_version`, `digest`, `logical_operation_id`, `plan_id`, `step_index`, `evidence_ids` (the evidence ids of the action's approved facts) |
| `validation.completed` written with an action id (`kernel/proposals.py`, `kernel/dispatch.py`, `kernel/plan_flow.py`) | `action_state` |
| `approval.requested` (`kernel/proposals.py:261`) | `plan_id`, `step_index` (the plan link the stored action has, null when unlinked) |
| `approval.decided` for `approved` and `rejected` (`kernel/approval_flow.py:213`) | `approval_id`, `policy_version`, `issued_at`, `expires_at` |
| `outcome.reported` written with an action id (`kernel/verification.py`, `kernel/proposals.py`) | `action_state` |

- `credential_version` is an approval-digest input (`kernel/approval.py:36`, `:47`). Plan D9 of the first draft, which would have shortened it in exports, is withdrawn, so the full value is recorded: an auditor recomputes the approval digest from the exported action.
- `credential_subject` is the connection's credential subject identifier, already in the action row and the digest input; it is never a secret.
- `approval.decided` for `expired` and `surface_changed` creates no approval record, so it needs no new key; it only moves the action to `BLOCKED`.
- `approval.requested` already carries `digest` and `expires_at`; receipts need nothing.

### 4. The `off` proof, refined (D7)

This refines ADR 0027's "a golden event stream recorded before the feature lands proves it" for these keys only:

- The Phase 2 goldens stay frozen: `tests/unit/kernel/golden/off_mode_events.json` and `tests/unit/plugins/erp/simulator/golden/off_mode_events_erp.json` are not re-recorded.
- New goldens are recorded beside them (`off_mode_events_v3.json`, `off_mode_events_erp_v3.json`).
- A test proves each frozen golden is a projection of its new one: the same events in the same order with the same types, keys and values, plus only the keys in the table above. Any other difference fails.
- The Phase 2 golden tests compare the projection of the current stream onto the Phase 2 keys.

No other Phase 3 change uses this refinement: `context_assembler`, `kernel_repeat` and `grounded_answers` in `off` add no event and no key.

### 5. `KERNEL-REPEAT` (toggle `features.kernel_repeat`)

- **The rule.** A write proposal is a repeat when an earlier write proposal of the same run was blocked by validation in `_handle_proposal`, and both of these hold:
  - its approval digest, recomputed with the earlier revision's rule bundle version, equals the earlier action's `digest`;
  - the registry surface digest equals the run's `surface_digest`, so the validators and their rule bundles are the ones the earlier validation ran.
- **The revision set.** The digest input covers the contract, connection and connection version, credential subject and version, arguments, expected effects, policy version, and, for every observation the validation saw, its evidence id, source, revision, completeness and, for a revision-less fact, its `fact_digest` (`digest_input`, `kernel/approval.py:38-61`; `observed_at` is not an input). It is the full set the original validation used: `_validate` receives exactly the continuation's observations (`kernel/proposals.py:445`). A re-read with a new revision, a new completeness, or new data for a revision-less fact changes the digest, so the proposal is validated again (Review Focus 6). A re-read with the same revision is the same fact, which is the rule the pre-dispatch staleness check already applies (`_staleness`, `kernel/dispatch.py`).
- **Not repeats:** a proposal whose digest is the sentinel `invalid` (`KERNEL-ARGS`); a proposal blocked by staleness at dispatch, by approval rejection or expiry, or by policy (policy denial ends the run); a proposal in another run.
- **`on`:** a repeat creates no action. The kernel records `validation.completed` (no action id) with status `FAIL`, the fixed finding `KERNEL-REPEAT` whose `observed` names the earlier action id, and the earlier revision's findings, and returns them to the driver as a repair. The repair counts against `max_validation_repairs`; past the budget the run fails `VALIDATION_FAILED`, as a blocked proposal does.
- **`shadow`:** validation runs as today. The kernel records `repeat.compared` with `would_repeat` (bool), `repeat_of` (action id or null) and `same_findings` (whether validation returned the same rule ids and statuses). Real consumer: `test_repeat_shadow_agrees_with_validation` over the fixture corpus asserts zero disagreements and its case count, and the release report counts disagreements. A shadow error records `repeat.shadow_failed` with a stage and a fixed message and changes nothing else.
- **`off`:** today. Nothing is recorded or kept.
- The blocked revisions' digests and rule bundle versions are kept in the continuation only when the pinned mode is not `off`, and the field is left out when empty, so an `off` continuation is byte-identical (D8, ADR 0032).
- **Failure handling (ADR 0027):** before the run's first write reservation, `feature.fallback` with `REPEAT_CHECK_FAILED`, and the proposal is validated as today. After a reservation there is no fallback: the run fails closed with `REPEAT_UNAVAILABLE`, or goes to `NEEDS_RECONCILIATION` when a reservation is unresolved. `REPEAT_CHECK_FAILED` is carried only by `feature.fallback` and never ends a run. Both are `ReasonCode` members with fixed messages (the full code list is in ADR 0032).

## Alternatives considered

- **Event sourcing the rows** (the rows become a projection the store derives): rejected for Phase 3. The rows carry compare-and-swap revisions that the store's write paths depend on, and changing write ownership is a store-port change for both stores. Reconstruction as a checked projection gives U3 without it.
- **New events for the five event-less action writes:** rejected because D7's proof requires the same events in the same order. A key on the following state change records the same fact.
- **A generic `action_state` key on every action event:** rejected as wider than needed. The type already says the state for every event except `validation.completed`, `outcome.reported` and the event-less writes.
- **Storing the ledger:** rejected. A stored ledger is a second source of truth that can drift from the events (target §6.2).
- **`KERNEL-REPEAT` on the bare digest:** rejected because the digest includes the rule bundle version that only validation produces; without the surface digest check a changed validator could be skipped.

## Consequences

- Code: `contracts/progress.py`, `kernel/progress.py` (3c.1); `kernel/reconstruct.py`, the key additions above and the v3 goldens with their recording scripts (3c.2); the repeat rule in `kernel/proposals.py`, `repeat.compared` and `repeat.shadow_failed` in `contracts/events.py`, and the release report's disagreement count (3d.6).
- Known gap: a crash between an event-less write and the state change that carries `blocked_action_ids` leaves the log one write behind the row. Reconstruction then reports the earlier state for that action, which the U3 test does not cover because it runs completed sequences. Closing it needs those writes to carry their own event, which changes the `off` stream and needs its own golden refinement.
- The `outcome.reported` payload of an unavailable verifier (`kernel/verification.py:88`, `{status, error}`) stays as it is; outcomes are not reconstructed here.
- Events written before 3c.2 reconstruct as `partial`. No migration rewrites old events.
- `KERNEL-REPEAT` assumes a validator is a function of its `ValidationInput` and context. The shadow comparison is the evidence for that assumption before `on` is used.
- `KERNEL-REPEAT` is behind the D9 cut line: if Phase 3 runs long it moves to a Phase 3′ plan with 3f.1 and 3f.2, and the rest of this ADR still applies.

## Verification

- 3c.1: `test_progress_*`, including `test_progress_is_pure` and `test_progress_holds_no_model_text`.
- 3c.2: `test_reconstruction_equals_stored_rows` over every recorded fixture scenario on both stores, printing its scenario count and failing on zero; `test_pre_key_events_reconstruct_as_partial`; `test_phase2_golden_is_a_projection_of_v3`.
- 3d.6: `test_repeat_*`, including `test_changed_fact_revision_revalidates` and the post-reservation test (Review Focus 6 and 7).
- Revisit when a write path gains its own event (the known gap above), or when a store port change makes rows a projection.

## Gates

Accepted at gate G2 (Task 3a.2, 2026-10-19). Tasks 3c.1, 3c.2 and 3d.6 implement it; each runs gates `full` and `pg`.
