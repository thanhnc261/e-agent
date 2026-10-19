/**
 * Framework-free run controller: the one stateful object every UI binds to
 * (React via useSyncExternalStore, the vanilla reference UI via subscribe).
 * It talks to the server only through the L2 client.
 */
import { ApiError, newIdempotencyKey, type EAgentClient, type HostContext, type RunEvent } from "@e-agent/client";
import { canRequestApprove, initialApproval, isExpired, reduceApproval, type ApprovalEvent, type ApprovalState } from "./approval.ts";
import { canCompose, presentationMatchesCanonical } from "./presentation.ts";
import {
  projectConnections,
  projectTaskCatalog,
  type ConnectionView,
  type DiscoveryState,
  type TaskTemplateView,
} from "./selectors/discovery.ts";
import { translate } from "./i18n.ts";
import { verifyDigest } from "./digest.ts";
import type { Locale } from "./i18n.ts";
import { emptyRunView, reduceRunView, TERMINAL_STATES, type RunView, type RunViewAction } from "./store.ts";

export type ConnectionStatus = "idle" | "connecting" | "open" | "reconnecting" | "closed";

export interface ControllerState {
  locale: Locale;
  draft: string;
  runId: string | null;
  view: RunView;
  approval: ApprovalState;
  connection: ConnectionStatus;
  busy: boolean;
  error: string | null;
  evidence: Record<string, unknown> | null;
  /** Number of snapshot fetches; observable by tests and diagnostics. */
  snapshots: number;
  history: TaskHistoryEntry[];
  /** Member discovery projections (ADR 0017). Display only; they authorize nothing. */
  connections: DiscoveryState<ConnectionView>;
  catalog: DiscoveryState<TaskTemplateView>;
}

export interface TaskHistoryEntry { runId: string; task: string; state: string; reasonCode?: string | null }

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
  private storageKey: string;
  private sessionPromise: Promise<void> | null = null;
  private pendingSubmission: { task: string; key: string; runId?: string } | null = null;
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
      draft: "",
      runId: null,
      view: emptyRunView,
      approval: initialApproval,
      connection: "idle",
      busy: false,
      error: null,
      evidence: null,
      snapshots: 0,
      history: [],
      connections: { kind: "idle" },
      catalog: { kind: "idle" },
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

  setDraft(draft: string): void {
    this.set({ draft });
  }

  setLocale(locale: Locale): void {
    this.set({ locale });
  }

  /**
   * Exactly the host context the next submission would send, or null when the host
   * sends none. It is read from the same source `start()` uses, so a preview can never
   * show more or less than the request carries.
   */
  hostContextPreview(): HostContext | null {
    return this.hostContext?.() ?? null;
  }

  // -- lifecycle -----------------------------------------------------------
  async init(): Promise<void> {
    try {
      await this.ensureSession();
      try {
        const history: unknown = JSON.parse(this.storage?.getItem(this.storageKey + ".history") ?? "[]");
        if (Array.isArray(history)) this.set({ history: history.filter((h): h is TaskHistoryEntry => !!h && typeof h.runId === "string" && typeof h.task === "string" && typeof h.state === "string").slice(0, 20) });
        const pending: unknown = JSON.parse(this.storage?.getItem(this.storageKey + ".pending") ?? "null");
        if (pending && typeof pending === "object" && "task" in pending && "key" in pending && typeof pending.task === "string" && typeof pending.key === "string") this.pendingSubmission = pending as typeof this.pendingSubmission;
      } catch { /* Ignore corrupt local navigation metadata; server remains authoritative. */ }
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

  private async ensureSession(): Promise<void> {
    if (this.client.hasSession) return;
    this.sessionPromise ??= this.client.startLocalSession().then(session => {
      this.storageKey += "." + encodeURIComponent(this.client.storageOrigin) + "." + encodeURIComponent(session.tenant) + "." + encodeURIComponent(session.principal);
    }).catch(err => { this.sessionPromise = null; throw err; });
    await this.sessionPromise;
  }

  async start(task: string): Promise<boolean> {
    const text = task.trim();
    if (!text || this.state.busy) return false;
    const current = this.state.view.run;
    if (!canCompose(current?.state)) return false;
    this.set({ busy: true, error: null });
    try {
      await this.ensureSession();
      if (current?.state === "WAITING_INPUT" && this.state.runId) {
        await this.client.submitInput(this.state.runId, text, current.revision);
        await this.refresh();
        return true;
      }
      if (this.pendingSubmission && this.pendingSubmission.task !== text) {
        this.set({ error: translate(this.state.locale, "error.pending") });
        return false;
      }
      this.pendingSubmission ??= { task: text, key: newIdempotencyKey() };
      this.storage?.setItem(this.storageKey + ".pending", JSON.stringify(this.pendingSubmission));
      const pending = this.pendingSubmission;
      const runId = pending.runId ?? (await this.client.createRun(text, pending.key, this.hostContext?.())).run_id;
      pending.runId = runId;
      this.storage?.setItem(this.storageKey + ".pending", JSON.stringify(pending));
      if (!await this.attach(runId)) return false;
      this.pendingSubmission = null;
      this.storage?.removeItem(this.storageKey + ".pending");
      return true;
    } catch (err) {
      this.fail(err);
      return false;
    } finally {
      this.set({ busy: false });
    }
  }

  newTask(): void {
    // Navigation is explicit and never cancels or rejects server work.
    this.detach();
  }

  private remember(): void {
    const run = this.state.view.run;
    if (!run) return;
    const history = [{ runId: run.run_id, task: run.task, state: run.state, reasonCode: run.reason_code ?? null }, ...this.state.history.filter(h => h.runId !== run.run_id)].slice(0, 20);
    this.set({ history });
    this.storage?.setItem(this.storageKey + ".history", JSON.stringify(history));
  }

  async attach(runId: string): Promise<boolean> {
    this.closeStream();
    if (this.expiryTimer) clearTimeout(this.expiryTimer);
    this.storage?.setItem(this.storageKey, runId);
    this.set({ runId, view: emptyRunView, approval: initialApproval, evidence: null, error: null });
    await this.refresh();
    if (this.state.runId !== runId || this.state.view.run?.run_id !== runId) return false;
    this.openStream(runId);
    return true;
  }

  /** Forget the current run locally (never cancels it on the server). */
  detach(): void {
    this.closeStream();
    if (this.expiryTimer) clearTimeout(this.expiryTimer);
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
      onEvent: (event) => { if (this.state.runId === runId) this.onEvents([event]); },
      onText: (frame) => {
        if (this.state.runId !== runId) return;
        this.dispatchView({ type: "text", frame });
        if (this.state.view.needsSnapshot) void this.refresh();
      },
      onEnd: () => {
        if (this.state.runId !== runId) return;
        this.stream = null;
        this.set({ connection: "closed" });
        void this.refresh();
      },
      onError: (closed) => {
        if (this.state.runId !== runId) return;
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
      onOpen: () => { if (this.state.runId === runId) this.set({ connection: "open" }); },
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
      if (missing.some((event) => event.sequence > snapshot.latest_sequence)) {
        // Gap-fill can observe events committed after the snapshot read.
        // Fetch their matching state before presenting approval or clearing triggers.
        this.refreshAgain = true;
        return;
      }
      this.dispatchView({ type: "snapshot", snapshot });
      this.remember();
      if (snapshot.streaming_text && !TERMINAL_STATES.has(snapshot.run.state) && snapshot.run.state !== "WAITING_INPUT") {
        this.dispatchView({ type: "text", frame: snapshot.streaming_text });
      }
      await this.present(snapshot.pending_approval ?? null);
    } catch (err) {
      if (this.state.runId !== runId) return;
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
    const runId = this.state.runId;
    const digestOk = p.run_id === runId && presentationMatchesCanonical(p) && await verifyDigest(p.canonical_proposal, p.digest);
    if (this.state.runId !== runId) return;
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
      if (this.state.runId === runId) this.dispatchApproval({ type: "SUBMITTED", decision });
    } catch (err) {
      if (this.state.runId !== runId) return;
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
    await this.guard(async () => {
      const evidence = await this.client.evidence(runId);
      if (this.state.runId === runId) this.set({ evidence });
    });
  }

  // -- member discovery (read-only projections, ADR 0017) ----------------------
  /**
   * An authenticated member may still not be allowed to see a projection, and an
   * older server may not offer it at all. Those are different outcomes and are kept
   * apart here so the UI never renders "nothing is connected" for either of them.
   */
  private async loadDiscovery<T>(
    key: "connections" | "catalog",
    fetch: () => Promise<unknown>,
    project: (body: unknown) => DiscoveryState<T>,
  ): Promise<void> {
    if (this.state[key].kind === "loading") return;
    this.set({ [key]: { kind: "loading" } } as Partial<ControllerState>);
    try {
      await this.ensureSession();
      const body = await fetch();
      this.set({ [key]: project(body) } as Partial<ControllerState>);
    } catch (err) {
      const status = err instanceof ApiError ? err.status : 0;
      const code = err instanceof ApiError ? err.code : "";
      const next: DiscoveryState<T> =
        code === "FORBIDDEN"
          ? { kind: "denied" }
          : status === 404 || status === 405
            ? { kind: "unsupported", schemaVersion: null }
            : { kind: "error", message: translate(this.state.locale, "error.command") };
      this.set({ [key]: next } as Partial<ControllerState>);
    }
  }

  loadConnections(): Promise<void> {
    return this.loadDiscovery("connections", () => this.client.myConnections(), projectConnections);
  }

  loadTaskCatalog(): Promise<void> {
    return this.loadDiscovery("catalog", () => this.client.myTaskCatalog(), projectTaskCatalog);
  }

  private async guard(work: () => Promise<unknown>): Promise<void> {
    try {
      await work();
    } catch (err) {
      this.fail(err);
    }
  }

  private fail(err: unknown): void {
    this.set({ error: translate(this.state.locale, err instanceof ApiError ? err.status === 409 ? "error.stale" : "error.command" : "error.network") });
  }
}
