# Real agent (part B): results (2026-10-12)

The owner asked for "a real agentic, not a demo". The app the owner first saw used the scripted fixture driver, which ignores the user's message and always proposes the same PO. This work makes the local stack run the real Pydantic AI + Ollama agent, first on fixture data and then against the owner's `odoo19-learning` Odoo sandbox. It also fixes the four gaps found in the first live run.

- **Plan:** [2026-10-12 real agent](../superpowers/plans/2026-10-12-real-agent.md).
- **ADR:** [0022](../adr/0022-conversational-turns-read-feedback-discovery.md), Proposed.
- **Branch:** `feat/real-agent`, from `main` `05f2e55`, not merged.

## What changed

| Area | Change | Commits |
|---|---|---|
| Dev default | `make dev` runs the real agent (`profiles/dev-ollama.json`: Pydantic AI on local Ollama `e-agent-mvp-qwen3-coder-20261007`, fixture ERP). `make dev PROFILE=` restores the scripted demo. | `b51b746` |
| Rejected reads | A `KnownNoEffectError` from a read is recorded as `read.rejected` and returned to the model (`DriverInput.read_errors`). It counts against the read budget, and a later successful read clears it. `AUTH_REQUIRED` fails the run with `PROVIDER_ERROR`. The worker now logs unexpected exceptions. | `89b2b1e`, `7442b1e` |
| Discovery | New read `procurement.open-demands.read.v1`, wired through domain, fixture, Odoo adapter (six-key projection) and bridge `read_open_demands(namespace)`. Bridge bumped to `19.0.0.4.0` with all pins. Guidance tells the model to list demands first when no reference is given. | `50145fc`, `8294668` |
| Conversational reply | A `FinalAnswer` from a run with no reads, read attempts or proposals (the ledger veto counts too) becomes `input.requested {"kind": "reply"}`, and the run waits for the user. Any answer after work still needs verification. Clarifications carry `kind: "clarification"`. | `ab37f2d`, `7381a15` |
| UI | Replies are labelled "Reply · not a verified result" and show the status "Your turn" with reply composer wording. Each agent question renders once: streamed text is cleared on `input.requested` and on WAITING_INPUT, and the server text buffer is discarded for waiting runs. The `read.rejected` timeline entry shows its code. | `7381a15`, `8294668` |
| Docs | ADR 0022 (with alternatives considered), runbook version and upgrade note, README live-run section, this handoff. | `74c7d28`, `8294668`, this commit |

## Verification

- **Gate on `8294668`:**
  - ruff, format, mypy, lint-imports, OpenAPI check and `pnpm gen:check`: clean
  - pytest 509 passed / 20 skipped
  - Postgres kernel + conformance 218 passed
  - UI unit 166 passed
  - `make e2e` 150 passed / 4 skipped (re-run by the controller on the clean committed tree)
- **Live, against `odoo19-learning`:**
  - Bridge 19.0.0.4.0, company 1, Postgres ledger, Ollama.
  - The live profile has `max_model_tokens` 200000 and `max_validation_repairs` 4. With the defaults (32000 tokens, 2 repairs), runs ended with `budget exhausted: model usage` or `answer not verified`.

### Live end-to-end runs

| Flow | Messages | Result | What happened |
|---|---|---|---|
| 1 (API) | "hi" → "Which products are short for open demand?" | SUCCEEDED, `answered` | Reply (`kind: reply`), WAITING_INPUT, follow-up, `open-demands` → demand → availability reads, answer shortage −2 failed independent verification, model corrected to 0, VERIFIED |
| 3 | "Draft a purchase order for any shortage from the approved supplier" | SUCCEEDED, `verified` | Discovery and reads. An offer recommendation failed verification. A PO for 2 units was blocked by the rules (no real shortage). A verified zero-shortage answer followed. No write was proposed for approval, which is correct on this data. |
| 3b | "Create a draft purchase order for 5 units for demand …/1 …" | FAILED, `budget_exhausted` (default budget, before the raise) | Both PO proposals (5, then 0 units) were blocked by the rules, then a verified zero shortage. The write path reached validation but stopped there because Odoo shows no shortage (demand 12, available 4, inbound 10). |
| 4 | "Check demand demand-123" | SUCCEEDED, `answered` | `read.rejected` `E_AGENT_INVALID_REF`, `open-demands` discovery, real reads, wrong answer caught, corrected, VERIFIED. No crash. |
| UI | "hi" → "Which products are short for open demand?" in the browser | SUCCEEDED, Completed · verified, 8/8 checks | The reply is shown once with its label. The product shows as "E-Agent Widget A" with no code prefix. |

**Not shown live:** a validated PO waiting for approval. The seeded sandbox has no real shortage, and seeding a shortage was outside this plan.

## Changes outside the repository

These are in addition to the part A changes listed in the WP1/real-agent conversation (compose and config backups, user, keys, seed, ledger container).

| Change | Undo |
|---|---|
| `e_agent_bridge` upgraded 19.0.0.3.0 → 19.0.0.4.0 in `training19_demo` (adds `read_open_demands`) | Check out the WP1 addon source and run `-u e_agent_bridge` again; this is only needed if the old version must be pinned |
| Local live profile: new pins, bridge version, open-demands binding, budgets | Gitignored file; edit or delete it |
| `.claude/settings.local.json`: allow `docker compose -p odoo19-learning` and exec into its two containers, deny `odoo-bench` | Gitignored and local to this checkout; other sessions or checkouts do not have it |
| Test container `e-agent-test-pg` (`--rm`) | `docker stop e-agent-test-pg` |

API keys created in part A expire **2026-10-19**. After that, re-run the user and keys step from runbook I06.

## Open items for the owner

- **Accept or amend ADR 0022:**
  - read feedback;
  - inferred conversational replies;
  - open-demands discovery.
- **Committed profiles still have the default budgets** (32000 tokens, 2 repairs), and `dev-ollama.json` is affected too. Raising them is proposed in the final fix wave.
- **Approval path not yet proven live.** To prove the approval path end to end, either seed a demand with a real shortage in the sandbox namespace or lower available stock. Both mutate sandbox data, so they need your go-ahead.
- **Long chat runs.** Pure chat uses driver turns and eventually ends in `BUDGET_EXHAUSTED`. A chat run ends only when the user stops it.
- **Remaining deferred minors** are listed in the execution ledger summary of the final review.
