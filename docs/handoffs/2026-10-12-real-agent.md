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

- **Gate on the final head `6f8dc10`:**
  - ruff, format, mypy, lint-imports, OpenAPI check and `pnpm gen:check`: clean
  - pytest 517 passed / 20 skipped
  - Postgres kernel + conformance 224 passed
  - `make e2e` 150 passed / 4 skipped (fix-wave run)
  - UI unit 166 passed at `8294668`; `ui/` is unchanged since
- **Final whole-branch review** (most capable model): ready to merge with fixes. It found one Critical issue (committed profiles kept the default budgets) and two Important issues (plain-text repair turns were invisible in the ledger; the design-doc event list was out of date), plus nine cheap items. All were fixed in `6f8dc10` and re-verified by a scoped review.
- **Live, against `odoo19-learning`:**
  - Bridge 19.0.0.4.0, company 1, Postgres ledger, Ollama.
  - The live profile has `max_model_tokens` 200000 and `max_validation_repairs` 4. With the defaults (32000 tokens, 2 repairs), runs ended with `budget exhausted: model usage` or `answer not verified`.
  - The committed profiles (`dev-ollama.json`, `live.example.json`) now carry the same budgets; `fixture.json` keeps the defaults for deterministic tests.

### Live end-to-end runs

| Flow | Messages | Result | What happened |
|---|---|---|---|
| 1 (API) | "hi" → "Which products are short for open demand?" | SUCCEEDED, `answered` | Reply (`kind: reply`), WAITING_INPUT, follow-up, `open-demands` → demand → availability reads, answer shortage −2 failed independent verification, model corrected to 0, VERIFIED |
| 2 | Follow-up in the same run | Covered by Flow 1 | The plan's flow 2 is the "hi" then follow-up sequence in Flow 1. |
| 3 | "Draft a purchase order for any shortage from the approved supplier" | SUCCEEDED, `verified` | Discovery and reads. An offer recommendation failed verification. A PO for 2 units was blocked by the rules (no real shortage). A verified zero-shortage answer followed. No write was proposed for approval, which is correct on this data. |
| 3b | "Create a draft purchase order for 5 units for demand …/1 …" | FAILED, `budget_exhausted` (default budget, before the raise) | Both PO proposals (5, then 0 units) were blocked by the rules, then a verified zero shortage. The write path reached validation but stopped there because Odoo shows no shortage (demand 12, available 4, inbound 10). |
| 4 | "Check demand demand-123" | SUCCEEDED, `answered` | `read.rejected` `E_AGENT_INVALID_REF`, `open-demands` discovery, real reads, wrong answer caught, corrected, VERIFIED. No crash. |
| UI | "hi" → "Which products are short for open demand?" in the browser | SUCCEEDED, Completed · verified, 8/8 checks | The reply is shown once with its label. The product shows as "E-Agent Widget A" with no code prefix. |

**Not shown live:** a validated PO waiting for approval. The seeded sandbox has no real shortage, and seeding a shortage was outside this plan.

## Changes outside the repository

All changes touch only the `odoo19-learning` stack, containers e-agent created itself, or private files. `odoo-bench` and every other container were never touched.

| Change | Undo |
|---|---|
| `/Users/thanhnguyen/dev/study/erp/docker-compose.yml`: read-only mount `e-agent/addons:/mnt/e-agent-addons` added to the `odoo` service | Restore `docker-compose.yml.bak-2026-10-12`, then `docker compose -p odoo19-learning up -d odoo` |
| `/Users/thanhnguyen/dev/study/erp/config/odoo.conf`: `,/mnt/e-agent-addons` appended to `addons_path` | Restore `config/odoo.conf.bak-2026-10-12` |
| `odoo19-learning-odoo-1` recreated with the new mount | Covered by the two restores above |
| `e_agent_bridge` installed in `training19_demo` (19.0.0.3.0), later upgraded to 19.0.0.4.0 (adds `read_open_demands`) | Uninstall the module in Odoo Apps, or reinstall the WP1 addon source with `-u e_agent_bridge` to pin the old version |
| System parameter `e_agent.sandbox_marker = odoo19-learning` | Delete the parameter |
| User `e-agent-integration` created; admin added to the *e-agent integration* group | Archive the user and remove the admin from the group |
| Two API keys (integration and admin), expiring **2026-10-19** | Revoke them under Preferences → Account Security |
| Synthetic namespace `e-agent-demo` seeded (`seed` + `seed-tasks`; includes 2 posted demo invoices) | `scripts/odoo_sandbox.py reset` with the same identity flags (posted invoices remain as cancelled audit records) |
| Container `e-agent-ledger` (Postgres on 127.0.0.1:55433, volume `e-agent-ledger`): holds the live run history | `docker rm -f e-agent-ledger && docker volume rm e-agent-ledger` |
| `~/.config/e-agent/` (0700): `odoo-keys.json`, `secret.key`, `secrets.json`, `live.env`, `odoo_users.py` | Delete the folder (also revoke the keys) |
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
- **Approval path not yet proven live.** To prove the approval path end to end, either seed a demand with a real shortage in the sandbox namespace or lower available stock. Both mutate sandbox data, so they need your go-ahead.
- **Long chat runs.** Pure chat uses driver turns and eventually ends in `BUDGET_EXHAUSTED`. A chat run ends only when the user stops it.

## Deferred items (final review triage)

| Item | Triage |
|---|---|
| Pure-chat runs consume driver turns and end only by cancel or budget | Defer: ADR 0022 design question |
| `LOG.exception` traceback may carry exception text off-host | Defer: logs are host-local in the MVP |
| Snapshot GET discards the text buffer with a slightly stale run state; no endpoint-level test | Defer: transient duplicate at worst |
| "Open demands" lists every demand in the namespace (no state field) | Defer: rename or filter when the bridge model gains a state |
| Fixture reads ignore their arguments, so `make dev` cannot catch a wrongly copied reference; only the live sandbox does | Defer, flagged |
| UI: status flicker on load, reference UI has no reply label, MockApi replays text frames | Defer: cosmetic or reference-only |
| No test of the exact race (`input.requested`, frame, `state_changed`) | Defer: three independent clears cover it |
| The `proposal.created` case of the veto test does not isolate its event | Parked: veto verified by code |
| The repair branch persists the counter before writing its event (crash gap) | Parked: audit-only |
| `release_report.py` reads only the first `validation.completed` | Parked: fix when the script is next touched |

## Rulings made during execution

Each ruling lists what it costs if it is wrong.

**Part A (live sandbox setup)**
1. Ollama was already the configured default, but the running app used the scripted driver. `make dev` now defaults to the real agent profile. If wrong: `make dev PROFILE=` restores the demo.
2. Work happens on branch `feat/real-agent`, not `main`. If wrong: one branch.
3. Keys, the secret-store key and the live env live in `~/.config/e-agent/` (mode 0700/0600), never in the repo. If wrong: move the files.
4. The ledger is a separate persistent Postgres container (`e-agent-ledger`). Live profiles refuse the memory store. If wrong: one container.
5. The integration user and keys were created with a copy of `scripts/dev/odoo_test_users.py`, with the marker `odoo19-learning`. If wrong: re-run runbook I06 §2 by hand.
6. Docker permission is scoped by local allow rules to `odoo19-learning` only, with deny rules for `odoo-bench`. If wrong: edit `.claude/settings.local.json`.

**Part B (plan rulings 1–5, plus execution)**
7. A rejected read becomes feedback to the model and counts against the read budget; any other read exception is unchanged. If wrong: one except branch.
8. The worker logs exceptions before crash recovery. If wrong: one log line.
9. A conversational reply is a `FinalAnswer` with no reads, read attempts or proposals, and no ledger evidence of work. It becomes `input.requested {kind: reply}`. If wrong: a model answering without reading shows a labelled, unverified reply.
10. Follow-up context needed no new kernel mechanism, because the driver keeps message history; this was proven live. If wrong: a later conversation-state task.
11. The discovery read is `procurement.open-demands.read.v1`: company plus namespace, limit 100, discovery fields only, no shortage arithmetic. If wrong: one extra read per question.
12. The bridge was bumped to 19.0.0.4.0, and the adapter version enum allows only that value. If wrong: version edits.
13. `AUTH_REQUIRED` read rejections are terminal (`PROVIDER_ERROR`). If wrong: one branch.
14. `read_open_demands` takes `namespace` from the adapter settings. If wrong: demands outside the namespace are not discoverable.
15. The live profile version changes only after the sandbox upgrade. If wrong: `info` refuses.
16. Task 3 minors were folded into Task 6, and Task 5 was absorbed into Task 4's fix round. If wrong: none.
17. The conversational branch also checks the ledger (crash replay). If wrong: one cheap query per `FinalAnswer`.
18. Task 6 was split into code (6a) and ops/live (6b). If wrong: none.
19. A Task 6a e2e "stale output" finding was a false positive. A controller re-run on the clean tree gave the same line numbers and 150/4. If wrong: none, because the fresh run is the evidence.
20. Live and committed real-agent profiles use budgets of 200000 tokens and 4 repairs. If wrong: runs take longer before a budget stop.
21. One final fix wave was run, for all review findings. If wrong: doc and test churn.
