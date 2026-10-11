# Agentic UI/UX patterns

Patterns are tier-4 application guidance (S-13 is a practitioner library, read partially: overviews of all pages, plus do/don't sections for four) and never override a criterion. Each of the 32 patterns in S-13 has a decision: apply, limit, or exclude with a reason. Every decision cites the `AG-*` criteria that govern it, and every limit or exclusion keeps the criteria's stricter rule. Source locators are S-13 sub-page slugs.

### Human-in-the-Loop

- **Decision:** apply
- **Criteria:** AG-APPR-1, AG-APPR-4, AG-CTRL-4
- **Application:** Route consequential decisions to a person at defined points, with the exact action shown and an explicit confirmation step proportional to risk.
- **Limits:** Review capacity is finite: queues that outgrow it push reviewers to rush, so friction stays proportional to risk and the interface never lowers a tier to reduce load (AG-APPR-7). Only the overview was read.
- **Source:** S-13 (human-in-the-loop)

### Approval Queues & Escalation Chains

- **Decision:** apply
- **Criteria:** AG-APPR-1, AG-APPR-5, AG-APPR-7, AG-APPR-9
- **Application:** Render the risk tier assigned by system policy; package decisions with summary, exact change, impact and reversibility; show expiry and escalation; mark a decision invalid when the state it relied on drifts after rehydration.
- **Limits:** The interface never assigns or lowers a tier. The source's auto-approval of reversible actions is a policy decision outside the interface. The page has no do/don't section, so only its overview was read.
- **Source:** S-13 (risk-tiered-approval-escalation)

### Mixed-Initiative Interface

- **Decision:** apply
- **Criteria:** AG-CTRL-3, AG-CTRL-2
- **Application:** Show who holds initiative at every moment and give a visible handoff whenever it changes; keep suggestion and override paths.
- **Limits:** Indicators are easily missed, so the agent never takes over input without a handoff the user can see.
- **Source:** S-13 (mixed-initiative-interface-patterns)

### Agent Status & Activity

- **Decision:** apply
- **Criteria:** AG-STAT-1, AG-STAT-2, AG-STAT-3, AG-STAT-4
- **Application:** Show the current state in the vocabulary of the normative state model, driven by real events, with stale or disconnected data distinct and status exposed to assistive technology.
- **Limits:** Thinking animations and progress bars are allowed only when backed by real events; frequent updates must not create false urgency.
- **Source:** S-13 (agent-status-activity-patterns)

### Progressive Disclosure

- **Decision:** apply
- **Criteria:** AG-EXPL-3, AG-APPR-3, AG-A11Y-2
- **Application:** Start with essentials and reveal detail on demand, nest at most three to four levels, and keep disclosure controls keyboard-operable.
- **Limits:** Material terms on a decision surface and other critical information are never only inside a collapsed level. The source lists smooth transition animation as a do; motion must stay disableable (AG-A11Y-5).
- **Source:** S-13 (progressive-disclosure-patterns)

### Trust and Transparency

- **Decision:** apply
- **Criteria:** AG-ID-1, AG-EXPL-1, AG-EXPL-2, AG-EXPL-3, AG-APPR-4
- **Application:** Mark AI-generated content, give source-attributed explanations in layers, and add mindful friction for high-stakes decisions.
- **Limits:** Explanations rest on facts, rules and sources, never model chain-of-thought (AG-EXPL-1). Confidence indicators follow AG-EXPL-4.
- **Source:** S-13 (trust-transparency-patterns)

### Error Handling and Recovery

- **Decision:** apply
- **Criteria:** AG-UNC-3, AG-UNC-2, AG-MEM-1
- **Application:** State problem, cause where known and an authorized next step in plain text near the affected action, keep the user's work, and keep technical detail behind disclosure.
- **Limits:** Recovery steps must be authorized and actually work; an action with unknown effect gets a safe check, never a blind retry (AG-UNC-2). Raw stack traces are not shown to end users.
- **Source:** S-13 (error-recovery-patterns)

### Chat Interface

- **Decision:** apply
- **Criteria:** AG-MEM-1, AG-ID-1, AG-ID-2, AG-ID-6
- **Application:** Use threads and preserved context so the active task survives navigation; mark message origin; render all message content as inert text.
- **Limits:** Rich or interactive message content must not imitate system UI or a decision surface (AG-ID-6). Collaboration signals are out of scope until multi-user use exists.
- **Source:** S-13 (chat-interface-patterns)

### Conversational Interface

- **Decision:** apply
- **Criteria:** AG-CTX-2, AG-UNC-1, AG-CTRL-3
- **Application:** Time proactive engagement to context, defer it during focus conditions, deliver it as an actionable artifact, and ask a clarifying question when a request is ambiguous.
- **Limits:** Agent-initiated conversation is limited to what AG-CTX-2 permits; modality switching belongs to the excluded multimodal pattern.
- **Source:** S-13 (conversational-interface-patterns)

### Onboarding and Education

- **Decision:** apply
- **Criteria:** AG-DISC-2, AG-DISC-3, AG-MEM-4, AG-ENT-2
- **Application:** State capabilities and limits at the entry surface, introduce features in stages, offer contextual help, and announce changes to capabilities.
- **Limits:** Users who skip onboarding still form mental models, so the capability and limits statement sits on the entry surface rather than only in a tour.
- **Source:** S-13 (onboarding-education-patterns)

### Accessibility in Agent Design

- **Decision:** apply
- **Criteria:** AG-A11Y-1, AG-A11Y-2, AG-A11Y-3, AG-A11Y-4, AG-A11Y-5, AG-STAT-4
- **Application:** Meet WCAG 2.2 AA in every state, follow APG semantics, support reflow and resize, and expose status messages to assistive technology.
- **Limits:** Automated checkers miss gaps, so verification includes review with assistive technology.
- **Source:** S-13 (accessibility-agent-design)

### Ambient Agent

- **Decision:** apply
- **Criteria:** AG-CTX-2, AG-CTRL-3, AG-CTRL-5, AG-MEM-2
- **Application:** Background presence only as visible, controllable, non-interrupting help; anticipatory output arrives as an artifact the user can act on or dismiss.
- **Limits:** Background actions must not be unpredictable: initiative stays visible, capabilities can be turned off, and no consequential action bypasses the decision flow (AG-APPR-1).
- **Source:** S-13 (ambient-agent-patterns)

### Cross-Platform Agent UX

- **Decision:** apply
- **Criteria:** AG-ENT-3, AG-MEM-1, AG-STAT-3
- **Application:** Keep components and behavior consistent across embedded, docked and full-page placements and preserve the active task across them.
- **Limits:** State divergence under poor connectivity is shown as stale, never as current (AG-STAT-3).
- **Source:** S-13 (cross-platform-agent-ux)

### Privacy and Security UX

- **Decision:** apply
- **Criteria:** AG-ID-3, AG-ID-4, AG-ID-5, AG-CTRL-5
- **Application:** Show the acting identity and connection, keep secrets out of the client, and give users visible settings and capability switches in plain language.
- **Limits:** Controls must really restrict access; a control that does not is compliance theater, and missing access is never shown as granted (AG-UNC-4).
- **Source:** S-13 (privacy-security-ux)

### Progressive Consent & Communication

- **Decision:** apply
- **Criteria:** AG-APPR-2, AG-APPR-4, AG-CTRL-5
- **Application:** Request a permission at the point of need with a plain-language explanation and optional detail; a consent decision authorizes exactly what is shown.
- **Limits:** Repeated routine requests cause fatigue, so consent prompts are not a substitute for the approval flow of a consequential action.
- **Source:** S-13 (progressive-consent-communication)

### Confidence Visualization

- **Decision:** limit
- **Criteria:** AG-EXPL-4, AG-A11Y-4
- **Application:** Calibrated only: express uncertainty qualitatively, or numerically only when calibrated against measured accuracy.
- **Limits:** No false precision, no hidden real uncertainty, and confidence is never the sole decision factor. Color-coded meters also need a non-color cue. Read with its do/don't section.
- **Source:** S-13 (confidence-visualization-patterns)

### Visual Reasoning

- **Decision:** limit
- **Criteria:** AG-EXPL-1, AG-EXPL-2
- **Application:** Evidence chain only: show facts used, rules applied, findings and sources.
- **Limits:** Do not render model reasoning steps as an explanation, and do not show confidence as a guarantee.
- **Source:** S-13 (visual-reasoning-patterns)

### Adaptive Interface

- **Decision:** limit
- **Criteria:** AG-MEM-2, AG-MEM-4
- **Application:** Explicit preferences only: adapt layout or style only from settings the user can see and reverse.
- **Limits:** No behavior change learned silently from observed behavior; changes are announced.
- **Source:** S-13 (adaptive-interface-patterns)

### Human On the Loop

- **Decision:** limit
- **Criteria:** AG-STAT-1, AG-CTRL-1
- **Application:** Operator surfaces only: monitoring views with status and a stop to a safe state.
- **Limits:** Not a replacement for per-action approval of consequential actions (AG-APPR-1). Alert-based oversight is weak after long uneventful periods, so it is not the sole control for high-impact actions.
- **Source:** S-13 (human-on-the-loop)

### Monitoring and Control

- **Decision:** limit
- **Criteria:** AG-STAT-1, AG-CTRL-1
- **Application:** Operator surfaces only, as for Human On the Loop: status, anomalies, and pause or stop controls.
- **Limits:** Alert volume is limited so real anomalies are not missed; no dashboard shows simulated activity (AG-STAT-2).
- **Source:** S-13 (monitoring-control-patterns)

### Transparent Data Handling

- **Decision:** limit
- **Criteria:** AG-EXPL-2
- **Application:** Show the sources behind a claim and when each was observed.
- **Limits:** Full data-flow visualization and third-party sharing disclosure are not adopted; they apply with the privacy patterns excluded below.
- **Source:** S-13 (transparent-data-handling)

### AG-UI Protocol

- **Decision:** limit
- **Criteria:** AG-STAT-2, AG-STAT-3, AG-CTRL-1
- **Application:** Reference only. The wire protocol is adopted only by an explicit stream-contract decision.
- **Limits:** Whatever the transport, events stay real, stale states stay distinct and stop stays reachable. The overview was read; event details were not.
- **Source:** S-13 (ag-ui-protocol)

### Generative UI

- **Decision:** exclude (safety)
- **Criteria:** AG-ID-2, AG-APPR-1, AG-ID-6
- **Application:** Not applied.
- **Limits:** Model-generated executable or decision UI violates AG-ID-2 and AG-APPR-1 (and AG-ID-6). Revisit only if the model supplies data rendered by fixed, reviewed components and never a decision surface.
- **Source:** S-13 (generative-ui)

### Agent Collaboration UX

- **Decision:** exclude (not applicable yet)
- **Criteria:** AG-CTRL-3
- **Application:** Not applied.
- **Limits:** Trigger: more than one agent acts on the same task for one user. Then show who does what and keep decisions and blockers visible.
- **Source:** S-13 (agent-collaboration-ux)

### Multimodal Interaction

- **Decision:** exclude (not applicable yet)
- **Criteria:** AG-A11Y-1
- **Application:** Not applied.
- **Limits:** Trigger: a requirement for voice, gesture or camera input. Then every modality must meet AG-A11Y-1 and the decision flow.
- **Source:** S-13 (multimodal-interaction-patterns)

### Realtime Voice Agents

- **Decision:** exclude (not applicable yet)
- **Criteria:** AG-APPR-1
- **Application:** Not applied.
- **Limits:** Trigger: a spoken or telephony channel is adopted. Then consequential actions still need the exact-action confirmation (AG-APPR-1) and an accessible equivalent.
- **Source:** S-13 (realtime-voice-agents)

### Context Window Management UI

- **Decision:** exclude (not applicable yet)
- **Criteria:** AG-MEM-1
- **Application:** Not applied.
- **Limits:** Trigger: long sessions where users must choose what context to keep. Until then the interface does not expose token meters or pruning.
- **Source:** S-13 (context-window-management-patterns)

### Privacy-by-Design Principles dashboarding

- **Decision:** exclude (not applicable yet)
- **Criteria:** AG-CTRL-5
- **Application:** Not applied.
- **Limits:** Trigger: the product holds personal data under a retention or deletion obligation. The principles still shape architecture, but no dashboard is built now.
- **Source:** S-13 (privacy-by-design-principles)

### Granular Privacy Controls

- **Decision:** exclude (not applicable yet)
- **Criteria:** AG-CTRL-5
- **Application:** Not applied.
- **Limits:** Trigger: several data types or purposes need separate consent. Until then AG-CTRL-5 global settings suffice.
- **Source:** S-13 (granular-privacy-controls)

### User Empowerment Privacy Dashboard

- **Decision:** exclude (not applicable yet)
- **Criteria:** AG-CTRL-5
- **Application:** Not applied.
- **Limits:** Trigger: personal data held across multiple agents or services, or a data-subject-rights request process.
- **Source:** S-13 (user-empowerment-privacy-dashboard)

### Regulatory Compliance UX

- **Decision:** exclude (not applicable yet)
- **Criteria:** AG-DISC-1
- **Application:** Not applied.
- **Limits:** Trigger: a jurisdiction-specific consent, right-to-explanation or audit obligation takes effect; then map it to AG-DISC-1 and AG-EXPL-1.
- **Source:** S-13 (regulatory-compliance-ux)

### Advanced Privacy Technologies UX

- **Decision:** exclude (not applicable yet)
- **Criteria:** AG-DISC-3
- **Application:** Not applied.
- **Limits:** Trigger: the product adopts a privacy-preserving technique it must explain. Simplified explanations must not overstate guarantees (AG-DISC-3).
- **Source:** S-13 (advanced-privacy-technologies-ux)

## Secondary principles (S-14, S-15)

Both are tier-4 and were read in full. They inform and never raise a criterion's severity.

### UX Pilot enterprise principles (S-14)

- Principle 4, contextual help and progressive onboarding, and Principle 7, efficiency and retention: AG-ENT-2.
- Principle 2, a design system that scales: AG-ENT-3.
- Principle 5, role-based personalization and access control: AG-ENT-1.
- Principle 3, AI-powered interfaces and predictive workflows: AG-CTX-2 for proactivity, kept inside AG-APPR-1 for consequential actions.
- Principle 8, measure success with enterprise-specific metrics: see `metrics.md`.
- Principles 1 (user research across roles) and 6 (clear, actionable data visualization) have no criterion; they are process and content advice.

### Vasquez agentic UX principles (S-15)

- 1 Think systematically: no criterion; a precondition on information architecture and workflows.
- 2 Agents should be invisible, not absent: AG-CTX-1.
- 3 Shift from reactive to proactive: AG-CTX-2, AG-CTRL-3.
- 4 Context makes or breaks the experience: AG-CTX-1, AG-MEM-1.
- 5 Use known patterns: AG-A11Y-2, AG-ENT-3.
- 6 Collect the right data at the right time: AG-UNC-1, AG-UNC-4.
- 7 Keep humans in control and ensure agents stay transparent: AG-CTRL-1, AG-CTRL-4, AG-EXPL-1, AG-ID-1.
