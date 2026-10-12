# Scalability and runtime architecture review

Date: 2026-10-11. Reviewed candidate: uncommitted working tree based on `ceae677`. This is a source/design review against current agentic-architecture practice for scale, high concurrency, plugin-driven extension, package reuse and event-driven integration. No product code was changed, no load was generated and no throughput numbers are claimed. Accepted designs and ADRs are not edited; baseline changes are listed as ADR candidates (§6).

## Verdict

**Keep the architecture; fix the runtime concurrency model inside it.** The package/plugin structure is already what 2026 practice recommends: a thin agent library behind a port, a host-owned business ledger, Postgres as the transactional event log, separately releasable adapters and import-linter boundaries. None of that needs replacement, and no service split, broker or workflow engine is justified yet.

The limits to scale are in the runtime, not the structure. Today one process executes one run at a time; SSE polls the database instead of using the designed `LISTEN` wake-up; the serialized-writer lock pins a pool connection for the full ERP call; and some live-run state is process-local. These are bounded fixes (§4 P0–P1).

**Do not replace FastAPI with Litestar** (§5). The HTTP framework is not on the critical path, and FastAPI is already confined to one module.

## 1. What already matches modern practice

| Practice (2026) | e-agent status | Evidence |
|---|---|---|
| Thin, typed agent loop; framework behind a port | Pydantic AI behind `AgentDriver`; effectful tools deferred to kernel | ADR 0004, `adapters/pydantic_ai/driver.py` |
| Separate agent loop from durability substrate | Kernel ledger owns retry/resume; framework durability explicitly not used | ADR 0003 |
| Plugin metadata discovery before import, admission, scoped injection | Entry points + static manifest, admitted factories | `sdk/discovery.py`, `kernel/registry.py`, MVP §6 |
| Reusable, independently released packages | Per-adapter distributions, PEP 420 namespace, uv workspace | `pyproject.toml` workspace, HLD §4 |
| Enforced dependency direction | import-linter layers/forbidden/independence contracts; core cannot import `fastapi`, `httpx`, `psycopg`, `pydantic_ai` | root `pyproject.toml` |
| Event log as source of truth; outbox only when there is a consumer | `run_events` with per-run sequence; outbox deferred | MVP §9, ADR 0007 |
| Work queue on Postgres with leases and fencing | `run_work` + `FOR UPDATE SKIP LOCKED`, fence checks | `store.py:546`, ADR 0014 |
| Approval/UNKNOWN as business semantics, not engine replay | Explicit action state machine, no blind replay | MVP §7, §9 |

The market research in `research/Agent Frameworks … September 2026.md` (§4.3–4.4) concludes that topology, not framework, dominates cost, and that durability should be delegated or owned explicitly. e-agent made the explicit-ownership choice deliberately (ADR 0003). That remains sound for write actions whose correctness depends on approval digests and reconciliation.

## 2. Findings

### SR-01 — P0: one run at a time per process

Evidence: `apps/server/src/e_agent/server/api.py:205-216`. The single `worker()` task (started once at line 371) claims one item and `await`s `_run_work(claim)` to completion before claiming the next. A run spends most of its wall time waiting on model calls (seconds each, up to 12 turns) and ERP I/O, so queued runs wait behind the active run even though the event loop is idle.

Impact: throughput is bounded to one active run per server process regardless of CPU, pool size or framework. This is the dominant scalability limit.

Fix: run up to `N` claims concurrently per process, bounded by an `asyncio.Semaphore` / task group. Expose `N` as a profile setting. Keep the per-claim heartbeat and fencing unchanged. Size `N` against model-provider rate limits and the PG pool (SR-03), not CPU. Add a per-tenant cap in the claim query so one tenant cannot occupy all slots. With the ADR 0001 local Ollama model, the effective `N` is also capped by Ollama's parallel-request setting.

Before enabling `N > 1`, audit shared singletons for concurrent-run safety. Partial check done for this review: the Pydantic AI driver keys `_RunState` by `run_id` (`driver.py:251`), and `PostgresRunStore._work_claim` is a `ContextVar`, which is safe only if each claim runs in its own task. Still to check: the Odoo executor/client, `PublicTextBus` and coordinator caches.

### SR-02 — P0: SSE polls the database; the designed LISTEN consumer is missing

Evidence: `store.py:101` publishes `pg_notify` on every event append, but no `LISTEN` consumer exists anywhere in `apps/` or `packages/`. The stream handler (`api.py:530-547`) runs `list_events` plus `get_run` every 200 ms per open connection. ADR 0003 states that `LISTEN/NOTIFY` wakes stream handlers, so this is an implementation gap, not a design flaw.

Impact: database load grows linearly with open streams (about 10 loop iterations per second per viewer, two queries each) even when runs are idle. A burst of viewers competes with workers for the 8-connection pool.

Fix: one dedicated `LISTEN` connection per process feeding an in-process fan-out (per `(tenant, run)` `asyncio.Event`/queue). Handlers re-read `run_events` only when woken, with a slow poll (for example 5–15 s) as a safety net for missed notifications. Keep the NOTIFY payload as an ID only (8000-byte limit; notifications are not durable). LISTEN/NOTIFY uses a global queue lock under heavy write load. That is acceptable at this scale, but measure it (§7).

### SR-03 — P0: the serialized-writer lock pins a pool connection across the ERP call

Evidence: `coordinator.py:1114` wraps `executor.execute(...)` in `store.writer_lock(...)`. `store.py:496-508` takes a session-level `pg_advisory_lock` on a pooled connection and holds it until the Odoo call returns or times out (`provider_timeout_seconds`). The pool maximum is 8 (`store.py:45`).

Impact:
- Each in-flight write consumes one of the 8 connections for the full provider latency. With SR-01 fixed, concurrent writes to different connections can starve the pool and stall reads, event appends and heartbeats.
- If the database session drops mid-call, PostgreSQL releases the advisory lock while the Odoo request may still be in flight. A second worker can then acquire the lock and dispatch a *different* logical operation on the same sandbox connection. MVP §9 makes "one serialized writer per sandbox connection" the uniqueness backstop when the provider has no atomic idempotency, so a lost lock weakens that guarantee. Same-logical-operation duplicates are still prevented by `operation_reservations`.

No lock or lease can fully close this race: a lease can also expire while the Odoo call is still running, and MVP §9 states that fencing does not cancel an accepted network call. What restores the serialized-writer backstop is an **admission rule**. The current admission path (`coordinator.py:1041-1100`: staleness, expiry, `reserve_operation`) does not have it today.

Fix (ADR candidate C3), in priority order:
1. **Connection-level admission rule (safety).** Inside the reservation transaction, refuse to reserve a write on `(tenant_id, connection_id)` while any action on that connection is `DISPATCHING` or `UNKNOWN`. The blocked action waits or is surfaced for reconciliation. This holds even if a lock or lease is lost mid-call.
2. **Durable writer lease (pool fix).** Replace the session advisory lock with a lease row, `(tenant_id, connection_id) → owner, fence, expires_at`. Acquire it in a short transaction, renew it with the claim heartbeat, and release it after the receipt is persisted. This frees the pool connection during I/O. The lease TTL must exceed `provider_timeout_seconds` plus a margin, so that normal slow calls do not expire it.
3. **Pool sizing per role.** Worker: `N` + heartbeat + LISTEN. API: its own pool.

### SR-04 — P1: live-run state that is process-local

Evidence and assessment:
- `Coordinator._runs` (`coordinator.py:132`) is a cache. `_load_cont` reloads from `store.load_continuation` (lines 263-276), so another process can resume a run. **Not a blocker.**
- `Coordinator._active_calls` (line 133) holds the in-flight model/provider task used for cancellation. A cancel request handled by a different process than the one executing the run cannot interrupt the in-flight call.
- `PublicTextBus` (`api.py:139`) is intentionally memory-only (ADR 0014: token fragments never reach the ledger). In a multi-process deployment, text deltas are visible only to SSE clients connected to the executing process. Do not persist them; fan them out instead.
- `ApiState.sessions` is local-demo auth only (MVP §12). Production authentication is Phase 2 and not a finding here.

Fix: (a) persist cancel intent as it is today, and have the executing worker observe it, either through the heartbeat (it already renews every 5 s) or through a `LISTEN` wake. The worker then cancels its local task. Dispatch stays `cancellable=False`: a cancel interrupts model calls only, never an in-flight write. (b) For text deltas across processes: in combined mode (API with embedded worker) keep the in-process bus. In split mode (SR-05), API processes cannot reach a worker's memory, so sticky load-balancer routing does not help. The worker publishes coalesced deltas on a dedicated NOTIFY channel (100–250 ms batches, ≤ 8 KB, transient, best-effort, matching the transient `text.delta` contract); `message.final` stays durable and snapshot/reset frames cover gaps. Never send per-token NOTIFY: it multiplies notification volume and contends on the global queue lock noted in SR-02. Measure NOTIFY volume in the load harness. Introduce a broker only when a named consumer needs durability or throughput that NOTIFY cannot provide.

### SR-05 — P1: worker embedded in the API process

Evidence: the lifespan starts the worker inside `serve` (`api.py:367-381`); `cli.py` has no worker command. HLD §4 anticipates "a separate worker process … using the same application distribution".

Fix: add `e-agent worker` (same bootstrap and profile, no HTTP) and a `serve --no-worker` flag. API replicas then scale with viewers and workers scale with runs. Both already coordinate only through Postgres, so no new protocol is needed once SR-02 and SR-04 are in place.

### SR-06 — P2: `coordinator.py` concentrates too many responsibilities

Evidence: 1509 lines; the next-largest kernel module is 242. It holds run lifecycle, driver stepping, read gateway, validation, approval, dispatch, receipt application, verification, cancellation and recovery.

Fix: split along existing port boundaries without changing behavior: `RunLoop` (driver stepping/budgets), `ActionGateway` (read/write admission), `DispatchService` (reserve → dispatch → receipt, owns the writer lease), `VerificationService` and `RecoveryService`. Keep the public `Coordinator` facade so the API and CLI do not change. It is not a prerequisite for SR-01 (P0 uses the singleton audit instead), but it lowers the risk of later concurrency changes and any durable-engine option (§3). Do it as refactor-only commits gated by the existing recovery/approval test matrix.

### SR-07 — P2: no load or concurrency evidence

There is no load harness, so any scaling claim would be invented. See §7.

## 3. Event-driven and durable-execution options

**Event-driven.** `run_events` already is the transactional event log, with per-run sequences, schema versions and quarantine of unknown types. Add a transactional outbox (same-transaction insert plus an idempotent relay) only when a concrete external consumer exists, for example a SIEM export, an analytics sink or a second service. Do not add Kafka, NATS or Redis Streams speculatively (AGENTS.md: no unused abstractions). When a consumer appears, choose the transport by delivery need:

| Need | Candidate |
|---|---|
| Intra-cluster wake-ups, IDs only | PG `LISTEN/NOTIFY` (current) |
| Durable fan-out to a few internal consumers | Outbox table + polling relay, or NATS JetStream |
| High-volume external streaming/retention | Outbox → Kafka/Redpanda |

**Durable-execution engines.** ADR 0003 already evaluates them and defers DBOS as the best fit, since it is a Postgres-backed library with no extra service. Its revisit trigger ("hand-written lease and recovery code grows beyond what the recovery test matrix can cover") is not yet met. SR-03's lease work moves toward it, so re-check after P0.

Constraint for any engine spike: DBOS, Restate and Temporal advertise "exactly-once" step or side-effect semantics. That holds only within their journal; it does not make an Odoo `create` idempotent. The repository forbids claiming exactly-once without provider guarantees and requires `UNKNOWN` plus reconciliation. Any engine must therefore (1) wrap the kernel ledger, not replace it, (2) never auto-retry a write step whose result is ambiguous, and (3) keep write admission (approval digest, reservation, writer lease) in the kernel.

**Multi-agent / A2A / MCP.** Not needed for the procurement slice. If MCP tool sources are added, admit them as adapters behind `CapabilityProvider` and the action gateway, never as tools exposed directly to the model (threat model; research §4.4 item 8).

## 4. Plan

| Phase | Work | Exit evidence |
|---|---|---|
| **P0** | SR-01 singleton audit, then bounded concurrent claims + per-tenant cap; SR-02 LISTEN-driven SSE with slow fallback poll; SR-03 connection-level admission rule, durable writer lease replacing the session advisory lock, pool sizing per role | Existing suites green; new tests: N runs progress concurrently; no write is reserved on a connection with a `DISPATCHING`/`UNKNOWN` action; writer lease expiry mid-dispatch leads to reconcile-before-next-write; SSE delivers within one wake without polling; fault injection of the PG connection drop during dispatch |
| **P1** | SR-05 `e-agent worker` and `serve --no-worker`; SR-04 cross-process cancel via persisted intent; text-delta fan-out via coalesced NOTIFY in split mode | Two API + two worker processes on one DB: cancel from any API, stream from any API, no duplicate dispatch under kill -9 of a worker |
| **P2** | SR-06 coordinator decomposition (refactor-only); SR-07 load harness and baseline report | Line-count and import contracts for new kernel modules; first measured report (§7) |
| **P3 (conditional)** | DBOS spike behind the existing ports, only if ADR 0003's trigger fires after P0/P1 | Spike report comparing recovery code size and test matrix coverage; ledger authority preserved |

## 5. FastAPI vs Litestar

**Recommendation: keep FastAPI.** Revisit only if profiling after P0 shows HTTP routing or serialization as a significant share of request latency or CPU.

| Factor | Assessment |
|---|---|
| Where time goes | Model calls (seconds) and ERP I/O dominate; SR-01 caps throughput at one run per process. A faster router does not change either. |
| Blast radius | FastAPI appears only in `apps/server/src/e_agent/server/api.py` (33 `@app.`/`Depends` occurrences); import-linter forbids it in contracts, SDK, kernel and domains. This confinement is the valuable property: the HTTP layer stays replaceable without a rewrite. |
| Serialization advantage | Litestar's main published gains come from msgspec. e-agent contracts are Pydantic models shared with the kernel, domains and schema snapshots, so a switch would keep Pydantic and lose most of that gain, or require a contract-layer migration with no product benefit. |
| Features in use | `fastapi.sse.EventSourceResponse`, dependency-injected session/CSRF, lifespan, exception handlers, middleware. Litestar has equivalents, but each needs a port plus re-testing of the SSE resume semantics in ADR 0007. |
| Maintenance signal (PyPI, checked 2026-10-11) | FastAPI 0.143.0 released 2026-10-08; Starlette 1.7.0 released 2026-09-23. Litestar 2.24.0 released 2026-06-11. Comparisons also cite Litestar's smaller maintainer base and ecosystem. |
| Benchmarks | Published 2026 comparisons conflict (claims of up to ~2× on synthetic workloads; one guide notes no fixed ratio holds across hardware and workload) and do not reflect an LLM-bound workload. Not used as evidence here. |

Cheaper wins if HTTP overhead ever matters: run uvicorn with multiple workers or Granian, return `ORJSONResponse` for large evidence payloads, and remove per-stream polling (SR-02).

## 6. ADR candidates (proposed, not baseline)

- **C1:** concurrent run execution per process: bounded slots, per-tenant fairness, settings in the profile. Refines ADR 0003/0014.
- **C2:** stream wake-up implementation, LISTEN consumer, fallback poll interval, and text-delta routing per deployment mode (in-process when combined; coalesced NOTIFY from workers when split). Refines ADR 0007; keeps text deltas transient.
- **C3:** connection-level write admission rule (no new write while `DISPATCHING`/`UNKNOWN` exists on the connection) plus a durable writer lease replacing the session advisory lock. Refines ADR 0003 and MVP §9's serialized-writer mechanism.
- **C4:** separate worker and API process roles. Specializes HLD §4.
- **C5:** HTTP framework stays FastAPI, with the revisit trigger above. Records this decision so it is not reopened without evidence.

## 7. Load and concurrency evidence to collect

Use a deterministic fixture profile (scripted driver, fake ERP with injectable latency), so results measure the runtime and not model quality. Label results as fixture/infrastructure evidence, never live qualification.

Scenarios: K concurrent runs (with model latency simulated at fixed delays); M concurrent SSE viewers per run; writes spread across 1 and several connections; worker kill and PG connection drop during dispatch.

Measure: runs started and completed per minute; queue wait (enqueue to claim); time from event append to SSE delivery; PG pool wait and active connections; DB queries per second attributed to streaming; writer-lease wait; and safety counters (duplicate dispatches, which must be 0; unresolved UNKNOWN; fence rejections). Record hardware, versions and settings with each run. Set targets only after the first baseline.

## 8. Sources

- Repository: HLD §§4, 6, 8, 10; MVP design §§6, 7, 9, 12; ADR 0003, 0004, 0007, 0014; `research/Agent Frameworks, Orchestration Runtimes and Managed Agent Platforms — State of the Market, September 2026.md` §§2, 4.
- Pydantic AI durable execution backends: <https://pydantic.dev/docs/ai/capabilities/durable_execution/overview/>
- DBOS with Pydantic AI: <https://docs.dbos.dev/integrations/pydantic-ai>
- Temporal with Pydantic AI: <https://temporal.io/blog/build-durable-ai-agents-pydantic-ai-and-temporal>
- LISTEN/NOTIFY scaling limits: <https://recall.ai/blog/postgres-listen-notify-does-not-scale>; <https://www.postgresql.org/message-id/6899c044-4a82-49be-8117-e6f669765f7e%40app.fastmail.com>; payload and durability limits: <https://neon.com/guides/pub-sub-listen-notify>
- FastAPI vs Litestar comparisons (conflicting; context only): <https://betterstack.com/community/guides/scaling-python/litestar-vs-fastapi/>; <https://dev.to/locionic/fastapi-vs-litestar-2026-performance-benchmarks-when-to-switch-epf>
- PyPI release metadata for fastapi, litestar, starlette, msgspec, granian (queried 2026-10-11).
