/**
 * Conversation state behind `features.conversations` (ADR 0023, Phase 4 Task 4e.3).
 * The thread is built only from server snapshots and run events (AG-FE-2, EA-1); the UI
 * decides the legacy fallback by the error envelope, never by the status alone.
 */
import {
  ApiError,
  EAgentClient,
  type ConversationSnapshot,
  type ConversationSummary,
  type HostContext,
  type RunEvent,
  type RunSnapshot,
  type StreamHandlers,
} from "@e-agent/client";
import { describe, expect, it, vi } from "vitest";
import { RunController, selectViewMode } from "../src/controller.ts";
import { translate, translateServerHint } from "../src/i18n.ts";
import { emptyRunView, HIDDEN_EVENT_TYPES, reduceRunView, selectThread, selectTimeline } from "../src/store.ts";
import { presentation } from "./fixtures.ts";

type Mode = "off" | "shadow" | "on";
const BUSY = "wait, decide the approval, or stop the run";
const QUESTION_CHANGED = "the question changed; read it again";

function evt(runId: string, sequence: number, type: string, payload: Record<string, unknown> = {}): RunEvent {
  return {
    event_id: `${runId}-evt-${sequence}`,
    tenant_id: "t",
    run_id: runId,
    sequence,
    type: type as RunEvent["type"],
    occurred_at: "2026-10-22T09:40:00Z",
    payload,
    schema_version: "1",
  };
}

function runSnap(
  runId: string,
  state: string,
  revision: number,
  options: { conversationId?: string | null; task?: string; latest?: number; pending?: RunSnapshot["pending_approval"] } = {},
): RunSnapshot {
  return {
    run: {
      run_id: runId,
      tenant_id: "t",
      requester_id: "u",
      task: options.task ?? runId,
      state: state as RunSnapshot["run"]["state"],
      revision,
      logical_operation_id: `op-${runId}`,
      created_at: "2026-10-22T09:40:00Z",
      conversation_id: options.conversationId ?? null,
    },
    latest_sequence: options.latest ?? 0,
    actions: [],
    pending_approval: options.pending ?? null,
  };
}

function threadRun(runId: string, task: string, state: string, revision: number) {
  return { run_id: runId, task, state: state as RunSnapshot["run"]["state"], revision, reason_code: null, created_at: "2026-10-22T09:40:00Z" };
}

function convSnap(id: string, runs: ReturnType<typeof threadRun>[]): ConversationSnapshot {
  return {
    conversation: { conversation_id: id, tenant_id: "t", owner_id: "u", revision: runs.length, created_at: "2026-10-22T09:40:00Z", updated_at: "2026-10-22T09:40:00Z" },
    runs,
  };
}

function summary(id: string, title: string, updatedAt: string): ConversationSummary {
  return { conversation_id: id, title, updated_at: updatedAt, latest_state: "SUCCEEDED", reply_pending: false };
}

const enveloped = (status: number, code: string, message: string) => new ApiError(status, code, message);
const notMounted = (status: 404 | 405) =>
  new ApiError(status, "HTTP_ERROR", status === 404 ? "Not Found" : "Method Not Allowed", { enveloped: false });

/** A scripted server behind the controller's L2 client. */
function fake(mode: Mode | (() => Promise<{ conversations: Mode }>)) {
  const server = {
    runs: {} as Record<string, RunSnapshot>,
    events: {} as Record<string, RunEvent[]>,
    conversations: {} as Record<string, ConversationSnapshot>,
    list: [] as ConversationSummary[],
  };
  const handlers: Record<string, StreamHandlers> = {};
  const client = {
    hasSession: true,
    storageOrigin: "same-origin",
    startLocalSession: vi.fn(),
    myFeatures: vi.fn(typeof mode === "function" ? mode : async () => ({ conversations: mode })),
    createConversation: vi.fn(async () => {
      const id = `conv-${Object.keys(server.conversations).length + 1}`;
      server.conversations[id] = convSnap(id, []);
      return { conversation_id: id };
    }),
    listConversations: vi.fn(async () => ({ items: server.list, next_after: null })),
    getConversation: vi.fn(async (id: string) => {
      const snap = server.conversations[id];
      if (!snap) throw enveloped(404, "NOT_FOUND", "not found");
      return snap;
    }),
    postMessage: vi.fn(
      async (_id: string, _body: Record<string, unknown>, _key: string): Promise<{ route: "start" | "answer"; run_id: string }> => ({
        route: "start",
        run_id: "run-1",
      }),
    ),
    createRun: vi.fn(async (_task: string, _key: string, _host?: unknown) => ({ run_id: "run-1", created: true })),
    submitInput: vi.fn(async (_runId: string, _input: string, _rev: number) => ({ status: "accepted" })),
    getRun: vi.fn(async (id: string) => {
      const snap = server.runs[id];
      if (!snap) throw enveloped(404, "NOT_FOUND", "not found");
      return snap;
    }),
    listEvents: vi.fn(async (id: string, after = 0) => (server.events[id] ?? []).filter(e => e.sequence > after)),
    stream: vi.fn((id: string, _after: number, h: StreamHandlers) => {
      handlers[id] = h;
      return { close: vi.fn() };
    }),
  };
  const controller = (options: { hostContext?: () => HostContext } = {}) =>
    new RunController({ client: client as unknown as EAgentClient, storage: null, ...options });
  return { server, client, controller, emit: (e: RunEvent) => handlers[e.run_id]?.onEvent(e) };
}

describe("conversation state behind features.conversations", () => {
  it("reads the mode from /v1/me/features", async () => {
    for (const mode of ["off", "shadow", "on"] as const) {
      const { client, controller } = fake(mode);
      const c = controller();
      await c.init();
      expect(client.myFeatures).toHaveBeenCalledTimes(1);
      expect(c.getState().features).toEqual({ kind: "ready", conversations: mode, mounted: true });
      c.dispose();
    }
    // An older server without the route answers FastAPI's own 404: that is `off`.
    const old = fake(async () => {
      throw notMounted(404);
    });
    const c = old.controller();
    await c.init();
    expect(c.getState().features).toEqual({ kind: "ready", conversations: "off", mounted: false });
    c.dispose();
    // Any other failure is not a mode: the UI says it could not read it (EA-8).
    for (const failure of [enveloped(503, "DEPENDENCY_UNAVAILABLE", "unavailable"), new TypeError("offline")]) {
      const broken = fake(async () => {
        throw failure;
      });
      const b = broken.controller();
      await b.init();
      expect(b.getState().features).toEqual({ kind: "unavailable" });
      b.dispose();
    }
    // An unknown mode fails visibly instead of being guessed (AG-FE-13).
    const odd = fake(async () => ({ conversations: "maybe" as Mode }));
    const o = odd.controller();
    await o.init();
    expect(o.getState().features).toEqual({ kind: "unavailable" });
    o.dispose();
  });

  it("off and shadow keep the per-run view", async () => {
    for (const mode of ["off", "shadow"] as const) {
      const { client, controller } = fake(mode);
      const c = controller();
      await c.init();
      expect(selectViewMode(c.getState())).toEqual({ kind: "per-run", reason: mode });
      expect(client.listConversations).not.toHaveBeenCalled();
      c.dispose();
    }
    const on = fake("on");
    const c = on.controller();
    await c.init();
    expect(selectViewMode(c.getState())).toEqual({ kind: "thread" });
    c.dispose();
  });

  it("shadow posts through the conversation route", async () => {
    const { server, client, controller } = fake("shadow");
    server.runs["run-1"] = runSnap("run-1", "RUNNING", 1, { conversationId: "conv-1", task: "restock" });
    const c = controller();
    await c.init();
    expect(await c.start("restock")).toBe(true);
    expect(client.createConversation).toHaveBeenCalledTimes(1);
    expect(client.postMessage).toHaveBeenCalledTimes(1);
    expect(client.postMessage.mock.calls[0]?.[0]).toBe("conv-1");
    expect(client.postMessage.mock.calls[0]?.[1]).toEqual({ text: "restock", reply_to: null, host_context: null });
    expect(client.postMessage.mock.calls[0]?.[2]).toMatch(/^ui-/);
    expect(client.createRun).not.toHaveBeenCalled();
    expect(c.getState()).toMatchObject({ runId: "run-1", conversationId: "conv-1" });
    // The per-run view stays: no thread is read in shadow.
    expect(client.getConversation).not.toHaveBeenCalled();
    expect(selectViewMode(c.getState())).toEqual({ kind: "per-run", reason: "shadow" });
    // One conversation per "New task".
    server.runs["run-1"] = runSnap("run-1", "SUCCEEDED", 2, { conversationId: "conv-1", task: "restock" });
    c.newTask();
    expect(c.getState().conversationId).toBeNull();
    client.postMessage.mockResolvedValueOnce({ route: "start", run_id: "run-2" });
    server.runs["run-2"] = runSnap("run-2", "RUNNING", 1, { conversationId: "conv-2", task: "again" });
    expect(await c.start("again")).toBe(true);
    expect(client.createConversation).toHaveBeenCalledTimes(2);
    expect(client.postMessage.mock.calls[1]?.[0]).toBe("conv-2");
    c.dispose();
  });

  it("on lists server threads, newest first", async () => {
    const { server, client, controller } = fake("on");
    // The server orders the list; the UI keeps that order and adds nothing of its own.
    server.list = [
      summary("conv-b", "Supplier price question", "2026-10-22T09:50:00Z"),
      summary("conv-a", "Restock short products", "2026-10-22T09:40:00Z"),
    ];
    const c = controller();
    await c.init();
    const threads = c.getState().threads;
    expect(threads.kind).toBe("ready");
    if (threads.kind !== "ready") return;
    expect(threads.items.map(t => t.conversation_id)).toEqual(["conv-b", "conv-a"]);
    expect(threads.items[0]).toEqual(server.list[0]);
    // A new message re-reads the list instead of inserting a local row.
    server.runs["run-1"] = runSnap("run-1", "RUNNING", 1, { conversationId: "conv-1", task: "hi" });
    server.conversations["conv-1"] = convSnap("conv-1", [threadRun("run-1", "hi", "RUNNING", 1)]);
    client.createConversation.mockResolvedValueOnce({ conversation_id: "conv-1" });
    expect(await c.start("hi")).toBe(true);
    expect(client.listConversations).toHaveBeenCalledTimes(2);
    const after = c.getState().threads;
    expect(after.kind === "ready" && after.items.map(t => t.conversation_id)).toEqual(["conv-b", "conv-a"]);
    // Thread runs are not written to the session-local history: that group is legacy (F-10).
    expect(c.getState().history).toEqual([]);
    c.dispose();
  });

  it("a refused message keeps the draft and shows the server's hint", async () => {
    const { server, client, controller } = fake("on");
    const pres = await presentation({ run_id: "run-1" });
    server.runs["run-1"] = runSnap("run-1", "WAITING_APPROVAL", 5, { conversationId: "conv-1", task: "draft a PO", pending: pres });
    server.conversations["conv-1"] = convSnap("conv-1", [threadRun("run-1", "draft a PO", "WAITING_APPROVAL", 5)]);
    const c = controller();
    await c.init();
    await c.openConversation("conv-1");
    const approvalBefore = c.getState().approval;
    expect(approvalBefore.phase).toBe("reviewing");
    c.setDraft("also add 10 of hinge H-3");
    client.postMessage.mockRejectedValueOnce(enveloped(409, "CONFLICT", BUSY));
    expect(await c.start("also add 10 of hinge H-3")).toBe(false);
    const s = c.getState();
    expect(s.draft).toBe("also add 10 of hinge H-3");
    expect(s.refusal).toEqual({ code: "CONFLICT", message: BUSY, correlationId: null });
    expect(s.error).toBeNull();
    expect(translateServerHint("en", s.refusal!.message)).toBe(translate("en", "conversation.refusedBusy"));
    expect(translateServerHint("vi", s.refusal!.message)).toBe(translate("vi", "conversation.refusedBusy"));
    expect(translate("vi", "conversation.refusedBusy")).not.toBe(translate("en", "conversation.refusedBusy"));
    // The approval card is unchanged (G-B 4): same presentation, same phase.
    expect(s.approval).toBe(approvalBefore);
    expect(s.approval.phase).toBe("reviewing");
    expect(s.approval.presentation?.digest).toBe(pres.digest);
    // An answer to a run that has ended is refused the same way, with its own hint (G-B 3).
    client.postMessage.mockRejectedValueOnce(enveloped(409, "CONFLICT", QUESTION_CHANGED));
    expect(await c.start("40")).toBe(false);
    expect(c.getState().refusal).toEqual({ code: "CONFLICT", message: QUESTION_CHANGED, correlationId: null });
    expect(translateServerHint("en", QUESTION_CHANGED)).toBe(translate("en", "conversation.refusedQuestion"));
    expect(translateServerHint("vi", QUESTION_CHANGED)).toBe(translate("vi", "conversation.refusedQuestion"));
    // A hint the UI does not know is shown as the server wrote it.
    expect(translateServerHint("vi", "request conflicts with the current run")).toBe("request conflicts with the current run");
    // Nothing was re-posted anywhere.
    expect(client.postMessage).toHaveBeenCalledTimes(2);
    expect(client.createRun).not.toHaveBeenCalled();
    expect(client.submitInput).not.toHaveBeenCalled();
    c.dispose();
  });

  it("falls back to the per-run view when a conversation route fails", async () => {
    const { server, client, controller } = fake("on");
    server.runs["run-1"] = runSnap("run-1", "RUNNING", 1, { conversationId: "conv-1", task: "restock" });
    client.listConversations.mockRejectedValueOnce(new TypeError("offline"));
    const c = controller();
    await c.init();
    expect(c.getState().threads.kind).toBe("error");
    expect(selectViewMode(c.getState())).toEqual({ kind: "per-run", reason: "thread-unavailable" });
    // A failed snapshot read also falls back, and the active run is still shown per run.
    client.getConversation.mockRejectedValueOnce(enveloped(503, "DEPENDENCY_UNAVAILABLE", "unavailable"));
    await c.attach("run-1");
    expect(c.getState().conversationId).toBe("conv-1");
    expect(c.getState().thread.status).toBe("error");
    expect(c.getState().view.run?.run_id).toBe("run-1");
    expect(selectViewMode(c.getState())).toEqual({ kind: "per-run", reason: "thread-unavailable" });
    // When both reads succeed again, the thread view returns.
    server.conversations["conv-1"] = convSnap("conv-1", [threadRun("run-1", "restock", "RUNNING", 1)]);
    await c.loadConversations();
    await c.openConversation("conv-1");
    expect(selectViewMode(c.getState())).toEqual({ kind: "thread" });
    // A features read that fails shows the per-run view too, and names why.
    const broken = fake(async () => {
      throw new TypeError("offline");
    });
    const b = broken.controller();
    await b.init();
    expect(selectViewMode(b.getState())).toEqual({ kind: "per-run", reason: "features-unavailable" });
    b.dispose();
    c.dispose();
  });

  it("goes to /v1/runs or /inputs only when /v1/me/features reports off, or a conversation route answers 404 or 405 without the error envelope (not mounted), with a fresh Idempotency-Key", async () => {
    // off: today's routes, never a conversation route.
    const off = fake("off");
    off.server.runs["run-1"] = runSnap("run-1", "WAITING_INPUT", 4, { task: "restock" });
    const o = off.controller();
    await o.init();
    expect(await o.start("restock")).toBe(true);
    expect(await o.start("demand:d-001")).toBe(true);
    expect(off.client.createRun).toHaveBeenCalledTimes(1);
    expect(off.client.submitInput).toHaveBeenCalledWith("run-1", "demand:d-001", 4);
    expect(off.client.createConversation).not.toHaveBeenCalled();
    expect(off.client.postMessage).not.toHaveBeenCalled();
    o.dispose();

    // shadow, a message route that is not mounted (405 from an older server's static mount).
    const old = fake("shadow");
    old.server.runs["run-1"] = runSnap("run-1", "RUNNING", 1, { task: "restock" });
    old.client.postMessage.mockRejectedValueOnce(notMounted(405));
    const s = old.controller();
    await s.init();
    expect(await s.start("restock")).toBe(true);
    const messageKey = old.client.postMessage.mock.calls[0]?.[2];
    const runKey = old.client.createRun.mock.calls[0]?.[1];
    expect(runKey).toMatch(/^ui-/);
    expect(runKey).not.toBe(messageKey);
    expect(old.client.createRun).toHaveBeenCalledTimes(1);
    expect(s.getState().error).toBeNull();
    // Once the routes are known to be absent, the next answer goes to /inputs directly.
    old.server.runs["run-1"] = runSnap("run-1", "WAITING_INPUT", 3, { task: "restock" });
    await s.refresh();
    expect(await s.start("40")).toBe(true);
    expect(old.client.submitInput).toHaveBeenCalledWith("run-1", "40", 3);
    expect(old.client.postMessage).toHaveBeenCalledTimes(1);
    s.dispose();

    // on, the create route answers a plain 404 (no envelope).
    const older = fake("on");
    older.server.runs["run-1"] = runSnap("run-1", "RUNNING", 1, { task: "restock" });
    older.client.createConversation.mockRejectedValueOnce(notMounted(404));
    const n = older.controller();
    await n.init();
    expect(await n.start("restock")).toBe(true);
    expect(older.client.postMessage).not.toHaveBeenCalled();
    expect(older.client.createRun).toHaveBeenCalledTimes(1);
    n.dispose();

    // An enveloped NOT_FOUND, an unreadable mode, and a non-404/405 plain error never reach /v1/runs.
    for (const [mode, failure] of [
      ["shadow", enveloped(404, "NOT_FOUND", "conversations are off")],
      ["on", new ApiError(502, "HTTP_ERROR", "Bad Gateway", { enveloped: false })],
    ] as const) {
      const f = fake(mode);
      f.client.postMessage.mockRejectedValueOnce(failure);
      const c = f.controller();
      await c.init();
      expect(await c.start("restock")).toBe(false);
      expect(f.client.createRun).not.toHaveBeenCalled();
      expect(f.client.submitInput).not.toHaveBeenCalled();
      c.dispose();
    }
    const unreadable = fake(async () => {
      throw new TypeError("offline");
    });
    const u = unreadable.controller();
    await u.init();
    expect(await u.start("restock")).toBe(false);
    expect(unreadable.client.myFeatures).toHaveBeenCalledTimes(2);
    expect(unreadable.client.createRun).not.toHaveBeenCalled();
    expect(unreadable.client.postMessage).not.toHaveBeenCalled();
    expect(u.getState().error).toBe(translate("en", "conversation.featuresFailed"));
    u.dispose();

    // Through the real L2 client: the static mount's 405 has a plain-text body and no envelope.
    const calls: { method: string; path: string; key: string | null }[] = [];
    const fetchImpl = vi.fn(async (url: string, init: RequestInit) => {
      const path = new URL(url, "http://ui.test").pathname;
      const headers = init.headers as Record<string, string>;
      calls.push({ method: init.method ?? "GET", path, key: headers["Idempotency-Key"] ?? null });
      const json = (status: number, body: unknown) =>
        new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
      if (path === "/v1/local/session") return json(200, { csrf_token: "csrf", tenant: "t", principal: "u" });
      if (path === "/v1/me/features") return json(200, { conversations: "shadow" });
      if (path === "/v1/conversations") return new Response("Method Not Allowed", { status: 405, headers: { "Content-Type": "text/plain" } });
      if (path === "/v1/runs") return json(202, { run_id: "run-1", created: true });
      if (path === "/v1/runs/run-1") return json(200, runSnap("run-1", "RUNNING", 1, { task: "restock" }));
      if (path === "/v1/runs/run-1/events") return json(200, []);
      return json(404, { detail: "Not Found" });
    });
    const real = new EAgentClient({ fetch: fetchImpl as unknown as typeof fetch, EventSource: class { readyState = 0; onopen = null; onerror = null; addEventListener() {} close() {} } as never });
    const r = new RunController({ client: real, storage: null });
    await r.init();
    expect(await r.start("restock")).toBe(true);
    expect(calls.filter(x => x.method === "POST").map(x => x.path)).toEqual(["/v1/local/session", "/v1/conversations", "/v1/runs"]);
    expect(calls.find(x => x.path === "/v1/runs")?.key).toMatch(/^ui-/);
    r.dispose();
  });

  it("in on, a missing-conversation NOT_FOUND with the error envelope is shown as an error, keeps the draft, re-reads /v1/me/features and never calls /v1/runs", async () => {
    const { server, client, controller } = fake("on");
    server.runs["run-1"] = runSnap("run-1", "SUCCEEDED", 2, { conversationId: "conv-1", task: "restock" });
    server.conversations["conv-1"] = convSnap("conv-1", [threadRun("run-1", "restock", "SUCCEEDED", 2)]);
    const c = controller();
    await c.init();
    await c.openConversation("conv-1");
    expect(client.myFeatures).toHaveBeenCalledTimes(1);
    c.setDraft("draft a PO for it");
    client.postMessage.mockRejectedValueOnce(enveloped(404, "NOT_FOUND", "not found"));
    expect(await c.start("draft a PO for it")).toBe(false);
    const s = c.getState();
    expect(s.draft).toBe("draft a PO for it");
    expect(s.error).toBe(translate("en", "conversation.notSent"));
    expect(s.refusal).toBeNull();
    expect(client.myFeatures).toHaveBeenCalledTimes(2);
    expect(client.postMessage).toHaveBeenCalledTimes(1);
    expect(client.createRun).not.toHaveBeenCalled();
    expect(client.submitInput).not.toHaveBeenCalled();
    c.dispose();
  });

  it("a shadow conversation-route error is shown with the draft kept; the UI does not re-post", async () => {
    const { server, client, controller } = fake("shadow");
    server.runs["run-1"] = runSnap("run-1", "RUNNING", 1, { conversationId: "conv-1", task: "restock" });
    const c = controller();
    await c.init();
    c.setDraft("restock");
    client.postMessage.mockRejectedValueOnce(enveloped(500, "INTERNAL", "internal error"));
    expect(await c.start("restock")).toBe(false);
    expect(c.getState().draft).toBe("restock");
    expect(c.getState().error).toBe(translate("en", "conversation.notSent"));
    expect(client.postMessage).toHaveBeenCalledTimes(1);
    expect(client.createRun).not.toHaveBeenCalled();
    expect(client.submitInput).not.toHaveBeenCalled();
    // A lost response is not re-posted either; only the user's own resend goes out, under the same key.
    client.postMessage.mockRejectedValueOnce(new TypeError("network"));
    expect(await c.start("restock")).toBe(false);
    expect(c.getState().error).toBe(translate("en", "error.network"));
    expect(client.postMessage).toHaveBeenCalledTimes(2);
    expect(client.createRun).not.toHaveBeenCalled();
    expect(await c.start("restock")).toBe(true);
    expect(client.postMessage.mock.calls[2]?.[2]).toBe(client.postMessage.mock.calls[1]?.[2]);
    expect(client.postMessage.mock.calls[1]?.[2]).toBe(client.postMessage.mock.calls[0]?.[2]);
    expect(client.createRun).not.toHaveBeenCalled();
    c.dispose();
  });

  it("a start sends the host context in the message body", async () => {
    const { server, client, controller } = fake("shadow");
    server.runs["run-1"] = runSnap("run-1", "RUNNING", 1, { conversationId: "conv-1", task: "restock" });
    const host: HostContext = { host_kind: "embedded", locale: "vi", resource_hints: [] };
    const c = controller({ hostContext: () => host });
    await c.init();
    expect(await c.start("restock")).toBe(true);
    expect(client.postMessage.mock.calls[0]?.[1]).toEqual({ text: "restock", reply_to: null, host_context: host });
    c.dispose();
  });

  it("an answer carries reply_to with the run revision shown with its question", async () => {
    const { server, client, controller, emit } = fake("on");
    server.runs["run-2"] = runSnap("run-2", "RUNNING", 3, { conversationId: "conv-1", task: "draft a PO for it" });
    server.conversations["conv-1"] = convSnap("conv-1", [threadRun("run-2", "draft a PO for it", "RUNNING", 3)]);
    const c = controller();
    await c.init();
    await c.openConversation("conv-1");
    // The question arrives; the snapshot the UI then reads carries the revision shown with it.
    server.events["run-2"] = [evt("run-2", 1, "input.requested", { question: "How many units?", kind: "clarification" })];
    server.runs["run-2"] = runSnap("run-2", "WAITING_INPUT", 4, { conversationId: "conv-1", task: "draft a PO for it", latest: 1 });
    server.conversations["conv-1"] = convSnap("conv-1", [threadRun("run-2", "draft a PO for it", "WAITING_INPUT", 4)]);
    emit(server.events["run-2"][0]!);
    await c.refresh();
    const entry = selectThread(c.getState().thread, c.getState()).at(-1);
    expect(entry).toMatchObject({ runId: "run-2", state: "WAITING_INPUT", revision: 4 });
    expect(entry?.messages.at(-1)).toMatchObject({ text: "How many units?", pending: true });
    client.postMessage.mockResolvedValueOnce({ route: "answer", run_id: "run-2" });
    expect(await c.start("40")).toBe(true);
    expect(client.postMessage.mock.calls[0]?.[1]).toEqual({
      text: "40",
      reply_to: { run_id: "run-2", run_revision: 4 },
      host_context: null,
    });
    expect(client.submitInput).not.toHaveBeenCalled();
    c.dispose();
  });

  it("the thread comes from server snapshots only", async () => {
    const { server, client, controller } = fake("on");
    server.events["run-1"] = [
      evt("run-1", 1, "input.requested", { question: "Hello. What do you need?", kind: "reply" }),
      evt("run-1", 2, "input.received", { input: "which products are short?" }),
      evt("run-1", 3, "message.final", { text: "One product is short." }),
    ];
    server.runs["run-1"] = runSnap("run-1", "SUCCEEDED", 6, { conversationId: "conv-1", task: "hi", latest: 3 });
    server.runs["run-2"] = runSnap("run-2", "RUNNING", 1, { conversationId: "conv-1", task: "draft a PO for it" });
    server.conversations["conv-1"] = convSnap("conv-1", [
      threadRun("run-1", "hi", "SUCCEEDED", 6),
      threadRun("run-2", "draft a PO for it", "RUNNING", 1),
    ]);
    const c = controller();
    await c.init();
    await c.openConversation("conv-1");
    const thread = selectThread(c.getState().thread, c.getState());
    expect(thread.map(r => [r.runId, r.task, r.state, r.latest, r.loaded])).toEqual([
      ["run-1", "hi", "SUCCEEDED", false, true],
      ["run-2", "draft a PO for it", "RUNNING", true, true],
    ]);
    expect(thread[0]?.messages.map(m => [m.role, m.text])).toEqual([
      ["agent", "Hello. What do you need?"],
      ["user", "which products are short?"],
      ["agent", "One product is short."],
    ]);
    // The active run streams; the ended one is read once and is not streamed.
    expect(client.stream.mock.calls.map(call => call[0])).toEqual(["run-2"]);
    // A sent message is never echoed locally: until the server's snapshot has it, it is not in the thread.
    client.postMessage.mockResolvedValueOnce({ route: "start", run_id: "run-3" });
    server.runs["run-3"] = runSnap("run-3", "RUNNING", 1, { conversationId: "conv-1", task: "and the hinges?" });
    await c.start("and the hinges?");
    const texts = (t: ReturnType<typeof selectThread>) => t.flatMap(r => [r.task, ...r.messages.map(m => m.text)]);
    expect(texts(selectThread(c.getState().thread, c.getState()))).not.toContain("and the hinges?");
    // Once the server lists the run, the thread shows it with the server's text.
    server.conversations["conv-1"] = convSnap("conv-1", [
      threadRun("run-1", "hi", "SUCCEEDED", 6),
      threadRun("run-2", "draft a PO for it", "SUCCEEDED", 2),
      threadRun("run-3", "and the hinges?", "RUNNING", 1),
    ]);
    await c.openConversation("conv-1");
    const after = selectThread(c.getState().thread, c.getState());
    expect(after.map(r => r.runId)).toEqual(["run-1", "run-2", "run-3"]);
    expect(after.at(-1)).toMatchObject({ task: "and the hinges?", latest: true });
    // A run whose events could not be read is marked as not loaded, never shown as empty (EA-8).
    const missing = selectThread({ snapshot: c.getState().thread.snapshot, runs: {} }, { runId: null, view: c.getState().view });
    expect(missing.every(r => !r.loaded && r.messages.length === 0)).toBe(true);
    c.dispose();
  });

  it("the reply label shows on the first reply of a conversation", async () => {
    const { server, controller } = fake("on");
    server.events["run-1"] = [
      evt("run-1", 1, "input.requested", { question: "Hello.", kind: "reply" }),
      evt("run-1", 2, "input.received", { input: "thanks" }),
    ];
    server.events["run-2"] = [evt("run-2", 1, "input.requested", { question: "Anything else?", kind: "reply" })];
    server.runs["run-1"] = runSnap("run-1", "SUCCEEDED", 3, { conversationId: "conv-1", task: "hi", latest: 2 });
    server.runs["run-2"] = runSnap("run-2", "WAITING_INPUT", 2, { conversationId: "conv-1", task: "hi again", latest: 1 });
    server.conversations["conv-1"] = convSnap("conv-1", [
      threadRun("run-1", "hi", "SUCCEEDED", 3),
      threadRun("run-2", "hi again", "WAITING_INPUT", 2),
    ]);
    const c = controller();
    await c.init();
    await c.openConversation("conv-1");
    const replies = selectThread(c.getState().thread, c.getState()).flatMap(r => r.messages.filter(m => m.kind === "reply"));
    expect(replies.map(m => [m.text, m.firstReply])).toEqual([
      ["Hello.", true],
      ["Anything else?", false],
    ]);
    c.dispose();
  });
});

describe("conversation state, fix round 1 (review 4e.3)", () => {
  it("in on, an answer to an unlinked run that waits for input goes to /inputs and makes no conversation", async () => {
    const { server, client, controller } = fake("on");
    server.runs["legacy-1"] = runSnap("legacy-1", "WAITING_INPUT", 4, { conversationId: null, task: "restock hinge H-3" });
    const c = controller();
    await c.init();
    await c.attach("legacy-1");
    expect(c.getState().conversationId).toBeNull();
    expect(await c.start("40")).toBe(true);
    expect(client.submitInput).toHaveBeenCalledTimes(1);
    expect(client.submitInput).toHaveBeenCalledWith("legacy-1", "40", 4);
    expect(client.createConversation).not.toHaveBeenCalled();
    expect(client.postMessage).not.toHaveBeenCalled();
    expect(client.createRun).not.toHaveBeenCalled();
    expect(c.getState().conversationId).toBeNull();
    c.dispose();
  });

  it("hidden conversation events show no row, need no snapshot and still advance lastSequence", () => {
    // The full hidden set, pinned: hiding another event type needs a deliberate change here
    // (the conversation records, then the Phase 3 records ruled in Task 4e.4).
    expect([...HIDDEN_EVENT_TYPES].sort()).toEqual([
      "context.assembled",
      "context.compared",
      "context.shadow_failed",
      "conversation.compared",
      "conversation.context_carried",
      "conversation.shadow_failed",
      "grounding.compared",
      "grounding.shadow_failed",
      "repeat.compared",
      "repeat.shadow_failed",
    ]);
    const baseline = reduceRunView(emptyRunView, {
      type: "events",
      events: [
        evt("run-1", 1, "run.created", { task: "restock" }),
        evt("run-1", 2, "run.state_changed", { from: "CREATED", to: "RUNNING" }),
        evt("run-1", 3, "read.recorded", { contract_id: "procurement.demand.read.v1" }),
      ],
    });
    const shadow = reduceRunView(emptyRunView, {
      type: "events",
      events: [
        evt("run-1", 1, "run.created", { task: "restock" }),
        evt("run-1", 2, "conversation.compared", { conversation_id: "conv-1", route: "start", carried_run_ids: [], items: 0 }),
        evt("run-1", 3, "run.state_changed", { from: "CREATED", to: "RUNNING" }),
        evt("run-1", 4, "conversation.shadow_failed", { stage: "carry", code: "CONFLICT" }),
        evt("run-1", 5, "conversation.context_carried", { conversation_id: "conv-1", carried_run_ids: ["run-0"] }),
        evt("run-1", 6, "read.recorded", { contract_id: "procurement.demand.read.v1" }),
      ],
    });
    const rows = (view: typeof shadow) => selectTimeline(view).map(r => [r.type, r.labelKey, r.detail, r.supported]);
    expect(rows(shadow)).toEqual(rows(baseline));
    expect(shadow.unsupportedEvents).toBe(0);
    expect(shadow.needsSnapshot).toBe(false);
    expect(shadow.lastSequence).toBe(6);
    expect(shadow.events).toHaveLength(6);
    // The next event after a hidden one is in order: no gap is invented.
    const next = reduceRunView(shadow, { type: "events", events: [evt("run-1", 7, "validation.completed", { status: "PASS" })] });
    expect(next.lastSequence).toBe(7);
    expect(next.needsSnapshot).toBe(false);
  });

  it("a hidden conversation event on the stream causes no extra snapshot read", async () => {
    const { server, client, controller, emit } = fake("shadow");
    server.runs["run-1"] = runSnap("run-1", "RUNNING", 1, { conversationId: "conv-1", task: "restock" });
    const c = controller();
    await c.init();
    expect(await c.start("restock")).toBe(true);
    const reads = client.getRun.mock.calls.length;
    emit(evt("run-1", 1, "conversation.compared", { conversation_id: "conv-1", route: "start" }));
    expect(client.getRun.mock.calls.length).toBe(reads);
    expect(c.getState().view.lastSequence).toBe(1);
    expect(selectTimeline(c.getState().view)).toEqual([]);
    c.dispose();
  });

  it("a pending conversation message refuses a different text and survives New task", async () => {
    const { server, client, controller } = fake("shadow");
    server.runs["run-1"] = runSnap("run-1", "RUNNING", 1, { conversationId: "conv-1", task: "restock A" });
    const c = controller();
    await c.init();
    client.postMessage.mockRejectedValueOnce(new TypeError("network"));
    expect(await c.start("restock A")).toBe(false);
    // The first post may have been committed: another text is refused locally, as on the legacy path.
    c.setDraft("restock A, 10 units");
    expect(await c.start("restock A, 10 units")).toBe(false);
    expect(c.getState().error).toBe(translate("en", "error.pending"));
    expect(c.getState().draft).toBe("restock A, 10 units");
    expect(client.postMessage).toHaveBeenCalledTimes(1);
    // New task does not drop it: the same text still recovers it, to its conversation, under its key.
    c.newTask();
    expect(await c.start("restock B")).toBe(false);
    expect(c.getState().error).toBe(translate("en", "error.pending"));
    expect(await c.start("restock A")).toBe(true);
    expect(client.postMessage).toHaveBeenCalledTimes(2);
    expect(client.postMessage.mock.calls[1]?.[0]).toBe(client.postMessage.mock.calls[0]?.[0]);
    expect(client.postMessage.mock.calls[1]?.[1]).toEqual(client.postMessage.mock.calls[0]?.[1]);
    expect(client.postMessage.mock.calls[1]?.[2]).toBe(client.postMessage.mock.calls[0]?.[2]);
    expect(client.createConversation).toHaveBeenCalledTimes(1);
    expect(c.getState().conversationId).toBe("conv-1");
    // Once recovered, a new text is a new message.
    client.postMessage.mockResolvedValueOnce({ route: "start", run_id: "run-1" });
    server.runs["run-1"] = runSnap("run-1", "SUCCEEDED", 2, { conversationId: "conv-1", task: "restock A" });
    await c.refresh();
    expect(await c.start("restock B")).toBe(true);
    expect(client.postMessage.mock.calls[2]?.[2]).not.toBe(client.postMessage.mock.calls[0]?.[2]);
    c.dispose();
  });
});
