# ADR 0018: Run transition table, reason codes and event attribution

Date: 2026-10-12. Status: Proposed. Refines ADRs 0003, 0007; MVP design §7, §11.
Source: [target architecture](../target-architecture.md) §5.1, §5.5, §5.6, §12.4 (candidates C6, C17 part 1, C18 part 1).

## Context

The action state machine is tabled (`contracts/action.py: ALLOWED_ACTION_TRANSITIONS`) but
run states change through `_set_run_state` with no check, and two paths set the run state
directly. Run events carry no actor; `actor_id` appears only inside two payloads. Failure
reasons are free text and the evidence classifier matches substrings. `list_events` has no
limit, so snapshots, SSE and evidence export load whole runs.

## Decision

- `contracts/run.py` gains `ALLOWED_RUN_TRANSITIONS`, derived from the coordinator's observed
  transitions, and the coordinator refuses any other change with `ErrorCode.CONFLICT`.
  Terminal states have no successors. The table is a contract; widening it needs a new ADR.
- `RunEvent.actor` names who caused the event: `principal:<id>` for a request or a decision,
  `system:kernel` for kernel-internal changes, `system:worker:<owner>` for recovery and sweeps.
  The value comes from a context variable set by the API session and by the worker per claim;
  `EventSpec` stays a 3-tuple.
- `RunRecord.reason_code: ReasonCode | None` accompanies the human `reason`. The evidence
  classifier reads the code first and falls back to text only for rows written before this ADR.
- `RunStore.list_events` accepts `limit`; API readers page (`EVENT_PAGE = 500`, ceiling 1000);
  evidence export pages internally.

## Consequences

Old rows read with `actor = None` and `reason_code = None`. OpenAPI and the generated TypeScript
types change (`RunEvent.actor`, `RunRecord.reason_code`, `events?limit=`). A correlation id is
deliberately **not** added here: `run_work` compares the full payload for idempotency
(`store.py:535-541`), so it needs its own column (WP2).

## Verification

Kernel suite on both stores; conformance tests for actor and paging; `export_openapi.py --check`
and `pnpm gen:check`. Revisit if a legitimate transition is missing from the table in production
logs (the error is CONFLICT with the pair named).
