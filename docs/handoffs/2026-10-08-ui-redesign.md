# UI redesign implementation handoff

Date: 2026-10-08. Scope: the owner's requested UI change following the architecture/component reviews. **UI implementation and local fixture checks complete; live MVP remains NOT_READY.** Existing unrelated working-tree changes and earlier evidence are preserved. No live ERP, model, benchmark or research-system mutation was performed.

## Delivered

- Focused task workspace instead of a permanent grid of empty technical panels. Desktop navigation, conversation/decision/result column and contextual evidence/activity; compact disclosures in overlay/sidebar/mobile.
- Clear task status and separate approval-recorded, verifying, verified, failed and unresolved semantics. UNKNOWN outcome activity no longer claims verification. Public clarification questions/answers remain in the transcript.
- Readable complete approval terms, admitted schema titles/labels/order, checks and execution details. Actual amendment baseline is separate from a superseded proposal; absent/ambiguous baselines remain unknown. Mobile/sidebar/overlay review bodies scroll while decision controls remain reachable.
- Exact displayed terms, scope and expected effects checked against the canonical proposal alongside its digest; non-PASS findings block approval. Explicit review → confirm, expiry and stale-review behavior preserved. Unknown event versions do not mutate view state.
- Failed submissions retain the draft; admission retries use the same key across reload, and successful admission with a failed refresh reuses the known run ID. Active tasks require explicit New task navigation and remain in bounded current-session history. Clarification resumes the same run. Local initialization scopes history to API origin/tenant/principal.
- Result values correlate verified actions and host reports; verified object references come from the corresponding committed receipt. Source records/time/completeness are inspectable during review, with refresh and authorized audit download. Raw JSON remains an optional inspector/export.
- Shared light/dark/high-contrast tokens and EN/VI controls; named navigation slot and primary-slot ordering. Provider neutrality and Shadow DOM isolation retained. The vanilla reference consumes the same safety/retry core; it remains a minimal conformance reference rather than the production visual design.

Architecture decision: [ADR 0015](../adr/0015-task-workspace-presentation.md). [UI architecture](../design/ui-architecture.md), HLD/MVP clarifications, implementation plan and README updated. The kernel only projects generic admitted schema annotations and host-retained facts; the domain declares the concrete amendment reference. UI code contains no domain rule inventory or provider field lists. Canonical approval terms and server revalidation remain authoritative.

## Observed verification

| Command | Result |
|---|---|
| `pnpm --dir ui check` | Passed: TypeScript, **54 unit tests**, dependency boundaries, provider neutrality, three host builds |
| `E_AGENT_UI_CAPTURE_DIR=<unused-absolute-directory> pnpm --dir ui conformance` | **63 passed**, Chromium; includes opt-in screenshot capture. Normal runs skip that one capture case. Default/overlay/reference safety and real-kernel fixture journeys; narrow sidebar/overlay added |
| `uv run pytest -q -rs` | **294 passed, 29 skipped**. Skips: 2 PostgreSQL migration, 8 process-recovery checks without isolated PostgreSQL; 19 live ERP checks without sandbox configuration |
| `uv run mypy` | Passed, 91 source files |
| `uv run ruff check .` / `uv run ruff format --check .` | Passed, 147 formatted files |
| `uv run lint-imports` | Seven architecture contracts kept |
| `uv run python scripts/check_wheels.py` | Ten distributions install/import from their dependency closures; trusted inventories match; installed procurement and ERP-04..08 demos pass outside the repository |
| `uv run python scripts/export_openapi.py` / `pnpm --dir ui gen` | OpenAPI, TypeScript and token outputs regenerated |
| `git diff --check` | Passed |

Regressions cover display substitution with an intact digest, missing/duplicate/conflicting paths, altered scope, non-PASS findings, unsupported schema versions, changed same-identity findings, lost admission responses, known admission with unavailable snapshot, stable retry after reload, active-task navigation, session identity, outcome correlation and baseline versus prior-proposal values. Existing stale/expired/keyboard approval, stream replay, text sanitization, theme isolation and complete/reject/reload journeys still pass.

During development, checks caught outdated label/order assertions and a real narrow history-button overflow. The assertions now reflect the admitted schema order/new copy; box sizing and compact history corrected the overflow. The final runs above pass. 640×450 validates an effective half-size layout representative of 200% desktop zoom; it is not a claim of exhaustive browser/assistive-technology certification.

## Screenshots and reproduction

Fresh final captures are in ignored local evidence directory `evidence/ui-redesign/20261008/reviewed-screens/`. `visual-review.spec.ts` is the reproducible capture script and refuses an existing destination directory. Screenshots are deterministic fixture results, not live ERP evidence.

- [Desktop start](../../evidence/ui-redesign/20261008/reviewed-screens/desktop-empty.png)
- [Desktop approval](../../evidence/ui-redesign/20261008/reviewed-screens/desktop-approval.png)
- [Mobile approval](../../evidence/ui-redesign/20261008/reviewed-screens/mobile-approval.png)
- [Verified fixture result](../../evidence/ui-redesign/20261008/reviewed-screens/desktop-result.png)
- [Evidence inspector](../../evidence/ui-redesign/20261008/reviewed-screens/desktop-evidence.png)
- [Overlay approval](../../evidence/ui-redesign/20261008/reviewed-screens/overlay-approval.png)
- [Mobile overlay](../../evidence/ui-redesign/20261008/reviewed-screens/mobile-overlay-approval.png)
- [Sidebar approval](../../evidence/ui-redesign/20261008/reviewed-screens/sidebar-approval.png)
- [Dark theme](../../evidence/ui-redesign/20261008/reviewed-screens/desktop-dark.png)

Desktop/mobile/overlay/sidebar/dark/source screens were visually inspected. All exact terms remain available through review scrolling; evidence/activity are secondary. Operator usability review and comprehensive accessibility audit remain release follow-ups.

Preview the fixture app using `uv run e-agent serve --static ui/dist/web`, then open `http://127.0.0.1:8787/`, `/host.html` or `/?layout=sidebar`. Playwright's ephemeral fixture server has been stopped after its tests; no deployment or commit was performed.

## Review finding coverage and remaining work

| Finding | This change |
|---|---|
| LC-02 displayed/canonical mismatch | Shared core fails closed; all three hosts tested |
| LC-03 unfinished tasks hidden | Explicit navigation + bounded session history/resume. No server-wide history API |
| LC-04 failed submission loses input/retry identity | Draft retained and stable admission retry/known run ID; no ERP replay semantics added |
| LC-05 false verification/obsolete approval copy | State/status selectors and accurate recorded decision/result copy |
| LC-06 unknown event version interpreted | Unsupported payload retained without interpretation; snapshot refresh |
| LC-07 unreadable approval/false amendment baseline | Schema labels/order, exact values and actual/proposal comparison; resource names remain references when unavailable |
| LC-08 poor hierarchy/mobile action reachability | New layouts, bounded review scrolling, narrow and effective zoom checks, screenshots |
| LC-09 raw evidence only after completion | Structured source inspector and verified values over existing authoritative records, pre-decision access and full export. Rich typed BFF projections/immutable provenance remain incomplete |
| LC-10 customization/accessibility | Navigation slot, primary order, unique region IDs, semantic status, focus/theme/locale controls; comprehensive a11y/operator certification still unverified |

LC-01 (missing SHACL shapes), AR-01 (task acceptance allowing an unrelated verified answer), AR-02 (driver-independent recovery), plugin admission/routing findings, immutable execution provenance, readiness/telemetry and stale broader design claims remain separate backend work. This change does not certify that a successful action fulfills every original task intent. Rich resource labels, localized domain labels, admitted task examples, cross-device history and dedicated mobile sheets/tabs are not implemented.

The owner's exact sandbox bridge upgrade and integrated model/persistent API/UI qualification are still required. Older model/ERP reports remain evidence for their frozen source/environment; they were not rerun for this changed candidate. Do not call the MVP or enterprise product ready based on this UI work.
