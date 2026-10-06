# @e-agent/ui-conformance

Playwright suite that any UI offering approval must pass (UI architecture §6). It
drives UIs only through the DOM contract below, so it also applies to custom UIs.

```bash
pnpm build            # dist/web: default app, overlay host page, reference UI
pnpm conformance      # starts `e-agent serve --static ui/dist/web` (fixture profile)
```

Targets (`src/targets.ts`): `default` (`/`), `overlay` (`/host.html`, the element on a
hostile neutral page) and `reference` (`/reference/`, the non-React T4 UI). Add a
custom UI by adding a target.

- `tests/contract.spec.ts` mocks the API (`src/mock-api.ts`) to produce digest
  mismatches, expiry, stale revisions, dropped streams, unknown events and hostile text.
- `tests/live.spec.ts` runs the real server and kernel on the fixture profile.

## DOM contract

| `data-testid` | Meaning |
|---|---|
| `composer`, `composer-input`, `composer-submit` | Task form; Enter only starts a run |
| `approval` (`data-phase`) | Approval surface; phase from the ui-core state machine |
| `material-field` (`data-path`, `data-changed`) | One row per `material_fields` entry |
| `finding` (`data-status`) | One per rule finding |
| `approval-approve`, `approval-confirm-prompt`, `approval-confirm`, `approval-back`, `approval-reject` | Two-step approval controls |
| `approval-digest-mismatch`, `approval-expired`, `approval-stale`, `approval-review-again` | Blocking states |
| `timeline-item` (`data-type`, `data-supported`) | One per run event |
| `final-message`, `blocked-image` | Agent text (links show the full URL; images never load) |
| `run-state`, `outcome-state` (`data-state`), `outcome-unresolved`, `outcome-reconcile` | Run outcome |
| `evidence-load`, `evidence-bundle` | Evidence export |
