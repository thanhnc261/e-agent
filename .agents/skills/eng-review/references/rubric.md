# Review rubric

Work through the areas in order. Severity by effect on a person using the software, not by how the spec is worded.

| # | Area | Questions | Rules |
|---|---|---|---|
| 1 | Scope and contract | Does the diff stay inside the allowed paths? Is every acceptance step demonstrated by a named test or command output? Does the cited evidence come from a successful gate on a clean commit at or before HEAD with only bookkeeping after it? | ENG-WORK-1, ENG-EVID-1 |
| 2 | Trust anchor | Can any path let model output approve, change policy, or mark verified? Did any state machine, digest, admission or verification logic move out of the kernel? Is stale approval rejected? Is evidence persisted before a write? Does a timeout stay UNKNOWN and reconcile? | ENG-TRUST-1 to ENG-TRUST-5 |
| 3 | Toggles and fallback | Does the feature have `off`, `shadow`, `on`? Does `shadow` act on the old path? Is fallback impossible after a reservation? Do readiness and evidence report the toggle? | ENG-TOGGLE-1 to ENG-TOGGLE-3 |
| 4 | Both stores | Does store-touching behaviour pass the conformance suite on the memory store and PostgreSQL, or is the Postgres run named as pending in the handoff? | ENG-STORE-1 |
| 5 | Architecture | Layer direction kept (lint-imports)? Portable contracts? Composition at bootstrap? No speculative module? Namespace layout intact? | ENG-ARCH-1 to ENG-ARCH-5 |
| 6 | Honest tests | Was each test watched failing first? Does it assert behaviour, not a mock? Are fixtures distinct from live results? | ENG-WORK-2, ENG-EVID-2 |
| 7 | Links and paths | Relative links resolve; moved paths are updated in code, config and current docs; dated records keep their history. | ENG-DOC-1 |
| 8 | Evidence and secrets | Evidence files are redacted; no key material in the diff, handoff or logs; skipped checks are named. | ENG-EVID-2, ENG-EVID-3, ENG-BOUND-3 |

Severity: **Blocker** = a rule enforced by gate, test, hook or permission is broken, or an accepted ADR is contradicted; **High** = correctness or the contract is affected but no hard rule breaks; **Medium** = a review-only rule is broken with a real effect; **Low** = style or a note. Only Blocker and High need a fix before the task closes.
