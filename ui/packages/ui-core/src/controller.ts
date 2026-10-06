/**
 * Framework-free run controller: the one stateful object every UI binds to
 * (React via useSyncExternalStore, the vanilla reference UI via subscribe).
 * It talks to the server only through the L2 client.
 */
import { ApiError, newIdempotencyKey, type EAgentClient, type HostContext, type RunEvent } from "@e-agent/client";
import { canRequestApprove, initialApproval, isExpired, reduceApproval, type ApprovalEvent, type ApprovalState } from "./approval.ts";
import { verifyDigest } from "./digest.ts";
import type { Locale } from "./i18n.ts";
import { emptyRunView, reduceRunView, TERMINAL_STATES, type RunView, type RunViewAction } from "./store.ts";

export type ConnectionStatus = "idle" | "connecting" | "open" | "reconnecting" | "closed";

export interface ControllerState {
  locale: Locale;
  runId: string | null;
  view: RunView;
  approval: ApprovalState;
  connection: ConnectionStatus;
  busy: boolean;
  error: string | null;
  evidence: Record<string, unknown> | null;
  /** Number of snapshot fetches; observable by tests and diagnostics. */
  snapshots: number;
}

type KeyValueStorage = Pick<Storage, "getItem" | "setItem" | "removeItem">;

export interface ControllerOptions {
  client: EAgentClient;
  locale?: Locale;
  /** Remembers the current run across reloads; null disables persistence. */
  storage?: KeyValueStorage | null;
  storageKey?: string;
  reconnectDelayMs?: number;
  /** Untrusted hints about the embedding page; the server resolves or drops them. */
  hostContext?: () => HostContext;
}

function defaultStorage(): KeyValueStorage | null {
  try {
    return globalThis.sessionStorage ?? null;
  } catch {
    return null;
  }
}

export class RunController {
  private state: ControllerState;
  private readonly listeners = new Set<() => void>();
  private readonly client: EAgentClient;
  private readonly storage: KeyValueStorage | null;
  private readonly storageKey: string;
  private readonly reconnectDelayMs: number;
  private readonly hostContext: (() => HostContext) | undefined;
  private stream: { close(): void } | null = null;
  private refreshing: Promise<void> | null = null;
  private refreshAgain = false;
  private expiryTimer: ReturnType<typeof setTimeout> | null = null;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private disposed = false;

  constructor(options: ControllerOptions) {
    this.client = options.client;
    this.storage = options.storage === undefined ? defaultStorage() : options.storage;
    this.storageKey = options.storageKey ?? "e-agent.run";
    this.reconnectDelayMs = options.reconnectDelayMs ?? 1000;
    this.hostContext = options.hostContext;
    this.state = {
      locale: options.locale ?? "en",
      runId: null,
      view: emptyRunView,
      approval: initialApproval,
      connection: "idle",
      busy: false,
      error: null,
      evidence: null,
      snapshots: 0,
    };
  }

  // -- store protocol ------------------------------------------------------
  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  getState = (): ControllerState => this.state;

  private set(patch: Partial<ControllerState>): void {
    if (this.disposed) return;
    this.state = { ...this.state, ...patch };
    for (const l of this.listeners) l();
  }

  private dispatchView(action: RunViewAction): void {
    this.set({ view: reduceRunView(this.state.view, action) });
  }

  private dispatchApproval(event: ApprovalEvent): void {
    this.set({ approval: reduceApproval(this.state.approval, event) });
  }

  setLocale(locale: Locale): void {
    this.set({ locale });
  }

  // -- lifecycle -----------------------------------------------------------
  async init(): Promise<void> {
    try {
      if (!this.client.hasSession) await this.client.startLocalSession();
      const remembered = this.storage?.getItem(this.storageKey);
      if (remembered) await this.attach(remembered);
    } catch (err) {
      this.fail(err);
    }
  }

  dispose(): void {
    this.closeStream();
    if (this.expiryTimer) clearTimeout(this.expiryTimer);
    this.disposed = true;
    this.listeners.clear();
  }

  async start(task: string): Promise<void> {
    const text = task.trim();
    if (!text || this.state.busy) return;
    this.set({ busy: true, error: null });
    try {
      const created = await this.client.createRun(text, newIdempotencyKey(), this.hostContext?.());
      await this.attach(created.run_id);
    } catch (err) {
      this.fail(err);
    } finally {
      this.set({ busy: false });
    }
  }

  async attach(runId: string): Promise<void> {
    this.closeStream();
    this.storage?.setItem(this.storageKey, runId);
    this.set({ runId, view: emptyRunView, approval: initialApproval, evidence: null, error: null });
    await this.refresh();
    if (this.state.runId === runId) this.openStream(runId);
  }

  /** Forget the current run locally (never cancels it on the server). */
  detach(): void {
    this.closeStream();
    this.storage?.removeItem(this.storageKey);
    this.set({ runId: null, view: emptyRunView, approval: initialApproval, evidence: null, connection: "idle" });
  }

  // -- stream and snapshots --------------------------------------------------
  private openStream(runId: string): void {
    if (TERMINAL_STATES.has(this.state.view.run?.state ?? "")) {
      this.set({ connection: "closed" });
      return;
    }
    this.set({ connection: "connecting" });
    this.stream = this.client.stream(runId, this.state.view.lastSequence, {
      onEvent: (event) => this.onEvents([event]),
      onEnd: () => {
        this.stream = null;
        this.set({ connection: "closed" });
        void this.refresh();
      },
      onError: (closed) => {
        this.set({ connection: "reconnecting" });
        if (closed) {
          this.stream = null;
          this.reconnectTimer = setTimeout(() => {
            if (this.state.runId === runId && !this.disposed) {
              void this.refresh().then(() => this.openStream(runId));
            }
          }, this.reconnectDelayMs);
        }
      },
      onOpen: () => this.set({ connection: "open" }),
    });
  }

  private closeStream(): void {
    this.stream?.close();
    this.stream = null;
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
  }

  private onEvents(events: RunEvent[]): void {
    if (this.state.connection !== "open") this.set({ connection: "open" });
    this.dispatchView({ type: "events", events });
    if (this.state.view.needsSnapshot) void this.refresh();
  }

  /** Coalesced snapshot + gap fill. Safe to call at any time. */
  refresh(): Promise<void> {
    if (this.refreshing) {
      this.refreshAgain = true;
      return this.refreshing;
    }
    this.refreshing = (async () => {
      do {
        this.refreshAgain = false;
        await this.refreshOnce();
      } while (this.refreshAgain && !this.disposed);
    })().finally(() => {
      this.refreshing = null;
    });
    return this.refreshing;
  }

  private async refreshOnce(): Promise<void> {
    const runId = this.state.runId;
    if (!runId) return;
    try {
      const snapshot = await this.client.getRun(runId);
      const missing = await this.client.listEvents(runId, this.state.view.lastSequence);
      if (this.state.runId !== runId) return;
      this.set({ snapshots: this.state.snapshots + 1 });
      this.dispatchView({ type: "events", events: missing });
      this.dispatchView({ type: "snapshot", snapshot });
      await this.present(snapshot.pending_approval ?? null);
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        this.detach();
        return;
      }
      this.fail(err);
    }
  }

  private async present(p: ControllerState["approval"]["presentation"]): Promise<void> {
    if (this.expiryTimer) clearTimeout(this.expiryTimer);
    if (!p) {
      this.dispatchApproval({ type: "CLEARED" });
      return;
    }
    const digestOk = await verifyDigest(p.canonical_proposal, p.digest);
    this.dispatchApproval({ type: "PRESENTED", presentation: p, digestOk });
    if (isExpired(p)) {
      this.dispatchApproval({ type: "EXPIRED" });
    } else {
      const ms = Math.min(Date.parse(p.expires_at) - Date.now() + 50, 2 ** 31 - 1);
      this.expiryTimer = setTimeout(() => this.dispatchApproval({ type: "EXPIRED" }), ms);
    }
  }

  // -- approval (the only path to a decision) --------------------------------
  requestConfirm(): void {
    this.dispatchApproval({ type: "REQUEST_CONFIRM" });
  }

  back(): void {
    this.dispatchApproval({ type: "BACK" });
  }

  reviewAgain(): void {
    this.dispatchApproval({ type: "REVIEW_AGAIN" });
  }

  canApprove(): boolean {
    return this.state.approval.phase === "confirming" && canRequestApprove(this.state.approval);
  }

  approve(): Promise<void> {
    return this.decide("approved");
  }

  reject(): Promise<void> {
    return this.decide("rejected");
  }

  private async decide(decision: "approved" | "rejected"): Promise<void> {
    const before = this.state.approval;
    const p = before.presentation;
    const runId = this.state.runId;
    if (!p || !runId) return;
    this.dispatchApproval({ type: "SUBMIT", decision });
    if (this.state.approval.phase !== "submitting" || this.state.approval === before) return;
    try {
      await this.client.decide(runId, {
        action_id: p.action_id,
        digest: p.digest,
        expected_revision: p.run_revision,
        decision,
      });
      this.dispatchApproval({ type: "SUBMITTED", decision });
    } catch (err) {
      const stale = err instanceof ApiError && err.status === 409;
      this.dispatchApproval({ type: "FAILED", error: err instanceof Error ? err.message : String(err), stale });
      if (stale) void this.refresh();
    }
  }

  // -- other commands ----------------------------------------------------------
  async cancel(): Promise<void> {
    if (!this.state.runId) return;
    await this.guard(() => this.client.cancel(this.state.runId as string));
    await this.refresh();
  }

  async reconcile(): Promise<void> {
    if (!this.state.runId) return;
    await this.guard(() => this.client.reconcile(this.state.runId as string));
    await this.refresh();
  }

  async loadEvidence(): Promise<void> {
    const runId = this.state.runId;
    if (!runId) return;
    await this.guard(async () => this.set({ evidence: await this.client.evidence(runId) }));
  }

  private async guard(work: () => Promise<unknown>): Promise<void> {
    try {
      await work();
    } catch (err) {
      this.fail(err);
    }
  }

  private fail(err: unknown): void {
    this.set({ error: err instanceof ApiError ? `${err.code}: ${err.message}` : String(err) });
  }
}
