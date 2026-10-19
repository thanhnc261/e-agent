// @vitest-environment happy-dom
/**
 * A run the server ended `grounded` (ADR 0033 §3) is never labelled verified (PR-19):
 * the outcome badge, the task overview and the timeline's SUCCEEDED transition read the
 * run's reason code. A verified run keeps its label.
 */
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render } from "@testing-library/react";
import { RunController, emptyRunView, translate, type ControllerState } from "@e-agent/ui-core";
import { RunProvider } from "@e-agent/ui-react";
import { OutcomePanel } from "../src/features/outcome/OutcomePanel.tsx";
import { TaskOverview } from "../src/features/task-overview/TaskOverview.tsx";
import { Timeline } from "../src/features/timeline/Timeline.tsx";

afterEach(cleanup);

type RunRecord = NonNullable<ControllerState["view"]["run"]>;
type RunEvent = ControllerState["view"]["events"][number];
type Client = ConstructorParameters<typeof RunController>[0]["client"];

const VERIFIED = translate("en", "status.SUCCEEDED");
const GROUNDED = translate("en", "status.SUCCEEDED.grounded");

function controller(reasonCode: RunRecord["reason_code"]): RunController {
  const base = new RunController({ client: {} as Client, storage: null }).getState();
  const run: RunRecord = {
    run_id: "run-1",
    tenant_id: "t",
    requester_id: "u",
    task: "List the open purchase orders",
    state: "SUCCEEDED",
    revision: 3,
    logical_operation_id: "op-1",
    created_at: "2026-10-20T00:00:00Z",
    reason: null,
    reason_code: reasonCode,
  };
  const changed: RunEvent = {
    event_id: "e1",
    tenant_id: "t",
    run_id: "run-1",
    sequence: 1,
    type: "run.state_changed",
    occurred_at: "2026-10-20T00:00:00Z",
    payload: { from: "RUNNING", to: "SUCCEEDED", reason_code: reasonCode },
    schema_version: "1",
  } as RunEvent;
  const state: ControllerState = {
    ...base,
    runId: "run-1",
    view: { ...emptyRunView, run, events: [changed] },
  };
  return { subscribe: () => () => {}, getState: () => state } as unknown as RunController;
}

function rendered(reasonCode: RunRecord["reason_code"]): string {
  const { container } = render(
    <RunProvider controller={controller(reasonCode)}>
      <OutcomePanel />
      <TaskOverview />
      <Timeline />
    </RunProvider>,
  );
  return container.textContent ?? "";
}

describe("grounded run status", () => {
  it("never shows the verified label for a grounded run", () => {
    const text = rendered("grounded");
    expect(text).not.toContain(VERIFIED);
    expect(text.split(GROUNDED).length - 1).toBe(3); // badge, overview, transition
  });

  it("keeps the verified label for a verified run", () => {
    const text = rendered("verified");
    expect(text).not.toContain(GROUNDED);
    expect(text.split(VERIFIED).length - 1).toBe(3);
  });
});
