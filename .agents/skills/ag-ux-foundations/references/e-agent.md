# e-agent binding requirements (tier R)

These requirements are binding. They come from accepted ADRs, repository rules in [AGENTS.md](../../../../AGENTS.md) and explicit owner decisions. A violation of any EA requirement may be rated Blocker, regardless of the AG cap on the related criterion. A criterion in the standard can never weaken them, and they can be changed only through an ADR, never silently in a review or a gap audit. The current UI implementation is audited against these requirements and against the standard; the audit result is a finding, not a reason to relax either side.

Source conventions:

- Links point to files that exist in this checkout. Documents that exist only as uncommitted files in the owner's main checkout (as of 2026-10-11) are cited as plain code paths, for example `docs/adr/0016-selectable-agent-surfaces.md`. Where the committed and the uncommitted version of a document differ for a requirement, the section is cited from the main-checkout version and says so.
- Kind is one of `ADR` (stated in an accepted ADR), `AGENTS.md` (stated as a repository rule) or `Owner decision` (chosen by the owner on 2026-10-11, recorded here because no accepted ADR yet states it).

### EA-1 — Server authority

- **Requirement:** The server is authoritative for capabilities, connections, scope, exact action versions, approval and verification. The client renders these values and never derives, widens or promotes them; model output cannot select credentials or connections, grant approval or mark its own task verified.
- **Binding source:** [ADR 0011](../../../../docs/adr/0011-layered-replaceable-ui.md) decisions 1 and 4; [ADR 0013](../../../../docs/adr/0013-integration-auth-sdk-and-delegated-connections.md) decisions 3 and 5; [UI architecture §1](../../../../docs/ui-architecture.md) ("Approval, policy and validation stay on the server"); [AGENTS.md](../../../../AGENTS.md) architecture rules and execution rules; `docs/adr/0014-mvp-remediation-boundaries.md` (uncommitted on main as of 2026-10-11), approval binding to policy, connection and credential revisions.
- **Standard cross-reference:** AG-FE-1, AG-FE-12, AG-APPR-7, AG-ID-3
- **Kind:** ADR

### EA-2 — Exact one-action approval

- **Requirement:** The decision surface renders the complete server-owned approval presentation for exactly one action; the client never reinterprets terms. Approve is disabled on a digest mismatch, expiry or staleness, and a changed or expired authorization requires re-review before execution.
- **Binding source:** [ADR 0011](../../../../docs/adr/0011-layered-replaceable-ui.md) decisions 4 and 5 (the server owns the approval presentation and every UI renders it); [ADR 0006](../../../../docs/adr/0006-approval-digest-canonicalization.md) (digest canonicalization only); [UI architecture §4.2, §4.3 and §6](../../../../docs/ui-architecture.md); [AGENTS.md](../../../../AGENTS.md) ("Approval binds the exact normalized action, scope and versions ... reject stale approval"); [ADR 0013](../../../../docs/adr/0013-integration-auth-sdk-and-delegated-connections.md) verification (a credential change makes the approval stale); `docs/adr/0014-mvp-remediation-boundaries.md` (uncommitted on main as of 2026-10-11), approval keyed by exact action, digest and run revision.
- **Standard cross-reference:** AG-APPR-1, AG-APPR-2, AG-APPR-9, AG-FE-1
- **Kind:** ADR

### EA-3 — Approved, committed and verified are separate

- **Requirement:** Approved (decision recorded), committed (effect executed) and verified (independently read back) are separate states with separate labels. Success is claimed only for a verified outcome, and the verified marker is rendered only from a server-provided field.
- **Binding source:** [AGENTS.md](../../../../AGENTS.md) ("Verify outcomes by independent authorized read-back. Distinguish committed effect from verified business success"; "Model output ... cannot ... mark its own task verified"); `docs/adr/0015-task-workspace-presentation.md` (uncommitted on main as of 2026-10-11), verified result values come only from a VERIFIED action correlated with its outcome report; `docs/ui-architecture.md` §10 (uncommitted on main as of 2026-10-11), "Status copy distinguishes approval recorded, checking a result, verified, failed and unresolved".
- **Standard cross-reference:** AG-APPR-6, AG-FE-12
- **Kind:** ADR / AGENTS.md

### EA-4 — Unknown outcomes are reconciled, never resent

- **Requirement:** An external timeout can mean `UNKNOWN`. A possibly committed write is never blindly resent or retried; the interface says the outcome is unknown and only independent read-back reconciliation can resolve it.
- **Binding source:** [AGENTS.md](../../../../AGENTS.md) execution rules ("External timeouts can mean UNKNOWN. Never blindly replay a possibly committed write"); `docs/adr/0014-mvp-remediation-boundaries.md` (uncommitted on main as of 2026-10-11), a negative lookup during an uncertain call does not prove no effect and reconciliation stays unresolved until authoritative evidence exists.
- **Standard cross-reference:** AG-UNC-2
- **Kind:** AGENTS.md

### EA-5 — No hidden reasoning, simulated progress or uncalibrated confidence

- **Requirement:** No hidden model reasoning is displayed, streamed or persisted, and no simulated progress, invented plan or progress estimate is shown; activity reflects real recorded events only. No uncalibrated numeric confidence or score is displayed; calibrated numeric confidence is allowed only through an ADR with calibration evidence.
- **Binding source:** [ADR 0007](../../../../docs/adr/0007-run-event-stream-contract.md) decision 5 ("Model thinking is never streamed"); [AGENTS.md](../../../../AGENTS.md) ("do not persist hidden chain-of-thought"); `docs/adr/0014-mvp-remediation-boundaries.md` (uncommitted on main as of 2026-10-11), only public text parts are emitted and reasoning is excluded; `docs/adr/0015-task-workspace-presentation.md` (uncommitted on main as of 2026-10-11), "The UI does not invent subtotals, resource names or progress percentages"; `docs/ui-architecture.md` §10 (uncommitted on main as of 2026-10-11), the Workbench shows only authoritative run state "without generated plans or progress estimates"; [AG UX skills design §2](../../../../docs/superpowers/specs/2026-10-11-ag-ux-skills-design.md) (owner approval 2026-10-11: no uncalibrated numeric scores; calibrated numeric confidence only through an ADR with calibration evidence); `research/15-agentic-ux-patterns-mockup.md` (uncommitted on main as of 2026-10-11) line 32, "not hidden reasoning, confidence percentages or simulated progress estimates".
- **Standard cross-reference:** AG-EXPL-1, AG-STAT-2, AG-EXPL-4
- **Kind:** ADR / Owner decision

### EA-6 — No provider identifiers in UI packages

- **Requirement:** UI packages contain no provider or third-party system identifiers. Provider names, icons and forms come from manifests through the server API.
- **Binding source:** [AGENTS.md](../../../../AGENTS.md) architecture rules; [UI architecture §6a](../../../../docs/ui-architecture.md) (provider neutrality gate); [ADR 0011](../../../../docs/adr/0011-layered-replaceable-ui.md) decision 3 (system neutrality).
- **Standard cross-reference:** none. No criterion in the standard addresses provider neutrality, because the standard is product-neutral by design. Note: AG-ID-3 partially overlaps the "model never selects connections" clause only.
- **Kind:** AGENTS.md

### EA-7 — No model-generated approval renderer

- **Requirement:** No model-generated approval renderer and no arbitrary JSON-to-UI. Agent-generated UI, if ever added, may only reference a host-trusted component catalog and never covers an approval or policy surface; model or retrieved content cannot imitate a decision surface.
- **Binding source:** [ADR 0011](../../../../docs/adr/0011-layered-replaceable-ui.md) decision 8; [UI architecture §2 and §7](../../../../docs/ui-architecture.md) (non-goals: "never for approval or policy surfaces").
- **Standard cross-reference:** AG-ID-2, AG-ID-6
- **Kind:** ADR

### EA-8 — Missing access or information is explicit

- **Requirement:** Missing access, connection, scope or information is shown explicitly and is never treated or rendered as an empty, zero, granted or approved value; an unknown event or schema version is shown as unsupported and never guessed.
- **Binding source:** [AGENTS.md](../../../../AGENTS.md) ("explicit missing/unknown states. Never treat an absent fact as an approved fact"); [ADR 0013](../../../../docs/adr/0013-integration-auth-sdk-and-delegated-connections.md) decision 6 (a missing connection or scope pauses the run as `connect_required`); [UI architecture §4.1](../../../../docs/ui-architecture.md) (unknown event shown as unsupported); `docs/adr/0015-task-workspace-presentation.md` (uncommitted on main as of 2026-10-11), unsupported versions retained as unsupported activity and unsupported value shapes fail closed.
- **Standard cross-reference:** AG-UNC-4, AG-FE-13
- **Kind:** ADR

### EA-9 — Presentation is separate from business state

- **Requirement:** Switching surface, placement or appearance is separate from business state. It keeps the active task, exact approval state and in-progress work, never submits a task, grants approval or chooses a connection, and resets an open confirmation to review.
- **Binding source:** `docs/adr/0016-selectable-agent-surfaces.md` (uncommitted on main as of 2026-10-11), Decision paragraphs 2 and 3; [ADR 0011](../../../../docs/adr/0011-layered-replaceable-ui.md) decision 2 (customization tiers); `docs/ui-architecture.md` §10 "Selectable presentation surfaces" (uncommitted on main as of 2026-10-11).
- **Standard cross-reference:** AG-MEM-1
- **Kind:** ADR

### EA-10 — Conversation first, closable artifact workspace

- **Requirement:** The conversation is the primary surface. The task artifact opens in a workspace that the user can close, with sources and activity inside the workspace; enterprise breadth comes from supported capabilities and authorization, not from a homepage catalog.
- **Binding source:** `research/16-conversation-workspace-revision.md` (uncommitted on main as of 2026-10-11), established by the owner's rejection of study 03; owner approval 2026-10-11. No accepted ADR states it yet, and production implementation stays paused in that document.
- **Standard cross-reference:** AG-CTX-1, AG-CTRL-2
- **Kind:** Owner decision

### EA-11 — Sample data is labelled as sample

- **Requirement:** Sample, fixture or fictional data is always labelled as sample and is never presented as a real business record or as live evidence.
- **Binding source:** `research/16-conversation-workspace-revision.md` (uncommitted on main as of 2026-10-11), examples kept "explicitly fictional"; `research/15-agentic-ux-patterns-mockup.md` (uncommitted on main as of 2026-10-11) line 11, "All data and outcomes are labelled as samples"; owner approval 2026-10-11. Related repository rule: [AGENTS.md](../../../../AGENTS.md) ("Keep deterministic fixtures distinct from live model/ERP results"), which governs evidence reporting rather than UI labels.
- **Standard cross-reference:** AG-ID-1
- **Kind:** Owner decision

## Current stack choices

`frontend.md` records no current product choices; the e-agent stack is recorded here. Each choice below is a current choice and can be replaced through an ADR; the audit checks it against the listed criteria, and no version is recorded.

- React: current choice, audited against AG-FE-1, AG-FE-2 and AG-FE-4.
- React Aria Components: current choice, audited against AG-FE-5 and AG-FE-7.
- DTCG token compiler: current choice, audited against AG-DS-1 and AG-DS-6.
- Namespaced plain CSS: current choice, audited against AG-FE-6, AG-FE-8 and AG-DS-1.
- External store (framework-free run store): current choice, audited against AG-FE-1, AG-FE-2 and AG-FE-4.
- Hash routes: current choice, audited against AG-FE-1 and AG-FE-10.
- Vite component gallery: current choice, audited against AG-FE-9 and AG-DS-2.
- Vitest: current choice, audited against AG-FE-9 and AG-FE-11.
- Playwright: current choice, audited against AG-FE-9 and AG-FE-11.

Current-state snapshot (2026-10-11, per the design spec section 7): no CSS container queries are used in `ui/`; `useContainerWidth.ts` uses ResizeObserver.
