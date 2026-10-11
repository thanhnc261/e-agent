# Evaluation metrics

These metrics measure whether a product meets the intent behind the criteria. Browser and conformance tests verify mechanics (for example that a control exists or focus lands correctly) and do not measure any of these metrics. Each metric needs participants or instrumentation that a test script cannot supply.

### M-1 — Task completion time

- **Measures:** Time from starting a task to a verified result, per task type and role.
- **Method:** Instrumented flow, or a moderated test with role-matched participants; report median and spread, separating agent working time from user waiting and decision time.
- **Criteria:** AG-STAT-1, AG-CTRL-2, AG-ENT-2

### M-2 — Error rate

- **Measures:** Share of tasks with a wrong, rejected-after-execution or corrected outcome, and share of user-visible errors per task.
- **Method:** Instrumented; classify errors by the normative state in which they surfaced.
- **Criteria:** AG-UNC-3, AG-UNC-1, AG-APPR-6

### M-3 — Approval comprehension

- **Measures:** Whether the approver can state what will change, where, and whether it is reversible, before approving.
- **Method:** Moderated task test with role-matched participants; scored against the exact action.
- **Criteria:** AG-APPR-1, AG-APPR-3

### M-4 — Oversight effectiveness

- **Measures:** Share of seeded bad proposals the approver catches, and success at stopping or overriding the agent.
- **Method:** Moderated test with seeded errors in otherwise normal proposals; measure catches, misses and time to stop. Aligned with S-03 (Art. 14(4)(b)) on awareness of automation bias and Art. 14(4)(e) on intervention.
- **Criteria:** AG-APPR-4, AG-APPR-8, AG-CTRL-1, AG-CTRL-4

### M-5 — Trust calibration

- **Measures:** Whether user reliance matches the agent's measured reliability: acceptance of correct output and rejection of incorrect output.
- **Method:** Moderated test against a known reliability profile. S-09 (PAIR) was read only at home-page and pattern-index level (one-line summaries), so it is cited as a pointer to trust calibration, not as a method source; the method here is this skill's own.
- **Criteria:** AG-DISC-3, AG-EXPL-4, AG-EXPL-1

### M-6 — Recovery success

- **Measures:** Share of failed and uncertain outcomes that the user resolves safely without a blind retry or outside help.
- **Method:** Moderated test with induced failures and uncertain outcomes, or instrumented resolution tracking.
- **Criteria:** AG-UNC-2, AG-UNC-3, AG-MEM-1

### M-7 — Clarification count

- **Measures:** Number of clarification questions per task, and the share the user judges necessary.
- **Method:** Instrumented; review a sample of transcripts for questions that asked for information the context already held.
- **Criteria:** AG-UNC-1, AG-CTX-1
