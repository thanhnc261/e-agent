// @vitest-environment happy-dom
/**
 * The earlier runs a run used as hints (G-D 4.U1, brief item 8, ADR 0023 §6). Rendered from the
 * run's evidence bundle and the loaded thread only: each run is named as the thread names it,
 * selecting one opens it in the workspace as its run card does, and nothing is shown in
 * `shadow`, for an empty list, or before the bundle is read. Nothing reads as verified or as
 * evidence.
 */
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render } from "@testing-library/react";
import { RunController, emptyRunView, type ControllerState, type Locale } from "@e-agent/ui-core";
import { RunProvider } from "@e-agent/ui-react";
import { CarriedRuns } from "../src/features/conversation/CarriedRuns.tsx";
import {
  ArtifactWorkspaceProvider,
  type ArtifactWorkspaceControls,
} from "../src/features/conversation/workspace.ts";

afterEach(cleanup);

type Client = ConstructorParameters<typeof RunController>[0]["client"];
type RunRecord = NonNullable<ControllerState["view"]["run"]>;

const RUN = "run-2";

function run(runId: string, task: string, state: RunRecord["state"]) {
  return {
    run_id: runId,
    tenant_id: "t",
    requester_id: "u",
    task,
    state,
    revision: 3,
    logical_operation_id: `op-${runId}`,
    created_at: "2026-10-20T00:00:00Z",
    reason: null,
    reason_code: null,
  } as RunRecord;
}

function bundle(mode: string, carried: string[]): Record<string, unknown> {
  return {
    schema: "e-agent-evidence-v1",
    run: run(RUN, "draft a PO for it", "SUCCEEDED"),
    modes: { conversations: mode },
    conversation: {
      conversation_id: "conv-1",
      mode,
      carried_run_ids: carried,
      compared: { start: 1, refuse: 0 },
    },
  };
}

function show(evidence: Record<string, unknown> | null, locale: Locale = "en") {
  const base = new RunController({ client: {} as Client, storage: null }).getState();
  const earlier = run("run-1", "which products are short?", "SUCCEEDED");
  const current = run(RUN, "draft a PO for it", "SUCCEEDED");
  const state: ControllerState = {
    ...base,
    locale,
    runId: RUN,
    evidence,
    view: { ...emptyRunView, run: current },
    thread: {
      status: "ready",
      runs: {},
      snapshot: { conversation: { conversation_id: "conv-1" }, runs: [earlier, current] } as never,
    },
  };
  let loads = 0;
  const controller = {
    subscribe: () => () => {},
    getState: () => state,
    loadEvidence: async () => {
      loads += 1;
    },
  } as unknown as RunController;
  const opened: { runId: string; opener: HTMLElement | null | undefined }[] = [];
  const workspace: ArtifactWorkspaceControls = {
    runId: RUN,
    open: (runId, opener) => opened.push({ runId, opener }),
    close: () => {},
  };
  const result = render(
    <RunProvider controller={controller}>
      <ArtifactWorkspaceProvider value={workspace}>
        <CarriedRuns />
      </ArtifactWorkspaceProvider>
    </RunProvider>,
  );
  return { ...result, opened, loads: () => loads };
}

const byTest = (root: ParentNode, id: string) => [
  ...root.querySelectorAll<HTMLElement>(`[data-testid="${id}"]`),
];

describe("the earlier runs used as hints", () => {
  it("names each carried run as the thread does, and selecting one opens that run", () => {
    const { container, opened } = show(bundle("on", ["run-1", "run-gone"]));
    const region = byTest(container, "carried-runs")[0]!;
    expect(region.textContent).toContain("Used earlier runs as hints");
    expect(region.textContent).toContain("Hints only");
    const items = byTest(region, "carried-run");
    expect(items.map(i => i.textContent)).toEqual(["Run 1 · which products are short?", "run-gone"]);
    expect(items[0]!.tagName).toBe("BUTTON");
    fireEvent.click(items[0]!);
    expect(opened).toEqual([{ runId: "run-1", opener: items[0] }]);
    // Hints, never evidence and never verified.
    expect(region.textContent?.toLowerCase()).not.toMatch(/verif|evidence/);
  });

  it("is in Vietnamese with the thread's run label", () => {
    const { container } = show(bundle("on", ["run-1"]), "vi");
    const region = byTest(container, "carried-runs")[0]!;
    expect(region.textContent).toContain("Đã dùng các lượt trước làm gợi ý");
    expect(byTest(region, "carried-run")[0]!.textContent).toBe("Lượt 1 · which products are short?");
  });

  it("shows nothing in shadow or off, or for an empty list", () => {
    for (const evidence of [bundle("shadow", ["run-1"]), bundle("off", ["run-1"]), bundle("on", [])]) {
      const { container, loads } = show(evidence);
      expect(byTest(container, "carried-runs")).toHaveLength(0);
      expect(loads()).toBe(0);
      cleanup();
    }
  });

  it("reads the bundle once when it has not been read, and shows nothing meanwhile", () => {
    const { container, loads } = show(null);
    expect(byTest(container, "carried-runs")).toHaveLength(0);
    expect(loads()).toBe(1);
  });
});
