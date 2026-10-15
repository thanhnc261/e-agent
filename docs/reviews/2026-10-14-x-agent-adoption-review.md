# What to adopt from X-agent: review before the design and plan rewrite

Date: 2026-10-14. **Status: approved by the owner on 2026-10-14**, with decisions D-1 to D-4 recorded below and the instruction that AGENTS.md is rewritten as part of adoption (rewrite step 5). Input: the [X-agent reference catalogue](2026-10-14-x-agent-reference-catalog.md), 55 practices (AP-01 to AP-55) taken from 16 screenshots that were never committed (`research/dx/` is git-ignored). Baseline: `main` at `8bc7b1f` plus today's [design principles review](2026-10-14-design-principles-review.md) (DR-01 to DR-10) and the draft [Phase 1d](../plans/2026-10-14-phase1d-plugin-boundary.md) and [Phase 2](../plans/2026-10-14-phase2-execution-ir.md) plans.

Method: every AP item was mapped against e-agent's designs, ADRs, roadmap and code by three read-only research passes. The load-bearing claims were rechecked by hand (file:line below). The advisor reviewed each candidate before this document was written. Nothing was run, and no code or design document was changed.

Caveat: X-agent's evidence tags (`OBSERVED`, `INFERRED`) and counts are its own reviewer's; we did not check them. X-agent is a hosted, multi-product SaaS. e-agent is a local-first MVP with one Odoo sandbox and one owner. A practice that is right for X-agent can be premature here. Each item below says which.

## Verdict

**e-agent's approval-and-verification core matches or exceeds X-agent's, but it lacks per-tool effect declarations, and its weakest areas are the same ones X-agent rates weakest.** X-agent's strongest point, by its own review, is one executor chain: validate, authorize, guardrails, preview, approval bound to a payload hash, guarded invoke, bounded result, one audit record. e-agent already has the equivalent kernel chain, including approval digests that bind connection and credential versions, and outcome verification by independent read-back, which X-agent does not describe. Its weak spots are app-layer-only tenancy, in-memory per-process state and rules that are written but not machine-checked. e-agent has the same three (DR-07, Phase 7 RLS, and items XA-03 and XA-04 below).

X-agent offers three things worth taking:
1. **Declared effect metadata on every tool**: risk class, reversibility and idempotency (XA-01). This is the largest real gap. The draft Phase 2 plan, which introduces multi-write action plans, does not mention any of the three.
2. **Enforcement as the unit of a principle.** X-agent ties each principle to a decision record and a machine check, and its review counts only what tools enforce. That is the structure the rewrite should use (XA-00).
3. **A clear shape for authorization and secrets** (three planes, explicit deny, and plugins never see raw credentials) to use when Phase 7 is designed (XA-10 to XA-13).

Most of the rest either confirms existing findings, is already designed and waiting for its phase, or is premature at this scale.

## Rewrite map (order matters)

| Step | What | Why first |
|---|---|---|
| 1 | Owner accepts, amends or rejects ADRs 0018–0022 (DR-06). **Done 2026-10-14: all five accepted**; ADR files and index updated, pointers added in MVP design §7, §9, §10, §11 and HLD §3; full merge in step 4 | The rewritten baseline cannot rest on Proposed ADRs |
| 2 | Execution-IR design section and ADR (DR-01), **with effect metadata (XA-01)** and the approval-model ADR 0024. **Drafted 2026-10-14:** target §6.4; ADRs 0024, 0025, 0027, 0028, 0029 (Proposed, owner gate G1 of the Phase 2 plan); threats T20–T22; Phase 2 plan and roadmap amended | Phase 2 entry gate; every later phase builds on the step model |
| 3 | Data governance ADR (DR-05) folding in XA-13 (record classes) and the model egress boundary (DR-05 item 3); it **amends ADR 0021's clause that leaves data egress to the operator**; its threats are T23 (personal data egress to hosted models) and T24 (evidence export as an exfiltration channel), because T20–T22 went to the execution IR. **Drafted 2026-10-14:** target §13.3, ADR 0030 (Proposed), C19, T23–T24, roadmap Phases 3, 5, 7 | Phase 3 ContextAssembler needs it; Phase 5 widens the data surface |
| 4 | Consolidate HLD, MVP design and target architecture around the **principle → practice → check** table (XA-00); retire the duplicate roadmap and stale status lines (DR-10). **Done 2026-10-14:** [principles](../design/principles.md) (PR-01..PR-39, plus PR-40 for D-3 added in step 5; 17 rows have no check and 3 more are partial, 20 backlog entries in all); ADRs 0018–0022 merged into MVP §7, §9, §10, §11 and HLD §3; HLD and MVP status headers rewritten; target sections covered by accepted ADRs marked "merged", §18 marked superseded by the roadmap, §9 gains the D-2 fact-source mode and the XA-25 rules; stale "nothing is implemented" lines replaced in the threat model and both integration designs | One baseline that agents read first |
| 5 | **Rewrite AGENTS.md** (owner instruction, 2026-10-14) as the agent-facing summary of the new baseline; see "AGENTS.md rewrite" below. CLAUDE.md stays a thin pointer to it. **Done 2026-10-15:** AGENTS.md rewritten with a Principles section; every rule cites its `PR-nn` row; the rows in the table below were added; the status paragraph points to README and the roadmap; section names that `eng-foundations` and `ag-ux-foundations` cite are kept, as are the sentences they quote. CLAUDE.md unchanged | AGENTS.md is what every agent reads first; it must state the adopted rules, not the old ones |
| 6 | Fold Phase 1d additions (XA-02, XA-03) into the 1d plan before owner review; queue the hygiene items (XA-04, XA-14 to XA-17) as one small task. **Done 2026-10-15:** Phase 1d plan revision 3 (Task 1d.7, Review Focus 9–10, feature F-1d-7); [hygiene plan](../plans/2026-10-15-hygiene-gates-config-ci.md) (Tasks H.1–H.5), roadmap row 1h; principles backlog points at both | Cheap; they close real silent-pass holes |
| 7 | Write the Phase 7 design using the shapes in XA-10 to XA-13; record the deferred-phase notes (XA-20 to XA-24) in their sections | Prevents the deferred phases from being designed from scratch later |

---

## XA-00 Headline: principle → practice → enforcing check (AP-36, AP-37, AP-24)

**X-agent.** Principles are binding rules in AGENTS.md backed by 53 decision records, in a table of principle, practice and source. Its review counts "only what machines check, not advice in documents". New rules are enforced by type, lint or test, and a gate that cannot parse its input fails.

**e-agent today.** The rules are spread over AGENTS.md, the ENG-* rules, roadmap rules, HLD, MVP design and target architecture. Some are enforced (9 import-linter contracts, `pyproject.toml:90-170`; mypy strict; conformance suites; G- and R/U/Q fitness criteria). Others are prose only, for example "never blindly replay a possibly committed write" (XA-01) or "do not add unused abstractions". Nothing shows which is which.

**Adopt.** Make one table the spine of the rewritten design. Each row has: principle, what it means in practice, the deciding ADR or section, the **enforcing check** (contract, test, gate or "none: review only") and its status tag. Rows whose check is "none" become a visible backlog rather than an implicit assumption. The table replaces the scattered principle lists; the HLD, MVP design and target architecture then cite rows instead of restating them.

---

## Adopt now (Phase 1d and Phase 2 entry gate)

### XA-01 Effect metadata on every capability: risk class, reversibility, idempotency (AP-14, AP-44)

**X-agent.** Every tool declares `READ`, `WRITE_LOW`, `WRITE_HIGH` or `DESTRUCTIVE`. Write tools must declare idempotency. Retries of unattended work follow the declared idempotency. Unruled remote MCP tools are treated as `WRITE_HIGH`, and server hints never set risk.

**e-agent.** `CapabilityEffect` has only `READ`, `WRITE` and `ANSWER` (`contracts/capability.py:12-16`). Nothing declares idempotency or reversibility. AGENTS.md says "never blindly replay a possibly committed write", and MVP design §9 says not to assume an RPC create is idempotent. The bridge's `operation_key` and payload digest (`adapters/odoo/executor.py:340-347`, `addons/e_agent_bridge/models/bridge.py:234-237`) provide idempotency for the bridge path only, and nothing in the contract records it. The draft Phase 2 plan has no mention of risk, idempotency or reversibility (grep: none).

**Why it matters now.** Phase 2 brings multi-write action plans. Partial failure, retry after `UNKNOWN`, reconciliation and plan approval all depend on per-step facts: can this step be retried safely, can it be undone, and how severe is it? Without declarations those rules end up hard-coded in the kernel or the adapter.

**Adopt.**
- Add to the capability contract (pack data, validated by the registry): `risk` (`read | write_low | write_high | destructive`), `idempotency` (`none | provider_key | natural_key`, with the key source), `reversibility` (`irreversible | compensable:<capability>`).
- The execution-IR ADR uses them in the step model: retry only for declared-idempotent steps; reconciliation for the others; a plan's approval presentation shows its highest-risk step.
- Default for anything unmapped (Phase 8 MCP) is `write_high`; provider hints never set risk.
- **Link to ADR 0024 (owner decision D-3 below):** X-agent's "non-clearable tools always need fresh approval" is the guard that would make a benchmark-only auto-approve profile safe. Auto-approve could never cover `destructive` or `write_high`.

**Phase.** Phase 2 entry gate, with DR-01.

### XA-02 Plugin-isolation import contract (AP-01)

**X-agent.** A `plugin-isolation` contract forbids plugins from importing db, auth, identity, credentials, runtime, the durable engine and API internals.

**e-agent.** Today the Odoo adapter cannot import the store or the secret store, but only incidentally: the layers contract lists the adapters as independent siblings (`kernel | shacl | postgres | pydantic_ai | secretstore_local | odoo`, `pyproject.toml:95`), and the provider contract (`pyproject.toml:144-148`) forbids only kernel, server and `erp.testing`. No contract states the plugin rule. The draft Phase 1d plan moves providers to `e_agent.plugins.*`, outside that sibling list, and adds only "core never imports plugins" (`phase1d…md:30, :314`), not the reverse.

**Adopt.** Add one named contract to the Phase 1d plan, "Plugins are guests": `e_agent.plugins.*` (domain and provider plugins) must not import `e_agent.adapters.postgres`, `e_agent.adapters.secretstore_local`, `e_agent.server` or kernel internals. Credentials reach a plugin only through the scoped `PluginServices` (`sdk/ports.py:183-188`).

**Phase.** 1d.

### XA-03 Enforce declared capability requirements (AP-17)

**X-agent.** "Customer-agnostic read-surface doctrine": discover the tenant's instance at runtime or refuse honestly; never hard-code assumptions.

**e-agent.** `CapabilityContract.required_features` is declared (`contracts/capability.py:30`) and never read anywhere in `src/` (grep). A declared contract field with no enforcer is a silent pass. The bridge-version pin is the only instance check (DR-02).

**Adopt.** The registry refuses a binding whose provider does not declare every `required_features` entry at startup. The Phase 1d sandbox probe reports the instance's features, and a capability whose features are missing is absent from the tool surface with a reason code, not failing at call time. Full runtime discovery of an unknown ERP configuration stays out of scope.

**Phase.** 1d (registry check); Phase 5 (feature probe per new capability).

### XA-04 Gates fail on empty input (AP-24)

**X-agent.** A gate that cannot parse its input fails and prints the number of files scanned. "A gate that scans 0 files and stays green" is a named failure.

**e-agent.** `scripts/release_report.py:243` returns 0 when `passed == total`, so an empty case list reports `0/0` and passes. Today `CASES` is a non-empty constant, so the hole is latent. The harness gate (`tools/harness/src/e_agent_harness/gate.py:50-54`) parses counts but decides on exit codes; pytest already exits non-zero when it collects nothing, so no harness hole was shown.

**Adopt.** Every gate and report fails on zero cases or zero files and prints its count. Keep a finite list of known silent-pass paths in the ENG rules (none exists today) and add `release_report` to it.

**Phase.** None; one small hygiene task.

---

## Confirms existing findings (fold in, do not raise separately)

| AP | X-agent practice | e-agent | Fold into |
|---|---|---|---|
| AP-15 | Errors are never empty results; truncated results are never labelled complete | Partial: completeness `COMPLETE/PARTIAL/UNKNOWN` (`contracts/evidence.py:11-14`), read errors are explicit (`driver.py:402-406`). Missing: result bounding with a truncation marker; observations go to the model whole (`driver.py:402`). Target §7.2 designs per-capability caps [P] | DR-05 and Phase 3 ContextAssembler: the bound and the marker are recorded in `ContextPack.dropped` |
| AP-13, AP-41 | Narrowed tool surface per actor | All agent-visible tools are mounted per run (`server/bootstrap.py:106-133`). Phase 2 `TaskDefinition` fixes the capability set; `kernel/connections.py:38-75` filters unusable connections | Phase 2. **New line only:** search-based progressive disclosure (`find_capabilities`) stays deferred with a trigger: the tool count of one task exceeds what fits the context budget (about 30–40 tools) |
| AP-30, AP-43 | Egress stance, local-only mode, routes as infrastructure | Ollama default, LiteLLM opt-in, loopback endpoints only (ADR 0021, accepted 2026-10-14; data egress for a hosted upstream left to the operator). No egress or local-only setting | DR-05 item 3 (model routes declare their data boundary); a `local_only` profile setting falls out of it |
| AP-05 | One owner per kind of durable data | ADR 0003 (kernel ledger owns side-effect durability); MVP §9 | Already decided; list it as a row in the XA-00 table |
| AP-41 | Send receipts deduplicate retries by client request ID | Has: idempotency key on run creation (`server/api.py:303`) | Nothing to do |
| AP-34 | In-memory per-pod state is the scaling weak point | Same: in-process run store option, `PublicTextBus` (`server/streaming.py:18-26`), 200 ms SSE polling, no rate limits | DR-07 and Phase 6 |
| AP-25, AP-26 | Protocol ports; manual DI at the composition root | Has: `sdk/ports.py:79-210`; `create_app` + `bootstrap.py` | Nothing to do (DR-04 covers kind-string selection) |

---

## Shapes for Phase 7 (design text now, implementation in Phase 7)

### XA-10 Three-plane authorization (AP-07, AP-08, AP-38, AP-52)

**X-agent.** Verb (capability), tenancy (tenant clamp) and resource (classification, ownership, grants) are checked independently; passing one never implies another. Roles are capability sets, never ranks. Explicit deny wins. Identity providers assert identity and never define roles. Staff and customer realms are separated by exact issuer and audience, with tests proving they are disjoint.

**e-agent.** Role membership plus resource scope (`kernel/policy.py:13-31`), default deny, foreign and absent look the same (`server/api.py:55, :370`). The C16 `AuthorizationBundle` (target §13.2) is [P].

**Adopt.** Write C16 in this shape: three named planes, each with its own check and test; `capability_grants` as sets; explicit deny; a sentence in the context view that the IdP never defines e-agent roles and models never authorize. Separate operator and requester realms are only needed with OIDC (C15).

### XA-11 Secrets stay inside the host (AP-12, AP-47)

**X-agent.** A plugin receives an authenticated, SSRF-protected, IP-pinned client, never a raw credential. Envelope encryption uses an AAD that binds tenant and connection, so ciphertext copied to another row fails to decrypt.

**e-agent.** The envelope exists: AES-256-GCM, per-secret DEK, KEK from env or file (`adapters/secretstore_local/store.py:77-92`). **The AAD binds only `secret_ref` and revision** (`store.py:82`), not tenant or connection. `AuthContext.apply()` keeps the secret out of the adapter (`sdk/auth.py:67-92`). The designed `http_client()` is not implemented, there is no egress pinning, and the auth SDK designs `materialize()`, a raw-credential escape hatch (`integration-auth-sdk.md:151`).

**Adopt.** Bind tenant and connection ID into the AAD (a format version bump, `v3`). Put an egress allowlist (host pinning) into the `http_client()` design before the first HTTP provider beyond Odoo. Remove `materialize()` from the auth SDK design (decision D-1).

### XA-12 Route coverage test (AP-10)

**X-agent** rates this not enforced enough: the tenant filter is linted, but nothing checks that every route has a capability.

**Adopt.** A test enumerates the OpenAPI routes and asserts each has an authorization dependency. Today that means `Depends(session)` (`server/api.py:302, :320`) with an explicit allowlist for public routes. It grows into capability dependencies when C16 lands. It is cheap, so it can come before Phase 7.

### XA-13 Record classification and closed cross-user paths (AP-09)

**Split.**
- **Classification** (each stored record class tagged, for example `personal`, `tenant_shared`, `operational`, `infra`, with a test that every table has a tag) belongs in the DR-05 governance ADR next to its field-level classes.
- **The three cross-user paths** (share grants; audited, read-only, time-bounded impersonation; a sealed view-only widening; no fourth path) are multi-user personal-data machinery. They are premature for a single-operator MVP. Record them as a Phase 7 design note so that run visibility (`requester | approvers | operator | auditor`, target §13.2) does not grow an unaudited fourth path.

---

## Cheap hygiene (no phase; one small task)

| ID | Practice | e-agent evidence | Adopt |
|---|---|---|---|
| XA-14 | Typed config; `os.environ` banned (AP-19) | Typed `Profile` (`server/profile.py:70-108`), but raw env reads at `server/bootstrap.py:83,150,155` and `secretstore_local/store.py:50-56`; Ruff select has no TID (`pyproject.toml:57`) | Ruff TID251 ban on `os.environ`/`os.getenv` with an allowlist for the settings module and the KEK read in `secretstore_local` (a legitimate secret source) |
| XA-15 | Supervised background tasks (AP-21) | Bare `asyncio.create_task` at `server/worker.py:71`, `server/api.py:215,217`, `kernel/continuation.py:251`; the worker heartbeat has no done-callback | A `supervised_task` helper that logs and surfaces failure; Ruff bans the bare call outside it. OTel stays with ADR 0008 |
| XA-16 | Secret scan and dependency audit as required checks (AP-36) | CI has lint, types, imports, OpenAPI, tests, Postgres suite, wheels, UI (`.github/workflows/ci.yml:37-90`); no secret or vulnerability scan | Add a secret scan and a dependency vulnerability audit. Skip complexity thresholds, a PR-title lint and Sonar for a single-owner repository |
| XA-17 | Behaviour changes require evals; prompts are code (AP-18, AP-31) | Deterministic replays exist (`tests/replays/erp-model-calls/`, `tests/unit/server/test_recorded_model_replays.py`); the system prompt is a constant (`adapters/pydantic_ai/driver.py:66-74`) with no golden test; there is no model-eval lane | Do not build a new eval system. Name the replay suite the required check for driver, prompt and tool-schema changes; add one prompt golden file. A live model lane stays with ADR 0010 qualification |

---

## Design notes for deferred phases (one paragraph each in their sections)

- **XA-20 Unattended runs (AP-32, AP-44, AP-51), Phase 8.** Triggered runs (C13) carry a job-scoped permission set and a frozen service identity. A user's preferences never apply, and retries follow the declared idempotency (XA-01). This joins the service-principal text already in Phase 8.
- **XA-21 Connection addressing (AP-46), Phases 4 and 8.** Resolution order: explicit argument, then conversation pin, then user default, then the unique eligible connection; ambiguity asks the user. Today ambiguity silently drops the hint (`kernel/connections.py:55-75`). Phase 4 should turn that into `WAITING_INPUT`. Also align the connection status list, which differs between `contracts/connection.py:12-24` and integration management §5.
- **XA-22 Event schema evolution (AP-35), Phase 2.** Events carry `schema_version` (`contracts/events.py:39`) with no upcaster. Phase 2 adds event types and Phase 3 rebuilds runs from events (U3), so record the rule now: a version bump ships with an upcaster and a replay test.
- **XA-23 Explicit omissions (AP-42), Phases 3 and 4.** Nothing is silently dropped from what the model or the user sees; every omission is an explicit part. This matches `ContextPack.dropped` and the core plan's "typed state rather than an ever-growing transcript". Adopt the rule, not X-agent's single `TranscriptDocument` shape.
- **XA-24 A toggle is not cover for a stub (AP-22).** Add to roadmap rule 3 and ENG-TOGGLE: a feature in `shadow` must have a real comparison consumer, and a seam ships with its first consumer. The rest of X-agent's branch policy (release trains, merge queue) does not fit a one-owner repository.
- **XA-25 Knowledge doctrine (AP-16, AP-48, AP-50), Phase 9.** Add to target §9: indexes are projections, never authority (already stated); access re-checks withhold records rather than delete them; sync watermarks advance only after every sink accepts; facts carry valid time and evidence rows, and a superseded fact is kept (bitemporal). Whether models may extract facts is decision D-2.

---

## X-agent's own gaps: do not repeat them

X-agent's review rates these as weak. Each one is a trap e-agent can fall into.

| X-agent gap | e-agent exposure | Guard |
|---|---|---|
| Tenancy only in the application layer: no RLS, about 85 `noqa` suppressions on the tenant lint (AP-33) | Same today: composite tenant keys (`migrations/0001_initial.sql:24-25`) and `WHERE tenant_id` in the store, no RLS | Keep RLS (C15) in Phase 7 and do not let it slip behind a lint with suppressions; any tenant lint allows no inline suppressions |
| In-memory per-pod state for streams, limits and OAuth state (AP-34) | Same (DR-07) | Phase 6; DR-07's single-slot baseline before Phase 5 numbers |
| A framework leaking into a domain package with a contract exemption (AP-06) | Prevented: FastAPI is imported only in `server/api.py`, forbidden in contracts, sdk, kernel and erp (`pyproject.toml:161-165`) | Keep; never add an exemption to make a change fit |
| Rules written but not checked: route capability (AP-10), evals (AP-18) | Same pattern (XA-00, XA-03, XA-12, XA-17) | The XA-00 table makes "no check" visible |
| Event `payload_version` with no upcaster (AP-35) | Same (XA-22) | Upcaster rule in Phase 2 |
| Flags as deploy-time booleans with no per-tenant scope (AP-35) | e-agent's `off/shadow/on` toggles are already stronger by design | Keep roadmap rule 3 |
| A duplicated `Protocol` declared in 9 packages (AP-25) | Not observed | Ports live in `sdk/ports.py` only |
| A fat composition root (AP-26) | Partly: `bootstrap.py` hard-wires kinds (DR-04) | DR-04 |

---

## Deliberately not adopted (with where e-agent decided)

| X-agent practice | e-agent decision | Where |
|---|---|---|
| Contracts live with their producer in per-package `wire/` folders (AP-04) | One shared package of portable records | HLD §4; AGENTS.md "Contracts contain portable records"; target §15 |
| Five named tiers host/domain/platform/foundation/kernel (AP-03) | Layers contract `server > kernel \| adapters > erp > sdk > contracts` | `pyproject.toml:90-99`; a finer split is premature at about 10 distributions |
| Packages must earn their boundary (AP-02) | Already a rule; no change | AGENTS.md "no unused abstractions"; target [C] triggers |
| Caller-owned transactions over repositories (AP-29) | Atomic store methods; the kernel ledger owns durability | ADR 0003; target §12.2 |
| Temporal behind an engine-neutral job contract (AP-32, AP-51, AP-55) | Postgres `run_work` with `SKIP LOCKED`; a durable engine only on a trigger | Target §14; roadmap Phase 9 |
| Standing approvals: always-allow, never-allow (AP-44) | Every write is approved; approval binds the exact normalized action | AGENTS.md; ADR 0006; MVP §7 |
| Guardrail verdict `modify` after approval (AP-44) | A modified action would invalidate the approval digest; `modify` is allowed only before the digest and on text replies | ADR 0006; decided in D-4 |
| Catalog compiler and per-actor immutable snapshots (AP-45) | Domain → capability → binding → connection with host resolution | HLD §5; target §10.1; revisit with MCP (Phase 8) |
| Retry policy, rate limiter, circuit breaker in the plugin SDK (AP-27) | Request limits in Phase 6; retries only for declared-idempotent steps (XA-01) | Roadmap Phase 6 |
| Typed tabular IR on DuckDB and SQL pushdown (AP-49) | Generated queries never run raw; BigQuery adapter [C] | Target §9.1; ADR 0001 |
| A single error hierarchy with a messages module (AP-20) | Kernel `ErrorCode` + `safe_message` (`kernel/errors.py:21-30`), transport mapping in `server/api.py:234-244` | Enough at this size |
| Per-plugin crash isolation (AP-11) | First-party plugins run in process; a subprocess is not a sandbox | HLD §4 (line 111), §10 (line 201) |
| Hosted-defaults preservation for downstream products (AP-23) | No downstream product yet; Phase 1d makes the core reusable | Revisit with the first second distribution |
| GKE, Argo CD, merge queue, release branches (AP-39, AP-54) | Local-first; process split in Phase 6 | Target §11–§12 |
| Native shells, terminal client, one `ChatSurface` rule (AP-53) | Layered replaceable UI | ADR 0011; Phase 4 chat |

---

## Decisions for the owner

All four were decided by the owner on 2026-10-14; the last column records the decision. The design rewrite carries them into the auth SDK design (D-1), target §9 (D-2), ADR 0024 (D-3) and the guardrail section of the execution-IR design (D-4).

| ID | Decision | Options | Recommendation |
|---|---|---|---|
| D-1 | Keep the `materialize()` raw-credential escape hatch in the auth SDK (`integration-auth-sdk.md:151`)? | Keep it, audited and declared in the manifest; or remove it so plugins never hold a raw credential (X-agent's rule) | **Owner, 2026-10-14: remove.** Plugins never hold a raw credential. If a vendor SDK leaves no alternative, an ADR re-adds it for that one adapter, which then runs in a separate process |
| D-2 | May a model extract knowledge facts from text? Target §9.1 has "Extract under declared ontology → curate"; X-agent forbids model-proposed facts entirely | Model extraction yields candidates that only curation promotes; or facts only from structured connector fields and people | **Owner, 2026-10-14: support both, switchable.** A knowledge setting `fact_sources: structured_only \| with_model_candidates`. In both modes model output only ever creates candidates with a source span; curation alone accepts them. `/health/ready` and the evidence bundle report the mode |
| D-3 | ADR 0024: benchmark-only auto-approve profile | Allowed for `read` and `write_low` only, with `write_high` and `destructive` always needing fresh approval; or no auto-approve | **Owner, 2026-10-14: yes.** Allowed only for `read` and `write_low`, only once XA-01 risk classes exist, and only in a profile marked benchmark-only; `write_high` and `destructive` always need fresh approval; `/health/ready` reports the profile |
| D-4 | Guardrail stages (input, tool, output) | Adopt allow, block and confirm only; or also `modify` before the digest is computed | **Owner, 2026-10-14:** allow, block and confirm at every stage. `modify` only in two places: (1) on a proposed action before its approval digest is computed, with the change shown to the approver ("proposed 500, adjusted to 200 by rule R"); (2) on the model's text reply (for example redaction), which changes no external data. Never after approval |

## AGENTS.md rewrite (rewrite step 5)

AGENTS.md is rewritten after the consolidated design (step 4), so that it summarises the new baseline instead of a moving one. It points to the principle → practice → check table (XA-00) rather than restating it. It keeps the parts that still hold (purpose and state, environment boundaries, repository map, verification) and changes these:

| Area | Change | Source |
|---|---|---|
| Principles | Replace the scattered rule lists with a short list of binding principles, each linking to its row in the XA-00 table and naming its check; say that a rule without a check is a backlog item, not an assumption | XA-00 |
| Architecture rules | Add: plugins never import the store, the secret store, the server or kernel internals; never loosen an import contract or add an exemption to make a change fit | XA-02; X-agent's own gap AP-06 |
| Execution and data integrity | Add: every capability declares risk, idempotency and reversibility; only declared-idempotent steps are retried; unmapped tools default to `write_high` | XA-01 |
| Execution and data integrity | Add: guardrails allow, block or confirm at every stage; `modify` only before the approval digest (shown to the approver) or on text replies, never after approval | D-4 |
| Execution and data integrity | Add: a declared capability requirement is enforced or the capability is absent with a reason; never fail silently at call time | XA-03 |
| Execution and data integrity | Add: results are never fabricated: an error is never an empty result, and a bounded result carries a truncation marker | AP-15 |
| Plugins and knowledge | Add: plugins never hold a raw credential (no `materialize()`) | D-1 |
| Plugins and knowledge | Add: facts come from structure or people; model output only creates candidates that curation accepts; the fact-source mode is a reported setting | D-2 |
| Toggles | Add to the toggle rule: a feature in `shadow` needs a real comparison consumer, and a seam ships with its first consumer; a toggle is not cover for a stub | XA-24 |
| Approval | Add: auto-approve exists only in a benchmark-only profile, only for `read` and `write_low` | D-3 |
| Development and verification | Add: typed settings, no direct `os.environ`; supervised background tasks; gates fail on zero input and print their count; the replay suite is required for driver, prompt and tool-schema changes | XA-14, XA-15, XA-04, XA-17 |
| Documentation | Replace stale status lines with a pointer to the README status (DR-10); name the one roadmap | DR-10 |

Validate the rewrite with `uv run python scripts/check_agent_skills.py` where skills reference AGENTS.md sections, and update `eng-foundations` ENG-* rules where a rule moves.

## Advisor reviews of the rewrite (2026-10-14 to 2026-10-15)

Each rewrite step was reviewed by the advisor model before it was recorded as done. Findings and the fix applied:

| Step | Finding | Fix |
|---|---|---|
| 2 | Reason codes forked by plan length; mode table had two homes; acceptance check reachable from RUNNING unclear; ADR 0015 annotation; binding record names | Codes independent of plan length (only `PLAN_LINEAGE_REJECTED`, `ACCEPTANCE_UNMET` new); mode table only in target §6.4.8; transitions stated; names aligned |
| 3 | Findings listed in the session record; all fixed before step 4 | ADR 0030, target §13.3, T23–T24 amended |
| 4 | Target §18 note claimed the roadmap cites it (it does not) | Clause removed |
| 4 | Target header date and "ADR candidates 0018–0021" were stale | Date 2026-10-14 added; "ADRs 0018–0021, accepted 2026-10-14" |
| 4 | §5.5 merged marker overclaimed the correlation id | Marker says actor attribution, not the correlation id |
| 4 | Integration docs still said "Phase 2" for admin pages in their bodies | Headers state that their "Phase 2" is the post-MVP phase, now roadmap Phase 8 |
| 5 | AGENTS.md toggle rule had two sentences the roadmap's rule 3 lacked | Added to roadmap rule 3 with the XA-24 citation |
| 5 | principles.md section mapping put PR-10 under Plugins; AGENTS.md cites it under Execution | Mapping moved; a row added for the Principles and Documentation sections |
| 5 | AGENTS.md pointed to a README "status section" that is a bold paragraph | Wording matches the README |
| 5 | Final sign-off after the fixes | Step 5 complete; no further edits |
| 4–5 | Independent `reviewer` agent: PR-01 cited 11 import-linter contracts; there are 9 | Corrected here and in principles.md |
| 4–5 | Reviewer: AGENTS.md stated PR-10, PR-20 and PR-40 in the present tense although none is built | Rewritten as targets with their phase and an interim rule |
| 4–5 | Reviewer: PR-40 check placed in Phase 2; ADR 0024 puts it in Phase 5 and requires explicit declarations | Backlog row and PR-40 row corrected |
| 4–5 | Reviewer: §5.1 merged marker overclaimed principle 2 | Marker narrowed to principle 1 and actor attribution |
| 4–5 | Reviewer: "20 rows have no check" mixed missing and partial checks | 17 missing plus 3 partial |
| 6 | Advisor: hygiene H.4 claimed "9 files, 9 tasks"; there are 8 recordings and 8 tasks | Count corrected; the test compares `*.json` stems only |
| 6 | Advisor: H.3 put `supervised_task` in the kernel, which adapters and plugins may not import | Moved to `e_agent/sdk/tasks.py` |
| 6 | Advisor: Design refs and task file lists drifted; H.2 call sites will change after 1d.6; the guest-contract claim relied on an anchored grep | Files added to 1d.11, H.2 and H.3; re-take note in H.2; unanchored grep found no in-function imports |

Follow-ups the review left open: ENG rules in `eng-foundations` for PR-06, 10, 20, 21, 31, 32, 37, 38 and 40; the 20 backlog entries in principles.md (17 rows without a check, 3 partial).

## Not checked

- X-agent's own claims (all items): not verified; screenshots only.
- AP-40 "exactly one audit record per invocation": whether e-agent emits exactly one terminal event per action was not checked.
- Factory purity (AP-45): whether `create_plugin(services)` does any I/O was not checked.
- Branch protection and required-check settings live outside the repository and were not seen.
