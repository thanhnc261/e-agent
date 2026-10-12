# Real Agent (Part B) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the live Pydantic AI + Ollama agent usable against the real `odoo19-learning` Odoo: a rejected read becomes feedback instead of a crash, the agent can discover records instead of guessing references, follow-ups after small talk complete the real task, and a plain conversational reply waits for the user instead of failing the run.

**Architecture:** Kernel changes stay inside `RunCoordinator`'s read loop and `FinalAnswer` branch; the driver port gains one field (`DriverInput.read_errors`) so the model sees why a read failed. Discovery is a new read capability `procurement.open-demands.read.v1` added through the same layers as `procurement.demand.read.v1` (domain contract, fixture provider, Odoo adapter, bridge addon). The UI only learns the new event type, clears streamed text when a question arrives, and labels a conversational reply. All semantics are recorded in ADR 0022 (Proposed).

**Tech Stack:** Python 3.12, Pydantic v2 records, pydantic-ai 2.54, FastAPI, psycopg 3, Odoo 19 addon (Python), React/TypeScript UI (`ui/`, pnpm, vitest, Playwright).

**Spec:** Owner request 2026-10-12 ("do all 4"), the four gaps reported from the first live run, and [docs/target-architecture.md](../../target-architecture.md) §5–§7 (driver/kernel boundary). Rulings made while writing this plan are listed under "Rulings" and must be honoured by every task.

## Global Constraints

- Branch `feat/real-agent`; commit only your task's files with explicit `git add <paths>`; end every commit message with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- AGENTS.md invariants hold: model output is a proposal; every read goes through the action gateway; never treat an absent fact as an approved fact; never persist hidden chain-of-thought; never commit credentials.
- Never touch the docker containers `odoo-bench` or anything except `odoo19-learning-*` and `e-agent-ledger`. Odoo commands use `docker compose -p odoo19-learning --project-directory /Users/thanhnguyen/dev/study/erp ...` or `docker exec odoo19-learning-odoo-1|odoo19-learning-db-1 ...` only.
- Both `RunStore` implementations change together if a store changes (none is planned).
- Contract or event-type changes regenerate OpenAPI and TS types: `uv run python scripts/export_openapi.py && (cd ui && pnpm gen)`; stage the generated files before `pnpm gen:check`.
- UI changes follow the repository's `ag-ui-implement` skill (`.claude/skills/ag-ui-implement/SKILL.md`): tests first, server-owned state, conformance test per touched criterion.
- End-to-end after every task (owner rule): full gate `uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run lint-imports && uv run python scripts/export_openapi.py --check && uv run pytest -q && (cd ui && pnpm gen:check)`, the Postgres run `E_AGENT_TEST_PG_DSN=<dsn> E_AGENT_TEST_STORE=postgres uv run pytest -q packages/kernel tests/conformance`, and `make e2e` when `apps/server`, OpenAPI or `ui/` changed.
- Docs are English. ADR 0022 is Proposed until the owner accepts it.

## Rulings (binding for all tasks)

1. **Rejected read = feedback, not crash.** A `KnownNoEffectError` from a read executor is recorded as event `read.rejected` (`{"request_id", "contract_id", "connection_id", "code", "message"}` where `message` is the executor's `safe_message`) and returned to the driver through `DriverInput.read_errors: Mapping[str, str]` (request_id → `"<code>: <safe_message>"`). It counts against `max_read_calls` exactly like a successful read, so a model that keeps guessing hits the read budget, not an infinite loop. Any other exception from a read keeps today's behaviour.
2. **Worker exceptions are logged.** `ApiState._run_work`'s `except Exception` path logs `LOG.exception("run work failed", extra=...)` with run id and claim kind before `_mark_failed`; no secrets or payloads in the log line.
3. **Conversational reply.** When the driver returns `FinalAnswer` and the run has made **no reads, no read attempts and no proposals** in its lifetime, the kernel records `input.requested` with payload `{"question": <text>, "kind": "reply"}` and moves the run to `WAITING_INPUT`. Every other `FinalAnswer` keeps today's verification rule (repair, then `FAILED` with `VERIFICATION_FAILED`). Clarifications keep `kind` absent (old rows) or `"clarification"`.
4. **Follow-up context (item 3)** needs no new kernel mechanism: the driver already keeps the conversation as message history and receives the follow-up as `user_input`. Item 3 is delivered by discovery (Task 3), the reply path (Task 4) and the UI fixes (Task 5), and is proven by the live end-to-end in Task 6 ("hi" → reply → "which products are short?" completes without asking for a reference).
5. **Discovery capability** is `procurement.open-demands.read.v1`, tool name `procurement_open_demands_read_v1`, no required arguments, returns open demands with their references and product references so the model can copy exact refs. Guidance tells the model to list open demands first when the user gives no demand reference.

## Review Focus

1. **A model that keeps guessing references** — repeated rejected reads must end in `budget exhausted: read calls`, never a hang or a crash. → Task 2 test `test_repeated_rejected_reads_exhaust_the_read_budget`.
2. **A rejected read inside a run that later succeeds** — the run must reach its normal outcome and the evidence bundle must still classify it by its final reason code. → Task 2 test `test_rejected_read_is_fed_back_and_the_run_continues`.
3. **Small talk after real work** — a `FinalAnswer` after reads must NOT be treated as a reply (it is an unverified business claim). → Task 4 test `test_plain_answer_after_reads_still_requires_verification`.
4. **Old ledger rows** — `input.requested` without `kind` and runs without `read.rejected` events must still render and replay. → Task 4 contract/UI tests.
5. **Open-demand listing scoped to the sandbox** — the bridge method must return only demands of the configured namespace/company, never other companies' records. → Task 3 bridge/adapter test.

---

## Task 1: ADR 0022 (Proposed) and index row

**Files:**
- Create: `docs/adr/0022-conversational-turns-read-feedback-discovery.md`
- Modify: `docs/adr/README.md` (one row after 0021)

- [ ] **Step 1: Write ADR 0022**

```markdown
# ADR 0022: Conversational turns, read feedback and record discovery

Date: 2026-10-12. Status: Proposed. Refines ADRs 0003, 0018; MVP design §7.

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

## Consequences

A conversational reply is not verified and claims nothing; the UI labels it as a reply. A run
can remain `WAITING_INPUT` after a reply until the user answers or stops it. The bridge addon
gains a read method, so `e_agent_bridge` is upgraded in the sandbox and plugin artifact hashes
change. Correlation ids and multi-run conversations remain WP2/WP4.

## Verification

Kernel tests for rejected reads (feedback, budget exhaustion) and for reply versus verified
answer; adapter and bridge tests for the open-demands read; UI tests for the new event type and
reply label; a live end-to-end against `odoo19-learning` from "hi" to a validated proposal.
```

- [ ] **Step 2: Add the index row after the 0021 row in `docs/adr/README.md`**

```markdown
| [0022](0022-conversational-turns-read-feedback-discovery.md) | Rejected reads as feedback, conversational replies, open-demand discovery | Proposed | Real-agent plan Tasks 2–4 |
```

- [ ] **Step 3: Check and commit**

Run: `grep -c "| \[0022\]" docs/adr/README.md` → Expected: `1`.

```bash
git add docs/adr/0022-conversational-turns-read-feedback-discovery.md docs/adr/README.md
git commit -m "docs(adr): propose 0022 conversational turns, read feedback and discovery"
```

---

## Task 2: Rejected reads become driver feedback; worker logs failures

**Files:**
- Modify: `packages/plugin-sdk/src/e_agent/sdk/ports.py` (`DriverInput.read_errors`)
- Modify: `packages/contracts/src/e_agent/contracts/events.py` (`RunEventType.READ_REJECTED = "read.rejected"`)
- Modify: `packages/kernel/src/e_agent/kernel/coordinator.py` (`_drive` read loop, `_Continuation`, `continue_input`)
- Modify: `packages/adapter-agent-pydantic/src/e_agent/adapters/pydantic_ai/driver.py` (`_results_for`)
- Modify: `apps/server/src/e_agent/server/api.py` (`_run_work` `except Exception`)
- Modify: `ui/packages/ui-core/src/store.ts` (`KNOWN_EVENT_TYPES` gains `"read.rejected"`)
- Regenerate: `ui/packages/client/openapi.json`, `ui/packages/client/src/schema.ts`
- Test: `packages/kernel/tests/test_lifecycle.py`, `packages/adapter-agent-pydantic/tests/test_driver_unit.py`, `apps/server/tests/test_api.py`, `ui/packages/ui-core/test/*` (store test file that covers known event types)

**Interfaces:**
- Produces: `DriverInput.read_errors: Mapping[str, str]` (default empty mapping); `RunEventType.READ_REJECTED`; `_Continuation.read_errors: dict[str, str]` (persisted with the continuation); event payload `{"request_id", "contract_id", "connection_id", "code", "message"}`.

- [ ] **Step 1: Failing kernel tests.** In `packages/kernel/tests/conftest.py`, extend `NotesBackend.fail_mode` with `"read-reject"` (raise `KnownNoEffectError("E_AGENT_INVALID_REF", "Odoo rejected the request")` from `read`) and `"read-reject-once"` (raise only on the first read call, then behave normally; track with a counter field `read_calls: int = 0`). Append to `packages/kernel/tests/test_lifecycle.py`:

```python
async def test_rejected_read_is_fed_back_and_the_run_continues(make_kernel: MakeKernel) -> None:
    k = make_kernel()
    k.backend.fail_mode = "read-reject-once"
    seen: list[dict[str, str]] = []
    original = k.driver.advance

    async def spy(ctx, step_input):  # type: ignore[no-untyped-def]
        seen.append(dict(step_input.read_errors))
        return await original(ctx, step_input)

    k.driver.advance = spy  # type: ignore[method-assign]
    run = await _start(k)
    assert run.state is RunState.WAITING_APPROVAL
    assert {"r1": "E_AGENT_INVALID_REF: Odoo rejected the request"} in seen
    rejected = [e for e in await k.store.list_events(TENANT, run.run_id) if e.type is RunEventType.READ_REJECTED]
    assert rejected and rejected[0].payload["code"] == "E_AGENT_INVALID_REF"
    assert "Odoo rejected the request" == rejected[0].payload["message"]


async def test_repeated_rejected_reads_exhaust_the_read_budget(make_kernel: MakeKernel) -> None:
    k = make_kernel(budgets=Budgets(max_read_calls=3))
    k.backend.fail_mode = "read-reject"
    run = await _start(k)
    assert run.state is RunState.FAILED
    assert run.reason_code is ReasonCode.BUDGET_EXHAUSTED
    assert run.reason == "budget exhausted: read calls"
```

`NotesDriver.advance` must keep requesting the read while it has no observation (it already does: `if not step_input.observations: return RequestReads(...)`), so the second test loops until the budget. If `make_kernel` does not expose `k.driver`, add `driver: NotesDriver` to the `Kernel` dataclass and pass it from `_make`.

- [ ] **Step 2: Run them to verify they fail.** `uv run pytest -q packages/kernel/tests/test_lifecycle.py -k "rejected_read"` → FAIL (`AttributeError: ... read_errors` or the run ends `FAILED/interrupted` via an escaped `KnownNoEffectError`).

- [ ] **Step 3: Implement.**
  - `ports.py`: in `DriverInput` add `read_errors: Mapping[str, str] = field(default_factory=dict)` (import `field` from `dataclasses` and `Mapping` from `collections.abc` if absent; keep the dataclass frozen).
  - `events.py`: add `READ_REJECTED = "read.rejected"` after `READ_RECORDED`.
  - `coordinator.py`: add `read_errors: dict[str, str]` (default empty, matching how `_Continuation` declares its other dict fields — dataclass `field(default_factory=dict)` or pydantic `Field(default_factory=dict)`) to `_Continuation` (it is persisted; old snapshots without the key must still load — the default covers it). In the `RequestReads` loop wrap `_gateway_read`:

```python
                    try:
                        obs = await self._gateway_read(cont, request, count_budget=True)
                    except TimeoutError:
                        return await self._exhausted(run, "active time or provider deadline")
                    except KnownNoEffectError as exc:
                        await self._record_rejected_read(cont, request, exc)
                        continue
                    cont.reads[request.request_id] = request
                    cont.observations[request.request_id] = obs
                await self._persist(run.run_id)
                step_input = DriverInput(
                    task=run.task,
                    observations=tuple(cont.observations.values()),
                    read_errors=dict(cont.read_errors),
                )
                continue
```

  and add the helper next to `_gateway_read`:

```python
    async def _record_rejected_read(
        self, cont: _Continuation, request: ReadRequest, exc: KnownNoEffectError
    ) -> None:
        """A provider-rejected read had no effect: count it and tell the driver (ADR 0022)."""
        cont.read_calls += 1
        cont.read_errors[request.request_id] = f"{exc.code}: {exc.safe_message}"
        run = await self._store.get_run(cont.ctx.tenant_id, cont.ctx.run_id)
        await self._store.update_run(
            run.model_copy(update={"revision": run.revision + 1}),
            run.revision,
            [
                (
                    RunEventType.READ_REJECTED,
                    {
                        "request_id": request.request_id,
                        "contract_id": request.contract_id,
                        "connection_id": request.connection_id,
                        "code": exc.code,
                        "message": exc.safe_message,
                    },
                    None,
                )
            ],
        )
```

  `_gateway_read` increments `read_calls` only after success, so the helper increments it for the rejected call. In `continue_input`, pass `read_errors=dict(cont.read_errors)` too.
  - `driver.py` `_results_for`: when a pending read has no observation, use the kernel's reason if present:

```python
            results.calls[call_id] = (
                {"data": dict(obs.data), "evidence_id": obs.evidence.evidence_id}
                if obs is not None
                else {"error": step_input.read_errors.get(call_id, "read was not executed")}
            )
```

  - `api.py` `_run_work`: first line of the `except Exception:` block: `LOG.exception("run work failed (run=%s kind=%s)", claim.run_id, claim.kind)`.
  - `store.ts`: add `"read.rejected"` to `KNOWN_EVENT_TYPES` (it is not a snapshot trigger).

- [ ] **Step 4: Driver unit test.** Append to `packages/adapter-agent-pydantic/tests/test_driver_unit.py` a test that drives the `FunctionModel`-based harness already used in that file: first step requests a read; the second `advance` call passes `DriverInput(task=..., read_errors={<call id>: "E_AGENT_INVALID_REF: Odoo rejected the request"})` and asserts the tool result the model receives contains that error string (inspect the model's received messages the way neighbouring tests do). Run: `uv run pytest -q packages/adapter-agent-pydantic -k read_error` → PASS.

- [ ] **Step 5: Server test for logging.** Append to `apps/server/tests/test_api.py` a test that makes the coordinator's `start_admitted_run` raise `RuntimeError("boom")` (monkeypatch on the runtime's coordinator), starts a run through the API, waits for `FAILED`, and asserts with `caplog` that a record `"run work failed"` at ERROR level with `exc_info` exists. Run it → PASS.

- [ ] **Step 6: UI test.** In the ui-core store test file, assert that an event of type `read.rejected` is accepted (no `needsSnapshot`, `unsupportedEvents` unchanged). Run `cd ui && pnpm --filter ui-core test` (or the package's test command) → PASS.

- [ ] **Step 7: Regenerate, full gate, Postgres, e2e, commit.**

```bash
git add packages/plugin-sdk/src/e_agent/sdk/ports.py packages/contracts/src/e_agent/contracts/events.py packages/kernel/src/e_agent/kernel/coordinator.py packages/kernel/tests/conftest.py packages/kernel/tests/test_lifecycle.py packages/adapter-agent-pydantic/src/e_agent/adapters/pydantic_ai/driver.py packages/adapter-agent-pydantic/tests/test_driver_unit.py apps/server/src/e_agent/server/api.py apps/server/tests/test_api.py ui/packages/ui-core/src/store.ts ui/packages/ui-core/test ui/packages/client/openapi.json ui/packages/client/src/schema.ts
git commit -m "feat(kernel): feed provider-rejected reads back to the driver; log worker failures (ADR 0022)"
```

---

## Task 3: Discovery read `procurement.open-demands.read.v1`

Wiring follows `procurement.demand.read.v1` exactly; list-read templates are `sales.open-orders.read.v1` / `receivables.open-invoices.read.v1` (bridge `limit` + `complete` flag, executor `dec()` and evidence completeness). Rulings for this task:
- "Open demands" = every `e_agent.demand` of `self.env.company`, additionally filtered by the target namespace if `_check_target()` (or the target context) exposes it — check `bridge.py` and use it if present; otherwise company only. `order="id"`, `limit=100`, `complete = len(rows) < 100`.
- Rows carry discovery fields only: `demand_ref`, `product_ref`, `product_name` (display only), `quantity`, `unit`, `requested_date`. No shortage arithmetic in the bridge or adapter (the domain/answer tools own it).
- Bump the bridge addon to `19.0.0.4.0` and update every pin: `addons/e_agent_bridge/__manifest__.py:3`, `packages/adapter-odoo/src/e_agent/adapters/odoo/e_agent_plugin.json` `expected_bridge_version` enum (allow only `19.0.0.4.0`), `profiles/live.example.json`, `scripts/odoo_sandbox.py` default, `tests/integration/test_odoo_live.py` `BRIDGE_VERSION`, `tests/integration/test_bridge_guards_unit.py` (both pins), `packages/adapter-odoo/tests/test_transport_boundaries.py` `TARGET`, `docs/runbooks/i06-odoo-bridge.md` (version mentions + one sentence: upgrade the addon in Odoo before the new read works).

**Files:**
- Modify: `packages/domain-erp/src/e_agent/erp/procurement/__init__.py` (`OPEN_DEMANDS_READ`)
- Modify: `packages/domain-erp/src/e_agent/erp/procurement/api.py` (`OpenDemandsQuery`, `OpenDemand`, `OpenDemands`)
- Modify: `packages/domain-erp/src/e_agent/erp/e_agent_plugin.json` (capability entry)
- Modify: `packages/domain-erp/src/e_agent/erp/plugin.py` (`INPUT_SCHEMAS`, `GUIDANCE`)
- Modify: `packages/domain-erp/src/e_agent/erp/testing/fake_erp.py` (binding template + read branch in `_read_more`)
- Modify: `packages/adapter-odoo/src/e_agent/adapters/odoo/e_agent_plugin.json` (binding `odoo19.procurement.open-demands`, `requires_capabilities`, version enum)
- Modify: `packages/adapter-odoo/src/e_agent/adapters/odoo/executor.py` (`_read_more` branch)
- Modify: `addons/e_agent_bridge/models/bridge.py` (`read_open_demands`), `addons/e_agent_bridge/__manifest__.py` (version)
- Modify: `apps/server/src/e_agent/server/profiles/fixture.json`, `profiles/dev-ollama.json`, `profiles/live.example.json` (binding entries; a missing entry silently hides the tool — `bootstrap.py:112-120`)
- Modify: version pins listed above
- Test: `packages/domain-erp/tests/test_procurement.py`, `packages/adapter-odoo/tests/test_transport_boundaries.py`, `tests/integration/test_bridge_guards_unit.py`, `tests/integration/test_odoo_live.py`, `apps/server/tests/test_pydantic_driver_e2e.py` (tool exposed)

**Interfaces:**
- Produces: contract `procurement.open-demands.read.v1`, input schema id `procurement.OpenDemandsQuery.v1`, output schema id `procurement.OpenDemands.v1`, tool name `procurement_open_demands_read_v1`, bridge method `read_open_demands() -> {"demands": [...], "complete": bool}`, observation data `{"demands": [{"demand_ref", "product_ref", "product_name", "quantity", "unit", "requested_date"}], "complete": bool}`.

- [ ] **Step 1: Failing domain test** (copy the shape of `test_offers_read_reports_approval_status`, using `_Reader`, `CTX`):

```python
async def test_open_demands_read_lists_the_fixture_demand_with_exact_refs() -> None:
    erp = FakeErp(SCENARIOS["valid"])
    obs = await erp.read(CTX, None, ReadRequest("r", OPEN_DEMANDS_READ, "c", {}))  # type: ignore[arg-type]
    assert obs.data["complete"] is True
    [row] = obs.data["demands"]
    assert row["demand_ref"] == "demand:d-001" and row["product_ref"] == "product:widget-a"
    assert set(row) == {"demand_ref", "product_ref", "product_name", "quantity", "unit", "requested_date"}
```

Run `uv run pytest -q packages/domain-erp -k open_demands` → FAIL (import error).

- [ ] **Step 2: Domain implementation.**

`procurement/__init__.py`: `OPEN_DEMANDS_READ = "procurement.open-demands.read.v1"` (export it next to `DEMAND_READ`).

`procurement/api.py`:

```python
class OpenDemandsQuery(Record):
    """List open procurement demands; takes no arguments."""


class OpenDemand(Record):
    demand_ref: str = Field(description=_REFERENCE_DESCRIPTION)
    product_ref: str = Field(description=_REFERENCE_DESCRIPTION)
    product_name: str
    quantity: str
    unit: str
    requested_date: str


class OpenDemands(Record):
    demands: tuple[OpenDemand, ...]
    complete: bool
```

`e_agent_plugin.json` capability entry (after the demand read):

```json
{
  "contract_id": "procurement.open-demands.read.v1",
  "effect": "read",
  "input_schema_id": "procurement.OpenDemandsQuery.v1",
  "output_schema_id": "procurement.OpenDemands.v1",
  "description": "List open procurement demands with their exact demand and product references; use it first when the user gives no demand reference"
}
```

`plugin.py`: import `OpenDemandsQuery`, add `"procurement.OpenDemandsQuery.v1": OpenDemandsQuery.model_json_schema()` to `INPUT_SCHEMAS`, and prepend to the procurement part of `GUIDANCE`: `"If the user names no demand reference, list open demands first and copy the exact demand_ref and product_ref from that result. "`

`fake_erp.py`: add `BindingTemplate(binding_id="fixture-erp.procurement.open-demands", contract_id=OPEN_DEMANDS_READ)` to `BINDINGS`, and in `_read_more` a branch returning `{"demands": [{"demand_ref": s.demand_ref, "product_ref": s.product_ref, "product_name": <the product's display name: last segment of product_ref, e.g. "widget-a">, "quantity": s.demand_quantity, "unit": s.unit, "requested_date": s.requested_date.isoformat()}], "complete": True}` with evidence `self._evidence(ctx, "demand", "open", "demands:1")` (match the helper's real signature).

Run the Step 1 test and `uv run pytest -q packages/domain-erp` → PASS.

- [ ] **Step 3: Failing adapter test** in `packages/adapter-odoo/tests/test_transport_boundaries.py`: an `httpx.MockTransport` that answers `POST .../json/2/e_agent.bridge/read_open_demands` with `{"demands": [{"demand_ref": "odoo/e_agent.demand/1", "product_ref": "odoo/product.product/201", "product_name": "Widget A", "quantity": 12.0, "unit": "Units", "requested_date": "2026-10-20"}], "complete": true}`; drive the executor's `read` with `OPEN_DEMANDS_READ` and assert `obs.data["demands"][0]["quantity"] == "12"` (via `dec`) and the refs are copied exactly. → FAIL.

- [ ] **Step 4: Adapter implementation.** In `executor.py` `_read_more`, mirror the `OPEN_ORDERS_READ` branch: `raw = await self._call(ctx, cid, "read_open_demands")`; map rows with `dec(row["quantity"])`; evidence `self._evidence(ctx, "e_agent.demand", "open", None, raw["complete"])`. Manifest: binding `{"binding_id": "odoo19.procurement.open-demands", "contract_id": "procurement.open-demands.read.v1"}`, add the contract to `requires_capabilities`, change the version enum to `["19.0.0.4.0"]`. Run adapter tests → PASS.

- [ ] **Step 5: Bridge method** in `addons/e_agent_bridge/models/bridge.py` next to `read_demand`:

```python
    @api.model
    @api.readonly
    def read_open_demands(self):
        self._check_target()
        domain = [("company_id", "=", self.env.company.id)]
        # add ("namespace", "=", <target namespace>) here if the target context carries one
        demands = self.env["e_agent.demand"].search(domain, order="id", limit=100)
        return {
            "demands": [
                {
                    "demand_ref": self._ref(d),
                    "product_ref": self._ref(d.product_id),
                    "product_name": d.product_id.display_name,
                    "quantity": d.quantity,
                    "unit": d.product_id.uom_id.name,
                    "requested_date": d.requested_date and d.requested_date.isoformat(),
                }
                for d in demands
            ],
            "complete": len(demands) < 100,
        }
```

Bump `__manifest__.py` to `19.0.0.4.0` and every pin listed above. Add `("bridge.py", "read_open_demands", [])` to the parametrized guard list in `tests/integration/test_bridge_guards_unit.py` (adapt the argument list to the helper's expectations) and run it → PASS (the method calls `_check_target()` first).

- [ ] **Step 6: Profiles and server.** Add the binding entries: fixture and dev-ollama `"fixture-erp.procurement.open-demands": ["conn-fixture-erp"]`; live example `"odoo19.procurement.open-demands": ["conn-odoo"]`. In `apps/server/tests/test_pydantic_driver_e2e.py` assert `procurement_open_demands_read_v1` is among the tool names offered to the model. Add a live test in `tests/integration/test_odoo_live.py` that calls `_bridge("read_open_demands")` and asserts the seeded `demand_ref` appears (skipped without the sandbox, like its neighbours).

- [ ] **Step 7: Full gate, Postgres, `make e2e`, commit.**

```bash
git add packages/domain-erp packages/adapter-odoo addons/e_agent_bridge apps/server/src/e_agent/server/profiles/fixture.json apps/server/tests/test_pydantic_driver_e2e.py profiles/dev-ollama.json profiles/live.example.json scripts/odoo_sandbox.py tests/integration/test_odoo_live.py tests/integration/test_bridge_guards_unit.py docs/runbooks/i06-odoo-bridge.md
git commit -m "feat(procurement): open-demands discovery read across domain, fixture, Odoo adapter and bridge 19.0.0.4.0 (ADR 0022)"
```

---

## Task 4: Conversational reply instead of a verification failure

**Files:**
- Modify: `packages/kernel/src/e_agent/kernel/coordinator.py` (`FinalAnswer` branch in `_drive`; `_Continuation` gains nothing — use existing `cont.reads`, `cont.read_errors`, `cont.last_action_id`, `cont.pending_action_id`)
- Modify: `ui/packages/ui-core/src/store.ts`, `ui/packages/ui-core/src/i18n.ts`, the conversation component that renders agent messages (find it from `selectConversation` usages under `ui/packages/components/src/features/`)
- Test: `packages/kernel/tests/test_lifecycle.py`, `ui/packages/ui-core/test/*`, `ui/packages/components/test/*`, one Playwright conformance spec under `ui/packages/ui-conformance/tests/`

**Interfaces:**
- Consumes: `cont.read_errors` (Task 2).
- Produces: `input.requested` payload `{"question": str, "kind": "reply" | "clarification"}`; UI selector field `kind` on conversation items.

- [ ] **Step 1: Failing kernel tests** (add a small driver to the test that returns `FinalAnswer` on the first call; reuse `make_kernel` and swap `k.coordinator._driver` the way `test_recovery.py` does):

```python
async def test_plain_reply_without_any_work_waits_for_the_user(make_kernel: MakeKernel) -> None:
    k = make_kernel()
    k.coordinator._driver = _ReplyDriver("Hello! What would you like me to do?")  # type: ignore[assignment]
    run = await k.coordinator.start_run(k.requester, "hi", k.scope)
    assert run.state is RunState.WAITING_INPUT
    asked = [e for e in await k.store.list_events(TENANT, run.run_id) if e.type is RunEventType.INPUT_REQUESTED]
    assert asked[-1].payload == {"question": "Hello! What would you like me to do?", "kind": "reply"}


async def test_plain_answer_after_reads_still_requires_verification(make_kernel: MakeKernel) -> None:
    k = make_kernel()
    k.coordinator._driver = _ReadThenReplyDriver("Widget-a is short by 7.")  # type: ignore[assignment]
    run = await k.coordinator.start_run(k.requester, "is widget-a short?", k.scope)
    assert run.state is RunState.FAILED
    assert run.reason_code is ReasonCode.VERIFICATION_FAILED
```

`_ReplyDriver` returns `FinalAnswer(text=...)` on every call; `_ReadThenReplyDriver` returns one `RequestReads` (same request as `NotesDriver`) then `FinalAnswer`. Use the requester principal and scope the harness already exposes (check `Kernel` fields; `_start` shows how runs are started).

- [ ] **Step 2: Run → FAIL** (first test ends `FAILED`).

- [ ] **Step 3: Implement** at the top of the `FinalAnswer` branch, before the verification rule:

```python
            if isinstance(step, FinalAnswer):
                run = await self._store.get_run(run.tenant_id, run.run_id)
                conversational = (
                    not cont.reads
                    and not cont.read_errors
                    and cont.last_action_id is None
                    and cont.pending_action_id is None
                )
                if conversational:
                    await self._store.update_run(
                        run.model_copy(update={"revision": run.revision + 1}),
                        run.revision,
                        [(RunEventType.INPUT_REQUESTED, {"question": step.text, "kind": "reply"}, None)],
                    )
                    run = await self._store.get_run(run.tenant_id, run.run_id)
                    return await self._set_run_state(run, RunState.WAITING_INPUT)
```

Leave the existing `AskClarification` payload as `{"question": ...}` and add `"kind": "clarification"`. Check `RUNNING → WAITING_INPUT` is in `ALLOWED_RUN_TRANSITIONS` (it is).

- [ ] **Step 4: UI (follow the `ag-ui-implement` skill).** `store.ts` `selectConversation` adds `kind: p["kind"] === "reply" ? "reply" : "message"` for `input.requested`. The conversation renderer shows a reply like any agent message but with a small secondary label from i18n key `conversation.reply` ("Reply · not a verified result" / VI "Trả lời · không phải kết quả đã xác minh"). The composer status for a reply uses i18n `status.WAITING_INPUT.reply` = "Your turn" / "Đến lượt bạn" instead of "Your answer is needed". Tests first: ui-core selector test for `kind`, component test for the label, one Playwright spec in `ui-conformance` using the fixture server with a reply (if the fixture driver cannot produce one, assert the label via the component test and note it).

- [ ] **Step 5: Full gate, Postgres, regenerate if OpenAPI changed, `make e2e`, commit.**

```bash
git add packages/kernel/src/e_agent/kernel/coordinator.py packages/kernel/tests/test_lifecycle.py ui/packages/ui-core ui/packages/components ui/packages/ui-conformance/tests
git commit -m "feat(kernel): conversational replies wait for the user instead of failing (ADR 0022)"
```

---

## Task 5: UI shows each agent question once

**Files:**
- Modify: `ui/packages/ui-core/src/store.ts` (`reduceEvent`: `input.requested` clears `streamingText`)
- Test: `ui/packages/ui-core/test/*` (store reducer test), a Playwright conformance assertion if an existing spec renders a clarification

- [ ] **Step 1: Failing test:** a run view with `streamingText: "Could you…"` that receives `input.requested {"question": "Could you…"}` must end with `streamingText === ""` and exactly one agent conversation item.
- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Implement:** in the `input.requested` branch set `next.streamingText = ""` (mirror `message.final`).
- [ ] **Step 4: UI tests, full gate, `make e2e`, commit** (`git add ui/packages/ui-core`; message `fix(ui): an agent question renders once, not as stream plus question`).

---

## Task 6: Upgrade the sandbox, pin the new artifacts, live end-to-end

**Files:**
- Modify (gitignored, not committed): `profiles/live-odoo19-learning.local.json` (new `artifact_sha256` pins, new binding for `procurement.open-demands.read.v1`)
- Create: `docs/handoffs/2026-10-12-real-agent.md`
- Modify: `README.md` (live run section: how to start the live stack with `~/.config/e-agent/live.env`)

- [ ] **Step 1: Upgrade the bridge in the sandbox only:** `docker compose -p odoo19-learning --project-directory /Users/thanhnguyen/dev/study/erp stop odoo`, then `... run --rm --no-deps odoo odoo -d training19_demo -u e_agent_bridge --stop-after-init --log-level=warn`, then `... up -d odoo`. Verify `ir_module_module` shows the new bridge version.
- [ ] **Step 2: Rebuild trusted wheels and pins** (`uv build --package e-agent-domain-erp --wheel` and `--package e-agent-adapter-odoo`, then `scripts/plugin_inventory.py` as in `.github/workflows/odoo-live.yml`) and update the live profile pins, bridge version and bindings.
- [ ] **Step 3: Run `scripts/odoo_sandbox.py info`** with the expected identity (bridge version updated) — must pass.
- [ ] **Step 4: Live end-to-end** with `make dev PROFILE=profiles/live-odoo19-learning.local.json` and the env from `~/.config/e-agent/live.env`, through the API script and the UI:
  1. "hi" → `WAITING_INPUT` with a `kind: reply` message.
  2. Reply "Which products are short for open demand?" in the same run → the agent lists open demands, reads demand/stock, and answers with a verified shortage answer (no reference supplied by the user).
  3. A new run "Draft a purchase order for any shortage from the approved supplier" → either a validated `WAITING_APPROVAL` proposal or a verified zero-shortage answer, matching the real Odoo numbers.
  4. A run where the model is told a wrong reference ("check demand demand-123") → `read.rejected` recorded, run continues (lists open demands or asks), no crash.
  Record run ids, states, reason codes and the key events in the handoff.
- [ ] **Step 5: Handoff + README, commit** (`git add docs/handoffs/2026-10-12-real-agent.md README.md`).
