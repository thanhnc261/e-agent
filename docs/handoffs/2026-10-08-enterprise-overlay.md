# Selectable enterprise agent overlay handoff

Date: 2026-10-08. Scope: requested research/design and selectable UI overlays. Local fixture UI implementation complete; this does not establish live MVP readiness. Earlier working-tree changes and historical evidence were preserved. No live ERP/model, benchmark or research-system operation was performed.

## Delivered

[Research 11](../../research/11-enterprise-agent-overlay-design.md) compares Microsoft Copilot, Carbon/IBM and SAP primary design references, distinguishes vendor guidance from usability evidence and specifies the Workbench visual/interaction design. [ADR 0016](../adr/0016-selectable-agent-surfaces.md), UI architecture, HLD/MVP/implementation plan, research index and README record the implemented boundaries.

- **Workbench:** expanded floating workspace with a task/review column and context column for authoritative task overview, supported recorded milestones, evidence and activity. Responsive stack, shared themes/EN/VI, restrained accent and existing exact business review controls.
- **View switch:** Compact, Workbench, Docked and standalone Workspace. Embedded hosts expose the first three. Switching uses the same controller, retains active run/history/unsent draft, restores focus and returns an open confirmation to review. It sends no decision or new task.
- **Minimize/reopen:** draft and run retained; pending-review badge; Escape first backs out of confirmation, then minimizes and returns focus to the launcher.
- **Preference:** validated session-local layout identifier, overridden by explicit URL/element config. Embedded keys use element ID; multiple instances should have distinct IDs. Unsent draft text is in memory and does not survive reload.

L3 owns draft state; L5 exposes surface context and `task-overview`; L6 renders the selector and overview; L7 owns selection/preferences/focus; L8 limits embedded modes. No new backend endpoint, vendor dependency, provider identifier, simulated plan or enforcement rule was added.

## Verification

| Command | Observed result |
|---|---|
| `pnpm --dir ui check` | Passed: **56 unit tests**, TypeScript, dependency boundary and provider-neutrality gates, all three host builds |
| `pnpm --dir ui conformance` | **86 passed, 2 skipped** opt-in capture cases; Chromium across default, embedded, Workbench and vanilla reference |
| `E_AGENT_OVERLAY_CAPTURE_DIR=<unused-absolute-directory> pnpm --dir ui conformance` | **87 passed, 1 skipped**; includes the new capture case; older capture case remains opt-in |
| `git diff --check` | Passed |

New browser checks cover draft retention across remounts, pending exact review, confirmation reset, keyboard focus, standalone/embedded mode availability, reload preference and explicit override, minimized review and 390×844 mobile controls. Shared conformance adds Workbench to digest/expiry/stale-review, stream recovery, safe text, explicit keyboard approval, EN/VI and fixture journeys. An initial narrow-screen test reproduced inspector overlap with submit; content-sized grid rows fixed it. The final View control width avoids clipping “Workbench.”

Screens are deterministic fixture presentations, not live ERP evidence. Formal accessibility certification and representative user usability research remain unperformed. Existing backend admission/ontology/completion/recovery/provenance/readiness findings remain separate; no backend changes were made in this overlay task.

## Screens and reproduction

Run `make dev`, open `http://127.0.0.1:5173`, and choose **View → Workbench**. Or open `/?layout=workbench` and use the launcher. `/host.html` exercises the embedded element. `layout="workbench"` is also supported on `<e-agent-overlay>`.

Fresh opt-in captures use `ui/packages/ui-conformance/tests/overlay-visual.spec.ts`, which refuses an existing destination. Initial `screens/` captures are preserved; final reviewed captures are in ignored local evidence directory `evidence/overlay-design/20261008/reviewed-screens/`:

- [Workbench review](../../evidence/overlay-design/20261008/reviewed-screens/workbench-review.png)
- [Workbench dark](../../evidence/overlay-design/20261008/reviewed-screens/workbench-dark.png)
- [Workbench mobile](../../evidence/overlay-design/20261008/reviewed-screens/workbench-mobile.png)
- [Compact](../../evidence/overlay-design/20261008/reviewed-screens/overlay-review.png)
- [Docked](../../evidence/overlay-design/20261008/reviewed-screens/sidebar-review.png)
- [Workspace](../../evidence/overlay-design/20261008/reviewed-screens/full-page-review.png)

Python/backend checks from the previous UI handoff were not rerun for this presentation-only change. Screenshot artifacts are local and ignored by Git; the reproducible capture test and design documents are source files.
