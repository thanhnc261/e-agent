// @vitest-environment happy-dom
/**
 * In the thread the stream status sits in the thread head (S-2). A lost or stale connection
 * must stay visible whatever the host's layout config says (AG-STAT-3, review T4-5): hiding
 * the `connection-status` slot does not remove it, as the header never let it.
 */
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render } from "@testing-library/react";
import { RunController, type ControllerState } from "@e-agent/ui-core";
import { RunProvider } from "@e-agent/ui-react";
import { TaskSurface } from "../src/shared/TaskSurface.tsx";

afterEach(cleanup);

type Client = ConstructorParameters<typeof RunController>[0]["client"];

function threadController(connection: ControllerState["connection"]): RunController {
  const base = new RunController({ client: {} as Client, storage: null }).getState();
  const state: ControllerState = {
    ...base,
    connection,
    features: { kind: "ready", conversations: "on", mounted: true },
    threads: { kind: "ready", items: [], nextAfter: null },
  };
  return { subscribe: () => () => {}, getState: () => state } as unknown as RunController;
}

describe("thread stream status", () => {
  it("renders in the thread head even when the layout config hides its slot", () => {
    const { container } = render(
      <RunProvider controller={threadController("reconnecting")}>
        <TaskSurface
          // Messages and composer are hidden too, so only the thread head is under test.
          config={{
            layout: "sidebar",
            slots: { "connection-status": { hidden: true }, messages: { hidden: true }, composer: { hidden: true } },
          }}
          variant="stack"
          navigation={false}
        />
      </RunProvider>,
    );
    const head = container.querySelector('[data-testid="thread-head"]');
    expect(head).not.toBeNull();
    const status = head?.querySelector('[data-testid="connection-status"]');
    expect(status?.getAttribute("data-status")).toBe("reconnecting");
    expect(status?.getAttribute("role")).toBe("status");
  });
});
