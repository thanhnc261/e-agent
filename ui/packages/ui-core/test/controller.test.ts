import { ApiError, type EAgentClient, type StreamHandlers } from "@e-agent/client";
import { describe, expect, it, vi } from "vitest";
import { RunController } from "../src/controller.ts";
import { ev, presentation, snapshot } from "./fixtures.ts";

function fakeClient(snap: () => Promise<ReturnType<typeof snapshot>>) {
  let handlers: StreamHandlers | null = null;
  const client = {
    hasSession: true,
    startLocalSession: vi.fn(),
    createRun: vi.fn(async () => ({ run_id: "run-1", created: true })),
    getRun: vi.fn(async () => snap()),
    listEvents: vi.fn(async () => []),
    decide: vi.fn(async (_runId: string, _body: Record<string, unknown>) => ({ status: "accepted" })),
    stream: vi.fn((_id: string, _after: number, h: StreamHandlers) => {
      handlers = h;
      return { close: vi.fn() };
    }),
  };
  return { client, emit: (e: ReturnType<typeof ev>) => handlers?.onEvent(e) };
}

describe("RunController", () => {
  it("approves only after explicit confirm, once", async () => {
    const pres = await presentation();
    const { client } = fakeClient(async () => snapshot("WAITING_APPROVAL", pres));
    const c = new RunController({ client: client as unknown as EAgentClient, storage: null });
    await c.start("restock");
    expect(c.getState().approval.phase).toBe("reviewing");
    await c.approve();
    expect(client.decide).not.toHaveBeenCalled();
    c.requestConfirm();
    await Promise.all([c.approve(), c.approve()]);
    expect(client.decide).toHaveBeenCalledTimes(1);
    expect(client.decide.mock.calls[0]?.[1]).toMatchObject({ digest: pres.digest, expected_revision: 5 });
  });

  it("refuses to confirm a tampered proposal", async () => {
    const pres = await presentation({ canonical_proposal: { arguments: { quantity: "4000" } } });
    const { client } = fakeClient(async () => snapshot("WAITING_APPROVAL", pres));
    const c = new RunController({ client: client as unknown as EAgentClient, storage: null });
    await c.start("restock");
    c.requestConfirm();
    await c.approve();
    expect(c.getState().approval.digestOk).toBe(false);
    expect(client.decide).not.toHaveBeenCalled();
  });

  it("refreshes the snapshot on an unknown event without crashing", async () => {
    const { client, emit } = fakeClient(async () => snapshot("RUNNING", null));
    const c = new RunController({ client: client as unknown as EAgentClient, storage: null });
    await c.start("x");
    const before = client.getRun.mock.calls.length;
    emit(ev(1, "brand.new.event"));
    await c.refresh();
    expect(client.getRun.mock.calls.length).toBeGreaterThan(before);
    expect(c.getState().view.unsupportedEvents).toBe(1);
  });

  it("resumes a remembered run instead of creating a new one", async () => {
    const store = new Map<string, string>([["e-agent.run", "run-1"]]);
    const storage = { getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => void store.set(k, v), removeItem: (k: string) => void store.delete(k) };
    const { client } = fakeClient(async () => snapshot("SUCCEEDED", null));
    const c = new RunController({ client: client as unknown as EAgentClient, storage });
    await c.init();
    expect(client.createRun).not.toHaveBeenCalled();
    expect(c.getState().runId).toBe("run-1");
    expect(c.getState().connection).toBe("closed");
  });

  it("forgets runs that are absent or out of scope", async () => {
    const { client } = fakeClient(async () => {
      throw new ApiError(404, "NOT_FOUND", "not found");
    });
    const c = new RunController({ client: client as unknown as EAgentClient, storage: null });
    await c.attach("run-x");
    expect(c.getState().runId).toBeNull();
  });
});
