# Task presentation state matrix

Date: 2026-10-09. This specifies visible mockup behavior only. Product permissions and transitions must come from authoritative server/core state.

| State | Status | Available task controls | Approval available? |
| --- | --- | --- | --- |
| Preparing | Working | Stop task; minimize/resume | No |
| Clarification (handoff only) | Needs your input | Choose audience, then continue | No |
| Proposal | Needs review | Review & approve opens exact confirmation; reject | Only through explicit confirmation |
| Read-back pending | Verifying outcome | Simulate read-back (study control) | No |
| Completed | Verified | Inspect fictional read-back evidence; Done | No |
| Dispatched, uncertain | Outcome unknown | Check existing result; then View recovery details | No; no resend |
| Changed facts/revision | Review outdated | Prepare a fresh review | No |
| Rejected/stopped before dispatch | Not approved | Return to review | No |
| Missing access | Setup needed | View connections; preserve request | No |
| Read-only response | Answer ready | Inspect sources; Done | No; no changes made |

For the two-action handoff, verifying the document opens a new message proposal requiring separate approval. The clarified audience carries into both actions. Confirmation includes operation, destination, audience, identity, workspace, connection revision, proposal revision, material values and content. Input sources and post-action observations are separate.

Minimize and expand preserve the task. Study selectors jump to fictional states and are not product controls. Shared `actionView` is a presentation helper, not a normalized server action or approval token. Separate requester/reviewer roles and escalation remain unspecified and must be designed before adoption.
