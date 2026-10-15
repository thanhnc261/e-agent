# ADR 0022: Conversational turns, read feedback and record discovery

Date: 2026-10-12. Status: Accepted (owner, 2026-10-14). Refines ADRs 0003, 0018; MVP design §7.

## Context

The first live run of the Pydantic AI + Ollama driver against the `odoo19-learning` sandbox
showed four gaps. (1) A read the provider rejects (`KnownNoEffectError`, e.g.
`E_AGENT_INVALID_REF`) escaped the read loop and failed the run as "interrupted during driver
turn"; the worker logged nothing. (2) Every read needs an exact provider reference and no
capability lists records, so the model guessed references. (3) A follow-up after small talk
could not complete because of (2). (4) A plain reply with no business claim ("hi") had no
outcome other than a verification failure.

## Decision

- A `KnownNoEffectError` from a read executor is recorded as `read.rejected` and returned to
  the driver as `DriverInput.read_errors` (request id → safe code and message). It counts
  against the read budget. Other read exceptions are unchanged.
- The worker logs unexpected exceptions before applying the crash rules.
- A `FinalAnswer` from a run that has made no reads, read attempts or proposals is a
  conversational reply: it is recorded as `input.requested {"kind": "reply"}` and the run waits
  for input. Any `FinalAnswer` after reads or proposals still needs an independently verified
  outcome (ADR 0018 reason codes unchanged).
- The domain pack adds `procurement.open-demands.read.v1` so the model discovers demand and
  product references instead of guessing them.

## Alternatives considered

- Fail the run on a rejected read (status quo): rejected. A guessable mistake kills the task and hides the cause; feedback within the read budget lets the model correct itself while still bounding retries.
- A dedicated reply tool the model must call for small talk: rejected for now. Local models call it unreliably and it adds a tool to every turn; inferring "reply" from a run with no reads, read attempts or proposals (plus a ledger check) is deterministic and cannot let a business claim through.
- Relax exact references (fuzzy matching of names to records in the bridge): rejected. It moves ambiguity resolution into the provider and weakens the exact-reference invariant; a listing capability keeps references exact and auditable.

## Consequences

A conversational reply is not verified and claims nothing; the UI labels it as a reply. A run
can remain `WAITING_INPUT` after a reply until the user answers or stops it. The bridge addon
gains a read method, so `e_agent_bridge` is upgraded in the sandbox and plugin artifact hashes
change. Correlation ids and multi-run conversations remain WP2/WP4.

A provider rejection on a verifier read is still reported as an UNKNOWN verification, not as
`read.rejected`. A rejected staleness re-read ends the run INTERRUPTED (pre-existing
behavior). `connect.required` is the intended future home for `AUTH_REQUIRED` once
user-delegated connections exist (WP2); until then it fails the run with `PROVIDER_ERROR`.
"Open demands" lists every demand in the namespace until the bridge model gains a state.

## Verification

Kernel tests for rejected reads (feedback, budget exhaustion) and for reply versus verified
answer; adapter and bridge tests for the open-demands read; UI tests for the new event type and
reply label; a live end-to-end against `odoo19-learning` from "hi" to a validated proposal.
