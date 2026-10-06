# ADR 0003: kernel ledger owns side-effect durability; no framework durability in MVP

Date: 2026-10-06. Status: Proposed.

## Context

The design's invariant is that exactly one component owns retry and resume for each step. In 2026 the market default is "durability by delegation": Pydantic AI ships first-party Temporal, DBOS and Prefect durability capabilities and a Restate integration, in which every model and tool call becomes a durable activity or step. Its harness also offers step persistence with tool-effect idempotency annotations. These are good products, but they replay or retry tool calls by their own rules. The MVP already needs a business ledger (reservation, approval, dispatch, receipt, reconciliation) because approval and `UNKNOWN` handling are business semantics that no engine supplies. If both the ledger and the engine can retry a write, the invariant breaks.

## Decision

1. The kernel's PostgreSQL ledger and state machine (MVP design §7–9) are the **only** owner of retry, resume and reconciliation for effectful actions.
2. The MVP does not use Pydantic AI durability capabilities (Temporal/DBOS/Prefect/Restate) or harness step persistence for business tools.
3. Work scheduling is in-database: a `run_work` claim using `SELECT … FOR UPDATE SKIP LOCKED` plus a lease and fencing token. A transaction-scoped advisory lock keyed by `(tenant_id, connection_id)` serializes writes per sandbox connection when the provider has no atomic uniqueness.
4. Model calls are not journaled for replay. After a crash the driver resumes from the last persisted continuation checkpoint (ADR 0004), and the ledger decides whether any action may have occurred.

## Alternatives considered

- **DBOS (Postgres-backed library).** This is the best fit if the MVP later needs a workflow engine: no extra service, and it shares PostgreSQL. It is deferred, not rejected. Revisit if hand-written lease and recovery code grows beyond what the recovery test matrix can cover.
- **Temporal.** This is strong for multi-day waits and versioned workflows, but it is an extra cluster and brings determinism constraints on workflow code. It is excessive for a local-first MVP.
- **Engine owns everything and the ledger is a projection.** Approval binding, `UNKNOWN` and the reconciliation rules would then live in engine code anyway, and the engine's retries would still need provider idempotency.

## Consequences

- The project writes and tests its own lease/recovery code. The MVP design §9 crash matrix is the test specification.
- Adopting an engine later means an ADR that assigns step ownership explicitly: the engine schedules, and the ledger still decides dispatch eligibility. It also needs a migration that drains in-flight runs.

## Verification

- Fault-injection suite: kill the worker at each boundary in MVP design §9 and assert no duplicate external effect.
- Static check: no import of `pydantic_ai.durable_exec` or harness step persistence in adapter or driver packages (import-linter `forbidden` contract).
