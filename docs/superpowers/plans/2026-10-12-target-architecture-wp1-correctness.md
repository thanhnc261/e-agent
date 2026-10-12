# Target Architecture WP1: Correctness and Truthfulness Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the eight verified defects that three review rounds found in the running kernel (run transitions unchecked, self-approval allowed, events without actor, free-text failure reasons, approvals that never expire unattended, unbounded event reads, no write-admission backstop) without touching the trust anchor's semantics or adding infrastructure.

**Architecture:** Every fix stays inside the existing seams: contracts gain typed tables and codes, the two `RunStore` implementations change together under the conformance suite, the coordinator enforces the new rules, and the API only maps identity and pages. The approval sweeper reuses the fenced work queue (`run_work`) instead of mutating state outside a claim. Nothing in this plan changes approval digests, dispatch, or the Pydantic AI driver.

**Tech Stack:** Python 3.12, Pydantic v2 `Record` contracts (`extra="forbid"`, frozen), psycopg 3 async + packaged SQL migrations, `InMemoryRunStore` for tests, FastAPI, pytest-asyncio (`asyncio_mode = "auto"`), `openapi-typescript` for the TS client.

**Spec:** [docs/target-architecture.md](../../target-architecture.md) (v2, revised 2026-10-12). Sections closed by this plan: §5.1 principle 1, §5.5 "Actor attribution" and "Failure classification", §5.6 `ReasonCode`, §11.2 rule 6 (sweeper), §12.2 "Connection-level write admission", §12.4 "Snapshot or export of a long run", §13.2 rule 2. ADR candidates: C3 (part 1), C6, C13 (part), C16 (part), C17 (part 1), C18 (part 1).

## Reading of the request

"Làm lại những chỗ đang sai" is read as: rework the **verified code defects** listed in the synthesis below, not the design documents. Each defect has a `file:line` that was checked against commit `af50c62` plus the uncommitted working tree on 2026-10-12. If the owner meant something else, stop after Task 1 and ask.

## Global Constraints

Copied from AGENTS.md, the design doc and the repository configuration:

- Proposed ADRs are not baseline. Contract-changing tasks (2, 4, 5, 6, 7, 8) merge only after the owner accepts the ADR drafted in Task 1; until then they live on a branch.
- No database transaction spans a model or provider call (ADR 0003, ADR 0014). The sweeper and the admission rule use short transactions only.
- Every `RunStore` change is implemented in **both** stores (`packages/kernel/src/e_agent/kernel/memory_store.py` and `packages/adapter-postgres/src/e_agent/adapters/postgres/store.py`) and covered by `tests/conformance/test_run_store.py`. Run the kernel suite twice: in-memory (default) and `E_AGENT_TEST_STORE=postgres E_AGENT_TEST_PG_DSN=<dsn> uv run pytest -q packages/kernel tests/conformance`.
- The CI gate is, in order: `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy`, `uv run lint-imports`, `uv run python scripts/export_openapi.py --check`, `uv run pytest -q`, then `cd ui && pnpm gen:check`. Every task's final step runs the subset it touched; Task 9 runs all of it.
- Contracts never import framework types; the kernel never imports domains, adapters or the server (import-linter contracts in root `pyproject.toml`).
- Never commit credentials; never access live business data. All tests use the `notes` fixture domain (`packages/kernel/tests/conftest.py`) or the fixture profile.
- Docs are English. Design doc status tags flip from `[P]` to `[I]` only in Task 9, after the code and tests exist.

### Owner amendments (2026-10-12, at execution start)

- **End to end after every task.** Each task's final verification runs the **full** CI gate (not only the touched subset) plus the PostgreSQL kernel/conformance run, and `make e2e` (UI build + Playwright conformance) whenever the task touches `apps/server`, the OpenAPI document or `ui/`. Baseline before Task 1: gate green (418 passed, 19 skipped; postgres 176 passed).
- **Model providers.** Ollama stays the default provider (`DriverConfig.provider = "ollama"`). LiteLLM is added as an explicit, opt-in provider in Task 10 under ADR 0021 (drafted in Task 1). There is never a fallback from one provider to another.

## Review Focus

Inputs the spec implies but no existing test exercises; each is pinned to a task below.

1. **Old ledger rows after upgrade** — a run written before this plan has events without `actor` and a `RunRecord` without `reason_code`; snapshot, SSE and evidence export must still read it. → Task 4 step 6, Task 5 step 7.
2. **Late decision racing an `expire` claim** — an approver decides at 15:59 while the sweeper already enqueued `expire`; exactly one of them changes state, the other sees CONFLICT/stale, never two state changes. → Task 6 step 8.
3. **Two writes to one connection where the first is `UNKNOWN`** — the second run's reservation must be refused, with a typed reason, not dispatched behind a lost lock. → Task 8 steps 1 and 6.
4. **A live profile that accidentally allows self-approval** — the readiness endpoint must say so, so a release gate can refuse it. → Task 3 step 7.
5. **SSE client resuming past the page limit** — a run with more events than one page must still be streamed completely and in order. → Task 7 step 7.

---

## Part A — Synthesis: defect → task → ADR → design section

| # | Defect (verified) | Evidence | Task | ADR | Design § |
|---|---|---|---|---|---|
| D1 | `_set_run_state` performs no transition check; `accept_input` and the approval checkpoint set run state directly | `coordinator.py:240-255`, `:445`, `:694` | 2 | 0018 | §5.1(1), §5.2, C6 |
| D2 | `decide` checks only the approver role; a principal holding both roles approves their own run | `coordinator.py:969`; `bootstrap.py:161-166`; `fixture.json` operator has both roles | 3 | 0019 | §13.2 rule 2, C16 |
| D3 | `RunEvent` has no actor; `actor_id` only inside two payloads | `events.py:36-46`; `coordinator.py:1028`, `:1397` | 4 | 0018 | §5.5 "Actor attribution", C17 |
| D4 | `run.reason` is free text; `evidence.classify()` substring-matches it | `coordinator.py` 30 call sites; `evidence.py:21-31` | 5 | 0018 | §5.5 "Failure classification", §5.6, C18 |
| D5 | Approval expiry is checked only when a decision arrives; unattended runs stay `WAITING_APPROVAL` forever | `coordinator.py:992-1001`; no sweeper | 6 | 0019 | §11.2 rule 6, C13 |
| D6 | `list_events` has no limit; SSE, snapshot and evidence export load whole runs | `store.py:391-399`; `api.py:530`; `evidence.py:34-` | 7 | 0018 | §12.4, Q3 |
| D7 | Write serialization relies only on a session advisory lock held across the ERP call | `store.py:496-508`; `coordinator.py:1114` | 8 | 0020 | §12.2, §19, C3 |
| D8 | Design doc rows for D1–D7 say `[P]` | `docs/target-architecture.md` | 9 | — | header, §5.5, §12.2, §12.4, §13.2 |

### Work packages beyond WP1 (each gets its own plan; not started here)

| WP | Content | Entry criteria | Design § |
|---|---|---|---|
| WP2 — concurrency | Run slots > 1 with per-tenant fairness (C1), LISTEN dispatcher (C2), durable writer lease (C3 part 2), `e-agent worker` role and `serve --no-worker` (C4), cross-process cancel, correlation id on events and work items (C17), load harness | WP1 merged; the shared-singleton audit (§12.2) written up as a checklist | §12, §11.1 |
| WP3 — kernel structure | SR-06 split behind the `RunCoordinator` facade (`transitions.py`, `run_loop.py`, `gateway.py`, `dispatch.py`, `verification.py`, `recovery.py`), task definitions with acceptance specs (C11), per-task approval TTL | WP2 slots > 1 stable; import-linter contracts per new module drafted | §3.3, §15, §16 |
| WP4 — cognition | Step records, progress ledger, `KERNEL-REPEAT` (C8), ContextAssembler and resume-safe rendering (C9), driver conformance suite, `ProposalRationale` and explanation projection (C18 part 2) | WP3 facade split merged; first context ablation designed | §5.4, §6, §7, §5.6 |
| WP5 — integration and production | MCP binding (C12), triggers with inbox (C13 rest), authorization bundle with approval scopes and run visibility (C16 rest), RLS with two roles and DB grants (C15, C17 part 2), API rate limits, memory and knowledge when triggered (C10, C14) | Second domain pack chosen; OIDC provider available in a staging profile | §10, §11.2, §13, §9, §8 |

---

## Part B — WP1 tasks

### Interfaces introduced by this plan (one spelling each)

| Name | Where | Introduced in |
|---|---|---|
| `ALLOWED_RUN_TRANSITIONS: dict[RunState, frozenset[RunState]]` | `e_agent.contracts.run` | Task 2 |
| `RunCoordinator._check_run_transition(run: RunRecord, to: RunState) -> None` | `e_agent.kernel.coordinator` | Task 2 |
| `RunCoordinator(..., allow_self_approval: bool = False)` | `e_agent.kernel.coordinator` | Task 3 |
| `OperatorConfig.allow_self_approval: bool = False` | `e_agent.server.profile` | Task 3 |
| `current_actor: ContextVar[str]` (default `"system:kernel"`), `actor_scope(actor: str)` | `e_agent.sdk.store` | Task 4 |
| `RunEvent.actor: str \| None = None` | `e_agent.contracts.events` | Task 4 |
| `ReasonCode(StrEnum)`, `RunRecord.reason_code: ReasonCode \| None = None` | `e_agent.contracts.run` | Task 5 |
| `RunCoordinator._set_run_state(run, state, reason=None, *, code: ReasonCode \| None = None)` | `e_agent.kernel.coordinator` | Task 5 |
| `classify(run_state, reason, environment, reason_code=None)` | `e_agent.kernel.evidence` | Task 5 |
| Work kind `"expire"`; `WorkClaim.kind` literal extended | `e_agent.contracts.work`, migration `0004_run_work_expire.sql` | Task 6 |
| `RunCoordinator.sweep_expired_approvals() -> int`, `RunCoordinator.expire_approval(tenant_id, run_id, action_id) -> RunRecord` | `e_agent.kernel.coordinator` | Task 6 |
| `APPROVAL_SWEEP_SECONDS = 30`, `ApiState.sweeper()` | `e_agent.server.api` | Task 6 |
| `RunStore.list_events(tenant_id, run_id, after_sequence=0, limit: int \| None = None)` | `e_agent.sdk.store` + both stores | Task 7 |
| `EVENT_PAGE = 500` | `e_agent.server.api` | Task 7 |
| `ConnectionBusy(ConcurrencyConflict)` | `e_agent.sdk.store` | Task 8 |

---

### Task 1: Draft ADRs 0018–0021 (Proposed) and index them

**Files:**
- Create: `docs/adr/0018-run-transitions-reason-codes-event-attribution.md`
- Create: `docs/adr/0019-approval-reachability-and-self-approval.md`
- Create: `docs/adr/0020-connection-level-write-admission.md`
- Create: `docs/adr/0021-litellm-model-provider.md` (owner amendment)
- Modify: `docs/adr/README.md` (table, after the 0017 row)

**Interfaces:**
- Produces: the three ADR numbers that Tasks 2–8 cite in commit messages and docstrings.

- [ ] **Step 1: Write ADR 0018**

```markdown
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
```

- [ ] **Step 2: Write ADR 0019**

```markdown
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
```

- [ ] **Step 3: Write ADR 0020**

```markdown
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
`(tenant_id, connection_id)` is in `DISPATCHING` or `UNKNOWN`, raising `ConnectionBusy`. The
check and the reservation insert are serialized per connection with a transaction-scoped
advisory lock. The coordinator blocks the action and fails the run with
`reason_code = CONNECTION_BUSY`; reconciliation of the earlier action must finish first.
The durable writer lease that replaces the session lock is a separate decision (WP2).

## Consequences

A connection with an unresolved write accepts no new write from any run until reconciled. This
is the intended backstop, not a throughput feature.

## Verification

Conformance test on both stores: a `DISPATCHING` action on the connection makes the next
reservation raise `ConnectionBusy`; after it reaches `COMMITTED`, reservation succeeds.
```

- [ ] **Step 3b: Write ADR 0021** (`docs/adr/0021-litellm-model-provider.md`)

```markdown
# ADR 0021: LiteLLM as an explicit second model provider

Date: 2026-10-12. Status: Proposed. Refines ADR 0001 (Ollama first, no silent cloud fallback).

## Context

The Pydantic AI driver accepts only Ollama (`DriverConfig.provider: Literal["ollama"]`,
`ollama_model()` refuses non-loopback endpoints and `-cloud` models). The owner asked to keep
Ollama as the default and also support LiteLLM, which exposes many model backends behind one
OpenAI-compatible proxy.

## Decision

- `DriverConfig.provider` becomes `Literal["ollama", "litellm"]`, default `"ollama"`.
- `litellm` uses Pydantic AI's `LiteLLMProvider` against a LiteLLM proxy whose URL comes from the
  environment variable named by `base_url_env` (default `E_AGENT_LITELLM_URL`, fallback
  `http://localhost:4000`). The endpoint must be loopback (`localhost`, `127.0.0.1`, `::1`) over
  http or https, with no userinfo, query or fragment — the same guard as Ollama.
- An API key, if the proxy needs one, comes from the environment variable named by `api_key_env`;
  the profile never contains the key, and the key never appears in errors, logs or evidence.
- The profile must name the provider explicitly to use LiteLLM. There is no fallback between
  providers: a missing model or an unreachable proxy rejects startup or fails the run.
- Evidence runtime metadata records `model_provider` next to `model`.

## Consequences

Which upstream model the proxy routes to (local or hosted) is configured in the operator's LiteLLM
proxy, outside e-agent; a hosted upstream is the operator's explicit choice, not a fallback, and
data-egress review for it belongs to that deployment. Model qualification evidence remains
per provider and model; a LiteLLM-routed model is not qualified by an Ollama run of a similar model.

## Verification

Unit tests for the endpoint guard and model construction; bootstrap tests that a `litellm` profile
builds a driver, that a missing model or a remote endpoint is rejected, and that the API key is read
from the named variable without being echoed.
```

- [ ] **Step 4: Add the four rows to `docs/adr/README.md` after the 0017 row**

```markdown
| [0018](0018-run-transitions-reason-codes-event-attribution.md) | Run transition table, reason codes, event actor, paged events | Proposed | WP1 Tasks 2, 4, 5, 7 |
| [0019](0019-approval-reachability-and-self-approval.md) | Approval expiry sweeper; self-approval forbidden unless profile allows | Proposed | WP1 Tasks 3, 6 |
| [0020](0020-connection-level-write-admission.md) | Reservation refused while the connection has an unresolved write | Proposed | WP1 Task 8 |
| [0021](0021-litellm-model-provider.md) | LiteLLM as an explicit, opt-in second model provider; Ollama stays default | Proposed | WP1 Task 10 |
```

- [ ] **Step 5: Check the links render and nothing else changed**

Run: `uv run python - <<'EOF'
import pathlib,re
for n in ("0018-run-transitions-reason-codes-event-attribution","0019-approval-reachability-and-self-approval","0020-connection-level-write-admission","0021-litellm-model-provider"):
    assert pathlib.Path(f"docs/adr/{n}.md").exists(), n
idx = pathlib.Path("docs/adr/README.md").read_text()
assert all(idx.count(f"| [{n}]") == 1 for n in ("0018", "0019", "0020", "0021"))
print("ok")
EOF`
Expected: `ok`

- [ ] **Step 6: Commit**

```bash
git add docs/adr/0018-run-transitions-reason-codes-event-attribution.md docs/adr/0019-approval-reachability-and-self-approval.md docs/adr/0020-connection-level-write-admission.md docs/adr/0021-litellm-model-provider.md docs/adr/README.md
git commit -m "docs(adr): propose 0018-0021 for run transitions, approval reachability, write admission and LiteLLM"
```

---

### Task 2: Run transition table (D1, ADR 0018, C6)

**Files:**
- Modify: `packages/contracts/src/e_agent/contracts/run.py`
- Modify: `packages/kernel/src/e_agent/kernel/coordinator.py:240-255` (`_set_run_state`), `:426-461` (`accept_input`), `:691-696` (approval checkpoint)
- Test: `packages/contracts/tests/test_records.py`, `packages/kernel/tests/test_lifecycle.py`

**Interfaces:**
- Produces: `ALLOWED_RUN_TRANSITIONS`, `RunCoordinator._check_run_transition(run, to)`.

- [ ] **Step 1: Write the failing contract test**

Append to `packages/contracts/tests/test_records.py`:

```python
from e_agent.contracts.run import ALLOWED_RUN_TRANSITIONS, TERMINAL_RUN_STATES, RunState


def test_run_transition_table_covers_every_state_and_terminals_are_final() -> None:
    assert set(ALLOWED_RUN_TRANSITIONS) == set(RunState)
    for state in TERMINAL_RUN_STATES:
        assert ALLOWED_RUN_TRANSITIONS[state] == frozenset()
    for state, targets in ALLOWED_RUN_TRANSITIONS.items():
        assert RunState.CREATED not in targets, f"{state} must not return to CREATED"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest -q packages/contracts/tests/test_records.py -k transition_table`
Expected: FAIL with `ImportError: cannot import name 'ALLOWED_RUN_TRANSITIONS'`

- [ ] **Step 3: Record the transitions the suite actually performs (temporary, not committed)**

Add this at the top of `_set_run_state` in `coordinator.py` (line 243, before `events`):

```python
        import json, os  # TEMP: transition recording, remove before commit
        if path := os.environ.get("E_AGENT_RECORD_RUN_TRANSITIONS"):
            with open(path, "a") as fh:
                fh.write(json.dumps([run.state, state]) + "\n")
```

Run: `E_AGENT_RECORD_RUN_TRANSITIONS=/tmp/run-transitions.jsonl uv run pytest -q packages/kernel apps/server tests && sort -u /tmp/run-transitions.jsonl`
Expected: all tests pass; the sorted output is the observed pair list. Keep it next to you for Step 4, then **delete the temporary block**.

- [ ] **Step 4: Add the table to `contracts/run.py`**

Below `TERMINAL_RUN_STATES` insert the table. Start from this superset, which was derived from the 30 `_set_run_state` call sites plus the two direct writes (`accept_input`, approval checkpoint) and the recovery rules in `_recover_run`; then **remove every pair that neither appeared in Step 3 nor is justified by a recovery rule comment**:

```python
# Allowed run transitions (ADR 0018). Self-transitions carry a new reason or repair;
# terminal states are final. Pairs marked "recovery" are reached only by crash rules.
ALLOWED_RUN_TRANSITIONS: dict[RunState, frozenset[RunState]] = {
    RunState.CREATED: frozenset({RunState.RUNNING, RunState.FAILED, RunState.CANCELLED}),
    RunState.RUNNING: frozenset(
        {
            RunState.RUNNING,  # stale-approval repair re-enters the driver loop
            RunState.WAITING_INPUT,
            RunState.WAITING_APPROVAL,
            RunState.VERIFYING,
            RunState.NEEDS_RECONCILIATION,  # recovery: effect unknown
            RunState.SUCCEEDED,  # verified structured answer
            RunState.FAILED,
            RunState.CANCELLED,
        }
    ),
    RunState.WAITING_INPUT: frozenset({RunState.RUNNING, RunState.FAILED, RunState.CANCELLED}),
    RunState.WAITING_APPROVAL: frozenset(
        {
            RunState.RUNNING,  # stale digest -> repair
            RunState.VERIFYING,  # dispatched and committed
            RunState.NEEDS_RECONCILIATION,  # receipt UNKNOWN
            RunState.FAILED,
            RunState.CANCELLED,
        }
    ),
    RunState.VERIFYING: frozenset(
        {
            RunState.VERIFYING,  # verifier unavailable / inconclusive, re-checked later
            RunState.SUCCEEDED,
            RunState.FAILED,
            RunState.NEEDS_RECONCILIATION,  # recovery
            RunState.CANCELLED,
        }
    ),
    RunState.NEEDS_RECONCILIATION: frozenset(
        {RunState.NEEDS_RECONCILIATION, RunState.VERIFYING, RunState.SUCCEEDED, RunState.FAILED}
    ),
    RunState.SUCCEEDED: frozenset(),
    RunState.FAILED: frozenset(),
    RunState.CANCELLED: frozenset(),
}
```

- [ ] **Step 5: Run the contract test to verify it passes**

Run: `uv run pytest -q packages/contracts/tests/test_records.py -k transition_table`
Expected: PASS

- [ ] **Step 6: Write the failing kernel test**

Append to `packages/kernel/tests/test_lifecycle.py`:

```python
async def test_terminal_run_rejects_further_transitions(make_kernel: MakeKernel) -> None:
    k = make_kernel()
    run = await _approve(k, (await _start(k)).run_id)
    assert run.state is RunState.SUCCEEDED
    with pytest.raises(KernelError) as err:
        await k.coordinator._set_run_state(run, RunState.RUNNING, "must not happen")
    assert err.value.code is ErrorCode.CONFLICT
    assert (await k.coordinator.get_run(TENANT, run.run_id)).state is RunState.SUCCEEDED
```

- [ ] **Step 7: Run it to verify it fails**

Run: `uv run pytest -q packages/kernel/tests/test_lifecycle.py -k terminal_run_rejects`
Expected: FAIL — `DID NOT RAISE` (the state actually changes today)

- [ ] **Step 8: Enforce the table in the coordinator**

In `coordinator.py` change the import on line 28 to:

```python
from e_agent.contracts.run import (
    ALLOWED_RUN_TRANSITIONS,
    TERMINAL_RUN_STATES,
    RunRecord,
    RunState,
)
```

Add the helper above `_set_run_state` and call it first thing inside `_set_run_state`:

```python
    def _check_run_transition(self, run: RunRecord, to: RunState) -> None:
        if to not in ALLOWED_RUN_TRANSITIONS[run.state]:
            raise KernelError(ErrorCode.CONFLICT, f"illegal run transition {run.state}->{to}")

    async def _set_run_state(
        self, run: RunRecord, state: RunState, reason: str | None = None
    ) -> RunRecord:
        self._check_run_transition(run, state)
        events: list[EventSpec] = [
```

In `accept_input` (line 444, before `run = await self._store.update_run(`) add:

```python
        self._check_run_transition(run, RunState.RUNNING)
```

In the approval checkpoint (line 692, before `waiting = run.model_copy(`) add:

```python
        self._check_run_transition(run, RunState.WAITING_APPROVAL)
```

- [ ] **Step 9: Run the full kernel and server suites on both stores**

Run: `uv run pytest -q packages/kernel apps/server tests/conformance`
Expected: PASS. If a test fails with `illegal run transition A->B`, that pair is real: add it to the table **with a comment naming the call site**, not by removing the check.

Run (PostgreSQL available): `E_AGENT_TEST_STORE=postgres E_AGENT_TEST_PG_DSN=$E_AGENT_TEST_PG_DSN uv run pytest -q packages/kernel tests/conformance`
Expected: PASS

- [ ] **Step 10: Lint, type-check, commit**

Run: `uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run lint-imports`
Expected: all clean (confirm the temporary recording block from Step 3 is gone: `grep -n E_AGENT_RECORD_RUN_TRANSITIONS packages/kernel/src/e_agent/kernel/coordinator.py` prints nothing).

```bash
git add packages/contracts/src/e_agent/contracts/run.py packages/contracts/tests/test_records.py packages/kernel/src/e_agent/kernel/coordinator.py packages/kernel/tests/test_lifecycle.py
git commit -m "feat(kernel): table and enforce run transitions (ADR 0018, C6)"
```

---

### Task 3: Self-approval rule gated by the profile (D2, ADR 0019, C16)

**Files:**
- Modify: `packages/kernel/src/e_agent/kernel/coordinator.py:110-133` (constructor), `:958-970` (`decide`)
- Modify: `apps/server/src/e_agent/server/profile.py:16-19` (`OperatorConfig`)
- Modify: `apps/server/src/e_agent/server/profiles/fixture.json` (operator block)
- Modify: `apps/server/src/e_agent/server/bootstrap.py:239-247`
- Modify: `apps/server/src/e_agent/server/api.py:424-432` (`/health/ready`)
- Modify: `packages/kernel/tests/conftest.py:278-323` (`make_kernel` passthrough)
- Test: `packages/kernel/tests/test_lifecycle.py`, `apps/server/tests/test_api.py`

**Interfaces:**
- Produces: `RunCoordinator(allow_self_approval: bool = False)`, `OperatorConfig.allow_self_approval: bool = False`, `/health/ready` field `self_approval_allowed`.

- [ ] **Step 1: Write the failing kernel tests**

Append to `packages/kernel/tests/test_lifecycle.py`:

```python
async def test_requester_with_approver_role_cannot_approve_own_run(make_kernel: MakeKernel) -> None:
    k = make_kernel()
    carol = principal("carol", {"requester", "approver"})
    run = await k.coordinator.start_run(carol, "write standup note", k.scope)
    assert run.state is RunState.WAITING_APPROVAL
    pres = await k.coordinator.pending_approval(TENANT, run.run_id)
    with pytest.raises(KernelError) as err:
        await k.coordinator.decide(
            actor=carol,
            run_id=run.run_id,
            action_id=pres.action_id,
            action_digest=pres.digest,
            expected_run_revision=pres.run_revision,
            decision=ApprovalDecision.APPROVED,
        )
    assert err.value.code is ErrorCode.FORBIDDEN
    assert (await k.coordinator.get_run(TENANT, run.run_id)).state is RunState.WAITING_APPROVAL


async def test_profile_may_allow_self_approval_for_local_demo(make_kernel: MakeKernel) -> None:
    k = make_kernel(allow_self_approval=True)
    carol = principal("carol", {"requester", "approver"})
    run = await k.coordinator.start_run(carol, "write standup note", k.scope)
    pres = await k.coordinator.pending_approval(TENANT, run.run_id)
    run = await k.coordinator.decide(
        actor=carol,
        run_id=run.run_id,
        action_id=pres.action_id,
        action_digest=pres.digest,
        expected_run_revision=pres.run_revision,
        decision=ApprovalDecision.APPROVED,
    )
    assert run.state is RunState.SUCCEEDED
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest -q packages/kernel/tests/test_lifecycle.py -k self_approval`
Expected: first test FAILS with `DID NOT RAISE`; second FAILS with `TypeError: _make() got an unexpected keyword argument 'allow_self_approval'`

- [ ] **Step 3: Add the coordinator setting and the check**

Constructor (`coordinator.py:110-133`): add the parameter and field.

```python
        approval_ttl: timedelta = DEFAULT_APPROVAL_TTL,
        allow_self_approval: bool = False,
        budgets: Budgets | None = None,
```
```python
        self._approval_ttl = approval_ttl
        self._allow_self_approval = allow_self_approval
```

In `decide`, directly after the approver-role check (line 970):

```python
        if actor.principal_id == run.requester_id and not self._allow_self_approval:
            raise KernelError(ErrorCode.FORBIDDEN, "the requester cannot approve their own run")
```

- [ ] **Step 4: Thread the flag through the test harness**

In `packages/kernel/tests/conftest.py` `_make(...)` signature add `allow_self_approval: bool = False,` after `binding_connections`, and pass `allow_self_approval=allow_self_approval,` to `RunCoordinator(...)`.

- [ ] **Step 5: Run the kernel tests**

Run: `uv run pytest -q packages/kernel`
Expected: PASS (the existing `test_requester_cannot_approve` still passes: alice lacks the role).

- [ ] **Step 6: Thread the flag through profile, bootstrap and the fixture profile**

`profile.py` `OperatorConfig`:

```python
class OperatorConfig(Record):
    principal_id: str
    roles: frozenset[str]
    display_name: str | None = None
    allow_self_approval: bool = False
    """Local demo only: one operator holds requester and approver (HLD §3, ADR 0019)."""
```

`fixture.json` operator block: add `"allow_self_approval": true` after `"roles": [...]`.

`bootstrap.py:239-247`:

```python
    coordinator = RunCoordinator(
        store=store,
        registry=registry,
        connections=catalog,
        policy=DefaultPolicy(),
        driver=driver,
        allow_self_approval=profile.operator.allow_self_approval,
        budgets=profile.budgets,
        credentials=credentials,
    )
```

- [ ] **Step 7: Write the failing API test for the readiness report, then implement it**

Append to `apps/server/tests/test_api.py`:

```python
def test_ready_reports_whether_self_approval_is_allowed(client: TestClient) -> None:
    body = client.get("/health/ready").json()
    assert body["self_approval_allowed"] is True  # fixture profile: one local operator
```

Run: `uv run pytest -q apps/server/tests/test_api.py -k self_approval_is_allowed` → Expected: FAIL with `KeyError: 'self_approval_allowed'`.

In `api.py` `/health/ready` add the field:

```python
            "store": rt.profile.store.kind,
            "self_approval_allowed": rt.profile.operator.allow_self_approval,
```

Run again → Expected: PASS.

- [ ] **Step 8: Full server suite, OpenAPI check, lint**

Run: `uv run pytest -q apps/server && uv run python scripts/export_openapi.py --check && uv run ruff check . && uv run mypy`
Expected: PASS; the OpenAPI check passes unchanged (`/health/ready` is typed `dict[str, Any]`). If `export_openapi.py --check` fails, run `uv run python scripts/export_openapi.py && (cd ui && pnpm gen)` and add the two generated files to the commit.

- [ ] **Step 9: Commit**

```bash
git add packages/kernel/src/e_agent/kernel/coordinator.py packages/kernel/tests/conftest.py packages/kernel/tests/test_lifecycle.py apps/server/src/e_agent/server/profile.py apps/server/src/e_agent/server/profiles/fixture.json apps/server/src/e_agent/server/bootstrap.py apps/server/src/e_agent/server/api.py apps/server/tests/test_api.py
git commit -m "feat(kernel): forbid self-approval unless the profile allows it (ADR 0019, C16)"
```

---

### Task 4: Actor on every run event (D3, ADR 0018, C17 part 1)

**Files:**
- Modify: `packages/plugin-sdk/src/e_agent/sdk/store.py` (new context variable + scope)
- Modify: `packages/contracts/src/e_agent/contracts/events.py:36-46` (`RunEvent.actor`)
- Modify: `packages/adapter-postgres/src/e_agent/adapters/postgres/store.py:65-101` (`_append`)
- Modify: `packages/kernel/src/e_agent/kernel/memory_store.py:59-72` (`_append`)
- Modify: `apps/server/src/e_agent/server/api.py:408-417` (`session`), `:218-290` (`_run_work`)
- Regenerate: `ui/packages/client/openapi.json`, `ui/packages/client/src/schema.ts`
- Test: `tests/conformance/test_run_store.py`, `apps/server/tests/test_api.py`

**Interfaces:**
- Produces: `current_actor`, `actor_scope`, `RunEvent.actor`.

- [ ] **Step 1: Write the failing conformance test**

Append to `tests/conformance/test_run_store.py`:

```python
from e_agent.sdk.store import actor_scope


async def test_events_record_the_current_actor(store: Any) -> None:
    await store.create_run(_run(), [(RunEventType.RUN_CREATED, {}, None)])
    with actor_scope("principal:alice"):
        await store.update_run(_run(rev=2), 1, [(RunEventType.RUN_STATE_CHANGED, {}, None)])
    events = await store.list_events("t1", "run_1")
    assert [e.actor for e in events] == ["system:kernel", "principal:alice"]
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest -q tests/conformance/test_run_store.py -k current_actor`
Expected: FAIL with `ImportError: cannot import name 'actor_scope'`

- [ ] **Step 3: Add the context variable to the SDK and the field to the contract**

`packages/plugin-sdk/src/e_agent/sdk/store.py`, after the imports:

```python
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

current_actor: ContextVar[str] = ContextVar("e_agent_current_actor", default="system:kernel")
"""Who causes the events appended in this context (ADR 0018): ``principal:<id>``,
``system:kernel`` or ``system:worker:<owner>``. Set by the API session and the worker."""


@contextmanager
def actor_scope(actor: str) -> Iterator[None]:
    token = current_actor.set(actor)
    try:
        yield
    finally:
        current_actor.reset(token)
```

`packages/contracts/src/e_agent/contracts/events.py` `RunEvent`, after `correlation_id`:

```python
    actor: str | None = None
    """Who caused the event (ADR 0018). None on rows written before the field existed."""
```

- [ ] **Step 4: Stamp the actor in both `_append` implementations**

PostgreSQL `store.py` `_append`: import `from e_agent.sdk.store import ..., current_actor` (extend the existing import line) and set `actor=current_actor.get(),` in the `RunEvent(...)` construction after `action_id=action_id,`.

`memory_store.py` `_append`: same import extension and the same `actor=current_actor.get(),` line.

- [ ] **Step 5: Run the conformance test**

Run: `uv run pytest -q tests/conformance/test_run_store.py -k current_actor`
Expected: PASS (memory). With PostgreSQL: `E_AGENT_TEST_PG_DSN=$E_AGENT_TEST_PG_DSN uv run pytest -q tests/conformance/test_run_store.py -k current_actor` → PASS for both params.

- [ ] **Step 6: Pin old rows: an event without `actor` still parses**

Append to `packages/contracts/tests/test_records.py`:

```python
from e_agent.contracts.events import RunEvent


def test_run_event_without_actor_still_parses() -> None:
    event = RunEvent.model_validate(
        {
            "event_id": "evt_1",
            "tenant_id": "t1",
            "run_id": "run_1",
            "sequence": 1,
            "type": "run.created",
            "occurred_at": "2026-10-06T00:00:00Z",
            "payload": {},
        }
    )
    assert event.actor is None
```

Run: `uv run pytest -q packages/contracts/tests/test_records.py -k without_actor` → Expected: PASS.

- [ ] **Step 7: Set the actor at the API boundary and in the worker**

`api.py` imports: add `actor_scope, current_actor` to the `e_agent.sdk.store` import. In `session()` just before `return found`:

```python
        current_actor.set(f"principal:{found.principal.principal_id}")
```

In `_run_work`, after `run = await rt.store.get_run(claim.tenant_id, claim.run_id)` compute the actor and wrap the execution branches:

```python
                if claim.kind == "decide":
                    actor_label = f"principal:{claim.payload['actor']['principal_id']}"
                elif claim.kind in {"start", "input"}:
                    actor_label = f"principal:{run.requester_id}"
                else:
                    actor_label = f"system:worker:{claim.owner}"
```

and replace the block from `if claim.fence > 1 and not untouched:` through the `decide(...)` call with the same code indented under `with actor_scope(actor_label):`. Recovery (`recover_run`) runs with `system:worker:<owner>`: wrap that single call separately:

```python
                if claim.fence > 1 and not untouched:
                    with actor_scope(f"system:worker:{claim.owner}"):
                        await rt.coordinator.recover_run(claim.tenant_id, claim.run_id)
                else:
                    with actor_scope(actor_label):
                        if claim.kind == "start":
                            await rt.coordinator.start_admitted_run(claim.tenant_id, claim.run_id)
                        elif claim.kind == "input":
                            await rt.coordinator.continue_input(claim.tenant_id, claim.run_id)
                        else:
                            payload = claim.payload
                            await rt.coordinator.decide(
                                actor=Principal.model_validate(payload["actor"]),
                                run_id=claim.run_id,
                                action_id=payload["action_id"],
                                action_digest=payload["digest"],
                                expected_run_revision=payload["expected_revision"],
                                decision=ApprovalDecision(payload["decision"]),
                            )
```

- [ ] **Step 8: Write the failing API test, then run it**

Append to `apps/server/tests/test_api.py`:

```python
def test_events_name_the_principal_who_caused_them(client: TestClient) -> None:
    h = _login(client)
    r = client.post(
        "/v1/runs", json={"task": "restock widget-a"}, headers={**h, "Idempotency-Key": "actor-key-0001"}
    )
    run_id = r.json()["run_id"]
    body = _wait(client, run_id, {"WAITING_APPROVAL"})
    pres = body["pending_approval"]
    client.post(
        f"/v1/runs/{run_id}/approvals",
        json={
            "action_id": pres["action_id"],
            "digest": pres["digest"],
            "expected_revision": pres["run_revision"],
            "decision": "approved",
        },
        headers=h,
    )
    _wait(client, run_id, {"SUCCEEDED", "FAILED"})
    events = client.get(f"/v1/runs/{run_id}/events").json()
    by_type = {e["type"]: e["actor"] for e in events}
    assert by_type["run.created"] == "principal:local-operator"
    assert by_type["approval.decided"] == "principal:local-operator"
    assert all(e["actor"] for e in events), "every event names an actor"
```

Run: `uv run pytest -q apps/server/tests/test_api.py -k name_the_principal`
Expected: PASS. If `run.created` shows `system:kernel`, the request path creates the run outside the session context: check that `create_run_idempotent` is called from the endpoint (same task as `session()`), not from a background task.

- [ ] **Step 9: Regenerate OpenAPI and TypeScript types**

Run: `uv run python scripts/export_openapi.py && (cd ui && pnpm gen) && uv run python scripts/export_openapi.py --check && (cd ui && pnpm gen:check)`
Expected: both checks exit 0; `git status` shows `ui/packages/client/openapi.json` and `ui/packages/client/src/schema.ts` modified with a new optional `actor` on `RunEvent`.

- [ ] **Step 10: Full gate for touched packages and commit**

Run: `uv run pytest -q packages apps tests && uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run lint-imports`
Expected: PASS

```bash
git add packages/plugin-sdk/src/e_agent/sdk/store.py packages/contracts/src/e_agent/contracts/events.py packages/contracts/tests/test_records.py packages/adapter-postgres/src/e_agent/adapters/postgres/store.py packages/kernel/src/e_agent/kernel/memory_store.py apps/server/src/e_agent/server/api.py apps/server/tests/test_api.py tests/conformance/test_run_store.py ui/packages/client/openapi.json ui/packages/client/src/schema.ts
git commit -m "feat(ledger): record the acting principal on every run event (ADR 0018, C17)"
```

---

### Task 5: Reason codes replace substring classification (D4, ADR 0018, C18 part 1)

**Files:**
- Modify: `packages/contracts/src/e_agent/contracts/run.py` (`ReasonCode`, `RunRecord.reason_code`)
- Modify: `packages/kernel/src/e_agent/kernel/coordinator.py` (`_set_run_state` signature + 30 call sites listed below)
- Modify: `packages/kernel/src/e_agent/kernel/evidence.py:21-31` (`classify`), `:74` (call)
- Regenerate: `ui/packages/client/openapi.json`, `ui/packages/client/src/schema.ts`
- Test: `packages/kernel/tests/test_evidence.py` (new), `packages/kernel/tests/test_lifecycle.py`

**Interfaces:**
- Produces: `ReasonCode`, `RunRecord.reason_code`, `_set_run_state(..., *, code=None)`, `classify(..., reason_code=None)`.

- [ ] **Step 1: Write the failing classifier tests**

Create `packages/kernel/tests/test_evidence.py`:

```python
"""Evidence classification reads typed reason codes first (ADR 0018)."""

from e_agent.contracts.run import ReasonCode
from e_agent.kernel.evidence import classify


def test_reason_code_decides_the_class_before_any_text() -> None:
    assert classify("FAILED", "whatever", "fixture", ReasonCode.POLICY_DENIED) == (
        "fixture:blocked-by-design"
    )
    assert classify("FAILED", "whatever", "fixture", ReasonCode.BUDGET_EXHAUSTED) == (
        "fixture:infrastructure-or-budget"
    )
    assert classify("FAILED", "whatever", "fixture", ReasonCode.APPROVAL_EXPIRED) == (
        "fixture:failed"
    )


def test_rows_without_a_code_fall_back_to_the_text_rules() -> None:
    assert classify("FAILED", "validation blocked", "fixture") == "fixture:blocked-by-design"
    assert classify("FAILED", "budget exhausted: turns", "fixture") == (
        "fixture:infrastructure-or-budget"
    )
    assert classify("SUCCEEDED", None, "live") == "live:succeeded"
    assert classify("RUNNING", None, "live") == "live:unresolved"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest -q packages/kernel/tests/test_evidence.py`
Expected: FAIL with `ImportError: cannot import name 'ReasonCode'`

- [ ] **Step 3: Add `ReasonCode` and the field to `contracts/run.py`**

After `RunState`:

```python
class ReasonCode(StrEnum):
    """Typed cause of a run state change (ADR 0018). The human `reason` text stays."""

    ANSWERED = "answered"
    VERIFIED = "verified"
    VERIFICATION_PENDING = "verification_pending"
    VERIFICATION_FAILED = "verification_failed"
    VALIDATION_FAILED = "validation_failed"
    POLICY_DENIED = "policy_denied"
    STALE = "stale"
    SURFACE_CHANGED = "surface_changed"
    APPROVAL_REJECTED = "approval_rejected"
    APPROVAL_EXPIRED = "approval_expired"
    OPERATION_RESERVED = "operation_reserved"
    CONNECTION_BUSY = "connection_busy"
    EFFECT_UNKNOWN = "effect_unknown"
    PROVIDER_ERROR = "provider_error"
    BUDGET_EXHAUSTED = "budget_exhausted"
    INTERRUPTED = "interrupted"
    CANCELLED = "cancelled"
```

`RunRecord`: after `reason: str | None = None` add `reason_code: ReasonCode | None = None`.

- [ ] **Step 4: Rewrite `classify`**

Replace `classify` in `evidence.py`:

```python
BLOCKED_BY_DESIGN = frozenset(
    {
        ReasonCode.VALIDATION_FAILED,
        ReasonCode.POLICY_DENIED,
        ReasonCode.STALE,
        ReasonCode.SURFACE_CHANGED,
        ReasonCode.APPROVAL_REJECTED,
        ReasonCode.OPERATION_RESERVED,
        ReasonCode.VERIFICATION_FAILED,
    }
)
INFRASTRUCTURE_OR_BUDGET = frozenset(
    {
        ReasonCode.BUDGET_EXHAUSTED,
        ReasonCode.INTERRUPTED,
        ReasonCode.PROVIDER_ERROR,
        ReasonCode.CONNECTION_BUSY,
    }
)


def classify(
    run_state: str,
    reason: str | None,
    environment: str,
    reason_code: ReasonCode | None = None,
) -> str:
    if run_state == "SUCCEEDED":
        return f"{environment}:succeeded"
    if run_state not in {str(s) for s in TERMINAL_RUN_STATES}:
        return f"{environment}:unresolved"
    if reason_code is not None:
        if reason_code in BLOCKED_BY_DESIGN:
            return f"{environment}:blocked-by-design"
        if reason_code in INFRASTRUCTURE_OR_BUDGET:
            return f"{environment}:infrastructure-or-budget"
        return f"{environment}:failed"
    # Rows written before ADR 0018 carry no code: keep the historical text rules.
    text = (reason or "").lower()
    if "validation" in text or "rejected" in text or "policy" in text:
        return f"{environment}:blocked-by-design"
    if "budget" in text or "interrupted" in text or "provider" in text:
        return f"{environment}:infrastructure-or-budget"
    return f"{environment}:failed"
```

Import `ReasonCode` next to `TERMINAL_RUN_STATES` and change the call in `build_evidence` to `classify(run.state, run.reason, environment, run.reason_code)`.

- [ ] **Step 5: Run the classifier tests**

Run: `uv run pytest -q packages/kernel/tests/test_evidence.py`
Expected: PASS

- [ ] **Step 6: Write the failing lifecycle test**

Append to `packages/kernel/tests/test_lifecycle.py`:

```python
async def test_rejected_approval_records_a_reason_code(make_kernel: MakeKernel) -> None:
    k = make_kernel()
    run = await _approve(k, (await _start(k)).run_id, ApprovalDecision.REJECTED)
    assert run.state is RunState.FAILED
    assert run.reason_code is ReasonCode.APPROVAL_REJECTED
    assert run.reason == "rejected by approver"
    changed = [
        e for e in await k.store.list_events(TENANT, run.run_id) if e.type is RunEventType.RUN_STATE_CHANGED
    ]
    assert changed[-1].payload["reason_code"] == "approval_rejected"
```

Add `ReasonCode` to the `e_agent.contracts.run` import at the top of the test file.

Run: `uv run pytest -q packages/kernel/tests/test_lifecycle.py -k reason_code` → Expected: FAIL with `AttributeError`/`AssertionError` on `reason_code`.

- [ ] **Step 7: Change `_set_run_state` and every call site**

Signature and body:

```python
    async def _set_run_state(
        self,
        run: RunRecord,
        state: RunState,
        reason: str | None = None,
        *,
        code: ReasonCode | None = None,
    ) -> RunRecord:
        self._check_run_transition(run, state)
        events: list[EventSpec] = [
            (
                RunEventType.RUN_STATE_CHANGED,
                {"from": run.state, "to": state, "reason": reason, "reason_code": code},
                None,
            )
        ]
        if state in TERMINAL_RUN_STATES:
            events.append(
                (RunEventType.RUN_TERMINAL, {"state": state, "reason": reason, "reason_code": code}, None)
            )
        updated = run.model_copy(
            update={"state": state, "revision": run.revision + 1, "reason": reason, "reason_code": code}
        )
```

Add `ReasonCode` to the `e_agent.contracts.run` import. Then add `code=` at each call site (line numbers are pre-change; match on the reason text):

| Line | Reason text | `code=` |
|---|---|---|
| 393 | `"no independently verified outcome"` | `ReasonCode.VERIFICATION_FAILED` |
| 422 | `"answered"` | `ReasonCode.ANSWERED` |
| 497 | `f"budget exhausted: {what}"` | `ReasonCode.BUDGET_EXHAUSTED` |
| 667 | `"policy denied"` | `ReasonCode.POLICY_DENIED` |
| 670 | `"validation blocked"` | `ReasonCode.VALIDATION_FAILED` |
| 819 | `"answer not verified"` | `ReasonCode.VERIFICATION_FAILED` |
| 988 | `"capability surface changed"` | `ReasonCode.SURFACE_CHANGED` |
| 1000 | `"approval expired"` | `ReasonCode.APPROVAL_EXPIRED` |
| 1038 | `"rejected by approver"` | `ReasonCode.APPROVAL_REJECTED` |
| 1064, 1066 | `stale_reason` (FAILED and RUNNING) | `ReasonCode.STALE` |
| 1097 | `"operation already reserved"` | `ReasonCode.OPERATION_RESERVED` |
| 1220 | `NEEDS_RECONCILIATION` after receipt | `ReasonCode.EFFECT_UNKNOWN` |
| 1227 | `"provider rejected the write"` | `ReasonCode.PROVIDER_ERROR` |
| 1238, 1266, 1281 | `VERIFYING` with a reason | `ReasonCode.VERIFICATION_PENDING` |
| 1293 | `"outcome verification failed"` | `ReasonCode.VERIFICATION_FAILED` |
| 1351 | `"outcome verified"` | `ReasonCode.VERIFIED` |
| 1400 | `"cancel requested; effect must be reconciled"` | `ReasonCode.EFFECT_UNKNOWN` |
| 1412 | `"cancelled before dispatch"` | `ReasonCode.CANCELLED` |
| 1483 | `"interrupted before dispatch; approve a new run"` | `ReasonCode.INTERRUPTED` |
| 1490 | `"persisted write outcome unknown"` | `ReasonCode.EFFECT_UNKNOWN` |
| 1504 | `"outcome verified"` (recovery) | `ReasonCode.VERIFIED` |
| 1506 | `"outcome verification failed"` (recovery) | `ReasonCode.VERIFICATION_FAILED` |
| 1508 | `"interrupted during driver turn"` | `ReasonCode.INTERRUPTED` |

Calls with no reason (191, 225, 380, 1228) keep `code=None`. Verify coverage: `grep -n '_set_run_state(' packages/kernel/src/e_agent/kernel/coordinator.py | grep -v 'async def' | grep -v 'code='` must list only those four lines plus multi-line calls whose `code=` is on the next line.

- [ ] **Step 8: Pin old rows: a `RunRecord` without `reason_code` still parses**

Append to `packages/contracts/tests/test_records.py`:

```python
from e_agent.contracts.run import RunRecord


def test_run_record_without_reason_code_still_parses() -> None:
    run = RunRecord.model_validate(
        {
            "run_id": "run_1",
            "tenant_id": "t1",
            "requester_id": "u",
            "task": "x",
            "state": "FAILED",
            "revision": 3,
            "logical_operation_id": "op_1",
            "created_at": "2026-10-06T00:00:00Z",
            "reason": "validation blocked",
        }
    )
    assert run.reason_code is None
```

- [ ] **Step 9: Run suites, regenerate types, lint, commit**

Run: `uv run pytest -q packages apps tests && uv run python scripts/export_openapi.py && (cd ui && pnpm gen) && uv run python scripts/export_openapi.py --check && uv run ruff check . && uv run ruff format --check . && uv run mypy`
Expected: PASS; `schema.ts` gains `reason_code` on the run record type.

```bash
git add packages/contracts/src/e_agent/contracts/run.py packages/contracts/tests/test_records.py packages/kernel/src/e_agent/kernel/coordinator.py packages/kernel/src/e_agent/kernel/evidence.py packages/kernel/tests/test_evidence.py packages/kernel/tests/test_lifecycle.py ui/packages/client/openapi.json ui/packages/client/src/schema.ts
git commit -m "feat(kernel): typed reason codes on run state changes; classifier reads them first (ADR 0018, C18)"
```

---

### Task 6: Approval expiry sweeper through fenced work (D5, ADR 0019, C13)

**Files:**
- Create: `packages/adapter-postgres/src/e_agent/adapters/postgres/migrations/0004_run_work_expire.sql`
- Modify: `packages/contracts/src/e_agent/contracts/work.py` (`kind` literal)
- Modify: `packages/kernel/src/e_agent/kernel/coordinator.py:990-1001` (extract `_expire_pending`), new `sweep_expired_approvals`, `expire_approval`
- Modify: `apps/server/src/e_agent/server/api.py:205-216` (`worker`), `:218-290` (`_run_work`), `:366-372` (lifespan)
- Modify: `packages/adapter-postgres/tests/test_migrations.py` (expected migration list, if asserted)
- Test: `packages/kernel/tests/test_lifecycle.py`, `tests/conformance/test_run_store.py`

**Interfaces:**
- Consumes: `ReasonCode.APPROVAL_EXPIRED` (Task 5), `_check_run_transition` (Task 2).
- Produces: work kind `"expire"`, `sweep_expired_approvals`, `expire_approval`, `ApiState.sweeper`, `APPROVAL_SWEEP_SECONDS`.

- [ ] **Step 1: Write the failing conformance test for the new work kind**

Append to `tests/conformance/test_run_store.py`:

```python
async def test_expire_work_kind_is_accepted_by_the_queue(store: Any) -> None:
    await store.create_run(_run(), [(RunEventType.RUN_CREATED, {}, None)])
    payload = {"action_id": "act_1", "requested_at": "2026-10-06T00:00:00+00:00"}
    await store.enqueue_work("t1", "run_1", "expire", payload, "digest-expire-1")
    await store.enqueue_work("t1", "run_1", "expire", payload, "digest-expire-1")  # idempotent
    claim = await store.claim_work("w1")
    assert claim is not None and claim.kind == "expire" and claim.payload == payload
    assert await store.claim_work("w2") is None
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest -q tests/conformance/test_run_store.py -k expire_work_kind`
Expected: memory FAILS with a Pydantic validation error on `kind` (`Input should be 'start', 'decide' or 'input'`); PostgreSQL (if configured) FAILS with `CheckViolation`.

- [ ] **Step 3: Widen the contract and the table**

`contracts/work.py`: `kind: Literal["start", "decide", "input", "expire"]`.

Create `migrations/0004_run_work_expire.sql`:

```sql
-- ADR 0019: approval expiry runs as fenced work, never outside a claim.
ALTER TABLE run_work DROP CONSTRAINT run_work_kind_check;
ALTER TABLE run_work ADD CONSTRAINT run_work_kind_check
    CHECK (kind IN ('start', 'decide', 'input', 'expire'));
```

If `packages/adapter-postgres/tests/test_migrations.py` asserts the applied list, append `"0004_run_work_expire.sql"`.

- [ ] **Step 4: Run the conformance and migration tests**

Run: `uv run pytest -q tests/conformance/test_run_store.py -k expire_work_kind packages/adapter-postgres`
Expected: PASS (memory). With `E_AGENT_TEST_PG_DSN` set: PASS for postgres too.

- [ ] **Step 5: Write the failing kernel test**

Append to `packages/kernel/tests/test_lifecycle.py`:

```python
async def test_expired_approval_is_swept_to_failed_without_a_decision(make_kernel: MakeKernel) -> None:
    k = make_kernel()
    run = await _start(k)
    assert await k.coordinator.sweep_expired_approvals() == 0, "not expired yet"
    k.clock.advance(minutes=16)
    assert await k.coordinator.sweep_expired_approvals() == 1
    assert await k.coordinator.sweep_expired_approvals() == 0, "idempotent while queued"
    claim = await k.store.claim_work("sweeper-test")
    assert claim is not None and claim.kind == "expire", claim
    async with k.store.work_scope(claim):
        run = await k.coordinator.expire_approval(TENANT, run.run_id, claim.payload["action_id"])
        await k.store.finish_work(claim)
    assert run.state is RunState.FAILED
    assert run.reason_code is ReasonCode.APPROVAL_EXPIRED
    actions = await k.store.list_actions(TENANT, run.run_id)
    assert actions[-1].state is ActionState.BLOCKED
    decided = [e for e in await k.store.list_events(TENANT, run.run_id) if e.type is RunEventType.APPROVAL_DECIDED]
    assert decided[-1].payload == {"decision": "expired"}
    with pytest.raises(KernelError) as err:
        await _approve(k, run.run_id)
    assert err.value.code is ErrorCode.NOT_FOUND  # no pending approval any more
```

If `claim.kind` comes back as `"start"` in this harness, `start_run` left a finished-or-pending start item; finish it with `await k.store.finish_work(claim)` inside a `work_scope` and claim again before asserting.

- [ ] **Step 6: Run it to verify it fails**

Run: `uv run pytest -q packages/kernel/tests/test_lifecycle.py -k swept_to_failed`
Expected: FAIL with `AttributeError: 'RunCoordinator' object has no attribute 'sweep_expired_approvals'`

- [ ] **Step 7: Extract `_expire_pending`, add the sweeper and the executor**

In `decide`, replace lines 990-1001 with:

```python
        now = self._clock()
        assert cont.approval_requested_at is not None
        if now > cont.approval_requested_at + self._approval_ttl:
            await self._expire_pending(cont, action)
            raise KernelError(ErrorCode.APPROVAL_STALE, "approval window expired")
```

Add the three methods in the approvals section (after `pending_approval`):

```python
    async def _expire_pending(self, cont: _Continuation, action: ActionRecord) -> RunRecord:
        """Decide-path expiry outcome, shared with the sweeper (ADR 0019)."""
        await self._transition(
            action,
            ActionState.BLOCKED,
            (RunEventType.APPROVAL_DECIDED, {"decision": "expired"}),
        )
        cont.pending_action_id = None
        run = await self._store.get_run(cont.ctx.tenant_id, cont.ctx.run_id)
        return await self._set_run_state(
            run, RunState.FAILED, "approval expired", code=ReasonCode.APPROVAL_EXPIRED
        )

    async def sweep_expired_approvals(self) -> int:
        """Enqueue fenced `expire` work for every approval past its TTL. Never mutates state."""
        now = self._clock()
        queued = 0
        for run in await self._store.list_unfinished_runs():
            if run.state is not RunState.WAITING_APPROVAL:
                continue
            try:
                cont = await self._load_cont(run.tenant_id, run.run_id)
            except KernelError:
                continue
            if cont.pending_action_id is None or cont.approval_requested_at is None:
                continue
            if now <= cont.approval_requested_at + self._approval_ttl:
                continue
            payload = {
                "action_id": cont.pending_action_id,
                "requested_at": cont.approval_requested_at.isoformat(),
            }
            if await self._store.has_pending_work(run.tenant_id, run.run_id):
                continue  # a decision or an earlier sweep is already queued
            await self._store.enqueue_work(
                run.tenant_id, run.run_id, "expire", payload, digest(payload)
            )
            queued += 1
        return queued

    async def expire_approval(self, tenant_id: str, run_id: str, action_id: str) -> RunRecord:
        """Executed under a work claim: re-check everything, then apply the expiry outcome."""
        run = await self._store.get_run(tenant_id, run_id)
        if run.state is not RunState.WAITING_APPROVAL:
            return run
        cont = await self._load_cont(tenant_id, run_id)
        if cont.pending_action_id != action_id or cont.approval_requested_at is None:
            return run
        if self._clock() <= cont.approval_requested_at + self._approval_ttl:
            return run
        action = await self._store.get_action(tenant_id, action_id)
        return await self._expire_pending(cont, action)
```

- [ ] **Step 8: Pin the race: a late decision and an `expire` claim cannot both change state**

Append to `packages/kernel/tests/test_lifecycle.py`:

```python
async def test_late_decision_after_sweep_sees_stale_not_double_change(make_kernel: MakeKernel) -> None:
    k = make_kernel()
    run = await _start(k)
    k.clock.advance(minutes=16)
    assert await k.coordinator.sweep_expired_approvals() == 1
    # The approver's decision arrives first and is itself rejected as expired.
    with pytest.raises(KernelError) as err:
        await _approve(k, run.run_id)
    assert err.value.code is ErrorCode.APPROVAL_STALE
    failed = await k.coordinator.get_run(TENANT, run.run_id)
    assert failed.state is RunState.FAILED
    # The queued expire claim then finds nothing to do and changes nothing.
    claim = await k.store.claim_work("sweeper-test")
    assert claim is not None and claim.kind == "expire"
    async with k.store.work_scope(claim):
        again = await k.coordinator.expire_approval(TENANT, run.run_id, claim.payload["action_id"])
        await k.store.finish_work(claim)
    assert again.revision == failed.revision
```

Run: `uv run pytest -q packages/kernel/tests/test_lifecycle.py -k "swept_to_failed or late_decision"`
Expected: PASS

- [ ] **Step 9: Wire the sweeper and the `expire` branch into the server**

`api.py`: add `APPROVAL_SWEEP_SECONDS = 30` next to `LOOPBACK`. In `ApiState` add:

```python
    async def sweeper(self) -> None:
        while True:
            await asyncio.sleep(APPROVAL_SWEEP_SECONDS)
            try:
                await self.runtime.coordinator.sweep_expired_approvals()
            except Exception:
                continue  # the next tick retries; sweeping never fails the server
```

In `lifespan`, after the worker task:

```python
        sweeper = asyncio.create_task(holder["state"].sweeper())
        holder["state"].tasks.add(sweeper)
```

In `_run_work`: after the `untouched` computations add `if claim.kind == "expire": untouched = True`, and add the branch inside the `actor_scope(actor_label)` block before the final `else`:

```python
                        elif claim.kind == "expire":
                            await rt.coordinator.expire_approval(
                                claim.tenant_id, claim.run_id, claim.payload["action_id"]
                            )
```

(The actor label for `expire` is already `system:worker:<owner>` from Task 4's `else` branch.)

- [ ] **Step 10: Run the suites on both stores, lint, commit**

Run: `uv run pytest -q packages apps tests && uv run ruff check . && uv run ruff format --check . && uv run mypy`
Expected: PASS. With PostgreSQL: `E_AGENT_TEST_STORE=postgres E_AGENT_TEST_PG_DSN=$E_AGENT_TEST_PG_DSN uv run pytest -q packages/kernel tests/conformance packages/adapter-postgres` → PASS.

```bash
git add packages/adapter-postgres/src/e_agent/adapters/postgres/migrations/0004_run_work_expire.sql packages/adapter-postgres/tests/test_migrations.py packages/contracts/src/e_agent/contracts/work.py packages/kernel/src/e_agent/kernel/coordinator.py packages/kernel/tests/test_lifecycle.py apps/server/src/e_agent/server/api.py tests/conformance/test_run_store.py
git commit -m "feat(kernel): sweep expired approvals through fenced expire work (ADR 0019, C13)"
```

---

### Task 7: Bounded event reads (D6, ADR 0018, Q3)

**Files:**
- Modify: `packages/plugin-sdk/src/e_agent/sdk/store.py` (`list_events` signature)
- Modify: `packages/adapter-postgres/src/e_agent/adapters/postgres/store.py:391-399`
- Modify: `packages/kernel/src/e_agent/kernel/memory_store.py:276-279`
- Modify: `apps/server/src/e_agent/server/api.py:499-508` (`events`), `:515-547` (`stream`)
- Modify: `packages/kernel/src/e_agent/kernel/evidence.py:34-` (`build_evidence`)
- Regenerate: `ui/packages/client/openapi.json`, `ui/packages/client/src/schema.ts`
- Test: `tests/conformance/test_run_store.py`, `apps/server/tests/test_api.py`

**Interfaces:**
- Produces: `list_events(..., limit: int | None = None)`, `EVENT_PAGE = 500`, `GET /v1/runs/{id}/events?after_sequence=&limit=` (1..1000, default 500).

- [ ] **Step 1: Write the failing conformance test**

Append to `tests/conformance/test_run_store.py`:

```python
async def test_list_events_pages_in_sequence_order(store: Any) -> None:
    await store.create_run(_run(), [(RunEventType.RUN_CREATED, {}, None)])
    await store.update_run(
        _run(rev=2), 1, [(RunEventType.RUN_STATE_CHANGED, {"n": 2}, None), (RunEventType.RUN_STATE_CHANGED, {"n": 3}, None)]
    )
    first = await store.list_events("t1", "run_1", 0, limit=2)
    assert [e.sequence for e in first] == [1, 2]
    rest = await store.list_events("t1", "run_1", first[-1].sequence, limit=2)
    assert [e.sequence for e in rest] == [3]
    assert [e.sequence for e in await store.list_events("t1", "run_1")] == [1, 2, 3]
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest -q tests/conformance/test_run_store.py -k pages_in_sequence`
Expected: FAIL with `TypeError: ... unexpected keyword argument 'limit'`

- [ ] **Step 3: Change the port and both stores**

`sdk/store.py`:

```python
    async def list_events(
        self, tenant_id: str, run_id: str, after_sequence: int = 0, limit: int | None = None
    ) -> list[RunEvent]:
        """Events after `after_sequence` in order; at most `limit` when given (ADR 0018)."""
        ...
```

PostgreSQL:

```python
    async def list_events(
        self, tenant_id: str, run_id: str, after_sequence: int = 0, limit: int | None = None
    ) -> list[RunEvent]:
        sql = (
            "SELECT record FROM run_events WHERE tenant_id = %s AND run_id = %s"
            " AND sequence > %s ORDER BY sequence"
        )
        params: tuple[Any, ...] = (tenant_id, run_id, after_sequence)
        if limit is not None:
            sql += " LIMIT %s"
            params += (limit,)
        rows = await self._records(sql, params)
        return [RunEvent.model_validate(r) for r in rows]
```

Memory:

```python
    async def list_events(
        self, tenant_id: str, run_id: str, after_sequence: int = 0, limit: int | None = None
    ) -> list[RunEvent]:
        events = [e for e in self._events[(tenant_id, run_id)] if e.sequence > after_sequence]
        return events if limit is None else events[:limit]
```

- [ ] **Step 4: Run the conformance test**

Run: `uv run pytest -q tests/conformance/test_run_store.py -k pages_in_sequence`
Expected: PASS (both params when the DSN is set).

- [ ] **Step 5: Page in the API and in evidence export**

`api.py`: add `EVENT_PAGE = 500` next to `APPROVAL_SWEEP_SECONDS`; import `Query` from `fastapi`. Events endpoint:

```python
    @app.get("/v1/runs/{run_id}/events")
    async def events(
        run_id: str,
        after_sequence: int = 0,
        limit: int = Query(default=EVENT_PAGE, ge=1, le=1000),
        s: Session = Depends(session),
    ) -> list[RunEvent]:
        rt = state().runtime
        await rt.store.get_run(s.principal.tenant_id, run_id)
        events: list[RunEvent] = await rt.store.list_events(
            s.principal.tenant_id, run_id, after_sequence, limit=limit
        )
        return events
```

SSE loop: replace the single `batch = await rt.store.list_events(...)` and its `for` with a paging loop that keeps `batch` meaning "anything delivered this tick":

```python
            batch: list[RunEvent] = []
            while True:
                page = await rt.store.list_events(
                    s.principal.tenant_id, run_id, cursor, limit=EVENT_PAGE
                )
                for event in page:
                    cursor = event.sequence
                    yield ServerSentEvent(
                        data=event.model_dump(mode="json"), event="run_event", id=str(event.sequence)
                    )
                batch.extend(page)
                if len(page) < EVENT_PAGE:
                    break
```

`evidence.py`: add a helper and use it in `build_evidence` instead of `store.list_events(tenant_id, run_id)`:

```python
EVIDENCE_PAGE = 1000


async def _all_events(store: RunStore, tenant_id: str, run_id: str) -> list[RunEvent]:
    events: list[RunEvent] = []
    cursor = 0
    while True:
        page = await store.list_events(tenant_id, run_id, cursor, limit=EVIDENCE_PAGE)
        events.extend(page)
        if len(page) < EVIDENCE_PAGE:
            return events
        cursor = page[-1].sequence
```

(Import `RunEvent` from `e_agent.contracts.events`.)

- [ ] **Step 6: Write the failing API paging test**

Append to `apps/server/tests/test_api.py`:

```python
def test_events_endpoint_pages_and_caps_the_limit(client: TestClient) -> None:
    h = _login(client)
    r = client.post(
        "/v1/runs", json={"task": "restock widget-a"}, headers={**h, "Idempotency-Key": "page-key-0001"}
    )
    run_id = r.json()["run_id"]
    _wait(client, run_id, {"WAITING_APPROVAL"})
    first = client.get(f"/v1/runs/{run_id}/events", params={"limit": 2}).json()
    assert [e["sequence"] for e in first] == [1, 2]
    rest = client.get(f"/v1/runs/{run_id}/events", params={"after_sequence": 2, "limit": 1000}).json()
    assert rest and rest[0]["sequence"] == 3
    assert client.get(f"/v1/runs/{run_id}/events", params={"limit": 5000}).status_code == 422
```

Run: `uv run pytest -q apps/server/tests/test_api.py -k pages_and_caps` → Expected: PASS (after Step 5; if it fails on `422`, the `Query` bounds are missing).

- [ ] **Step 7: Pin SSE resume across a page boundary**

Append to `apps/server/tests/test_api.py`:

```python
def test_stream_delivers_every_event_across_page_boundaries(client: TestClient, monkeypatch: Any) -> None:
    import e_agent.server.api as api_module

    monkeypatch.setattr(api_module, "EVENT_PAGE", 2)
    h = _login(client)
    r = client.post(
        "/v1/runs", json={"task": "restock widget-a"}, headers={**h, "Idempotency-Key": "sse-page-0001"}
    )
    run_id = r.json()["run_id"]
    _wait(client, run_id, {"WAITING_APPROVAL"})
    expected = [e["sequence"] for e in client.get(f"/v1/runs/{run_id}/events").json()]
    assert len(expected) > 2
    seen: list[int] = []
    with client.stream("GET", f"/v1/runs/{run_id}/stream", headers=h) as resp:
        for line in resp.iter_lines():
            if line.startswith("id: "):
                seen.append(int(line[4:]))
                if len(seen) == len(expected):
                    break
    assert seen == expected
```

Run: `uv run pytest -q apps/server/tests/test_api.py -k page_boundaries`
Expected: PASS. If the existing stream tests in this file use a different reading helper, reuse it instead of `iter_lines`.

- [ ] **Step 8: Regenerate types, run the gate, commit**

Run: `uv run python scripts/export_openapi.py && (cd ui && pnpm gen) && uv run pytest -q packages apps tests && uv run python scripts/export_openapi.py --check && uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run lint-imports`
Expected: PASS

```bash
git add packages/plugin-sdk/src/e_agent/sdk/store.py packages/adapter-postgres/src/e_agent/adapters/postgres/store.py packages/kernel/src/e_agent/kernel/memory_store.py packages/kernel/src/e_agent/kernel/evidence.py apps/server/src/e_agent/server/api.py apps/server/tests/test_api.py tests/conformance/test_run_store.py ui/packages/client/openapi.json ui/packages/client/src/schema.ts
git commit -m "feat(api): page run events for snapshots, SSE and evidence export (ADR 0018)"
```

---

### Task 8: Connection-level write admission rule (D7, ADR 0020, C3 part 1)

**Files:**
- Modify: `packages/plugin-sdk/src/e_agent/sdk/store.py` (`ConnectionBusy`)
- Modify: `packages/adapter-postgres/src/e_agent/adapters/postgres/store.py:304-326` (`reserve_operation`)
- Modify: `packages/kernel/src/e_agent/kernel/memory_store.py:211-223` (`reserve_operation`)
- Modify: `packages/kernel/src/e_agent/kernel/coordinator.py:1081-1097` (`_dispatch` reservation)
- Test: `tests/conformance/test_run_store.py`, `packages/kernel/tests/test_lifecycle.py`

**Interfaces:**
- Consumes: `ReasonCode.CONNECTION_BUSY` (Task 5).
- Produces: `ConnectionBusy(ConcurrencyConflict)` raised by `reserve_operation`.

- [ ] **Step 1: Write the failing conformance test**

Extend the `_action` helper in `tests/conformance/test_run_store.py` with a keyword `op: str = "op_1"` used for `logical_operation_id` (keep the connection id the helper already uses). Then append:

```python
from e_agent.sdk.store import ConnectionBusy


async def test_reservation_is_refused_while_the_connection_has_an_unresolved_write(store: Any) -> None:
    await store.create_run(_run("run_1"), [(RunEventType.RUN_CREATED, {}, None)])
    await store.create_run(_run("run_2"), [(RunEventType.RUN_CREATED, {}, None)])
    in_flight = _action("act_1", rev=1, state=ActionState.DISPATCHING, run_id="run_1", op="op_1")
    await store.put_action(in_flight, None, [])
    proposed = _action("act_2", rev=1, state=ActionState.PROPOSED, run_id="run_2", op="op_2")
    await store.put_action(proposed, None, [])
    reserved = proposed.model_copy(update={"state": ActionState.RESERVED, "revision": 2})
    with pytest.raises(ConnectionBusy):
        await store.reserve_operation(reserved, 1, [])
    # The earlier write resolves; the reservation now succeeds.
    committed = in_flight.model_copy(update={"state": ActionState.COMMITTED, "revision": 2})
    await store.put_action(committed, 1, [])
    assert (await store.reserve_operation(reserved, 1, [])).state is ActionState.RESERVED
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest -q tests/conformance/test_run_store.py -k unresolved_write`
Expected: FAIL with `ImportError: cannot import name 'ConnectionBusy'`

- [ ] **Step 3: Add the exception and the check to both stores**

`sdk/store.py`, after `DuplicateOperation`:

```python
class ConnectionBusy(ConcurrencyConflict):
    """Another action on this connection is DISPATCHING or UNKNOWN (ADR 0020)."""
```

PostgreSQL `reserve_operation`, after `await self._fence(conn)` and before `_cas_action`:

```python
            await conn.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                (f"e-agent-admit:{action.tenant_id}:{action.connection_id}",),
            )
            cur = await conn.execute(
                "SELECT action_id FROM actions WHERE tenant_id = %s AND connection_id = %s"
                " AND state IN ('DISPATCHING', 'UNKNOWN') AND action_id <> %s LIMIT 1",
                (action.tenant_id, action.connection_id, action.action_id),
            )
            if await cur.fetchone() is not None:
                raise ConnectionBusy(action.connection_id)
```

Memory `reserve_operation`, after `self._fence()`:

```python
            busy = any(
                a.connection_id == action.connection_id
                and a.state in {ActionState.DISPATCHING, ActionState.UNKNOWN}
                and a.action_id != action.action_id
                for (t, _), a in self._actions.items()
                if t == action.tenant_id
            )
            if busy:
                raise ConnectionBusy(action.connection_id)
```

(Import `ActionState` in `memory_store.py` if it is not already imported, and `ConnectionBusy` in both stores.)

- [ ] **Step 4: Run the conformance test**

Run: `uv run pytest -q tests/conformance/test_run_store.py -k unresolved_write`
Expected: PASS on memory; PASS on postgres when the DSN is set.

- [ ] **Step 5: Write the failing kernel test**

Append to `packages/kernel/tests/test_lifecycle.py`:

```python
async def test_second_write_on_a_busy_connection_is_refused_with_a_typed_reason(
    make_kernel: MakeKernel,
) -> None:
    k = make_kernel()
    first = await _start(k)
    # Simulate a write whose outcome is unknown: the earlier run's action is stuck in UNKNOWN.
    pres = await k.coordinator.pending_approval(TENANT, first.run_id)
    stuck = await k.store.get_action(TENANT, pres.action_id)
    await k.store.put_action(
        stuck.model_copy(update={"state": ActionState.UNKNOWN, "revision": stuck.revision + 1}),
        stuck.revision,
        [],
    )
    second = await _start(k, "write another note")
    run = await _approve(k, second.run_id)
    assert run.state is RunState.FAILED
    assert run.reason_code is ReasonCode.CONNECTION_BUSY
    assert k.backend.create_calls == 0, "nothing was dispatched behind the unresolved write"
    actions = await k.store.list_actions(TENANT, second.run_id)
    assert actions[-1].state is ActionState.BLOCKED
```

`ALLOWED_ACTION_TRANSITIONS` does not allow `AWAITING_APPROVAL -> UNKNOWN`; `put_action` performs no transition check, so the test can set up the stuck row directly. If `put_action` in either store rejects it, set the state through two allowed hops instead (`BLOCKED` is not what we need) and note it in the test.

- [ ] **Step 6: Run it to verify it fails, then handle `ConnectionBusy` in `_dispatch`**

Run: `uv run pytest -q packages/kernel/tests/test_lifecycle.py -k busy_connection`
Expected: FAIL — `ConnectionBusy` propagates as `ConcurrencyConflict` (the test errors instead of asserting).

In `coordinator.py` `_dispatch`, extend the reservation `try` (line 1081):

```python
        except ConnectionBusy:
            await self._transition(action, ActionState.BLOCKED)
            cont.pending_action_id = None
            return await self._set_run_state(
                run,
                RunState.FAILED,
                "connection has an unresolved write; reconcile it first",
                code=ReasonCode.CONNECTION_BUSY,
            )
        except DuplicateOperation:
```

(`ConnectionBusy` must be caught **before** any `ConcurrencyConflict` handler and is imported from `e_agent.sdk.store` next to `DuplicateOperation`.)

Run again → Expected: PASS.

- [ ] **Step 7: Full suites on both stores, lint, commit**

Run: `uv run pytest -q packages apps tests && uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run lint-imports`
Expected: PASS. With PostgreSQL: `E_AGENT_TEST_STORE=postgres E_AGENT_TEST_PG_DSN=$E_AGENT_TEST_PG_DSN uv run pytest -q packages/kernel tests/conformance` → PASS.

```bash
git add packages/plugin-sdk/src/e_agent/sdk/store.py packages/adapter-postgres/src/e_agent/adapters/postgres/store.py packages/kernel/src/e_agent/kernel/memory_store.py packages/kernel/src/e_agent/kernel/coordinator.py packages/kernel/tests/test_lifecycle.py tests/conformance/test_run_store.py
git commit -m "feat(ledger): refuse a reservation while the connection has an unresolved write (ADR 0020, C3)"
```

---

### Task 9: Update the design documents to match the code (D8)

**Files:**
- Modify: `docs/target-architecture.md` (header, §5.1, §5.5, §11.2, §12.2, §12.4, §13.2, matrix rows U3/Q1/Q3/Q4/Q5, §17, §18)
- Modify: `docs/adr/README.md` (statuses only if the owner accepted the ADRs; otherwise leave Proposed)
- Modify: `docs/README.md` (plan row already present; confirm)

- [ ] **Step 1: Flip the status tags that WP1 closed**

In `docs/target-architecture.md` make exactly these edits:

- Header: append to the **Verified against** sentence: `WP1 (this plan) re-verified against the commit that merged Task 8.` with the short SHA.
- §5.1 principle 1: replace `The run table is proposed (C6); `_set_run_state` does not check transitions today.` with `` The run table exists (`contracts/run.py: ALLOWED_RUN_TRANSITIONS`) and `_set_run_state` enforces it [I] (ADR 0018). ``
- §5.5 "Actor attribution" row: Status `[Pa]` → `[I] actor / [P] correlation id (WP2)`; rewrite the Today cell to describe the context variable.
- §5.5 "Failure classification" row: Status `[Pa]` → `[I] (ReasonCode, ADR 0018)`.
- §11.2 rule 6: replace `Add an **expiry sweeper [P]**` with `An **expiry sweeper [I]** (fenced `expire` work, ADR 0019)`; keep the inbox and per-task TTL as `[P]`.
- §12.2 "Connection-level write admission" row: `[P] (safety)` → `[I] (ADR 0020; lease still [P])`.
- §12.4 "Snapshot or export of a long run" row: Status → `[I] paged (EVENT_PAGE 500, ceiling 1000)`.
- §13.2 "Today" paragraph: add `Self-approval is refused unless `operator.allow_self_approval` is set (ADR 0019) [I].`
- Matrix: U3 status `[Pa] (no run table)` → `[Pa] (run table [I]; reconstructability [P])`; Q4 status → `[Pa] (actor [I]; DB grants, access log [P])`; Q5 status → `[Pa] (reason codes [I]; rationale and projection [P])`.
- §17: C6, C13, C16, C17, C18 rows: append `— WP1 part merged` to the Decision cell; C3: append `— admission rule merged, lease pending`.
- §18 P0 row: replace `C3 writer admission rule + lease; C6 run transition table;` with `C3 admission rule ✔, lease; C6 ✔;`.

- [ ] **Step 2: Re-run the document checks used during the reviews**

Run: `uv run python - <<'EOF'
import re,pathlib
t=pathlib.Path("docs/target-architecture.md").read_text().split("\n")
i=0;bad=[]
while i<len(t):
    if t[i].startswith("|") and i+1<len(t) and re.match(r"^\|[-: |]+\|$",t[i+1]):
        n=t[i].count("|");j=i+2
        while j<len(t) and t[j].startswith("|"):
            if t[j].count("|")!=n: bad.append(j+1)
            j+=1
        i=j
    else:i+=1
print("table mismatches:",bad or "none")
EOF
grep -nE 'postgres://|postgresql://|password|token=' docs/target-architecture.md; echo "safety exit=$?"`
Expected: `table mismatches: none`; `safety exit=1`.

- [ ] **Step 3: Run the complete CI gate once**

Run: `uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run lint-imports && uv run python scripts/export_openapi.py --check && uv run pytest -q && (cd ui && pnpm gen:check)`
Expected: all exit 0.

- [ ] **Step 4: Commit**

```bash
git add docs/target-architecture.md docs/adr/README.md docs/README.md
git commit -m "docs(design): mark WP1 mechanisms implemented; keep lease, inbox, grants proposed"
```

---

### Task 10: LiteLLM as an explicit second model provider (owner amendment, ADR 0021)

Executed **after Task 8 and before Task 9**, so Task 9's documentation pass and final gate cover it.

**Files:**
- Modify: `packages/adapter-agent-pydantic/src/e_agent/adapters/pydantic_ai/driver.py` (`litellm_model` next to `ollama_model`)
- Modify: `packages/adapter-agent-pydantic/src/e_agent/adapters/pydantic_ai/__init__.py` (export)
- Modify: `apps/server/src/e_agent/server/profile.py` (`DriverConfig`)
- Modify: `apps/server/src/e_agent/server/bootstrap.py` (`build_driver`, runtime metadata)
- Modify: `README.md` (how to run with LiteLLM; Ollama remains the default)
- Test: `packages/adapter-agent-pydantic/tests/test_driver_unit.py`, the server test file that already covers `build_driver`/bootstrap (find it; otherwise `apps/server/tests/test_walking_skeleton.py`)

**Interfaces:**
- Produces: `litellm_model(model_name: str, base_url: str, api_key: str | None = None) -> Model`; `DriverConfig.provider: Literal["ollama", "litellm"] = "ollama"`; `DriverConfig.base_url_env: str | None = None`; `DriverConfig.api_key_env: str | None = None`; runtime metadata key `model_provider`.
- No new dependency: `LiteLLMProvider` ships in `pydantic-ai-slim[openai]` 2.54 (`pydantic_ai.providers.litellm`), used with `pydantic_ai.models.openai.OpenAIChatModel`.

- [ ] **Step 1: Write the failing adapter unit tests**

Append to `packages/adapter-agent-pydantic/tests/test_driver_unit.py` tests that pin:
- `litellm_model("ollama/qwen3", "http://localhost:4000")` and `litellm_model("m", "https://127.0.0.1:4000/v1")` return a model whose provider name is `"litellm"` and whose base URL is the given endpoint;
- `ValueError` for `http://10.0.0.5:4000`, `https://proxy.example.com`, `http://user:pw@localhost:4000`, `http://localhost:4000/?x=1`, `ftp://localhost:4000`, and an empty model name;
- an `api_key` argument reaches the provider client (`model.client.api_key` or the provider's client) and is never part of the `ValueError` text;
- `ollama_model` behaviour is unchanged (existing tests still pass).

Run: `uv run pytest -q packages/adapter-agent-pydantic -k litellm` → Expected: FAIL with `ImportError: cannot import name 'litellm_model'`.

- [ ] **Step 2: Implement `litellm_model`**

```python
_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


def litellm_model(model_name: str, base_url: str, api_key: str | None = None) -> Model:
    """LiteLLM proxy on loopback only (ADR 0021); upstream routing is the proxy's configuration."""
    endpoint = urlsplit(base_url)
    if (
        endpoint.hostname not in _LOOPBACK_HOSTS
        or endpoint.scheme not in {"http", "https"}
        or endpoint.username
        or endpoint.query
        or endpoint.fragment
        or not model_name
    ):
        raise ValueError("LiteLLM inference requires a loopback proxy endpoint and a model name")
    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic_ai.providers.litellm import LiteLLMProvider

    return OpenAIChatModel(model_name, provider=LiteLLMProvider(api_base=base_url, api_key=api_key))
```

Reuse `_LOOPBACK_HOSTS` in `ollama_model` instead of its inline set (no behaviour change). If `LiteLLMProvider(api_key=None)` raises because the OpenAI client demands a key, pass a fixed non-secret placeholder (`"not-required"`) when `api_key is None` and pin that in a test. Export `litellm_model` from `__init__.py` (`__all__` too).

Run: `uv run pytest -q packages/adapter-agent-pydantic` → Expected: PASS.

- [ ] **Step 3: Write the failing bootstrap tests**

In the server test file that covers bootstrap, add tests that pin (use `monkeypatch.setenv`, never a real proxy; building the model makes no network call):
- a profile whose driver is `{"kind": "pydantic-ai", "provider": "litellm", "model": "ollama/qwen3"}` builds a `PydanticAiDriver` and the runtime metadata reports `model_provider == "litellm"` and `model == "ollama/qwen3"`;
- `E_AGENT_LITELLM_URL=https://proxy.example.com` → startup rejected with `ErrorCode.STARTUP_REJECTED`;
- `api_key_env: "E_AGENT_TEST_LITELLM_KEY"` with the variable unset → `STARTUP_REJECTED`, and the message names the variable but never a value; with it set to `sk-test-123`, the driver builds and `sk-test-123` appears in no error text or metadata;
- a pydantic-ai profile with no `provider` still builds an Ollama model (default unchanged) and reports `model_provider == "ollama"`;
- a pydantic-ai profile with no `model` is rejected for either provider.

Run them → Expected: FAIL (`provider` literal rejects `"litellm"`).

- [ ] **Step 4: Widen `DriverConfig` and route in `build_driver`**

`profile.py`:

```python
    provider: Literal["ollama", "litellm"] = "ollama"
    """Ollama is the default; LiteLLM is explicit opt-in (ADR 0021). Never a fallback."""
    model: str | None = None
    base_url_env: str | None = None
    """Env var holding the endpoint; defaults to E_AGENT_OLLAMA_URL or E_AGENT_LITELLM_URL."""
    api_key_env: str | None = None
    """LiteLLM only: env var holding the proxy key. The key itself is never in the profile."""
```

`bootstrap.py`:

```python
MODEL_ENDPOINTS: dict[str, tuple[str, str]] = {
    "ollama": ("E_AGENT_OLLAMA_URL", "http://localhost:11434/v1"),
    "litellm": ("E_AGENT_LITELLM_URL", "http://localhost:4000"),
}


def build_driver(profile: Profile, registry: PluginRegistry) -> AgentDriver:
    cfg = profile.driver
    if not cfg.model:
        raise KernelError(ErrorCode.STARTUP_REJECTED, f"pydantic-ai driver needs a {cfg.provider} model")
    env_name, default_url = MODEL_ENDPOINTS[cfg.provider]
    base_url = os.environ.get(cfg.base_url_env or env_name, default_url)
    try:
        if cfg.provider == "litellm":
            api_key = None
            if cfg.api_key_env is not None:
                api_key = os.environ.get(cfg.api_key_env)
                if not api_key:
                    raise KernelError(
                        ErrorCode.STARTUP_REJECTED, f"{cfg.api_key_env} is not set for the LiteLLM proxy"
                    )
            model = litellm_model(cfg.model, base_url, api_key)
        else:
            model = ollama_model(cfg.model, base_url)
    except ValueError as exc:
        raise KernelError(ErrorCode.STARTUP_REJECTED, str(exc)) from exc
    ...  # settings and PydanticAiDriver(...) as today, with `model`
```

If an existing test asserts that a non-loopback Ollama URL raises `ValueError` from bootstrap, update it to `STARTUP_REJECTED` and say so in the report. In the runtime metadata dict add `"model_provider": profile.driver.provider if profile.driver.kind == "pydantic-ai" else None,` after `"model"`.

Run the Step 3 tests → Expected: PASS.

- [ ] **Step 5: README**

In the model/driver section, keep Ollama as the documented default and add a short "LiteLLM (optional)" block: profile snippet `{"kind": "pydantic-ai", "provider": "litellm", "model": "<proxy model name>", "api_key_env": "E_AGENT_LITELLM_KEY"}`, `E_AGENT_LITELLM_URL` (default `http://localhost:4000`, loopback only), no fallback, and that qualification evidence is per provider and model (ADR 0021). Do not claim any LiteLLM model is qualified.

- [ ] **Step 6: Full gate, e2e, commit**

Run the full CI gate, the PostgreSQL run and `make e2e` (owner amendment). Expected: PASS.

```bash
git add packages/adapter-agent-pydantic apps/server/src/e_agent/server/profile.py apps/server/src/e_agent/server/bootstrap.py apps/server/tests README.md
git commit -m "feat(driver): LiteLLM as an explicit opt-in model provider; Ollama stays default (ADR 0021)"
```

---

## Self-review (done while writing)

**Spec coverage.** §5.1(1) → Task 2; §5.5 actor + classification → Tasks 4, 5; §5.6 `ReasonCode` → Task 5; §11.2 rule 6 sweeper → Task 6; §12.2 admission rule → Task 8; §12.4 paging → Task 7; §13.2 rule 2 → Task 3; design doc truthfulness → Task 9. Not in WP1 by decision: correlation id (ADR 0018 Consequences names the `run_work` payload-comparison trap), writer lease, slots, LISTEN, kernel split, rationale contract, DB grants — all listed under WP2–WP5 with entry criteria.

**Type consistency.** `ReasonCode` is defined in Task 5 and consumed in Tasks 6 and 8 (`APPROVAL_EXPIRED`, `CONNECTION_BUSY`); `_check_run_transition` defined in Task 2 and called from the Task 5 `_set_run_state` body; `actor_scope`/`current_actor` defined in Task 4 and reused by Task 6's worker branch; `EVENT_PAGE` defined in Task 7 and monkeypatched in its own test; `ConnectionBusy` defined and consumed in Task 8.

**Review Focus pinned.** (1) Task 4 step 6 and Task 5 step 8; (2) Task 6 step 8; (3) Task 8 steps 1 and 5; (4) Task 3 step 7; (5) Task 7 step 7.

**Ordering.** Task 2 before Task 5 (the new `_set_run_state` body calls `_check_run_transition`); Task 5 before Tasks 6 and 8 (reason codes); Task 4 before Task 6 (actor label on the `expire` branch). Tasks 3 and 7 are independent of the others after Task 1.
