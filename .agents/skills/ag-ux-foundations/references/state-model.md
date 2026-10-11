# Normative agentic task-state model

A product conforms to this model by mapping each of its own task states to the normative states below. Each mapping is dated, so a later reader can tell which product version it describes. One product state may map to only one normative state; a product state that would span two (for example "approved" meaning both decided and executing) must be split before it conforms.

### Ready

- **User need:** Know what the agent can do here
- **Presentation:** Capability and limits statement, a few admitted examples, composer
- **Allowed actions:** Start a task; open settings
- **Forbidden:** Empty dashboards; claims of unmeasured quality
- **Criteria:** AG-DISC-1, AG-DISC-2, AG-DISC-3, AG-CTX-1

### Working

- **User need:** Know work is active and whether to intervene
- **Presentation:** Plain-language state and real milestones; expandable activity
- **Allowed actions:** Stop; continue other work
- **Forbidden:** Simulated progress or ETA; invented activity text
- **Criteria:** AG-STAT-1, AG-STAT-2, AG-CTRL-1

### Needs input

- **User need:** Supply missing information
- **Presentation:** Focused question with the relevant context; original task kept
- **Allowed actions:** Answer; edit request; stop
- **Forbidden:** Guessing; losing the draft
- **Criteria:** AG-UNC-1, AG-UNC-4, AG-MEM-1

### Blocked by rules

- **User need:** Understand what rule blocked the proposal and what can change
- **Presentation:** Rule findings with sources and an authorized next step
- **Allowed actions:** Revise request; stop
- **Forbidden:** Offering approval of a blocked proposal
- **Criteria:** AG-EXPL-1, AG-UNC-3, AG-APPR-7

### Awaiting decision

- **User need:** Understand purpose, impact and the exact change
- **Presentation:** Business summary above the exact action and every material term
- **Allowed actions:** Approve with explicit confirmation; reject; ask
- **Forbidden:** Hidden material terms; default-focused or pre-selected approve
- **Criteria:** AG-APPR-1, AG-APPR-2, AG-APPR-3, AG-APPR-4, AG-APPR-8

### Decision invalidated

- **User need:** Know the pending decision no longer applies
- **Presentation:** Clear invalidation reason; what changed
- **Allowed actions:** Re-review a fresh proposal; stop
- **Forbidden:** Approving the stale version; executing on changed or expired authorization
- **Criteria:** AG-APPR-5, AG-APPR-9

### Rejected

- **User need:** Know nothing was executed
- **Presentation:** Rejection recorded; next options
- **Allowed actions:** Revise; start new task
- **Forbidden:** Silent retry of the rejected action
- **Criteria:** AG-CTRL-4

### Executing

- **User need:** Know the approved action is being carried out
- **Presentation:** "Executing" distinct from "approved"
- **Allowed actions:** Stop (with in-flight status reported)
- **Forbidden:** Showing success
- **Criteria:** AG-APPR-6, AG-CTRL-1

### Verifying

- **User need:** Know the result is being independently checked
- **Presentation:** "Verifying" distinct from "executed"
- **Allowed actions:** Wait; stop where safe
- **Forbidden:** Showing success before verification
- **Criteria:** AG-APPR-6

### Outcome uncertain

- **User need:** Know the effect is unknown and what is safe
- **Presentation:** Explanation of the possible effect; safe check
- **Allowed actions:** Run a check; escalate
- **Forbidden:** Blind retry or resend
- **Criteria:** AG-UNC-2

### Failed

- **User need:** Know what failed and what to do
- **Presentation:** Problem, cause where known and authorized next step, as text tied to the affected action and kept visible until dismissed
- **Allowed actions:** Retry only where safe; revise; escalate
- **Forbidden:** Toast-only failure; raw traces (design rules of this model)
- **Criteria:** AG-UNC-3

### Cancelled or stopped

- **User need:** Know the safe state reached
- **Presentation:** What stopped and the status of any in-flight action
- **Allowed actions:** Start again; inspect
- **Forbidden:** Implying nothing happened when an action was in flight
- **Criteria:** AG-CTRL-1

### Verified complete

- **User need:** Know the actual verified result
- **Presentation:** Verified result with reference and evidence; next action
- **Allowed actions:** Inspect evidence; follow up
- **Forbidden:** Claiming more than was verified
- **Criteria:** AG-APPR-6, AG-EXPL-2
