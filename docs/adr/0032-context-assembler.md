# ADR 0032: ContextAssembler, per-run mode pinning and the per-call route check

Date: 2026-10-19. Status: Proposed (2026-10-19); the owner accepts or amends it at gate G2 (Phase 3 Task 3a.2). Refines ADRs 0004, 0027 and 0030; [target architecture](../design/target-architecture.md) §7.1–§7.4, §13.3, §17 C9. Plan: [Phase 3](../plans/2026-10-19-phase3-cognition-context.md) D1, D3, D8, Tasks 3b.2, 3d.1–3d.5.

## Context

Target §7.1 puts "what may enter" the model's context in the kernel and "how it is rendered" in the driver adapter. Today the driver decides both. At `51c6c15`:

- The pydantic-ai driver builds every deferred read return from the full observation, `{"data": dict(obs.data), "evidence_id": ...}` (`adapters/pydantic_ai/driver.py:543`), so observations reach the model unbounded and unmasked.
- Validation feedback is appended to the persisted history as a new user prompt (`adapters/pydantic_ai/driver.py:387-399`), so per-turn state accumulates in the continuation.
- The kernel calls the driver from two places, the run loop (`kernel/run_loop.py:49`) and the optional acknowledgement turn after a verified write (`kernel/verification.py:186-188`). Both pass the driver input through `_with_tools` (`kernel/ir_on.py:149`).
- A run's driver state is restored in `_load_cont` (`kernel/continuation.py:298-307`, the `restore` call at `:305`) with no handler; the driver refuses an unknown snapshot schema with a `ValueError` (`adapters/pydantic_ai/driver.py:364-368`, `STATE_SCHEMA` at `:76`). The kernel continuation schema is `CONTINUATION_SCHEMA` (`kernel/continuation.py:57`, written at `:315`).
- `execution_ir` reads the profile on every call (Phase 2). A profile flip therefore changes an in-flight run's behaviour.

ADR 0030 (its Phase 3 parts are accepted at the same gate) decides field classes, route data boundaries and minimization in the assembler. Research 03 §8 proposes an ablation of chat history against typed state; target §7.2 rule 4 says typed state is the carrier.

## Decision

### 1. Records (`contracts/context_pack.py`, Task 3d.1)

- `ContextLayer`: `instructions`, `task`, `tools`, `skills` (the stable prefix) and `ledger`, `findings`, `evidence`, `knowledge`, `recent_turns` (the dynamic suffix), as in target §7.2. In Phase 3 `skills` and `knowledge` are always empty; their content arrives with their phases.
- `ContextPolicy`: `max_input_tokens`, `layer_budgets: Mapping[ContextLayer, int]`, `tool_result_retention_turns`, `max_tool_output_tokens` (the bound per observation, D3) and `class_rules`, the class-per-route rule of section 5. In Phase 3 the policy is the record's defaults, the same for every run. Profile and task-definition overrides (target §7.2 rule 3) and per-capability bounds are later work. There is no summarization field: Phase 3 never summarizes (§7.2 rule 2, third step), and a field nothing reads is not added (PR-04).
- `RenderedObservation(evidence, data, partial, truncated, masked)`: the observation as the model may see it. `partial` is true exactly when `truncated` or `masked` is true, or the evidence itself is not `COMPLETE` (`evidence.completeness`); the record refuses any other combination, so a partial rendering always says why (PR-21).
- `Dropped(kind, ref, reason)`:
  - `kind` is `observation`, `item`, `value` or `turn`;
  - `ref` is an evidence id, an evidence id with an RFC 6901 pointer into its data, or an event id, never a value;
  - `reason` is `budget`, `bound`, `cleared` or `class_route`, and is required.
- `ContextPack`: `stable_prefix`, `dynamic_suffix`, `observations: tuple[RenderedObservation, ...]`, `dropped: tuple[Dropped, ...]` and `digest`, the `jcs-sha256-v1` digest (ADR 0006 profile) of the pack without its digest. The pack holds no model reasoning (PR-28).
- These shapes replace the sketch in target §7.3.

### 2. Assembly (`kernel/context.py`, Task 3d.2)

- `assemble(policy, ledger, observations, read_errors, findings, classes, boundary) -> ContextPack` is pure. It imports no plugin or adapter (PR-01, PR-06). `classes` is the registry's data-class lookup (ADR 0030, Task 3b.3) and `boundary` the route's effective boundary (ADR 0030, Task 3b.1).
- Tokens are counted by a deterministic kernel estimator over the canonical JSON of each item. It never calls a model or a tokenizer service. The driver's `tokens_used` stays the authority for `max_model_tokens`.
- **Stable prefix:** the driver instructions, the task definition and its acceptance criteria when the run is bound to one, and the run's tool set as contract ids. It carries no per-turn state (§7.4 rule 2), so it is identical on every turn of a run.
- **Dynamic suffix:** the progress ledger (ADR 0031), the open findings and the read errors, rebuilt on every turn and never persisted (§7.4 rule 1).
- **Budgets:** each layer has its token budget. Over budget, the assembler drops the lowest-priority dynamic items first: knowledge, then the oldest recent turns, then the oldest evidence that no open finding and no proposal or answer of the run refers to. The ledger and the open findings are never dropped. Every drop is a `Dropped` entry. If the stable prefix, the ledger and the open findings alone exceed `max_input_tokens`, assembly fails (section 7).
- **Bounded observations (D3):** bounding happens in the pack, not in the gateway. The continuation keeps the full observation, which validation, approval and verification use. An observation over `max_tool_output_tokens` is cut (list members from the end, long strings at their end), rendered `partial` and `truncated`, and each removed item is a `Dropped` entry with reason `bound`.
- **Errors:** a read error is rendered as an error entry with its code and safe message, never as an empty result (PR-21).

### 3. Clearing (target §7.2 rule 2, §7.4 rules 3 and 4)

1. Tool results older than `tool_result_retention_turns` are cleared: their content becomes a stub with the `EvidenceRef` id, and the tool call, its return id and any deferred call id stay, so the provider still sees every call/return pair and a resume still matches `DeferredToolResults.calls` (Review Focus 2). Each clearing is a `Dropped` entry with reason `cleared`.
2. Output is capped per observation (section 2).
3. Summarization is not used in Phase 3.
4. Nothing is cleared or compacted while a deferred call is pending.

### 4. Fencing (target §7.2 rule 5, threat T1, PR-34)

- Untrusted text in the dynamic suffix (read errors, and the `expected` and `observed` values of findings, which can echo data) is wrapped in `<untrusted-data source="…" evidence="…">…</untrusted-data>`. The content is JSON-encoded, and inside the fence every `<` is written as `\u003c`, every `>` as `\u003e` and every `&` as `\u0026` (JSON unicode escapes), so no value can produce the closing delimiter `</untrusted-data>` (Review Focus 1). The same text is masked first where section 5 says so.
- Observations reach the model only as tool returns built from `RenderedObservation.data`, as JSON with the same escaping of string values and the observation's `evidence_id`.
- The stable prefix states that fenced blocks and tool returns are data and never instructions. Data cannot change the tool set, the plan, policy or budgets: the tool set is fixed per run (§7.2 rule 1) and the kernel checks every proposal.

### 5. Class-per-route rule (ADR 0030)

`class_rules` maps each data class to what a route may receive. An unmarked property counts as `personal`.

| Route | `public`, `internal` | `personal` | `sensitive_personal` | `secret` |
|---|---|---|---|---|
| `local` | kept | kept | kept | never present |
| hosted, `data_processing` declared | kept | kept | masked | never present |
| hosted, no `data_processing` (including `hosted:unknown`) | kept | masked | masked | never present |

A masked value is replaced by the string `[masked:<class>]` and recorded as a `Dropped` entry of kind `value` with reason `class_route` and its pointer; the rendered observation is `partial` and `masked`.

**Free text outside observations (threat T23).** Finding `expected` and `observed` fields (`contracts/validation.py`, `Finding`) and read-error text can echo observation values, and they have no schema to carry a class. On a route that is neither `local` nor hosted with `data_processing` declared:
- the `expected` and `observed` text of a finding is masked to `[masked:personal]`, unless the finding's validator declares the class of those fields. No validator declares one in Phase 3, so they are always masked there. Kernel findings (`KERNEL-*`) are kernel-authored with fixed text and keep their fields;
- a read error keeps its kernel code, and the provider's message after it is masked to `[masked:personal]`;
- each mask is a `Dropped` entry of kind `value`, reason `class_route`, whose `ref` names the finding (`finding:<index>#/expected` or `#/observed`) or the read request (`read_error:<request_id>`).

A finding's `rule_id`, `status` and `message` (the rule text from the pack's inventory, ADR 0009) are kept, so the model can still repair. Masking governs the model context only; the approval card is always built from the unmasked action (ADR 0030, ADR 0006, threat T9, Review Focus 3).

### 6. Rendering (target §7.4, Task 3d.4)

- When `DriverInput.context` is set, the driver renders the stable prefix as instructions and the dynamic suffix as a per-turn message that is not written to the persisted history. Findings are no longer appended to the history as a user prompt (`adapters/pydantic_ai/driver.py:387-399` today).
- Every observation that reaches the model comes from `ContextPack.observations`: the deferred read returns and the post-write acknowledgement turn included. `Observation.data` is never passed to the model on that path (Review Focus 4).
- When `DriverInput.context` is `None`, the driver is exactly today's.
- A driver that has rendered a pack marks its snapshot with `rendering: "pack"` and never removes the marker. A snapshot of a run that never rendered a pack has no such key, so `STATE_SCHEMA` and `off` snapshots are unchanged. The kernel reads this one key of the driver state (section 8).

### 7. Toggle `features.context_assembler` (D1)

| Mode | Behaviour |
|---|---|
| `off` | Today. No pack is built and no new event appears. |
| `shadow` | Before each driver turn the kernel builds the pack; after the turn it records `context.compared`: per-layer token estimates of the pack and of the same inputs rendered unbounded (both from the kernel estimator; the driver history is not read), the driver's `tokens_used` delta for the turn, the dropped and masked counts, and the pack digest. The driver still uses its own history. No model call, read or budget use is added (Review Focus 8). Real consumers: the release report's context columns and `test_shadow_pack_keeps_referenced_observations` over the recorded replay corpus (Task 3d.3). A shadow error records `context.shadow_failed` with a stage and a fixed message and changes nothing else. |
| `on` | Every driver call of a run pinned `on` passes the pack in `DriverInput.context`, and the driver renders it (section 6). |

Failure handling in `on` (ADR 0027 reservation rule):

- Before the run's first write reservation, on a route that is `local` or has `data_processing` declared: `feature.fallback` with `CONTEXT_ASSEMBLY_FAILED`, and that call uses today's history.
- Otherwise there is no fallback:
  - the optional acknowledgement turn is skipped, `context.failed` is recorded with `CONTEXT_UNAVAILABLE`, and the run keeps its verified outcome;
  - any other call fails the run closed with `CONTEXT_UNAVAILABLE`, or sends it to `NEEDS_RECONCILIATION` when a reservation is unresolved.
- A fallback never sends unmasked data to a route that is not `local` and has no `data_processing` (T23).

### 8. Per-run mode pinning (D8, Task 3b.2)

- A run pins `context_assembler`, `kernel_repeat` and `grounded_answers` when it is prepared, in `_prepare_run` (`kernel/coordinator.py`), so the pin is in the continuation that both `start_run` and `admit_run` (`create_run_idempotent`) store. The pin is a `RunModes` record in the kernel continuation.
- The pin is written only when a mode is not `off`, and the field is left out of the serialized continuation when absent, as `OutcomeReport` leaves out `verified_values` (`contracts/outcome.py`). An absent pin means every mode is `off`, so an `off` continuation is byte-identical and `CONTINUATION_SCHEMA` does not change.
- A profile flip affects new runs only; an in-flight `off` run keeps its history continuation. `execution_ir` is not pinned: it keeps reading the profile per call, as Phase 2 shipped.
- The driver learns what the pinned `grounded_answers` mode lets it offer only from `DriverInput.grounding` (ADR 0033), never from the profile.
- **Restore check.** Before `_load_cont` calls `restore`, the kernel compares the pin with the snapshot's `rendering` marker. A marker `pack` on a run not pinned `on`, or a marker value the kernel does not know, is a mismatch. A run pinned `on` without the marker is valid (no pack turn yet, or every turn so far fell back). On a mismatch the kernel does not restore: it fails the run closed with `DRIVER_STATE_MISMATCH`, or sends it to `NEEDS_RECONCILIATION` when an action of the run is `RESERVED`, `DISPATCHING`, `UNKNOWN` or `COMMITTED` without an outcome, and raises a conflict to the caller. Other restore refusals (a driver schema or version change) keep today's behaviour; handling them is a follow-up outside Phase 3.

### 9. The per-call route check (D8, T23)

- The route is not pinned, so the startup rule (ADR 0030) cannot protect a run that resumes after a restart on another route. Before every model call, `_with_tools` (`kernel/ir_on.py:149`), the one function both driver call sites use, checks the run's pinned `context_assembler` mode against the current route's effective boundary.
- A run not pinned `on`, on a route that is not `local` and has no `data_processing` declaration, makes no model call:
  - in the run loop, the run fails closed with `ROUTE_BOUNDARY_UNMET`, or goes to `NEEDS_RECONCILIATION` when a reservation is unresolved;
  - for the acknowledgement turn, the turn is skipped, `context.failed` is recorded with `ROUTE_BOUNDARY_UNMET`, and the run keeps its verified outcome.
- A run pinned `on` may call such a route only because everything its pack sends is masked by section 5: observation values by their class, and finding `expected` and `observed` text and read-error text by the free-text rule. The exemption depends on both; without the free-text rule, findings would carry unmasked values to the route.
- A conformance test fails if any `_driver.advance` call bypasses `_with_tools`.

### 10. Transitions

`DRIVER_STATE_MISMATCH` and `ROUTE_BOUNDARY_UNMET` use only existing pairs of the ADR 0018 table (`contracts/run.py`): `→ FAILED` from `CREATED`, `RUNNING`, `WAITING_INPUT`, `WAITING_APPROVAL`, `VERIFYING` and `NEEDS_RECONCILIATION`, and `→ NEEDS_RECONCILIATION` from `RUNNING`, `WAITING_APPROVAL`, `VERIFYING` and `NEEDS_RECONCILIATION`. An unresolved reservation exists only in those four states. No pair is added.

### 11. Reason codes and events

Phase 3 adds nine `ReasonCode` members in `contracts/run.py`: the eight toggle, restore and route codes below, which Task 3b.2 adds together, and `GROUNDED` (ADR 0033), which Task 3e.2 adds. Each fixed-message code has one message kept by the kernel (ADR 0027 amendment, PR-25, PR-28). Callers pass no text.

| Code | Kind | Decided in | Carried by | `classify` group |
|---|---|---|---|---|
| `CONTEXT_ASSEMBLY_FAILED` | fallback | this ADR | `feature.fallback` only | never ends a run |
| `CONTEXT_UNAVAILABLE` | terminal | this ADR | run state change; `context.failed` for a skipped acknowledgement turn | infrastructure-or-budget |
| `REPEAT_CHECK_FAILED` | fallback | ADR 0031 | `feature.fallback` only | never ends a run |
| `REPEAT_UNAVAILABLE` | terminal | ADR 0031 | run state change | infrastructure-or-budget |
| `GROUNDING_CHECK_FAILED` | fallback | ADR 0033 | `feature.fallback` only | never ends a run |
| `GROUNDING_UNAVAILABLE` | terminal | ADR 0033 | run state change | infrastructure-or-budget |
| `DRIVER_STATE_MISMATCH` | terminal | this ADR | run state change | failed |
| `ROUTE_BOUNDARY_UNMET` | terminal | this ADR | run state change; `context.failed` for a skipped acknowledgement turn | blocked-by-design |
| `GROUNDED` | success | ADR 0033 | the `SUCCEEDED` state change of a grounded answer | succeeded, but counted apart from `VERIFIED` in the release report and qualification (ADR 0033) |

New event types (`contracts/events.py`), each payload of ids, counts, digests and codes only (PR-26):

- `context.compared` and `context.shadow_failed` (Task 3d.3);
- `context.failed`, with `reason_code`, its fixed message and `turn: "acknowledgement"` (Task 3b.2, its first writer);
- `repeat.compared`, `repeat.shadow_failed` (ADR 0031); `grounding.compared`, `grounding.shadow_failed` (ADR 0033).

### 12. `sdk_api` 1.2

One additive minor version, `SDK_API_VERSION` `1.1` to `1.2`, covering three driver- and plugin-facing additions, each with a default so a `1.1` plugin or driver keeps working:

- `CapabilityDescriptor.data_classes` (ADR 0030; Task 3b.3 adds it and makes the bump);
- `DriverInput.context: ContextPack | None = None` (Task 3d.1), with the snapshot marker of section 6;
- `DriverInput.grounding` (ADR 0033, Task 3e.4).

Nothing is released between 3b.3 and 3e.4, so the three share one version. The existing `>=1.0,<2.0` manifest ranges still admit. `ActionProposal.citations` and `ActionProposal.rationale`, `ActionPlan.rationale` (ADR 0033) are optional contract fields with defaults that ship in the same unreleased window.

### 13. Observability (ENG-TOGGLE-3)

`/health/ready` and the evidence bundle report the four toggles under `features`, the route's `data_boundary`, its basis and whether `data_processing` is declared (ADR 0030). The evidence bundle also reports the run's pinned modes, and for a pinned-`on` run the pack digests and drop log.

## Alternatives considered

- **Minimization and bounding in the driver:** rejected (ADR 0030). The driver already holds the full observation, and every driver would re-implement the rule.
- **Bounding in the gateway:** rejected (D3). Validation, approval and verification need the full observation; only the model's view is bounded.
- **Ledger in the system instructions:** rejected (§7.4 rule 2). It would change the stable prefix every turn and invalidate the provider's prompt cache.
- **Reading every mode from the profile per call, as `execution_ir` does:** rejected for the three Phase 3 modes. A flip would change an in-flight run's history format mid-run, which a resume cannot survive.
- **Pinning the route too:** rejected. A route is a deployment fact the operator may change; the per-call check is cheaper and also covers a run whose route changed while it waited for approval.
- **Summarization in Phase 3:** deferred. It is lossy and costs tokens (§7.2 rule 2); clearing and bounding come first.

## Consequences

- Code: `contracts/context_pack.py`, `kernel/context.py`, the shadow and `on` paths in `kernel/run_loop.py` and `kernel/verification.py`, the pin in `kernel/continuation.py` and `kernel/coordinator.py`, the route check in `kernel/ir_on.py`, the restore check in `_load_cont`, the driver's rendering, the nine codes, the new events and the `sdk_api` bump.
- Tests and evidence: the tests listed in Tasks 3b.2 and 3d.1–3d.5, the `off` model-request goldens (notes and ERP) unchanged, a new `on` model-request golden, and the Phase 3 `off` baseline report (`evals/reports/phase3-baseline.json`, fixture evidence).
- Operations: an operator who moves a profile to a hosted route without `data_processing` gets a startup refusal while `context_assembler` is not `on` (ADR 0030), and in-flight runs that resume on it fail closed with `ROUTE_BOUNDARY_UNMET`.
- The fixed budgets are a starting point. The ablation (research 03 §8, Task 3f.2) and the release report's context columns are the evidence for changing them.

## Verification

- 3d.2: `test_finding_and_read_error_text_masked_on_hosted_route`, `test_layer_over_budget_drops_oldest_and_logs_it`, `test_bounded_observation_is_partial_with_truncated_marker`, `test_error_is_never_rendered_as_empty_result`, `test_personal_value_masked_on_hosted_route_and_logged`, `test_untrusted_values_are_fenced`, `test_fence_cannot_be_closed_from_inside`, `test_approval_presentation_ignores_the_pack`.
- 3d.4: `test_clearing_keeps_call_return_pairs` (parallel calls included), `test_no_clearing_with_pending_deferred_call`, `test_masked_value_absent_from_model_request`.
- 3b.2 and 3d.5: `test_modes_are_pinned_at_start`, `test_off_run_writes_no_pin`, `test_pinned_off_run_on_undeclared_hosted_route_fails_closed`, `test_every_driver_call_goes_through_with_tools`, `test_restore_rendering_mismatch_fails_closed`, and the post-reservation tests (Review Focus 7).
- Revisit when a profile needs its own budgets, when summarization is proposed, or when a second driver renders the pack.

## Gates

Gate G2 (Task 3a.2) accepts this ADR. Task 3b.2 waits for it (pinning and codes), and Tasks 3d.1–3d.5 build it: gates `full` and `pg`, plus `e2e` for 3d.4 and 3d.5.
