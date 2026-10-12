# Independent enterprise overlay implementation check

Date: 2026-10-09 (Asia/Ho_Chi_Minh). Verdict: implementation delivered, corrections required before completion. This review qualifies the completion claims in the [Claude results handoff](../handoffs/2026-10-08-enterprise-overlay-implementation-results.md).

**Independent retest after corrections (2026-10-09):** the five findings and the additional route-transition regression below are now covered by passing checks. Fresh runs passed `pnpm --dir ui check` (146 unit tests, formatting, boundaries, neutrality and three builds), full conformance (135 passed, two opt-in capture skips), and the discovery/API tests (32 passed). Original findings are retained below as historical evidence. This closes these correctness findings; it does not establish visual acceptance or live qualification. The user rejected the appearance, and a separate [visual rework](../handoffs/2026-10-09-overlay-visual-rework.md) is required.

## Fresh checks

- `pnpm --dir ui check`: passed, including 123 unit tests, formatting, boundaries, provider neutrality and all three builds.
- Existing `pnpm --dir ui conformance`: 126 passed, 2 opt-in capture skips.
- `uv run pytest -q packages/kernel/tests/test_discovery.py apps/server/tests/test_api.py`: 27 passed.
- Newly added `route-regressions.spec.ts`: **3 failed**. Passing the earlier suite does not cover these failures.

All reproduction used synthetic fixtures or isolated in-memory inputs. No live provider or model qualification was performed.

## Findings to correct

### 1. Missing task links cause an unbounded request loop (P1)

`ui/apps/web/src/main.tsx` attaches whenever the requested hash run differs from controller `runId`. On a 404, `refreshOnce` in `ui-core/src/controller.ts` detaches, changing `runId` to null; the effect immediately reattaches the same failed route.

Reproduction: open `/#/task/missing-task` using `MockApi`. The new test observed **245 snapshot requests during a roughly 500ms observation window**. Handle failed navigation explicitly and stop retrying until a deliberate new navigation/retry; retain a useful unavailable state. Cover denied/deleted routes and Back/Forward without repeated side effects.

### 2. New task is undone by the current task route (P1)

After a submission settles on `#/task/<id>`, `TaskNavigation` calls `controller.newTask()`, but the route remains on the old ID. The same effect reattaches the old task. With an outstanding review, the composer stays disabled and the user cannot start the intended new task.

Reproduction: wait for the exact task URL, click New task, then check the composer. It remains disabled. Coordinate explicit detachment and route state without changing server work, losing history/draft or weakening approval semantics. Also check history selection while the URL still names another run; controller changes must not be immediately undone by an old route.

### 3. Malformed URL encoding crashes the standalone application (P2)

`ui/apps/web/src/app/routes.ts` calls `decodeURIComponent` without catching malformed encoding. `parseRoute('#/task/%')` throws `URIError: URI malformed`; the browser renders no usable composer. Use a validated fallback and add pure route and browser regression coverage.

### 4. Discovery claims an ambiguous binding is available (P2)

`packages/kernel/src/e_agent/kernel/discovery.py::task_catalog` deduplicates bindings by connection ID. Two admitted bindings for the same contract and same connection collapse to one reachable connection, so discovery returns `available`. The actual `PluginRegistry.resolve` rejects exactly that state with `CONFLICT: ambiguous binding; refusing to choose`.

Reproduced by extending the existing discovery test registry with a second, distinct binding ID for `erp.order.create.v1` on `conn-shared`. Reuse the actual resolution rules when determining availability and add regression coverage. Do not change execution authority to make a misleading catalog claim true. Review ANSWER availability dependencies as well; a random usable connection is not sufficient proof of a usable verifier/read path.

### 5. Malformed discovery data becomes a valid empty result or invented revision (P2)

`ui/packages/ui-core/src/selectors/discovery.ts` accepts the schema version but does not validate collection shape. Direct calls reproduce:

```text
projectConnections({schema_version: '1'})
  -> {kind: 'ready', observedAt: null, items: []}
projectTaskCatalog({schema_version: '1', templates: 'invalid'})
  -> {kind: 'ready', observedAt: null, items: []}
```

A connection containing only `connection_id` and `integration_id` also yields `revision: 0` and `unusable: false`. This contradicts the guide's explicit missing/unknown rules and the handoff's malformed-input claims. Reject malformed collections distinctly from a legitimate empty list; preserve unknown revisions or reject invalid required fields. Do not silently discard malformed entries into an apparently complete inventory. Add malformed-envelope/entry tests and keep valid empty and denied states distinct.

## Reproduction and continuation

The three failing browser regressions are retained in `ui/packages/ui-conformance/tests/route-regressions.spec.ts`:

```bash
pnpm --dir ui conformance -- packages/ui-conformance/tests/route-regressions.spec.ts
```

Claude should correct these findings in the existing checkout, add the corresponding selector/kernel tests, rerun targeted checks followed by the relevant full gates, and update its results handoff with actual outcomes. Preserve prior changes and existing architecture. Human usability, screen-reader evaluation and live qualification remain separate outstanding gates.

### Follow-up during the correction run

The first correction passes the original three regression tests and ten route tests, independently rerun on 2026-10-09. A further test in `route-transitions.spec.ts` still fails: start a task, wait for its task route and pending review, then set the hash to `#/task/missing-task`. The requested unavailable state never appears. The two effects in `useTaskRoute` can both act on the same render: one starts attachment to the new request while the other follows the old controller run ID and replaces the new address. Distinguish a fresh route request from a deliberate controller change before applying reverse synchronization. Keep the additional test in the full suite and verify switching between two valid tasks as well.
