# ADR 0023: Conversation model: a thread of runs with carried context

Date: 2026-10-20. Status: Accepted by the owner at gate G-A, 2026-10-20 ("1 accept"). At the same gate the owner confirmed section 9's refinement of ADR 0027 ("5 ok"), accepted the never-carried `ref` paths of section 7 as a known limit ("6 ok"), and narrowed the recorded source ref to complete reads ("7 yes", section 6). Amends ADR 0022 (section 5); refines ADR 0032 (section 8: `recent_turns` holds carried items) and ADR 0027 (section 9: what `shadow` writes for this toggle); changes the plugin contract with `CapabilityDescriptor.answer_value_formats` (section 7). [Target architecture](../design/target-architecture.md) §5.7. Plan: [Phase 4](../plans/2026-10-20-phase4-conversation-chat.md) D1–D9, D11, D12, D17; Tasks 4c.1–4c.4, 4d.1–4d.5. Every `file:line` below is at `181585e`.

## Context

- There is no conversation. A message is a new run (`POST /v1/runs`, `server/api.py:309-327`) or the answer to a waiting run (`POST /v1/runs/{id}/inputs`, `server/api.py:459-482`). The UI keeps up to 20 session-local run references (UI architecture §10). A follow-up such as "draft a PO for it" therefore starts a run that knows nothing of the run before it.
- The [core plan](../plans/2026-10-12-core-conversation-cognition.md) Phase 1 offered two shapes: **A**, a thread of runs, each run bounded, with carried context; **B**, one long-lived run per conversation. The roadmap's default is A.
- A greeting is an ADR 0022 reply run: a `FinalAnswer` from a run with no reads, read attempts or proposals is recorded as `input.requested {"kind": "reply"}` and the run waits for input (`kernel/run_loop.py:145-181`). Every model call goes through `_with_tools` (`kernel/ir_on.py:156`), which runs the per-call route check (ADR 0032 §9).
- ADR 0032 defines a `recent_turns` layer in the dynamic suffix, with a default budget of 4000 tokens (`contracts/context_pack.py:43`, `:98`), and puts it second in the drop order. `assemble` never fills it (`kernel/context.py:311`, "in Phase 3 both are empty").
- Answer arguments have no host-side type beyond their JSON schema. The ERP answer models type every ref as a free `str` (`plugins/erp/domain/procurement/api.py:91-110`, `sales/api.py:88-93`, `receivables/api.py:36-42`); `data_classes` (ADR 0030) classifies a path but does not check its value. A carried "typed value" needs a check the host owns.

## Decision

### 1. Shape (D1)

Option A. A `Conversation` owns many runs. Each run keeps one task, one budget, one approval and one outcome, exactly as today. A conversation adds no state machine: the run and action tables (ADR 0018, ADR 0025) are unchanged.

### 2. Records (D4, Task 4c.2)

In `contracts/conversation.py`:

- `Conversation(tenant_id, conversation_id, owner_id, revision, created_at, updated_at)`. It holds no text. Its record kind is `conversations`, record class audit skeleton (ADR 0030 record classes).
- `RunRecord.conversation_id: str | None = None`. Runs created before Phase 4, and every run in `off`, have `None`. `run.created` gains the key `conversation_id` only when it is set (`run_created_keys`, `kernel/reconstruct.py:76`), so the `off` event goldens do not move.
- `ReplyTo(run_id, run_revision)`: the waiting run and the run revision the user saw with its question.
- `RouteKind` (`answer`, `start`, `refuse`) and `MessageRoute(kind, run_id, run_revision, hint)`.
- `CarriedRef(contract_id, source_ref, revision, observed_at)`, `CarriedAnswer(contract_id, arguments)`, `CarriedRun(run_id, task_id, task_version, state, reason_code, user_messages, answers, refs)`: section 6. No field holds model text.
- `ConversationPage(items, next_after)`: the store's page.
- `ConversationSummary(conversation_id, title, updated_at, latest_state, reply_pending)`, `ConversationList(items, next_after)`, `ThreadRun(run_id, task, state, reason_code, revision, created_at)` and `ConversationSnapshot(conversation, runs)`: the API projections.
- `MemberFeatures(conversations)` in `contracts/features.py`: the member projection of section 10.

The thread is a projection of the conversation's runs and their events (target §5.1 item 2); user text stays where it is today, in `runs.task` and `input.received`. The title is derived at read time from the first run's task, cut to 80 characters. Phase 4 adds no archive or delete route; retention and deletion are ADR 0030's Phase 7 parts.

### 3. The `ConversationStore` port (Task 4c.3)

A protocol in `sdk/store.py` beside `RunStore` (`sdk/store.py:70`), which is unchanged:

- `create_conversation`, `get_conversation(tenant_id, owner_id, conversation_id)`, `list_conversations(tenant_id, owner_id, *, after, limit)` (newest first, `limit` at most 100), `list_conversation_runs(tenant_id, owner_id, conversation_id)` (oldest first), and `lookup_idempotent(tenant_id, actor_id, key)`, which reads the record `create_run_idempotent` writes and writes nothing.
- Every query filters by tenant **and** owner. Another owner's or tenant's conversation raises `NotFound` (PR-24): it looks absent, never forbidden.
- `create_run_in_conversation(run, events, state, actor_id, key, request_digest, conversation_revision)` takes `RunStore.create_run_idempotent`'s arguments (`sdk/store.py:74-84`) plus the revision. It first looks up the (tenant, actor, key) record: a hit returns the recorded (run id, digest) and runs no conversation check, so a retried start replays while the first run is still active. On a miss, in the same transaction as the run insert, it checks that the conversation's revision equals `conversation_revision` and that no run of the conversation is in a non-terminal state, then creates the run and bumps the revision and `updated_at`. Both refusals raise `ConcurrencyConflict` (`sdk/store.py:38`). **One active run per conversation** is this check.
- Postgres: migration `0007_conversations.sql`, forward-only, with the conversation row locked `FOR UPDATE` and the idempotency row read again under the lock. Memory: a subclass with its own lock, taken before the parent's. The plan's Task 4c.3 holds the lock order.

### 4. Routing (D2, Task 4d.1)

`route_message(latest, reply_to) -> MessageRoute` is pure. It looks only at the conversation's latest run:

| Latest run | Message | Route |
|---|---|---|
| none, or `SUCCEEDED`, `FAILED`, `CANCELLED` | any | `start`: a new run in the conversation |
| `WAITING_INPUT` | `reply_to` names this run and the revision it is at | `answer`, through the existing `accept_input` |
| `WAITING_INPUT` | no `reply_to`, or another revision (Q1 while Q2 is pending) | `CONFLICT`, fixed hint "the question changed; read it again" |
| `CREATED`, `RUNNING`, `VERIFYING`, `WAITING_APPROVAL`, `NEEDS_RECONCILIATION` | any | `refuse`: `CONFLICT`, fixed hint "wait, decide the approval, or stop the run" |

- **An answer is bound to the question the user saw**, never to the conversation revision. `answer` calls `accept_input(run_id, text, reply_to.run_revision)`, whose revision and state check (`kernel/run_loop.py:243-256`) refuses a stale answer, as `/inputs` does today.
- **Order of checks** in `post_message`: (0) the (tenant, actor, Idempotency-Key) record (`lookup_idempotent`), before anything else: a hit with the same request digest returns the original `(start, run_id)` whatever state that run is in now, another digest is `CONFLICT` (PR-17); the digest covers the conversation id, the text, `reply_to` and `host_context`; (1) the caller owns the conversation, else `NOT_FOUND`; (2) `reply_to.run_id` is a run of this conversation, else `NOT_FOUND`, with the one `shadow` exception of section 9; (3) the answer replay check.
- **A retried answer is idempotent.** Today's replay check in the `/inputs` handler (`server/api.py:469-478`) moves into the kernel as `input_replayed`, unchanged in meaning, and refuses a non-requester with `FORBIDDEN` before it reads any event, as `server/api.py:467-468` does. The `/inputs` handler calls it; its behaviour is unchanged.
- A `start` uses the message's own `Idempotency-Key` and request digest, and passes the message's `host_context` with the type and validation of `CreateRun` (`server/api.py:76-78`).
- No queue and no auto-cancel. A run beside a `WAITING_APPROVAL` run is not allowed (alternatives).
- **A message is never a decision** (PR-13, PR-15). No code path from the message route reaches `approval_flow` or writes `approval.decided`; "approve it" is routed like any other text. Approval goes only through `/v1/runs/{id}/approvals`.

### 5. Greetings; amendment of ADR 0022 (D3)

No model call happens outside a run. A greeting stays an ADR 0022 reply run that waits for input, and the next message of the conversation answers it (section 4). A run-less turn would bypass mode pinning, the per-call route check in `_with_tools` (`kernel/ir_on.py:156`, threat T23), evidence and reconstruction. This ADR does not adopt the core plan's "a pure greeting needs no run".

ADR 0022 is amended in one point: a reply run belongs to a conversation when the run is linked to one. Its reply rule (`kernel/run_loop.py:148-181`) is unchanged.

### 6. Carried context (D5, D6, Task 4d.2)

When a run is admitted into a conversation that has earlier runs, the kernel builds its carried items once, from up to 5 earlier runs of the conversation, newest first. `carry` is pure and deterministic: it reads records and events, never a model. The items are stored in the run's continuation (class business payload) in their own field, `carried: tuple[CarriedRun, ...] = ()` on `_Continuation`, left out of the stored continuation when empty as the other optional fields are (`kernel/continuation.py:169-178`), so an `off` continuation is byte-identical. They are fixed for the run's life; a later message never changes them (D9). Carried items are never put in `cont.observations` or `cont.reads`: an observation there becomes an `ApprovedFact` of the next write proposal (`kernel/proposals.py:184-187`), part of the approval presentation's baseline (`kernel/approval.py:196`) and a staleness re-read target (`kernel/dispatch.py:363-366`), and a carried item is none of these (D6).

Per earlier run: its run id, task id and version, end state and reason code, and three kinds of fact.

1. **The user's own messages**: the task text and each `input.received`, class `personal`, fenced as data (ADR 0032 §4).
2. **Checked typed values** from the normalised arguments of each answer action of that run in state `VERIFIED`. A path is carried only when the answer contract declares a value format for it (section 7) and a `data_classes` entry covers it, and its value passes the format. A `ref` value must also equal a recorded source ref of the same run (item 3). Every other path and value is dropped, never carried as `personal`. So `explanation` and `summary` are never carried.
3. **The record refs it read**: for each `read.recorded` event of the run, the `EvidenceRef` of the observation with that `evidence_id` in the run's stored continuation (`load_continuation`), as `CarriedRef(contract_id, source_ref, revision, observed_at)`. `CarriedRef.source_ref` holds `EvidenceRef.locator`, and it is the run's **recorded source ref**. Only a read whose `EvidenceRef.completeness` is `complete` gives a `CarriedRef` and a recorded source ref; a `partial` or `unknown` read, such as Odoo's not-found read, gives neither (owner, G-A, 2026-10-20). The `read.recorded` payload is unchanged.

   Only the driver's reads put an observation in the continuation (`kernel/run_loop.py:103-104`), and a staleness re-read replaces it (`kernel/dispatch.py:364-366`). A verifier's reads write `read.recorded` too (`kernel/gateway.py:113-128`, through `_GatewayReader`, `kernel/continuation.py:195-213`), but their observations are never stored. An event whose `evidence_id` names no stored observation yields no `CarriedRef` and no recorded source ref, and is not an error.

Never carried: model text (`message.final`, a reply, question or rationale text, a grounded summary, a free-text answer field) and raw observations. `OutcomeReport.verified_values` is not a source: the answer verifiers do not set it, and the kernel drops it when `execution_ir` is not `on` (`kernel/ir_on.py:236-238`). A `GROUNDED` run (ADR 0033 §3) has no answer action, so it carries refs and user messages only.

**Carried facts are not evidence** (D6). A carried ref is a hint, not a fact of the new run. Citation lookup stays scoped to this run (ADR 0033 §1), so a citation that names an earlier run's evidence is `KERNEL-CITATION`. Validation, approval and verification use only this run's reads; the model must read again (PR-15, PR-19). Carried items never enter an approval digest and grant nothing.

### 7. Host-side answer value formats (D17, Task 4c.4)

**The field.** `CapabilityDescriptor.answer_value_formats: Mapping[str, str] = {}`, in the plugin manifest on each capability entry beside `data_classes`, keyed by the same RFC 6901 instance paths (ADR 0030, `items` for every array index; keys checked by `check_class_key`, `contracts/data_classes.py:187`). Each value is one of a closed set:

| Format | A value passes when it is |
|---|---|
| `decimal` | a JSON number, or a canonical decimal string as `DecimalStr` writes it (`contracts/common.py:43`) |
| `integer` | a JSON integer, not a boolean |
| `date` | an ISO 8601 calendar date that parses |
| `date-time` | an RFC 3339 time with an offset |
| `enum:<v1>\|<v2>…` | one of the listed values; an empty or repeated value makes the format invalid |
| `ref` | a non-empty string of at most 256 characters with no whitespace or control character |

A `null` passes only when the schema property allows it (a `null` member of its `anyOf` or `type`), and is carried as `null`. The recorded-source-ref check of a `ref` value is the carrier's (section 6), because it needs the run's evidence.

**Admission refusals.** The `CapabilityDescriptor` validator refuses any format on a capability whose `effect` is not `answer`. Registry admission, beside `dc.check_declarations` (`kernel/registry.py:306-310`), refuses:

- an unknown format;
- a path the contract's input schema does not have;
- a format the schema type at that path cannot hold: `decimal` needs a string or a number, `integer` an integer, every other format a string; a nullable union is judged by its non-null member;
- a format on a path that no `data_classes` entry covers. "Covers" means what `ClassIndex.declared` means (`contracts/data_classes.py:225-232`): an entry on the path or on an ancestor. `/input/late_order_refs: internal` therefore covers `/input/late_order_refs/items`.

**Never model-facing.** The formats are not in the tool schemas, so the tool schemas and both `off` model-request goldens are unchanged.

**`sdk_api`.** `git tag` lists no tag on 2026-10-20, so `sdk_api` 1.2 is unreleased and `answer_value_formats` joins its list (`sdk/__init__.py:3-8`, ADR 0032 §12); the version stays `"1.2"`. If 1.2 is released before Task 4c.4 lands, the field makes `sdk_api` 1.3 instead, with the same default.

**Per answer contract.** Every answer contract the code has today, with the paths that get a format and the free-text paths that get none. "Can match today" says whether a run's own reads record a locator that a correct value of that path can equal: if not, the guard always drops the path, and this ADR does not widen the guard.

| Answer contract | Path | Format | Can a `ref` match today? |
|---|---|---|---|
| `procurement.shortage.answer.v1` | `/input/demand_ref` | `ref` | Yes, only through `procurement.demand.read.v1`. Its locator is the demand ref: the simulator's scenario ref (`plugins/erp/simulator/fake_erp.py:148`), Odoo's requested `demand_ref` (`plugins/erp/odoo/executor.py:118-124`). `procurement.open-demands.read.v1` is located `"open"` (`fake_erp.py:238-240`, `executor.py:252`), so a run that only listed demands does not match. |
| | `/input/product_ref` | `ref` | Yes, through `inventory.availability.read.v1` (`fake_erp.py:137`, `executor.py:139-141`) or `procurement.offers.read.v1` (`fake_erp.py:166`, `executor.py:148-154`), both located by the product ref. |
| | `/input/demand_quantity`, `/input/available`, `/input/inbound`, `/input/shortage` | `decimal` | (not a ref) |
| `procurement.offer.recommend.v1` | `/input/demand_ref`, `/input/product_ref` | `ref` | As for the shortage answer. |
| | `/input/offer_ref` (nullable) | `ref` | No. The offers read is located by the product ref, and no read is located by an offer ref. |
| | `/input/supplier_ref` (nullable) | `ref` | No. No read is located by a supplier ref. |
| | `/input/unit_price` (nullable) | `decimal` | (not a ref) |
| | `/input/explanation` | none (free text, `personal`) | |
| `sales.late-orders.answer.v1` | `/input/as_of` | `date` | (not a ref) |
| | `/input/late_order_refs/items` | `ref` | No. `sales.open-orders.read.v1` is located by the date: the bare `as_of` in the simulator (`fake_erp.py:263-265`), `open@<as_of>` in Odoo (`executor.py:256-258`). |
| | `/input/summary` | none (free text, `personal`) | |
| `receivables.overdue-invoices.answer.v1` | `/input/as_of` | `date` | (not a ref) |
| | `/input/overdue_invoice_refs/items` | `ref` | No. `receivables.open-invoices.read.v1` is located by the date: the bare `as_of` in the simulator (`fake_erp.py:296`), `open@<as_of>` in Odoo (`executor.py:275-277`). |
| | `/input/totals/items/currency`, `/input/totals/items/total`, `/input/summary` | none | A total without a checked currency is not carried; the summary is free text. |
| `grounded.answer.v1` (kernel) | `/summary` | none | Not a registry capability (ADR 0033 §3; `kernel/grounded_answer.py`), so it has no descriptor and no formats. |
| `notes.summary.answer.v1` (kernel test pack) | `/input/count` | none | The fixture declares no `data_classes` and registers no input schema by default (`tests/unit/kernel/conftest.py:94-99`, `make_kernel(input_schemas=...)`), so admission could not accept a format. A test that needs a carried value registers a classed variant, as `CLASSED_READ` does for the read (`conftest.py:135-147`). |

Two facts about the locators matter for tests and the live check. The simulator locates a read by the **scenario's** ref, whatever the request asked for (`fake_erp.py:137`, `:148`, `:166`). Odoo locates it by the **requested** argument, also when the record is not found (`found` false, completeness `UNKNOWN`; `executor.py:118-124`, `:139-141`). The guard checks that the run read that ref and, since G-A (answer 7), that the read found it: a not-found read is completeness `unknown` and gives no recorded source ref (section 6); a `VERIFIED` answer was still checked by its verifier's own fresh reads.

### 8. Rendering in `recent_turns`; refinement of ADR 0032 (D7)

- Carried items reach the model only as the pack's `recent_turns` layer. `assemble` gains `carried: Sequence[CarriedRun] = ()`. With no carried items the pack is byte-identical to Phase 3's, digest included. No new `DriverInput` field is added.
- Every carried field goes through the class walk (`kernel/context_walk.py`) and the class-per-route rule of ADR 0032 §5. User text is `personal`, so it is masked on a hosted route without `data_processing`. Every carried value and user message is fenced (ADR 0032 §4).
- The drop order of ADR 0032 §2 is unchanged: knowledge first, then the oldest recent turns, so carried runs drop oldest first, then the oldest unreferenced evidence. Each drop is a `Dropped` entry.
- A turn that falls back to today's history (ADR 0032 §7, `CONTEXT_ASSEMBLY_FAILED`) sends no carried item.

### 9. Toggle, pinning, fallback and startup (D7, D8, D9)

`features.conversations`, `off | shadow | on` (ADR 0027), default `off` in every committed profile.

| Mode | Behaviour |
|---|---|
| `off` | Today. The conversation routes exist (the OpenAPI document is the same in every mode) and refuse with `NOT_FOUND` "conversations are off". No run is linked, no pin is written, no new event appears. |
| `shadow` | Messages go through the conversation route. `answer` and `start` are what today's client does anyway, so those runs are linked and the conversation row is written. Nothing today's path accepts is refused; a stale `reply_to` gets `CONFLICT`, as `/inputs` gives today. A message the router would refuse starts an unlinked run (`conversation_id = None`), as today, and records `conversation.compared` with `route: refuse`. A linked start or answer that fails in the conversation step (`ConcurrencyConflict`, a missing conversation, a store error on the conversation row) falls back inside the same request, under the message's own idempotency record, to today's unlinked run or plain input, and records `conversation.shadow_failed`; the request does not fail. A `reply_to` naming the caller's own unlinked run (made by such a fallback) is a plain `accept_input`, as `/inputs` would take it, and records `conversation.shadow_failed` with stage `reply_to`. At admission of a run with earlier runs, the kernel builds the carried items and the layer they would render, records `conversation.compared`, and gives the driver nothing; `cont.carried` stays empty. |
| `on` | Routing refuses as section 4 says. At admission the kernel builds the carried items, stores them in `cont.carried` (section 6), records `conversation.context_carried`, and every pack of the run renders them. |

- **Refinement of ADR 0027 for this toggle.** ADR 0027 says `shadow` acts on nothing. Here `shadow` writes conversation rows and links runs, because the linked runs are the ones today's client starts anyway. It adds no driver call, provider read, budget use, refusal or carried item; what it withholds is the refusal and the carried context. The fallback is server-side only: the UI never re-posts after a conversation-route error.
- **Pinning.** `RunModes` (`contracts/features.py:35-54`) gains `conversations`, pinned in `_prepare_run` with the other modes (`kernel/coordinator.py:150-155`, `kernel/features.py:217-221`) and written only when not `off`, so an `off` continuation is byte-identical (ADR 0032 §8).
- **Startup.** A profile with `conversations: on` is refused unless `context_assembler` is `on`, beside the ADR 0030 route rule (`check_route_boundary`, `server/bootstrap.py:228-254`). Both modes are pinned together, so a run pinned `conversations: on` is pinned `context_assembler: on`, and the per-call route check (ADR 0032 §9) covers what it sends.
- **Fallback (ADR 0027).** The carried items are built at admission, before the run can reserve anything. A failure there records `feature.fallback` with `CONVERSATION_CONTEXT_FAILED`, and the run starts without carried items, as in `off`. After admission the carried layer is part of the pack, so a later failure is ADR 0032's `CONTEXT_UNAVAILABLE`, or reconciliation when a reservation is unresolved. A fallback never sends unmasked data to a route that is not `local` and has no `data_processing` declaration (T23).

### 10. Routes and authorization (D10, D11, D12, Task 4d.4)

| Route | Returns |
|---|---|
| `POST /v1/conversations` | `{conversation_id}` |
| `GET /v1/conversations?after=&limit=` | `ConversationList`, newest first |
| `GET /v1/conversations/{id}` | `ConversationSnapshot`; each `ThreadRun` carries its `revision`, which the UI sends back in `reply_to` |
| `POST /v1/conversations/{id}/messages` | `{route, run_id}`; header `Idempotency-Key`; body `{text, reply_to: ReplyTo \| null, host_context: HostContext \| null}` |
| `GET /v1/me/features` | `MemberFeatures`, in every mode |

- Every route has the session dependency (`session`, `server/api.py:255-266`; PR-27). The handlers delegate to the kernel facade and hold no routing logic (PR-03). Errors use the existing envelope `{code, message, correlation_id}` (`server/api.py:194-198`), so the UI tells an e-agent `NOT_FOUND` from a route an older server never mounted.
- The UI learns the mode only from `GET /v1/me/features`, a member-readable projection in the pattern of ADR 0017. `/health/ready` has no session and is not read by the UI.
- In `on`, the sidebar lists the server's conversations. Runs with `conversation_id = None` stay in today's session-local history; no thread is made up for them (D11).
- There is no conversation event stream. The thread view uses the active run's existing stream (ADR 0007, unchanged) and reads the snapshot again after a posted message and after a run reaches a terminal or waiting state (D12).

### 11. Reason code and events

One `ReasonCode` member, added to the fallback group of `contracts/run.py` (ADR 0032 §11's table, `contracts/run.py:50-59`):

| Code | Kind | Carried by | `classify` group |
|---|---|---|---|
| `CONVERSATION_CONTEXT_FAILED` | fallback | `feature.fallback` only | never ends a run |

Three event types in `contracts/events.py`. Each payload holds ids, counts, digests, stages and codes, never user text or a value (PR-26):

- `conversation.context_carried {conversation_id, carried_run_ids, carried_digest}`, `on`, at admission.
- `conversation.compared {conversation_id, route, carried_run_ids, items, layer_digest, layer_tokens, masked, dropped}`, `shadow`. `layer_tokens` is the kernel's estimate. For `route: refuse` the carried keys are empty or zero and `layer_digest` and `layer_tokens` are left out, because `on` would have started no run.
- `conversation.shadow_failed {stage, code}` with the kernel's fixed message for the stage, `shadow`. `stage` is one of `start`, `answer`, `reply_to` and `carry`; `code` is the kernel error code of the failure.

### 12. Observability (ENG-TOGGLE-3)

`/health/ready` reports `features.conversations` with the other toggles (`server/api.py:281`). The evidence bundle's `conversation` key reports the run's `conversation_id`, its pinned mode, its carried run ids and the `conversation.compared` counts.

## Alternatives considered

- **B, one long-lived run per conversation:** rejected (core plan Phase 1). Budgets become unbounded, one approval or failure state covers unrelated tasks, and repair and verification blur.
- **A run-less greeting turn** (the core plan's first sketch): rejected (D3). It would call the model outside mode pinning, the per-call route check, evidence and reconstruction.
- **A new run beside a `WAITING_APPROVAL` run:** rejected (D2). ADR 0020 would refuse its write on the same connection anyway, and two live approval cards in one thread is a state the UI would have to cover.
- **Binding an answer to the conversation revision:** rejected. A conversation revision moves for reasons the user did not see; the run revision shown with the question is what the user answered.
- **Carrying summaries or the answer text:** rejected (D5, PR-34). Model text in the next run's context is unchecked and can carry an instruction; refs and checked values cannot.
- **Value formats as `pattern` in the JSON schemas** (D17 (b)): rejected. It changes the tool schemas and the `off` model-request goldens.
- **Refs only** (D17 (c)): rejected. It meets only "without re-asking" of the core plan exit; the shortage quantity would not carry.
- **A conversation event stream:** deferred (D12). The active run's stream and a re-read of the snapshot cover Phase 4.
- **The mode as a field of `SessionResponse`:** rejected (D10). `/v1/local/session` is loopback-only and never production authentication.

## Consequences

- Code: `contracts/conversation.py`, `MemberFeatures`, `RunRecord.conversation_id`, `RunModes.conversations`, `Features.conversations`, `_Continuation.carried`; `contracts/value_formats.py` and `CapabilityDescriptor.answer_value_formats`; the `ConversationStore` port on both stores and migration `0007`; `kernel/conversation.py`, `kernel/carried.py`, `kernel/memory_conversations.py`; `input_replayed`; `assemble(..., carried=...)`; the three events and the reason code; `server/conversations.py` and `GET /v1/me/features`; regenerated client types.
- Plugin contract: the ERP domain pack declares the formats of section 7, which changes the `domain-erp` artifact digest. Plugins that declare none admit unchanged.
- Known limit: four of the eight `ref` paths can never match a recorded source ref with today's reads, so they are never carried (section 7). Making them match needs a read located by those refs, or a locator change in the executors; neither is part of Phase 4.
- Known limit: a carried ref names a record an earlier run read. It may be stale or no longer visible; the new run must read it again (section 6).
- Retention and deletion of conversations follow ADR 0030's Phase 7 parts.

## Verification

- 4c.2: `test_conversation_record_holds_no_text`, `test_carried_run_has_no_model_text_field`, `test_run_created_has_no_conversation_key_when_unset`.
- 4c.3, on both stores: `test_foreign_owner_conversation_looks_absent`, `test_foreign_tenant_conversation_looks_absent`, `test_second_active_run_in_conversation_is_refused`, `test_idempotent_replay_starts_one_run`, `test_concurrent_same_key_starts_one_run`, `test_concurrent_messages_start_one_run`.
- 4c.4: `test_unknown_format_is_refused`, `test_format_on_a_non_answer_capability_is_refused`, `test_registry_refuses_a_format_without_a_data_class`, `test_erp_answer_formats_are_declared`, `test_value_formats_never_reach_the_model`.
- 4d.1: `test_answer_for_an_earlier_question_conflicts`, `test_retried_answer_is_accepted_once`, `test_message_while_waiting_approval_never_touches_the_action`, `test_message_text_is_never_a_decision`, `test_reply_to_foreign_run_is_not_found`.
- 4d.2: `test_carried_items_are_not_approved_facts`, `test_carry_holds_no_model_text`, `test_carry_drops_free_text_answer_fields`, `test_ref_not_among_recorded_source_refs_is_dropped`, `test_ref_from_incomplete_read_is_not_carried`, `test_carried_refs_come_from_recorded_evidence`, `test_carried_user_text_is_fenced`, `test_citation_to_carried_evidence_is_kernel_citation`, `test_pack_without_carried_items_is_unchanged`.
- 4d.3: the consumer `test_shadow_layer_digest_equals_on_layer_digest` over the fixture thread corpus, which prints its case count and fails on zero; `test_shadow_gives_the_driver_no_carried_item`; `test_compared_event_holds_no_value_or_text`.
- 4d.4: `test_conversation_routes_refuse_when_off`, `test_foreign_conversation_is_not_found`, `test_every_v1_route_has_an_authorization_dependency`.
- The `off` goldens (events, continuation, model requests) unchanged; the Phase 4 live check (Task 4f.2).
- Revisit when a conversation needs its own event stream, when a read located by offer, supplier, order or invoice refs exists, or when carried summaries are proposed.
