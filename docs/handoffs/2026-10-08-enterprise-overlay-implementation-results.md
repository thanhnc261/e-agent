# Enterprise overlay implementation: results

Date: 2026-10-09 (Asia/Ho_Chi_Minh), revised the same day after independent review. This is the implementation report requested by the [2026-10-08 Claude implementation handoff](2026-10-08-claude-overlay-implementation.md), for the [enterprise overlay adoption plan](../../archive/docs/plans/2026-10-08-enterprise-overlay-adoption.md). It replaces the interim [progress check](2026-10-09-overlay-progress-check.md).

The [independent implementation check](../reviews/2026-10-09-overlay-implementation-check.md) reproduced five defects in the first delivery. All five are corrected; §8 records what was wrong, what changed and the actual outcomes. Revision 1 of this report claimed the work was complete when it was not: the browser suite it cited did not cover a missing task link, a deliberate detach while a task address was current, or a malformed address, and the discovery tests it cited accepted malformed payloads. Those gaps are now closed by tests that fail against the original code.

Everything below was verified against deterministic fixtures only. **Live-release readiness is unchanged**: the README still states `local live release is NOT_READY`, and nothing here is evidence of live provider, model or human-approval qualification. No live business mutation, model qualification or sandbox reset was run for this assignment, and the separate `enterprise-agent/experiment` research system was not touched.

## 1. Work-package status

| ID | Status | What landed |
|---|---|---|
| FE-00 | Done | Baseline recorded (below); Prettier 3.6.2 pinned with `.prettierrc.json`, `.prettierignore` and a module-by-module `.prettierscope` driven by `ui/scripts/format.mjs`; `format` / `format:check` scripts, with `format:check` added to `pnpm check`; export and slot inventories pinned by Vitest; baseline screenshots captured. |
| FE-01 | Done | L5, L6 and L7 entry files reduced to public surfaces; implementations extracted into `providers/`, `hooks/`, `slots/`, `presentation/`, `primitives/`, `features/*`, `config.ts`, `shared/`, `overlay/`, `sidebar/`, `full-page/`. Four new dependency-cruiser rules, each negative-tested. |
| FE-02 | Done | Calm semantic tokens (surface/border/accent/status/shadow/duration/control roles); DTCG compiler extended with composite shadows, durations and per-dimension delta blocks; `ActionButton`, `StatusBadge`, `Surface`, `Disclosure`, `TextAreaField`, `Panel` primitives adopted across the features; theme/appearance/density dimensions with host-owned DOM attributes; development-only gallery. |
| FE-03 | Done | Typed evidence and outcome projections in `ui-core/selectors/`; `EvidencePanel` and `OutcomePanel` rewritten on them; every `window.innerWidth`, `closest()` and `getRootNode()` query removed from L6/L7; shared `TaskSurface` owns region membership and order for all placements. |
| FE-04 | Done, corrected | Standalone hash routes (`#/overview`, `#/work`, `#/connections`, `#/task[/<runId>]`) with validated parsing and fallback; neutral Overview, Session work and Connections pages; one controller above the router; L7 refuses a host page body while a decision is outstanding. Docked added to the shared conformance targets. Route/controller ownership reworked after review (§8.1–8.3). |
| FE-05 | Done, with a stated limitation | `presence` and `operator` appearances ship as **non-colour** token variants (shape, scale, elevation, motion). An appearance may not redefine a colour role, so no variant can weaken a theme's contrast guarantee; this is enforced by a test over every theme × appearance pair. The mockup's dark "Operator" palette is therefore *not* reproduced — see §5. |
| API-01 | Done, corrected | [ADR 0017](../adr/0017-member-discovery-read-models.md) accepted; `e_agent.kernel.discovery` application service; `GET /v1/me/connections` and `GET /v1/me/task-catalog`; OpenAPI and the TypeScript client regenerated; UI/integration designs updated. Availability now reuses the host's own resolution rules (§8.4). |
| FE-06 | Done, corrected | Catalog and read-only Connections views rendered from those APIs, with distinct loading / empty / denied / unsupported / malformed / error states, revoked marking, and navigation hidden when the workspace does not provide the view. Neutral discovery fixtures added to the mock API. Payload validation tightened after review (§8.5). |
| FE-07 | Partly done | Both deliveries are enabled by default and this report publishes screenshots, checks and limitations. No temporary rollout switch was introduced, so there is none to remove. **No human usability study and no screen-reader session were run** (§5). |

## 2. Changed behaviour

**Presentation.** Theme, appearance, density and surface are four independent dimensions. L7 resolves each as explicit host configuration → scoped session preference → validated default; a host-pinned dimension is marked locked and the header then offers no control for it. L7 reports the resolved values to L8 through `onPresentation`, and `apps/web` / `<e-agent-overlay>` are now the only places that write `data-theme`, `data-appearance`, `data-density` or `lang`. Previously the header read and mutated its own root node.

**Responsive ownership.** L7 observes its own surface with a `ResizeObserver` and publishes a semantic `compact` value through the L5 surface context. Task navigation history and the approval reveal read that instead of `window.innerWidth`; task navigation no longer inspects its ancestors. A new proposal is scrolled into view once in *every* placement (previously only below 640px), with `block: "nearest"`, no focus change, and `prefers-reduced-motion` honoured.

**Pending-control contract.** `ActionButton` previously implemented `isPending` as `isDisabled`, contradicting its own documentation. It now forwards `isPending` to React Aria: a pending control keeps its place in the tab order and its accessible name, is `aria-disabled`, cannot be activated, and announces the work. Verified by a happy-dom component test.

**Projections.** Evidence and outcome are typed discriminated unions built at the client/core boundary. A missing source, locator, observation time or completeness stays unknown rather than becoming an empty string or "complete"; an unrecognised bundle schema is reported as unsupported while the raw record stays inspectable; a verification check without a recorded `passed` verdict renders as unknown, not as a pass or a failure. `NEEDS_RECONCILIATION` remains unresolved and still offers only the existing authorized reconciliation.

**Navigation.** The standalone app has Overview, Session work and Connections sections. Navigating issues no run and no command, and preserves the active run, the submission identity and the draft (the controller is created once, above the router). Session work is labelled explicitly as this browser session only, shows each entry's last-known state as such, shows no count for anyone else's work, and re-reads a task from the server when it is opened. A run id in a route is only a navigation request, attached through the controller. A host page body is honoured on the standalone surface only, and only while no decision is outstanding — navigating cannot move a pending review out of reach.

**Discovery.** Overview shows the admitted task catalog with real availability and a bounded reason when a task type is unavailable; when the server cannot supply it, the honest non-specific statement stands in and no empty catalog is claimed. Connections is read-only: configuration status and observed health are separate facts, health is always "Unknown · not checked for this page", an undisclosed acting identity reads "Not disclosed", and the view contains no interactive control at all beyond disclosure toggles. A request to connect is never represented as access granted.

**Unchanged by design.** Package architecture, layer boundaries, public exports, slot IDs, surface modes, the approval state machine, digest and canonical-value checks, stale/expired handling, idempotency, the SSE contract and the controller lifetime. The export inventories are pinned by tests; additions are deliberate and listed there.

## 3. Verification actually run

Baseline before any change (same checkout, same dirty tree): `pnpm --dir ui check` passed with 8 test files / 56 tests; `pnpm --dir ui conformance` passed 86 with 2 opt-in capture skips. No pre-existing failure was observed, so none is carried forward.

| Command | Result |
|---|---|
| `pnpm --dir ui check` | **Passed** — TypeScript, scoped formatting ("All matched files use Prettier code style"), 146 unit tests across 15 files, 0 dependency violations over 134 modules / 350 dependencies, provider neutrality, and all three production host builds |
| `pnpm --dir ui conformance` | **Passed** — 135 passed, 2 skipped (the opt-in screenshot captures) in Chromium, including the reviewer's `route-regressions.spec.ts` and `route-transitions.spec.ts` |
| `uv run pytest -q` | **Passed** — 324 passed, 29 skipped |
| `uv run ruff check .` / `ruff format --check .` | **Passed** |
| `uv run mypy` | **Passed** — no issues in 92 source files |
| `uv run lint-imports` | **Passed** — 7 contracts kept, 0 broken |
| `uv run python scripts/export_openapi.py --check` | **Passed** — the checked-in OpenAPI matches the implementation |
| `git diff --check` | **Passed** |

These are the numbers after the corrections in §8. The pre-correction figures were 123 unit tests and 126 conformance cases.

Generated files: `pnpm --dir ui gen` was run after the token and API changes. `gen:check` compares against Git, and this checkout was already dirty before the assignment, so that comparison is not a regression signal here. Instead, generation was confirmed **idempotent** (two consecutive `pnpm gen` runs produce byte-identical `schema.ts`, `tokens.css` and `tokens.json`), and the OpenAPI diff was reviewed: 464 added lines, 0 removed, exactly the two new `/v1/me/*` paths and their schemas.

New tests added by this work:

- **Unit (Vitest):** `selectors.test.ts` (9) — evidence and outcome projections including malformed, missing and unrecognised input; `discovery.test.ts` (6) — discovery envelope validation, revoked marking, denied-vs-empty; `preferences.test.ts` (6) — presentation precedence and invalid values; `ActionButton.test.tsx` (3) — pending vs disabled focus and activation; `public-api.test.ts` ×2 — export, slot and surface inventories; `routes.test.ts` (4) — route parsing, fallback and run-id rejection; contrast suite extended to every theme × appearance pair and both densities.
- **Browser (Playwright):** `projections.spec.ts` (3), `routes.spec.ts` (7, including 320 CSS pixels and a full Vietnamese pass), `discovery.spec.ts` (6), `presentation.spec.ts` (5, including appearance-does-not-change-terms and reduced motion). Docked (`?layout=sidebar`) joined the shared target list, so the shared contract cases and the redesign-safety cases now also run against it.

Manual review performed: desktop (1440×1050), mobile (390×844), 320×740, a narrow docked column and the embedded shadow-root host, in light and dark, Calm/AI Presence/Operator, EN and VI, from the captured screenshots and the browser runs. Keyboard-only approval, focus visibility, Escape-before-close and focus return to the launcher are covered by the existing contract and surface suites, which still pass.

## 4. Evidence

Screenshots are deterministic fixture captures, produced by the opt-in specs and written to the git-ignored `evidence/` tree:

```bash
mkdir -p evidence/2026-10-09-overlay
E_AGENT_UI_CAPTURE_DIR=../evidence/2026-10-09-overlay/workspace \
  pnpm --dir ui conformance -- packages/ui-conformance/tests/visual-review.spec.ts
E_AGENT_OVERLAY_CAPTURE_DIR=../evidence/2026-10-09-overlay/surfaces \
  pnpm --dir ui conformance -- packages/ui-conformance/tests/overlay-visual.spec.ts
```

| View | Path |
|---|---|
| Standalone Overview with the real admitted catalog | `evidence/2026-10-09-overlay/workspace/desktop-overview.png` |
| Session work | `.../desktop-session-work.png` |
| Read-only Connections | `.../desktop-connections.png` |
| Review, Calm / compact / AI Presence / Operator | `.../desktop-approval.png`, `desktop-approval-compact.png`, `desktop-approval-presence.png`, `desktop-approval-operator.png` |
| Dark theme, verified result, evidence | `.../desktop-dark.png`, `desktop-result.png`, `desktop-evidence.png` |
| Mobile review, embedded overlay, docked | `.../mobile-approval.png`, `mobile-overlay-approval.png`, `overlay-approval.png`, `sidebar-approval.png` |
| All four surfaces under review, workbench dark and mobile | `evidence/2026-10-09-overlay/surfaces/*.png` |
| FE-00 baseline, for comparison | `evidence/2026-10-08-overlay/fe00-baseline/*.png` |

The Overview and Connections captures run against the real fixture server, not the mock: the catalog shows the eight admitted task types with their own descriptions, and the inventory shows the actual `fixture-erp` connection with 16 capabilities and unknown health.

## 5. Failures, skips and limitations

- **No human usability study and no screen-reader session were run.** The plan's §6 asks for small formative sessions with users from more than one business function; that needs people and was out of scope for this assignment. Automated accessibility coverage here is contrast tests, keyboard conformance and manual screenshot review — it does not substitute for either.
- **AI Presence and Operator are non-colour variants.** They change radius, elevation, type scale and motion only. Allowing an appearance to redefine a colour role would apply it on top of every theme and could silently break a contrast guarantee, so it is forbidden and tested. Reproducing the mockup's dark Operator palette needs per-theme appearance token sets; that is deferred, not attempted.
- **Two conformance cases are skipped** on every run: `visual-review.spec.ts` and `overlay-visual.spec.ts` are opt-in screenshot captures gated behind `E_AGENT_UI_CAPTURE_DIR` / `E_AGENT_OVERLAY_CAPTURE_DIR`. They were run separately (§4) and passed.
- **`pnpm --dir ui gen:check` was not used as a gate** because the working tree was already dirty before this work. Idempotency and the reviewed OpenAPI diff stand in; the check should pass on a clean candidate.
- **Formatting is scoped, not repository-wide.** `.prettierscope` lists the migrated modules. Files outside it — `ui/packages/ui-core/src/{approval,controller,digest,i18n,presentation,store}.ts` and `ui/apps/reference-vanilla/src/main.ts` — are not yet formatted. That is deliberate: the plan forbids bundling repository-wide reformatting with behaviour changes.
- **Live qualification is untouched.** No live provider call, no model run, no sandbox reset, no business mutation. The UI has still only been exercised against the fixture server.

## 6. Remaining unimplemented work

Still absent, and deliberately not simulated anywhere in the product:

- A durable cross-session or tenant-wide work and review inbox, and any pending-review count for other people's work. Session work is this browser session only.
- Proposal editing and any host re-proposal contract. The browser cannot patch canonical arguments.
- Administrative integration management: enabling, connecting, testing, re-authorizing, disabling and revoking have no API and no UI.
- Delegated OAuth and app registrations ([integration auth design](../design/integration-auth-sdk.md) §9 Phase 2).
- Icon and manifest asset delivery; the discovery responses carry identifiers and text only, because arbitrary manifest URLs would make the browser fetch unknown hosts.
- Cross-origin embedding. The session cookie is `SameSite=Strict`, so `<e-agent-overlay server=…>` remains same-origin.
- Additional provider integrations and cross-domain adapters. Procurement plus the existing sales, CRM and receivables answers remain the installed scope.

Next qualification steps are unchanged and separately identified: the owner's Odoo sandbox and upgraded bridge, live model qualification, and integrated model/API/UI runs with human approval, per the [remediation retest](../reviews/2026-10-07-mvp-remediation-retest.md).

## 7. How to run it

```bash
pnpm --dir ui check          # types, scoped format, unit tests, boundaries, neutrality, builds
pnpm --dir ui conformance    # browser contract suite against the fixture server
pnpm --dir ui gallery        # development-only component gallery (never in a production build)
uv run pytest -q             # server, kernel and domain suites
uv run python scripts/export_openapi.py --check
```

The standalone app serves Overview at `/`, with `#/work`, `#/connections` and `#/task/<runId>`; `?layout=`, `?lang=`, `?theme=`, `?appearance=` and `?density=` still pin their dimension and then hide its control.

## 8. Corrections after independent review

The [independent check](../reviews/2026-10-09-overlay-implementation-check.md) reproduced five defects. Each is fixed below, with a test that fails against the original code. The reviewer's own specs — `route-regressions.spec.ts` and `route-transitions.spec.ts` — were kept exactly as written; no assertion in them was relaxed.

### 8.1 Missing task links caused an unbounded request loop (P1)

**Was:** `main.tsx` attached whenever the route's run id differed from the controller's. A 404 makes the controller detach, which sets the run id to null, which makes the condition true again — so the render loop re-attached forever. The reviewer measured **245 snapshot requests in roughly 500 ms**.

**Now:** `useTaskRoute` in `apps/web/src/app/useRouter.ts` owns the task address as a small state machine (`none` / `attaching` / `attached` / `unavailable`). A requested run is attached **once per navigation**, tracked by a ref; the outcome of `controller.attach` decides the state. A failed attach becomes a terminal `unavailable` state that renders `TaskUnavailable` — the address is kept, the reason is stated, and Overview and Session work are offered. It is never retried without a deliberate new navigation.

Two subtleties the first fix got wrong and the tests caught: `attach` sets the controller's run id *before* the read completes, so "route id equals controller id" proves nothing mid-attach and is only consulted on the first evaluation of an address; and the attach outcome must survive the effect re-running (an effect cleanup was discarding it, leaving the state stuck at `attaching`).

**Verified by:** the reviewer's first regression; plus new cases for a denied route (`FORBIDDEN` rendered as 404, so indistinguishable from missing — both stop), and Back/Forward across an unavailable address causing no repeated reads.

### 8.2 New task was undone by the current task route (P1)

**Was:** `TaskNavigation` detached through the controller, but the address still named the old run, so the same effect re-attached it. With a review outstanding the composer stayed disabled and the user could not start the intended task.

**Now:** once an address has settled as attached, the address follows the controller rather than the reverse. A deliberate detach moves the route to Overview, and selecting another task from history moves it to that run — both with `history.replaceState`, so Back does not return to an address that no longer describes anything. A route whose attach failed is excluded from this rule, so it keeps its unavailable state instead of silently bouncing away.

The route is now also the **single place that attaches**: `SessionWorkList` only navigates, and no longer calls `controller.attach` itself. The controller still owns the re-read and every safeguard; the route only asks.

**Verified by:** the reviewer's second regression and `route-transitions.spec.ts`; plus a new case covering history selection while the address still names another run.

### 8.3 Malformed URL encoding crashed the application (P2)

**Was:** `parseRoute('#/task/%')` threw `URIError` and the app rendered nothing.

**Now:** `decodeRunId` catches malformed encoding and returns "no run id", the same as a value that fails the opaque-id shape check. An address a user can type cannot stop the app.

**Verified by:** the reviewer's third regression; plus pure tests over malformed escapes and every printable single-character suffix.

### 8.4 Discovery claimed an ambiguous binding was available (P2)

**Was:** `task_catalog` counted *distinct connection ids*, so two admitted bindings for the same contract on the same connection collapsed to one and the template was reported `available`. `PluginRegistry.resolve` refuses exactly that state with `CONFLICT: ambiguous binding; refusing to choose`.

**Now:** availability is decided by calling the host's own rules and reporting their refusal — `registry.resolve` for the binding and `registry.executor_for` for the adapter. **No execution rule was relaxed to make a catalog claim true**; the catalog reports what the coordinator would do. The reason union gained `no_executor` and `no_verifier` (OpenAPI and the client were regenerated).

The reviewer also asked about ANSWER capabilities, where "a random usable connection is not sufficient proof of a usable verifier/read path". That was a second real defect in the same function: answers previously counted *any* usable connection. An answer now requires exactly one usable read connection across all bindings — mirroring the agent tool surface — **and** an unambiguous registered verifier, because `_answer` raises `DEPENDENCY_UNAVAILABLE` without one.

**Verified by:** five new kernel tests, including one that asserts `registry.resolve` still raises `CONFLICT` for the duplicate-binding case and that the catalog agrees with it, and one that checks every template called available actually resolves to a binding with a unique executor. Against the real fixture profile all eight admitted task types remain `available` under the stricter rules, so the checks add no false negatives.

### 8.5 Malformed discovery data became a valid empty result (P2)

**Was:** the projection validated `schema_version` but not the payload. `projectConnections({schema_version: '1'})` returned `{kind: 'ready', items: []}` — a missing collection presented as an empty inventory — and an entry carrying only `connection_id` and `integration_id` produced an invented `revision: 0` with `unusable: false`.

**Now:** a declared version must actually be honoured. A missing or wrongly-typed collection, and any entry whose required fields are absent or of the wrong type, produce a new `malformed` state, distinct from `unsupported` (wrong version), `denied` and a legitimate empty list. One malformed entry fails the whole response rather than quietly shortening a list the user would read as complete, and no value is ever invented for a missing field. Unrecognised *enum values* still fail closed — an unknown availability is not usable, an unknown status is labelled unknown — because that is a safe interpretation, whereas a wrong *type* is not interpretable at all.

The Connections section stays visible in the `malformed` state: the workspace demonstrably offers the view, and hiding it would leave the user with no way to see that it is broken. An absent endpoint still shows no section.

**Verified by:** the reviewer's exact reproductions as assertions, parameterised per-field rejection tests for both projections, a test that nothing throws for any malformed input, and two browser cases confirming the UI reports malformed rather than showing an empty or partial inventory.

### Checks after the corrections

| Command | Result |
|---|---|
| `pnpm --dir ui conformance -- …/route-regressions.spec.ts` | 3 passed (3 failed before) |
| `pnpm --dir ui conformance -- …/route-transitions.spec.ts` | 1 passed (1 failed before) |
| `uv run pytest -q packages/kernel/tests/test_discovery.py apps/server/tests/test_api.py` | 32 passed (27 before) |
| `pnpm --dir ui check` | Passed — 146 unit tests, 0 boundary violations, 3 builds |
| `pnpm --dir ui conformance` | Passed — 135 passed, 2 opt-in skips |
| `uv run pytest -q` | Passed — 324 passed, 29 skipped |
| `uv run mypy` / `ruff check` / `ruff format --check` / `lint-imports` | Passed |
| `uv run python scripts/export_openapi.py --check` | Passed |

The limitations in §5 and the unimplemented work in §6 are unchanged. Human usability evaluation, screen-reader validation and live qualification remain outstanding and separate.
