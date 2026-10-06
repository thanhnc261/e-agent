# MVP development readiness review

**Date:** 2026-10-06. **Scope:** README, AGENTS.md, HLD, MVP detailed design, implementation plan, UI architecture, integration management, integration auth SDK, threat model and ADRs 0001–0013. **Question:** can MVP implementation start from these documents without guessing?

## 1. Verdict

**Ready to start, conditional on owner decisions D1–D5 in [plan §0](../implementation-plan.md#0-readiness-decisions-and-day-1-checklist).** Every work package on the critical path (I00 → I09) now has defined inputs, deliverables, a definition of done, and a gating ADR or decision. No unresolved input blocks I00–I11. BigQuery (D6) blocks only I12/I13, and the ERP Bench source (D7) is optional for I03.

The documents are design, not evidence. Nothing has been built or run, and the proposed toolchain versions must be confirmed in I01.

## 2. Checks performed

| Check | Result |
|---|---|
| Every accepted decision (ADR 0001) reflected in README, HLD, MVP design and plan | Yes, after the earlier review fixes |
| Every proposed ADR (0002–0013) referenced where it applies and mapped to a gated work package | Yes (ADR index *Gates* column; plan §0 D1–D5) |
| Every work package has dependencies, deliverables and definition of done | Yes (plan §3) |
| Planned packages consistent across HLD §4, MVP layout §3 and plan | Fixed: `adapter-secretstore-local` added to both |
| API surface sufficient for UI and CLI | Fixed: `ApprovalPresentation` endpoint and local browser session auth added (MVP design §12) |
| Event contract defined enough to generate UI types | Fixed: initial `RunEvent` catalog (MVP design §4.1) |
| Contracts cover later phases without kernel change | Yes: `ownership`, `credential_subject`, `connection_version` and digest fields are in I02 scope |
| System neutrality (UI/kernel free of provider identifiers) | Specified (ADR 0011/0012), now also an AGENTS.md rule and a CI gate |
| Security tests traceable to work packages | Yes (threat model T1–T19 → I05–I09, I12; gates in MVP design §13 and the UI conformance suite) |
| Single source for sequencing | Fixed: MVP design §14 now defers to the plan; there are no duplicate sequences |
| Phase 2 scope explicit, so MVP does not drift | Fixed: plan §10 backlog |
| Toolchain decided enough for I01 | Fixed: proposed baseline in plan §0 (uv/`uv_build`, ruff, mypy, pytest, import-linter, FastAPI native SSE, psycopg 3 + Alembic, pySHACL, Node 24 LTS/pnpm/React 19/React Aria/Vite/Vitest/Playwright) |
| Environment prerequisites explicit | Fixed: Day-1 checklist, including the external Odoo compose change that needs owner permission (D4) |
| Agent instructions point to the current baseline | Fixed: AGENTS.md reading order now includes the plan, ADR index and topic designs |

## 3. Issues found and fixed in this pass

| # | Issue | Fix |
|---|---|---|
| R1 | Plan header and design notes still said "ADRs 0002–0010" | Updated to 0002–0013, with gating via the ADR index |
| R2 | No consolidated list of owner decisions; risk of all proposed ADRs blocking everything | Plan §0 D1–D7, each tied to the earliest package it gates |
| R3 | Server framework, migration tool, TS toolchain unspecified | Proposed baseline in plan §0 |
| R4 | No browser auth for the MVP UI (MVP design only had a loopback CLI mode) | Local session cookie (HttpOnly, SameSite=Strict) + CSRF header. UI and the neutral test host are served same-origin; cross-origin embedding is Phase 2 |
| R5 | UI needed `ApprovalPresentation`, but the API table lacked it | `GET /v1/runs/{id}/approvals/pending` |
| R6 | No event type list for SSE/TS type generation | MVP design §4.1 catalog |
| R7 | `SecretStore` local adapter had no package home | `e-agent-adapter-secretstore-local` in HLD and layout |
| R8 | MVP design §14 kept an older six-step sequence that diverged from the plan | Replaced with a pointer to the plan |
| R9 | I00 still tracked an "overlay placement" open input | Removed (resolved by ADR 0011); I00 adds the Odoo integration user and sandbox marker |
| R10 | I03 appeared blocked on the ERP Bench source | Clarified: needed only before importing benchmark content |
| R11 | I06 implicitly required changing the external Odoo compose (outside this repo) | Explicit owner decision D4 |
| R12 | No milestones and no Phase 2 boundary | Plan §0 milestones M0–M6; plan §10 backlog |
| R13 | README pointed to the outdated MVP §14 anchor | Points to the plan and this review |

## 4. Remaining risks (accepted, tracked)

| Risk | Where handled |
|---|---|
| No local model reliably performs deferred writes | I04 rescope checkpoint (ADR 0010) |
| UI scope is large (eight TS packages + conformance + reference custom UI) | I08 builds client/ui-core/tokens first. Packages can start small, but boundaries are enforced from day one; visual polish is last |
| Odoo bridge transaction behaviour unverified on the local install | I06 concurrency and lost-response tests (ADR 0005) |
| Proposed toolchain versions may conflict | I01 confirms them and records actual versions; a rejection updates plan §0 |
| Ten-task scope without a deadline | Milestones M3/M5 are demonstrable checkpoints; I10/I11 cannot start before I07 + I09 |

## 5. Recommended first steps

1. Owner records D1–D5. Accepting the ADRs as proposed is the fastest path; any rejection needs a short alternative recorded in the ADR.
2. I00: environment manifest, Odoo integration user/API key, sandbox marker, Ollama model digests, a separate e-agent PostgreSQL.
3. I01–I02 to M1 (walking skeleton with CI green), then reassess estimates after I04/I07, as the plan states.
