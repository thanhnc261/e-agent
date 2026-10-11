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
- **Sources:** S-08 (G4), S-10 (Space: easily accessible), S-15 (embed in workflows), S-01 (SC 3.3.7 Redundant Entry)
- **Enforcement:** review
- **Max severity:** High
- **Evidence:** Walkthrough from a work screen to the agent showing the open item already attached, with no field the user must retype.
- **Notes:** S-01 is cited at title level (the SC 3.3.7 normative text was not read); it supports only the principle of not asking for information already entered.

### AG-CTX-2 — Proactivity timed and actionable

- **Statement:** Proactive engagement is timed to the user's context, does not interrupt focused work, and arrives as an actionable artifact rather than a bare alert.
- **Sources:** S-08 (G3), S-10 (Time: nudging more than notifying)
- **Enforcement:** review
- **Max severity:** Medium
- **Evidence:** For each proactive trigger: the context condition that gates it, and a screenshot of the artifact with its available actions.

## Status and activity

### AG-STAT-1 — Status always visible

- **Statement:** The agent's current state is always visible, in plain language that matches the normative state model (`state-model.md`).
- **Sources:** S-10 (Core: agent status is clearly visible at all times), S-03 (Art. 14(4)(a)), S-07 (self-descriptiveness)
- **Enforcement:** test, review
- **Max severity:** Blocker
- **Evidence:** A mapping from each product state to a state-model state; screenshots or a conformance test showing the status label for every state.
- **Notes:** S-07 is summary-only and is supporting, not primary.

### AG-STAT-2 — Activity from real events only

- **Statement:** Progress and activity reflect only real system events; no simulated progress, estimated times or invented activity text.
- **Sources:** S-03 (Art. 14(4)(a)), S-05 (3.4 Accountable and Transparent)
- **Enforcement:** review
- **Max severity:** Blocker
- **Evidence:** For each progress or activity element, the event that drives it; confirmation that no timer-driven, looping or placeholder progress exists.
- **Notes:** The statement is this standard's application of monitoring and transparency; the sources do not name simulated progress. A pattern-library page on status and activity (S-13) was considered and dropped: its watch-out note concerns over-frequent updates creating false urgency, not simulated progress.

### AG-STAT-3 — Staleness is distinct

- **Statement:** Lost connection, reconnection and stale data are shown distinctly and never presented as current or complete.
- **Sources:** S-10 (Core: agent status is clearly visible at all times), S-07 (self-descriptiveness), S-01 (SC 4.1.3 Status Messages)
- **Enforcement:** test, review
- **Max severity:** High
- **Evidence:** Screenshots or test output of the connected, disconnected, reconnecting and stale-data presentations, with the last-updated time where relevant.
- **Notes:** S-10 is the readable source because S-07 is summary-only. The sources support visible status and announced status changes; the distinct presentation of staleness is this standard's application of them.

### AG-STAT-4 — Accessible status announcements

- **Statement:** State changes are exposed to assistive technology as status messages without moving focus.
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
