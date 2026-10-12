# ADR 0020: Connection-level write admission rule

Date: 2026-10-12. Status: Proposed. Refines ADRs 0003, 0005, 0014; MVP design §9.
Source: [target architecture](../target-architecture.md) §12.2, §19 (C3 part 1).

## Context

Writes to one connection are serialized by a session advisory lock held across the ERP call
(`store.py:496-508`). ADR 0014 already states that a lock does not prove an expired worker's
external call stopped. If the lock is lost mid-call, a second worker can dispatch a second write
to the same connection while the first is in flight.

## Decision

`reserve_operation` refuses, inside its own short transaction, when another action on the same
`(tenant_id, connection_id)` is in `RESERVED`, `DISPATCHING` or `UNKNOWN`, raising `ConnectionBusy`. The
check and the reservation insert are serialized per connection with a transaction-scoped
advisory lock. The coordinator blocks the action and fails the run with
`reason_code = CONNECTION_BUSY`; reconciliation of the earlier action must finish first.
The durable writer lease that replaces the session lock is a separate decision (WP2).

## Consequences

A connection with an unresolved write accepts no new write from any run until reconciled. This
is the intended backstop, not a throughput feature. `RESERVED` is in the set because the
reservation commits and releases the admission lock before the action moves to `DISPATCHING` and
before the session writer lock is taken; without it two concurrent reservations would both pass
and the second would dispatch behind the first under the session lock alone. A crash-stranded
`RESERVED` row blocks the connection until startup or run recovery resolves it to `BLOCKED`
(automatic, no reconciliation needed).

## Verification

Conformance test on both stores: a `RESERVED`, `DISPATCHING` or `UNKNOWN` action on the connection
makes the next reservation raise `ConnectionBusy`; after it reaches `COMMITTED`, reservation
succeeds. A busy action on a different connection or a different tenant does not refuse it.
