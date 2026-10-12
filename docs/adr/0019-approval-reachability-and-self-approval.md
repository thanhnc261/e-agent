# ADR 0019: Approval reachability and the self-approval rule

Date: 2026-10-12. Status: Proposed. Refines ADR 0014; MVP design §10; HLD §3.
Source: [target architecture](../target-architecture.md) §11.2 rule 6, §13.2 rule 2 (C13, C16).

## Context

Approval expiry (`approval_ttl`, default 15 minutes) is checked only when a decision arrives
(`coordinator.py:992-1001`). A run nobody looks at stays `WAITING_APPROVAL` indefinitely and is
rescanned at every startup. `decide` checks the approver role but not whether the approver is
the run's requester; the fixture operator holds both roles by design (HLD §3).

## Decision

- A sweeper in the worker process scans unfinished runs every `APPROVAL_SWEEP_SECONDS` and, for
  each expired approval, enqueues fenced work of kind `expire`. The worker executes it under the
  claim; `expire_approval` re-checks state, pending action and TTL, then applies exactly the
  decide-path outcome: action `BLOCKED` with `approval.decided {"decision": "expired"}`, run
  `FAILED` with `reason_code = APPROVAL_EXPIRED`. No state changes outside a work claim.
- Self-approval (`actor.principal_id == run.requester_id`) is refused with `FORBIDDEN` unless the
  profile sets `operator.allow_self_approval: true`. The fixture profile sets it; live profiles
  default to forbidden and `/health/ready` reports the value so a release gate can refuse it.
  A service principal (triggers, later) never gets the flag.

## Consequences

Migration 0004 widens `run_work.kind`. Per-task TTL, approver inbox and the repair branch after
expiry wait for task definitions (WP3). A single-operator live trial must set the flag
explicitly and the evidence bundle records it through the profile.

## Verification

Kernel test: advance the clock, sweep, claim, expire, late decision rejected. Kernel test: a
principal with both roles cannot approve their own run unless the flag is set. API test: ready
endpoint reports `self_approval_allowed`.
