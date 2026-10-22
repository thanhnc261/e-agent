import { ApiError, type EAgentClient, type StreamHandlers } from "@e-agent/client";
import { describe, expect, it, vi } from "vitest";
import { RunController } from "../src/controller.ts";
import { ev, presentation, snapshot } from "./fixtures.ts";

function fakeClient(snap: () => Promise<ReturnType<typeof snapshot>>) {
  let handlers: StreamHandlers | null = null;
  const client = {
    hasSession: true,
    startLocalSession: vi.fn(),
    // Today's server: conversations are off, so every test here runs the per-run path.
    myFeatures: vi.fn(async () => ({ conversations: "off" as const })),
    createRun: vi.fn(async () => ({ run_id: "run-1", created: true })),
    getRun: vi.fn(async () => snap()),
    listEvents: vi.fn(async (): Promise<ReturnType<typeof ev>[]> => []),
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

  it("a quiet bundle read never sets the shared error; the explicit read still does (GD-1)", async () => {
    const { client } = fakeClient(async () => snapshot("RUNNING", null));
    const evidence = vi.fn(async () => {
      throw new ApiError(500, "INTERNAL", "boom");
    });
    const c = new RunController({
      client: { ...client, evidence } as unknown as EAgentClient,
      storage: null,
    });
    await c.start("x");
    await c.loadEvidence({ quiet: true });
    expect(evidence).toHaveBeenCalledTimes(1);
    expect(c.getState().error).toBeNull();
    expect(c.getState().evidence).toBeNull();
    await c.loadEvidence();
    expect(c.getState().error).not.toBeNull();
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

it("answers clarification through the same run", async () => {
  const { client } = fakeClient(async () => snapshot("WAITING_INPUT", null));
  const submitInput = vi.fn(async () => ({ status: "accepted" }));
  const c = new RunController({ client: { ...client, submitInput } as unknown as EAgentClient, storage: null });
  await c.attach("run-1");
  await c.start("demand:d-001");
  expect(submitInput).toHaveBeenCalledWith("run-1", "demand:d-001", 5);
  expect(client.createRun).not.toHaveBeenCalled();
});


it("refreshes again when gap-fill is newer than the snapshot", async () => {
  const pres = await presentation();
  let reads = 0;
  const { client } = fakeClient(async () => ++reads === 1
    ? snapshot("RUNNING", null, 0) : snapshot("WAITING_APPROVAL", pres, 1));
  client.listEvents.mockResolvedValueOnce([ev(1, "approval.requested")]);
  const controller = new RunController({ client: client as unknown as EAgentClient, storage: null });
  await controller.start("restock");
  expect(reads).toBe(2);
  expect(controller.getState().view.run?.state).toBe("WAITING_APPROVAL");
  expect(controller.getState().approval.presentation?.digest).toBe(pres.digest);
  controller.dispose();
});

it("preserves submission identity across a lost response, including reload", async () => {
  const data = new Map<string, string>();
  const storage = { getItem: (k: string) => data.get(k) ?? null, setItem: (k: string, v: string) => void data.set(k, v), removeItem: (k: string) => void data.delete(k) };
  const { client } = fakeClient(async () => snapshot("RUNNING", null));
  client.createRun.mockRejectedValueOnce(new TypeError("network failure"));
  const first = new RunController({ client: client as unknown as EAgentClient, storage });
  expect(await first.start("restock")).toBe(false);
  first.dispose();
  const resumed = new RunController({ client: client as unknown as EAgentClient, storage });
  await resumed.init();
  expect(await resumed.start("restock")).toBe(true);
  const calls = client.createRun.mock.calls as unknown as [string, string][];
  expect(calls[0]?.[1]).toBeTruthy();
  expect(calls[0]?.[1]).toBe(calls[1]?.[1]);
  resumed.dispose();
});

it("retries refresh after admission without creating another run", async () => {
  let unavailable = true;
  const { client } = fakeClient(async () => {
    if (unavailable) throw new TypeError("offline");
    return snapshot("RUNNING", null);
  });
  const c = new RunController({ client: client as unknown as EAgentClient, storage: null });
  expect(await c.start("restock")).toBe(false);
  unavailable = false;
  expect(await c.start("restock")).toBe(true);
  expect(client.createRun).toHaveBeenCalledTimes(1);
  c.dispose();
});

it("protects an unfinished task and retains it after explicit navigation", async () => {
  const { client } = fakeClient(async () => snapshot("WAITING_APPROVAL", await presentation()));
  const c = new RunController({ client: client as unknown as EAgentClient, storage: null });
  await c.start("restock");
  expect(await c.start("unrelated task")).toBe(false);
  expect(client.createRun).toHaveBeenCalledTimes(1);
  c.newTask();
  expect(c.getState().runId).toBeNull();
  expect(c.getState().history).toMatchObject([{ runId: "run-1", state: "WAITING_APPROVAL" }]);
  await c.attach("run-1");
  expect(c.getState().approval.phase).toBe("reviewing");
  c.dispose();
});

it("isolates remembered runs by session identity", async () => {
  const data = new Map<string, string>([["e-agent.run", "old-unscoped-run"]]);
  const storage = { getItem: (k: string) => data.get(k) ?? null, setItem: (k: string, v: string) => void data.set(k, v), removeItem: (k: string) => void data.delete(k) };
  const { client } = fakeClient(async () => snapshot("RUNNING", null));
  const scoped = { ...client, hasSession: false, storageOrigin: "same-origin", startLocalSession: vi.fn(async () => ({ tenant: "t", principal: "u" })) };
  const c = new RunController({ client: scoped as unknown as EAgentClient, storage });
  await c.init();
  expect(client.getRun).not.toHaveBeenCalled();
  await c.start("restock");
  expect(data.get("e-agent.run.same-origin.t.u")).toBe("run-1");
  c.dispose();
});


it("keeps an unsent draft in the shared controller across presentation mounts", () => {
  const { client } = fakeClient(async () => snapshot("RUNNING", null));
  const c = new RunController({ client: client as unknown as EAgentClient, storage: null });
  c.setDraft("Draft business request");
  c.setLocale("vi");
  c.back();
  expect(c.getState().draft).toBe("Draft business request");
  c.dispose();
});

describe("task history reply state", () => {
  it("history entry records a pending reply", async () => {
    const { client } = fakeClient(async () => snapshot("WAITING_INPUT", null, 1));
    client.listEvents.mockImplementation(async () => [ev(1, "input.requested", { question: "Hello! What next?", kind: "reply" })]);
    const c = new RunController({ client: client as unknown as EAgentClient, storage: null });
    await c.start("hi");
    expect(c.getState().history).toMatchObject([{ runId: "run-1", state: "WAITING_INPUT", replyPending: true }]);
    c.dispose();
  });

  it("records no pending reply for a clarification question", async () => {
    const { client } = fakeClient(async () => snapshot("WAITING_INPUT", null, 1));
    client.listEvents.mockImplementation(async () => [ev(1, "input.requested", { question: "Which supplier?" })]);
    const c = new RunController({ client: client as unknown as EAgentClient, storage: null });
    await c.start("restock");
    expect(c.getState().history[0]?.replyPending).toBeFalsy();
    c.dispose();
  });

  it("a stored entry without replyPending still loads", async () => {
    const store = new Map<string, string>([
      ["e-agent.run.history", JSON.stringify([{ runId: "run-0", task: "old", state: "WAITING_INPUT", reasonCode: null }])],
    ]);
    const storage = { getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => void store.set(k, v), removeItem: (k: string) => void store.delete(k) };
    const { client } = fakeClient(async () => snapshot("SUCCEEDED", null));
    const c = new RunController({ client: client as unknown as EAgentClient, storage });
    await c.init();
    expect(c.getState().history).toMatchObject([{ runId: "run-0", task: "old", state: "WAITING_INPUT" }]);
    expect(c.getState().history[0]?.replyPending).toBeUndefined();
    c.dispose();
  });
});

describe("task history reply state after the answer", () => {
  it("history entry clears replyPending after the answer", async () => {
    let state: "WAITING_INPUT" | "RUNNING" = "WAITING_INPUT";
    const { client, emit } = fakeClient(async () => snapshot(state, null, 1));
    client.listEvents.mockImplementation(async () => [ev(1, "input.requested", { question: "Hello! What next?", kind: "reply" })]);
    const submitInput = vi.fn(async () => ({ status: "accepted" }));
    const c = new RunController({ client: { ...client, submitInput } as unknown as EAgentClient, storage: null });
    await c.start("hi");
    expect(c.getState().history[0]?.replyPending).toBe(true);
    state = "RUNNING";
    await c.start("hi");
    expect(submitInput).toHaveBeenCalledTimes(1);
    emit(ev(2, "input.received", { input: "hi" }));
    emit(ev(3, "run.state_changed", { from: "WAITING_INPUT", to: "RUNNING" }));
    await c.refresh();
    expect(c.getState().history[0]).toMatchObject({ runId: "run-1", state: "RUNNING" });
    expect(c.getState().history[0]?.replyPending).toBe(false);
    c.dispose();
  });
});
