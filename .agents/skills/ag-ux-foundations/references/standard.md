# Agentic UI/UX standard

This file is a product-neutral standard for enterprise agentic interfaces. Each criterion is a testable statement about what a person using an agent can see, do or rely on. Criteria say nothing about any particular product, framework or visual style. A product applies the standard by mapping its own screens and states to the criteria and recording gaps.

## How to read a criterion

Each criterion is a block with a heading `### AG-<GROUP>-<n> — <title>` and these fields, in this order:

- **Statement:** the testable requirement.
- **Sources:** the sources that support it, as `S-nn (locator)`. Source IDs, tiers and reading levels are defined in `sources.md`. A criterion cites the highest tier that supports it.
- **Enforcement:** how it is checked: `gate` (automated, blocks a merge), `test` (an automated or scripted check) or `review` (a human reviewer with evidence).
- **Max severity:** the highest severity a violation may be given: `Low`, `Medium`, `High` or `Blocker`.
- **Evidence:** what a reviewer needs to see to pass or fail the criterion.
- **Notes:** optional reconciliation, narrowing or limits.

Severity rule: `Blocker` requires at least one cited source of tier T1 (normative or governance) or T2 (research-grade human-AI guidelines). A criterion supported only by T3 or T4 sources is capped at `High`. A criterion must also cite at least one source read at `full` or `partial` level; a `summary-only` source never stands alone.

## Conflict rules

Sources are ranked in this order: a product's binding requirements (accepted architecture decisions, repository rules and explicit owner decisions); then T1; T2; T3; T4. The current state of a product's interface is an audit target, never a source of criteria.

- The standard is stricter than the product's current interface: record a gap and build to the standard.
- The standard conflicts with a product's binding requirements: write a decision proposal and keep the binding requirement until it is accepted. Never override it silently.
- Two external tiers conflict: the higher tier wins, and the reconciliation is recorded in the criterion.

## Reconciling confidence and reasoning

Some guidance asks that the confidence level and the reasoning behind a recommendation be accessible (S-10, Core: embrace uncertainty), and that the system make clear how well it can do what it can do and why it did what it did (S-08, G2 and G11). A product's binding requirements may forbid hidden reasoning and simulated confidence. Both are satisfied by:

- stated capability limits;
- evaluated performance where it has been measured, with the evaluation's scope;
- source-grounded rationale (facts, then rule findings, then the proposal);
- qualitative evidence completeness and freshness;
- calibrated uncertainty labels.

They are not satisfied by model chain-of-thought or by uncalibrated numeric scores. Calibrated numeric confidence is allowable only through an explicit decision, with calibration evidence.

## Disclose and set expectations

### AG-DISC-1 — AI interaction disclosed

- **Statement:** People are informed they are interacting with an AI system, clearly and distinguishably, at the latest at first interaction, in an accessible form.
- **Sources:** S-04 (Art. 50(1), 50(5)), S-08 (G1), S-11 (Identifying AI-Generated Content; The AI Label as the Identifier)
- **Enforcement:** review
- **Max severity:** Blocker
- **Evidence:** Screenshot of the first-interaction surface showing the disclosure; assistive-technology output or accessibility tree showing the disclosure is exposed; note of any case where AI origin is not obvious from context.
- **Notes:** Art. 50(1) carries an exception where AI interaction is obvious to a reasonably observant person; an enterprise agent should not rely on it.

### AG-DISC-2 — Capabilities and limits stated

- **Statement:** The entry surface states what the agent can do, which systems it can act on, and what it cannot do, in the user's context.
- **Sources:** S-08 (G1), S-03 (Art. 14(4)(a)), S-10 (Core: agent knowledge, tools and connections are transparent)
- **Enforcement:** review
- **Max severity:** Blocker
- **Evidence:** Screenshot of the entry surface showing capabilities, reachable systems and stated limits, in the viewing user's role and context.

### AG-DISC-3 — Performance claims only where measured

- **Statement:** How well the agent performs is stated only from measured evaluation, with its scope and method; unmeasured quality claims are absent.
- **Sources:** S-08 (G2), S-05 (3.1 Valid and Reliable; 3.4 Accountable and Transparent)
- **Enforcement:** review
- **Max severity:** High
- **Evidence:** For each performance or accuracy statement shown to users, a link to the evaluation that supports it, with its test set and date; or confirmation that no such statement exists.
- **Notes:** S-05 (3.1) says accuracy measurements should be paired with realistic test sets and methodology details. Capped at High as specified: the sources support the principle, not a failure severity.

## Context and timing

### AG-CTX-1 — Invoked in the work context

- **Statement:** The agent is reachable inside the user's current workflow, and launching it carries the relevant context (for example the open record) without re-entry.
- **Sources:** S-08 (G4), S-10 (Space: easily accessible), S-15 (embed in workflows)
- **Enforcement:** review
- **Max severity:** High
- **Evidence:** Walkthrough from a work screen to the agent showing the open item already attached, with no field the user must retype.
- **Notes:** S-15 was not re-verified in this session (the page returned HTTP 403); its citation rests on the earlier full reading recorded in `sources.md`. S-08 (G4) and S-10 support the criterion independently.

### AG-CTX-2 — Proactivity timed and actionable

- **Statement:** Proactive engagement is timed to the user's context, is deferred while an explicit focus condition holds (for example the user is typing, editing a record or in an open decision), and arrives as an actionable artifact rather than a bare alert.
- **Sources:** S-08 (G3), S-10 (Time: nudging more than notifying)
- **Enforcement:** review
- **Max severity:** Medium
- **Evidence:** For each proactive trigger: the context condition that gates it and the focus condition that defers it, and a screenshot of the artifact with its available actions.

## Status and activity

### AG-STAT-1 — Status always visible

- **Statement:** The agent's current state is always visible, in plain language that matches the normative state model (`state-model.md`).
- **Sources:** S-10 (Core: agent status is clearly visible at all times), S-03 (Art. 14(4)(a))
- **Enforcement:** test, review
- **Max severity:** Blocker
- **Evidence:** A mapping from each product state to a state-model state; screenshots or a conformance test showing the status label for every state.

### AG-STAT-2 — Activity from real events only

- **Statement:** Progress and activity reflect only real system events; no simulated progress or invented activity text.
- **Sources:** S-03 (Art. 14(4)(a)), S-05 (3.4 Accountable and Transparent)
- **Enforcement:** review
- **Max severity:** High
- **Evidence:** For each progress or activity element, the event that drives it; confirmation that no timer-driven, looping or placeholder progress exists.
- **Notes:** This is an inference from the sources: they require that overseers can monitor operation and that information about the system be available, but neither names simulated progress, so severity is High. "Estimated times" was removed from the statement because no cited source supports it. A product's binding requirements may still make this non-negotiable. A pattern-library page on status and activity (S-13) was considered and dropped: its watch-out note concerns over-frequent updates creating false urgency, not simulated progress.

### AG-STAT-3 — Staleness is distinct

- **Statement:** Lost connection, reconnection and stale data are shown distinctly and never presented as current or complete.
- **Sources:** S-10 (Core: agent status is clearly visible at all times), S-07 (self-descriptiveness), S-01 (SC 4.1.3 Status Messages)
- **Enforcement:** test, review
- **Max severity:** High
- **Evidence:** Screenshots or test output of the connected, disconnected, reconnecting and stale-data presentations, with the last-updated time where relevant.
- **Notes:** S-10 is the readable source because S-07 is summary-only. The sources support visible status and announced status changes; the distinct presentation of staleness is this standard's application of them.

### AG-STAT-4 — Accessible status announcements

- **Statement:** Status messages (as defined by WCAG SC 4.1.3) are exposed to assistive technology as status messages without moving focus.
- **Sources:** S-01 (SC 4.1.3 Status Messages)
- **Enforcement:** test
- **Max severity:** Blocker
- **Evidence:** Accessibility-tree or screen-reader capture showing the status message role or live region for each state change, and a check that focus did not move.
- **Notes:** Two further clauses (announce politely; do not announce streamed text token by token) are design practice not yet supported by a source read at the needed depth: the ARIA live-region material was read only at pattern-title level and the SC 4.1.3 normative text was not re-read. They are held out of the statement until a full read. Blocker rests on S-01 (T1) with title-level support only.

## Control and oversight

### AG-CTRL-1 — Stop to a safe state

- **Statement:** The user can stop the agent at any time; stopping reaches a defined safe state, and the resulting status of any in-flight action is shown.
- **Sources:** S-03 (Art. 14(4)(e)), S-10 (Core: agent status is clearly visible at all times)
- **Enforcement:** test, review
- **Max severity:** Blocker
- **Evidence:** Test or recording of stopping an agent mid-action, showing the stop control, the final state, and the status of the interrupted action.
- **Notes:** The in-flight status clause rests on S-10, not on Art. 14.

### AG-CTRL-2 — Efficient invocation, dismissal and correction

- **Statement:** Users can invoke, dismiss and correct the agent (edit a proposal, refine the request) without restarting the task.
- **Sources:** S-08 (G7, G8, G9)
- **Enforcement:** review
- **Max severity:** High
- **Evidence:** Walkthrough showing invocation, dismissal of an unwanted suggestion, and correction of a proposal, each without losing task state.

### AG-CTRL-3 — Initiative is visible

- **Statement:** Who currently holds initiative (user or agent) is always visible; the agent never takes over input without a visible handoff.
- **Sources:** S-13 (mixed-initiative-interface-patterns), S-10 (Core: users are in control of the agent)
- **Enforcement:** review
- **Max severity:** High
- **Evidence:** Screenshots of the initiative indicator in each state, and of a handoff in both directions.
- **Notes:** Both sources are T3 or T4, so the criterion is capped at High.

### AG-CTRL-4 — Override, disregard, reverse

- **Statement:** The user can reject any proposal, disregard any output and, where the action allows, reverse it.
- **Sources:** S-03 (Art. 14(4)(d)), S-08 (G9)
- **Enforcement:** review
- **Max severity:** Blocker
- **Evidence:** Walkthrough showing rejection of a proposal, disregarding an output, and a reversal where the action supports one.
- **Notes:** Whether reversal is possible must also be stated before acting; that belongs to the consequential-action criteria, not to this one.

### AG-CTRL-5 — Global controls

- **Statement:** Users can set agent preferences and turn agent capabilities off, and can see those settings.
- **Sources:** S-08 (G17), S-10 (Core: users are in control of when the agent is on or off)
- **Enforcement:** review
- **Max severity:** Medium
- **Evidence:** Screenshot of the settings surface showing current preferences and the controls to turn each capability off.

## Consequential actions and decisions

### AG-APPR-1 — Exact consequential action

- **Statement:** Before any consequential action, the user sees the exact action: target system and resource, operation, every material value, consequences and reversibility.
- **Sources:** S-08 (G16), S-06 (ASI02 Prevention 2, Action-Level Authentication and Approval; ASI09 Prevention 7, expected side effects), S-03 (Art. 14(4)(c)), S-13 (Approval Queues & Escalation Chains: decision-ready context packages)
- **Enforcement:** test, review
- **Max severity:** Blocker
- **Evidence:** Screenshot or DOM of the decision surface showing each element (target system and resource, operation, each material value, consequences, reversibility); conformance test name if automated.
- **Notes:** S-06 (ASI02) says to display a pre-execution plan or dry-run diff before high-impact actions are approved. S-08 (G16) supports conveying consequences. The reversibility flag and the diff come from S-13 (T4), which lists "summary, diff, financial impact, reversibility flag". Art. 14(4)(c) supports correct interpretation of output in general, not this list. The itemised fields are this standard's application of those sources.

### AG-APPR-2 — One decision, one exact action

- **Statement:** Each decision authorizes exactly the action shown on the decision surface, and nothing more.
- **Sources:** S-06 (ASI02 Prevention 2, Action-Level Authentication and Approval; ASI03 Prevention 3, Mandate Per-Action Authorization; ASI09 Example scenario 6, consent laundering through read-only previews)
- **Enforcement:** test
- **Max severity:** Blocker
- **Evidence:** Test showing that an approval record is bound to the action shown, and that a changed or additional action cannot execute under it.
- **Notes:** S-06 (ASI02, ASI03) requires explicit approval or authorization per action. A grouped decision that lists every action it covers is guidance following from this statement; no source states it directly. Art. 14(4)(c) concerns interpreting output, not the scope of an approval, and is not cited.

### AG-APPR-3 — No hidden material terms

- **Statement:** Material terms are never only inside collapsed disclosure, truncation or unindicated scroll regions on the decision surface.
- **Sources:** S-06 (ASI09 Prevention 7, Separate preview from effect, and Prevention 8, Human-factors and UI safeguards), S-01 (SC 1.4.10 Reflow), S-13 (Progressive Disclosure UI Patterns: watch-out)
- **Enforcement:** test, review
- **Max severity:** High
- **Evidence:** Screenshots of the decision surface at the default and at 320 CSS px widths, with every material term visible without expanding, scrolling an unindicated region or reading truncated text.
- **Notes:** SC 1.4.10 supports "without loss of information" at narrow widths, and S-06 (ASI09) supports displaying expected side effects; only the pattern library (S-13, T4) says critical information is missed when it sits behind an expander. The rule about collapsed disclosure is an inference from the T1 sources, hence High.

### AG-APPR-4 — Friction against automation bias

- **Statement:** Friction is proportional to risk: irreversible or high-impact actions need an explicit confirmation step.
- **Sources:** S-06 (ASI09 Prevention 1, Explicit confirmations; Prevention 5, Adaptive Trust Calibration; Common example 2, Missing Confirmation for Sensitive Actions), S-03 (Art. 14(4)(b))
- **Enforcement:** test, review
- **Max severity:** Blocker
- **Evidence:** Test or recording showing the confirmation step for an irreversible or high-impact action and that the action cannot proceed without it.
- **Notes:** Explicit confirmation is directly supported by S-06 (ASI09) and by Art. 14(4)(b) (awareness of automation bias). Initial focus and pre-selection are in AG-APPR-8. "No approval from a notification alone" is guidance; no source read supports it.

### AG-APPR-5 — Invalidated decisions are visible

- **Statement:** When the facts or the authorization a pending decision relied on change, or the decision expires, it is visibly invalidated and requires re-review.
- **Sources:** S-06 (ASI03 Common example 4, Time-of-Check to Time-of-Use; Example scenario 5, Workflow Authorization Drift; Prevention 1, time-bound permissions), S-13 (Approval Queues & Escalation Chains: state rehydration watch-out)
- **Enforcement:** test
- **Max severity:** High
- **Evidence:** Test that changes a fact or permission after a decision was presented and shows the invalidated state, and one that lets a decision expire and shows it cannot be approved without re-review.
- **Notes:** S-06 (ASI03) directly supports re-validating authorization that changes or expires before execution; it does not speak to changes in other facts, and S-13 (T4) only warns that rehydration after a delay can fail silently. Blocking execution is in AG-APPR-9.

### AG-APPR-6 — Decided, executed and verified are separate

- **Statement:** Labels distinguish decided, executed (committed) and verified outcome; success is claimed only after independent verification.
- **Sources:** S-03 (Art. 14(4)(a), 14(4)(c)), S-05 (3.1 Valid and Reliable), S-06 (ASI08 Prevention 10, Logging and non-repudiation: execution outcomes)
- **Enforcement:** test, review
- **Max severity:** High
- **Evidence:** Mapping of each action to its decided, executed and verified labels, and a test showing that "verified" cannot appear until an independent check has returned.
- **Notes:** The sources support monitoring operation, interpreting output and recording execution outcomes; none states a three-way split of outcome labels or independent verification. That split is this standard's application of them, hence High.

### AG-APPR-7 — Risk tier comes from policy

- **Statement:** The approval requirement or risk tier shown comes from system policy; the interface never lowers it or offers a path around it.
- **Sources:** S-06 (ASI02 Prevention 4, Policy Enforcement Middleware; ASI03 Prevention 3, Mandate Per-Action Authorization), S-13 (Approval Queues & Escalation Chains: risk tiers)
- **Enforcement:** test
- **Max severity:** Blocker
- **Evidence:** Test showing that the tier displayed equals the tier returned by policy, that a client-side change cannot lower it, and that no control bypasses the approval.
- **Notes:** S-06 (ASI02, ASI03) treats model output as untrusted and puts validation in an external policy engine. The tier model itself comes from S-13 (T4).

### AG-APPR-8 — Approve is not the default

- **Statement:** The approving control is never the initial focus or pre-selected in a decision.
- **Sources:** S-02 (Dialog (Modal) pattern: initial focus on the least destructive action)
- **Enforcement:** test
- **Max severity:** High
- **Evidence:** Test or recording showing the element that holds initial focus when the decision opens, and that no approving option is pre-selected.
- **Notes:** S-02 says it "may be advisable" to focus the least destructive action when a dialog holds a hard-to-reverse final step; the source is advisory, hence High.

### AG-APPR-9 — Changed authorization blocks execution

- **Statement:** A decision whose authorization changed or expired cannot execute until it is re-reviewed.
- **Sources:** S-06 (ASI03 Common example 4, Time-of-Check to Time-of-Use; ASI03 Prevention 3, Mandate Per-Action Authorization; ASI03 Prevention 7, bind permissions to subject, resource, purpose and duration)
- **Enforcement:** test
- **Max severity:** Blocker
- **Evidence:** A test showing that an expired or changed authorization blocks execution and requires re-review.
- **Notes:** The visible invalidation is AG-APPR-5.

## Explanation and evidence

### AG-EXPL-1 — Source-grounded rationale

- **Statement:** "Why" is explained by the facts used, the rules applied and their findings, attributable to sources; model chain-of-thought is never presented as explanation.
- **Sources:** S-08 (G11), S-05 (3.5 Explainable and Interpretable), S-06 (ASI09 Prevention 4, plain-language risk summary, not model-generated rationales; Common example 4, Fake Explainability), S-11 (AI explainability)
- **Enforcement:** review
- **Max severity:** High
- **Evidence:** For a sample of explanations, the facts and rule findings shown, and confirmation that no model reasoning text is presented as the explanation.
- **Notes:** S-06 (ASI09) is the direct support for excluding model-generated rationales. The "facts, rules, findings" structure follows the reconciliation section above.

### AG-EXPL-2 — Inspectable sources

- **Statement:** Each claim links to its source with the time it was observed.
- **Sources:** S-08 (G11), S-06 (ASI09 Prevention 6, Content provenance: source identifiers, timestamps), S-13 (Trust and Transparency Patterns: source attribution)
- **Enforcement:** review
- **Max severity:** High
- **Evidence:** For a sample of claims, the link to the source and the observation time; any claim without both.
- **Notes:** "Restricted or missing sources are stated rather than omitted" is guidance; no source read supports it. See AG-UNC-4 for missing data.

### AG-EXPL-3 — Progressive explanation

- **Statement:** Explanation starts with a summary and gives details on demand, disclosure nests no deeper than three to four levels, and critical information is never only in a collapsed level.
- **Sources:** S-13 (progressive-disclosure-patterns: don'ts, max 3-4 levels; watch-out on missed critical information), S-11 (AI explainability: Start with summarized explanations)
- **Enforcement:** review
- **Max severity:** Medium
- **Evidence:** Screenshots of the summary level and of each detail level, showing that anything a decision depends on is visible at the summary level.
- **Notes:** The 3-4 level limit is S-13's do/don't guidance (T4).

### AG-EXPL-4 — Calibrated uncertainty only

- **Statement:** Uncertainty is expressed qualitatively, or numerically only when calibrated against measured accuracy.
- **Sources:** S-08 (G2), S-10 (Core: embrace uncertainty), S-06 (ASI09 Prevention 5, confidence-weighted cues), S-13 (confidence-visualization-patterns: don'ts, show false precision; calibration with historical accuracy)
- **Enforcement:** review
- **Max severity:** High
- **Evidence:** For each confidence or uncertainty display, the label or number and the calibration evidence behind any number.
- **Notes:** S-05 (3.1) says accuracy measurements should be paired with realistic test sets and methodology; "calibrated against measured accuracy" is this standard's application of that.

## Uncertainty and failure

### AG-UNC-1 — Clarify when in doubt

- **Statement:** An ambiguous or under-specified request produces a clarification question, or a stated safe degradation, not a guess.
- **Sources:** S-08 (G10)
- **Enforcement:** review
- **Max severity:** High
- **Evidence:** Walkthrough with an ambiguous request showing the clarification question or the stated safe degradation.
- **Notes:** "Focused" and "keeps the task context" are guidance; the source gives only the G10 title and one-line description. S-15's data-capture principle concerns when to collect inputs, not clarifying ambiguous requests, and is not cited.

### AG-UNC-2 — Uncertain outcome is explicit

- **Statement:** When an action's effect is unknown, the interface says so, explains the possible effect and offers a safe check; it never offers a blind retry of a possibly-completed action.
- **Sources:** S-06 (ASI08 Description, observable symptoms: repeated identical intents and oscillating retries; Prevention 6 and 7, rate limiting and circuit breakers)
- **Enforcement:** test, review
- **Max severity:** High
- **Evidence:** Test that makes an action time out after dispatch and shows the unknown-outcome presentation, the safe-check control, and the absence of a plain retry.
- **Notes:** S-06 (ASI08) lists repeated identical intents and retry loops as symptoms of cascading faults and recommends circuit breakers, but it does not address a user interface offering a retry of a possibly-completed action. This is an inference, hence High.

### AG-UNC-3 — Actionable errors

- **Statement:** Errors state the problem, its cause where known, and an authorized next step, in plain language and text, associated with the affected action.
- **Sources:** S-01 (SC 3.3.1 Error Identification, SC 3.3.3 Error Suggestion), S-13 (error-recovery-patterns: problem + cause + solution; severity-based display)
- **Enforcement:** test, review
- **Max severity:** High
- **Evidence:** Screenshots of the error states for a failed input, a failed action and a denied action, each showing the problem, the cause where known, the next step and its association with the action.
- **Notes:** SC 3.3.1 and 3.3.3 apply to automatically detected input errors only, so for those cases AG-A11Y-1 already carries Blocker; the broader statement rests on S-13 (T4). Placement by severity (inline, tooltip, modal, banner) is S-13's model; this criterion only requires association with the affected action. Whether a transient notice may be the only record is not covered by any source read.

### AG-UNC-4 — Missing is never defaulted

- **Statement:** Missing access or data is stated with how to resolve it; it is never shown as an empty, zero, granted or connected value.
- **Sources:** S-05 (3.1 Valid and Reliable), S-13 (Error Handling and Recovery Patterns: actionable solution)
- **Enforcement:** test, review
- **Max severity:** High
- **Evidence:** Test that withholds access or data and shows the missing-state presentation with its resolution path, not an empty or default value.
- **Notes:** No source states this directly. It applies the validity principle (a displayed value must be what the system actually knows) and the S-13 error pattern.

## Over time

### AG-MEM-1 — Work survives context changes

- **Statement:** Recent interactions, drafts and the active task survive navigation, layout or appearance changes and return visits within the retention policy.
- **Sources:** S-08 (G12), S-10 (Time, Past: reflecting on history)
- **Enforcement:** test
- **Max severity:** High
- **Evidence:** Test that navigates away, changes layout or theme, and returns, then shows the draft, task and recent interactions intact; the retention policy applied.
- **Notes:** G12 supports remembering recent interactions; the specific survivals (navigation, layout, appearance, drafts) are this standard's application.

### AG-MEM-2 — Adapt cautiously and visibly

- **Statement:** Learning or adaptation is visible, reversible and user-controlled; behavior never changes silently.
- **Sources:** S-08 (G13, G14), S-10 (Core: transparency, control and consistency)
- **Enforcement:** review
- **Max severity:** Medium
- **Evidence:** For each adaptive behavior, the place where the user sees it, the control to turn it off or reverse it, and a record of any change.
- **Notes:** G13 and G14 were read as titles and one-line descriptions only.

### AG-MEM-3 — Granular feedback

- **Statement:** Users can give feedback on a specific output or action.
- **Sources:** S-08 (G15), S-09 (Feedback + Control)
- **Enforcement:** review
- **Max severity:** Medium
- **Evidence:** Screenshot of the feedback control attached to a single output or action, and the record it creates.
- **Notes:** S-09 was read at pattern-title level only.

### AG-MEM-4 — Notify about changes

- **Statement:** Changes to capabilities, policies or behavior are announced to affected users.
- **Sources:** S-08 (G18)
- **Enforcement:** review
- **Max severity:** Medium
- **Evidence:** For a recent change, the notice shown to affected users and its audience.

## Trust boundary

### AG-ID-1 — Origin is distinguishable

- **Statement:** AI-generated content is marked as such, visibly and programmatically, and is distinguishable from user content and from system-verified facts.
- **Sources:** S-04 (Art. 50(2)), S-06 (ASI09 Prevention 6, Content provenance), S-11 (The AI Label: Mark AI-generated content with an AI label), S-13 (Trust and Transparency Patterns: source attribution)
- **Enforcement:** review
- **Max severity:** High
- **Evidence:** Screenshot and accessibility tree of a surface mixing AI-generated, user and system-verified content, showing each origin marked.
- **Notes:** Art. 50(2) obliges providers to mark synthetic output in a machine-readable form; it does not require the three-way distinction between AI, user and verified content in an interface. That distinction rests on S-06 (provenance), S-11 and S-13, hence High.

### AG-ID-2 — Untrusted content is inert

- **Statement:** Model output and retrieved or user-supplied content render as inert text: no active markup, no auto-loaded remote resources or controls, and no network or state-changing call from a preview.
- **Sources:** S-06 (ASI01 Prevention 1 and 6, treat natural-language inputs as untrusted and sanitize; ASI02 Prevention 4, treat model output as untrusted; ASI09 Prevention 7, separate preview from effect; ASI09 Example scenario 6, consent laundering through read-only previews)
- **Enforcement:** test
- **Max severity:** Blocker
- **Evidence:** Test that renders hostile content (markup, remote resource references, a preview that would call an endpoint) and shows that it appears as inert text, with no network request, state change or active element.
- **Notes:** S-06 (ASI01, ASI02) requires treating such inputs and outputs as untrusted; ASI09 (Prevention 7, scenario 6) forbids network or state-changing calls from a preview. Imitation of system UI is in AG-ID-6.

### AG-ID-3 — Identity and connection are not model-chosen

- **Statement:** The acting identity, credentials and connection are chosen by system policy and never selected by model output.
- **Sources:** S-06 (ASI03 Prevention 3 and 5, per-action authorization and bound intent; ASI02 Prevention 4 and 7, policy enforcement and fail closed on ambiguous resolution)
- **Enforcement:** test
- **Max severity:** Blocker
- **Evidence:** Test showing that a model-supplied identity or connection name is ignored or rejected.
- **Notes:** Display of the identity and connection is in AG-ID-5.

### AG-ID-4 — No secrets in the client

- **Statement:** Secrets and credentials are never displayed, logged to the client, placed in URLs or persisted in browser storage.
- **Sources:** S-06 (ASI03 Common example 2, memory-based privilege retention; Prevention 1, short-lived scoped tokens), S-05 (3.3 Secure and Resilient)
- **Enforcement:** test
- **Max severity:** High
- **Evidence:** Scan of the client bundle, network traffic, console output, URLs and browser storage for secret material after a full session.
- **Notes:** The sources support protecting credentials and keeping them short-lived; they do not name URLs, client logs or browser storage. Those specifics are an application of the principle, hence High.

### AG-ID-5 — Acting identity is shown

- **Statement:** The acting identity and connection used for an action are shown to the user.
- **Sources:** S-10 (Core: knowledge, tools and connections are transparent)
- **Enforcement:** review
- **Max severity:** High
- **Evidence:** Screenshot of the identity and connection shown for an action.
- **Notes:** S-10 is T3, hence High.

### AG-ID-6 — Content cannot imitate system UI

- **Statement:** Model or retrieved content cannot imitate system UI or a decision surface.
- **Sources:** S-06 (ASI09 Prevention 8, Human-factors and UI safeguards)
- **Enforcement:** test
- **Max severity:** High
- **Evidence:** Test that renders content styled as system chrome, a control or a decision panel and shows it is visibly distinct from the real surface.
- **Notes:** This is an application of S-06 (ASI09 Prevention 8: visually differentiate high-risk recommendations); the source does not name content imitating system UI, hence High.

## Accessibility

### AG-A11Y-1 — WCAG 2.2 AA in every state

- **Statement:** Every state of every surface conforms to WCAG 2.2 Level AA.
- **Sources:** S-01 (Conformance 5.2.1 Conformance Level, Level AA; 5.2.2 Full pages)
- **Enforcement:** test, review
- **Max severity:** Blocker
- **Evidence:** Automated and manual WCAG 2.2 AA check results for each state, with the list of states covered.
- **Notes:** Conformance is defined for full pages, so a state that is part of a page is covered. A claim of conformance needs manual review as well as automated checks.

### AG-A11Y-2 — APG interaction semantics

- **Statement:** Dialogs, disclosures, tabs, menus and listboxes follow APG patterns, including the explicit choice between modal and non-modal dialogs and focus on open, close and return.
- **Sources:** S-02 (Dialog (Modal), Disclosure, Tabs, Listbox and Menu Button patterns)
- **Enforcement:** test
- **Max severity:** Blocker
- **Evidence:** Keyboard and accessibility-tree test for each component type: roles, states, focus on open, focus return on close, and Escape behavior where the pattern defines it.
- **Notes:** The APG page for the modal dialog says focus moves into the dialog on open and returns to the invoking element on close, and describes non-modal dialogs by contrast; it has no separate non-modal pattern. APG is authoring guidance rather than a conformance requirement, so a deviation that leaves AG-A11Y-1 satisfied should be rated by its effect.

### AG-A11Y-3 — Reflow and resize

- **Statement:** Surfaces reflow at 320 CSS px without loss of information or functionality, and support text resize to 200 percent without loss.
- **Sources:** S-01 (SC 1.4.10 Reflow, SC 1.4.4 Resize Text)
- **Enforcement:** test
- **Max severity:** Blocker
- **Evidence:** Screenshots at 320 CSS px and at 200 percent text size for each surface.
- **Notes:** SC 1.4.10 and 1.4.4 are Level AA. Motion is in AG-A11Y-5. Forced-colours support is guidance; no source read supports it.

### AG-A11Y-4 — Not colour alone; sufficient contrast

- **Statement:** Status and meaning never rely on colour alone; text, non-text components and component states meet contrast minimums; keyboard focus is never entirely hidden by author-created content.
- **Sources:** S-01 (SC 1.4.1 Use of Color, SC 1.4.3 Contrast (Minimum), SC 1.4.11 Non-text Contrast, SC 2.4.11 Focus Not Obscured (Minimum))
- **Enforcement:** test
- **Max severity:** Blocker
- **Evidence:** Contrast measurements for text, non-text components and states, a check of each status indicator without colour, and a keyboard pass showing focus is not entirely hidden on each step.

### AG-A11Y-5 — Motion can be disabled

- **Statement:** Motion animation triggered by interaction can be disabled.
- **Sources:** S-01 (SC 2.3.3 Animation from Interactions)
- **Enforcement:** test
- **Max severity:** High
- **Evidence:** A test showing the control or setting that disables interaction-triggered motion.
- **Notes:** SC 2.3.3 is Level AAA, so it is a design bar rather than an AA requirement.

## Enterprise use

### AG-ENT-1 — Role-appropriate views

- **Statement:** The interface reflects the user's role; unavailable actions are absent or explained, never enabled and then failing.
- **Sources:** S-14 (Principle 5, Support role-based personalization and access control)
- **Enforcement:** test, review
- **Max severity:** High
- **Evidence:** Screens for at least two roles with differing permissions, showing the absent or explained actions, and a test that no enabled control fails with a permission error.
- **Notes:** S-14 supports restricting what users see or do by job function. The rule that an action is never enabled and then failing is this standard's application. S-14 is T4; High is the cap without a T1 or T2 source.

### AG-ENT-2 — Efficiency with learnability

- **Statement:** Frequent tasks have short paths; icon-only controls are paired with visible labels or tooltips; contextual help is available, and help mechanisms repeated across pages sit in the same relative place.
- **Sources:** S-14 (Principle 4, Build in contextual help; Principle 7, Design for efficiency and retention), S-01 (SC 3.2.6 Consistent Help)
- **Enforcement:** review
- **Max severity:** Medium
- **Evidence:** Step counts for the most frequent tasks, a list of icon-only controls with their label or tooltip, and the contextual help available on a sample of screens.
- **Notes:** Keyboard-operable paths and accessible names for icon-only controls are covered by AG-A11Y-1. S-14 also warns that unnecessary confirmation costs time; that does not relax AG-APPR-4 for consequential actions.

### AG-ENT-3 — Consistent across placements

- **Statement:** Components and behavior are consistent across every placement (embedded, docked, full page).
- **Sources:** S-14 (Principle 2, Build a design system that scales with your product)
- **Enforcement:** test, review
- **Max severity:** Medium
- **Evidence:** The same task performed in each placement, showing the same components, labels and states.
- **Notes:** S-14 is T4, hence Medium.

### AG-ENT-4 — Long content

- **Statement:** Long translated strings and long identifiers do not cause loss of content, truncated meaning or two-dimensional scrolling at the reflow width.
- **Sources:** S-01 (SC 1.4.10 Reflow)
- **Enforcement:** test
- **Max severity:** Medium
- **Evidence:** Screenshots with pseudo-localized strings and a long identifier at 320 CSS px.
- **Notes:** "All copy is localizable" is guidance; no source read supports it.

## Social context

### AG-SOC-1 — Match social and domain norms

- **Statement:** Tone and terminology match the users' professional and cultural norms.
- **Sources:** S-08 (G5), S-10 (Time, Now: nudging more than notifying; delivery based on social and cultural information)
- **Enforcement:** review
- **Max severity:** Medium
- **Evidence:** Review of sample copy against the users' domain vocabulary and norms.

### AG-SOC-2 — Mitigate social biases

- **Statement:** Content and suggestions about people avoid reinforcing social biases.
- **Sources:** S-08 (G6), S-05 (3.7 Fair, with Harmful Bias Managed)
- **Enforcement:** review
- **Max severity:** High
- **Evidence:** Review of a sample of content and suggestions about people for stereotyped or biased wording.
- **Notes:** S-05 (3.7) names systemic, computational and statistical, and human-cognitive biases; this criterion covers the content a user sees, not model training.
