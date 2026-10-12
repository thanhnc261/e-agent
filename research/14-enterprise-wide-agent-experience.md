# Enterprise-wide agent experience: research and mockup revision 2

Date: 2026-10-08. Status: product-vision mockup, using synthetic fixtures only. User clarification: e-agent serves enterprise work across integrations; ERP is one domain, not the product boundary. This study supersedes the procurement-centered visual framing of [research 13](13-agentic-overlay-mockup-study.md), while preserving that report and the [original prototype](mockups/procurement-overlay-v1/index.html).

## Answer: is e-agent only for ERP?

No. The [high-level design](../docs/high-level-design.md) defines a domain-neutral kernel, independently packaged provider adapters and portable capability contracts. The [integration design](../docs/integration-management.md) and [auth SDK design](../docs/integration-auth-sdk.md) describe manifest-driven configuration, scoped connections and shared versus delegated identity. Accepted ADRs 0002, 0011, 0012 and 0013 establish these boundaries.

However, this is **designed extensibility**, not universal integration availability. The implemented and tested product remains concentrated on eight ERP tasks and the procurement spine; generic integration administration, broader OAuth flows, external CRM/workspace providers and the illustrated multi-application workflows are not delivered by this mockup. The latest remediation retest remains the authority on current release evidence.

A new enterprise integration needs a compatible provider interface, an implemented and admitted adapter, supported business capabilities, authorized identity/resource scope, tested effect semantics and appropriate outcome verification. Custom APIs and compatible MCP servers can be integration mechanisms. They do not automatically provide domain semantics, correct permission mapping, replay safety or enterprise readiness. Some enterprise requirements will require new domain packs or contracts and additional product work.

## Research findings

Primary sources consulted on 2026-10-08. These are vendor documentation and protocol specifications, not independent comparative studies. Each design implication below is a project-specific inference.

| Source | Observed pattern | Implication for the mockup |
|---|---|---|
| [Glean: how connectors power the experience](https://docs.glean.com/connectors/connectors-power-glean) | Examples combine tickets, documents, communication and CRM context into a task-oriented experience. | Lead with business outcomes across departments. Put app identity inside context and evidence, rather than making one provider the shell. |
| [Glean: indexing and tools](https://docs.glean.com/connectors/configure-actions-in-datasource/config-actions-mcp-from-datasource) | Indexed content and runtime tools serve different purposes; tools may read or act without making all content searchable. | Show separate read and write capabilities. An available connection must not imply every operation is available. |
| [Glean: tools and permissions](https://docs.glean.com/agents/actions/introduction-to-actions) | Tool availability and confirmation behavior are controlled through configured permissions and admin settings. | Distinguish connection management from action approval. e-agent retains its stricter explicit approval baseline for business mutations. |
| [Microsoft: Copilot connector models](https://learn.microsoft.com/en-us/microsoft-365/copilot/connectors/overview) | Synced connectors index content; federated connectors retrieve at runtime. Access and setup models differ. | Preserve source path, revision and observation time. A cached search result and a direct transactional read are different evidence. |
| [Atlassian: connector management](https://support.atlassian.com/organization-administration/docs/manage-your-teamwork-graph-connectors/) | Organization administration governs connectors; third-party sources extend search, chat and agent experiences. | Make managed availability visible while showing the current user's usable connection and scope. |
| [Slack: enterprise search](https://slack.com/help/articles/39044407124755-Set-up-and-manage-Slack-enterprise-search) | Permitted content from other applications appears within an existing work surface. | Preserve an embeddable task surface alongside a neutral standalone home. |
| [MCP tools specification, 2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25/server/tools) | Tools expose schema-described operations; the specification recommends visible invocations and human controls. Annotations are not inherently trustworthy. | Treat MCP as a possible adapter transport. Host admission, policy, exact approval, durable evidence and verification still govern invocation. |

The Microsoft page consulted simultaneously mentions an early-October write rollout and retains a read-only statement. This study therefore does **not** infer universal current write availability from that page or use the rollout as an implementation dependency. Source-specific features and product plans require verification when adopting them.

The previous research on Microsoft agent UX and Carbon's contextual explainability remains relevant. This revision changes information architecture and scenario breadth, rather than merely changing the color palette.

## Product model

The user should think: **I have an outcome → the agent gathers permitted context → I inspect the answer or proposed action → each authorized effect has an inspectable result.**

The product has four persistent places:

1. **Overview:** natural-language task entry, cross-department workflow examples and recent work.
2. **My work:** resumable tasks with their state and context, retained for the prototype session.
3. **Needs review:** pending decisions, without requiring users to search through conversations.
4. **Connections:** app metadata, usable capabilities, source scope, identity and missing access.

The overlay is the portable task surface, with floating, docked and expanded placement. It follows the same task across appearances. It does not belong to procurement, a CRM vendor, or a named agent persona. No multi-agent architecture is implied by a task using several applications.

### Keep the four integration concepts separate

| Concept | Example in the handoff | Responsibility |
|---|---|---|
| Domain | Customer success / document collaboration / communication | Business semantics and allowed effects |
| Capability | Read account, create document, post message | Portable input/output and outcome contract |
| Provider binding | A particular CRM/document/chat implementation | Mapping to provider API and guarantees |
| Connection | Jamie's approved account in the Northstar workspace | Identity, credentials, scope, version and health |

Provider names and display metadata in the prototype come from [fixtures.js](mockups/agentic-overlay/fixtures.js), outside production `ui/` packages. The rendering code does not contain provider-name conditionals. These fixture objects are **not** claimed to implement the production manifest contract. In production, admitted server projections must supply this metadata.

## Reworked scenarios

| Scenario | Context and surface | Decision and result |
|---|---|---|
| Customer handoff | CRM account + success plan + internal channel. Draft document artifact, followed by message artifact. | Approve document creation; commit and read back; separately approve the exact team message. No blanket approval of a multi-app plan. |
| Knowledge answer | Synthetic travel policy plus an announcement pointing to that policy. | Cited read-only answer, source inspector and observation time. No write-approval button. |
| IT service triage | Assigned request + access runbook. | Internal-comment proposal. It does not grant access, provision users or close the ticket. |
| People onboarding | Handbook is available; the people connection is absent. | Explain unknown role/manager/date. Offer a general checklist or a local access-request preview, without granting scope. |
| Procurement | Stock shortage + supplier offer. | Existing draft-PO use case appears as one Operations workflow among several. |
| Custom/internal systems | Connection catalog and integration-path explanation. | Explain the path through supported capability, adapter admission, scoped identity and validation. No pretend one-click universal connector. |

The illustrative provider names are familiar examples, not an installed integration inventory, implementation claim or commercial partnership. Available means available **inside the fixture**. The persistent prototype label and connection-page copy make this distinction explicit.

### Cross-application writes require more than one success badge

A document created successfully followed by a lost message response is a **partial verified result with an unresolved effect**. The mockup shows the document as verified, the message as unknown, and a read-only status check. It neither reports total success nor repeats the message or rolls the document back.

Each approval displays operation, content, destination, audience, acting identity, connection version, workspace and proposal revision. A second operation needs a second confirmation. Editing creates a new review revision. The simulation does not compute a real digest or validate domain rules, and edits do not regenerate dependent artifacts; the next message remains a separately reviewed artifact.

Read access to a source does not itself authorize redistribution. The handoff fixture explicitly states that the summary is cleared for the stated internal audience; the linked document keeps its existing folder access. Production requires host-enforced disclosure/resource policy, audience revalidation and explicit unknowns when membership or authorization cannot be established. A channel-membership count alone is not a disclosure check.

## Technology assessment

| Layer | Recommendation | Reason / limit |
|---|---|---|
| Default presentation | Retain repository React, TypeScript, React Aria and token tooling. | Reuse accessible behavior and existing layering. The static mockup intentionally adds no production dependencies. |
| Task state and events | Retain typed host API, ui-core, durable SSE and approval machine. | Multiple apps do not justify moving policy or outcome authority into prompts or browser state. |
| Embedding | Retain the custom-element/Shadow-DOM product route. | This single-document prototype demonstrates placement, not actual embedding isolation. |
| External integrations | Independently packaged native API adapters; compatible MCP via admitted adapter where useful. | Transport interoperability does not supply business guarantees. All reads and writes still pass through authorization and the gateway. |
| Discovery/configuration | Manifest metadata plus schemas, current capabilities and connection projections. | End users inspect/request access; only authorized admin/user flows change configuration. Never let model text install plugins. |
| Authentication | Continue shared/delegated separation and scoped auth SDK. | The broader OAuth engine is designed but not implemented by this work. Do not silently substitute a shared identity for a revoked user write. |
| Enterprise knowledge | Distinguish indexed search, live reads and derived answers. | ACL propagation, deletion, freshness, provenance and semantic migration remain required; a connector logo proves none of them. |
| AG-UI | Optional future event adapter. | [Its protocol](https://docs.ag-ui.com/introduction) addresses agent–UI interaction; it is not the e-agent ledger or policy system. |
| A2UI | Research only for future constrained display artifacts. | [Declarative UI](https://a2ui.org/) is distinct from tool integration. Generated approval/policy surfaces remain out of scope. |

No architecture ADR is changed because this is an isolated visual/interaction study. Promoting its cross-domain workflows, integration administration and wider auth into the product requires concrete implementation scope and the appropriate architecture decisions, tests and qualification.

## Artifact, operation and evidence

- [Current mockup](mockups/agentic-overlay/index.html), [reference board](mockups/agentic-overlay/board.html), [QA report](mockups/agentic-overlay/QA.md).
- [Preserved procurement v1](mockups/procurement-overlay-v1/index.html), including its original screenshots and verification files.
- Shared interaction and rendering: [app.js](mockups/agentic-overlay/app.js). Authored connection/task data: [fixtures.js](mockups/agentic-overlay/fixtures.js).

Run from the repository root:

```bash
python3 -m http.server 4178 --bind 127.0.0.1 --directory research/mockups/agentic-overlay
# In another terminal, with the repository UI dependencies installed:
node research/mockups/agentic-overlay/verify.mjs
```

Open `http://127.0.0.1:4178`. Use workflow cards, source links, connection details and per-action controls. The bottom selector jumps between synthetic states; it is a design-review aid rather than product UI. The prototype's free-text entry opens a guided workflow chooser and retains the original draft, instead of pretending a general model fulfilled an arbitrary request. No network-connected model, provider, credentials or business system is involved.

## Evaluation and remaining work

Evaluate with people from sales/customer success, IT, people operations and procurement. Check whether they can discover a relevant outcome, distinguish read from write, explain the exact audience and identity, recognize unavailable context and recover from partial completion without repeating a write. Compare Calm, AI Presence and Operator appearances on the same task, on desktop and mobile. Test keyboard, screen readers, zoom, contrast and localized copy before integrating.

Automated browser checks validate the prototype mechanics, not real approval security, multi-domain product support, accessibility certification or enterprise readiness. Broad provider implementations, actual cross-domain orchestration, production identity, live verification and user research remain unimplemented here.
