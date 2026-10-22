/**
 * Framework-free run controller: the one stateful object every UI binds to
 * (React via useSyncExternalStore, the vanilla reference UI via subscribe).
 * It talks to the server only through the L2 client.
 */
import {
  ApiError,
  newIdempotencyKey,
  type ConversationSnapshot,
  type ConversationSummary,
  type EAgentClient,
  type FeatureMode,
  type HostContext,
  type PostMessage,
  type ReplyTo,
  type RunEvent,
} from "@e-agent/client";
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
import {
  emptyRunView,
  reduceRunView,
  TERMINAL_STATES,
  selectPendingReply,
  type RunView,
  type RunViewAction,
  type ThreadSource,
} from "./store.ts";

export type ConnectionStatus = "idle" | "connecting" | "open" | "reconnecting" | "closed";

/**
 * The conversations mode as `GET /v1/me/features` reported it (ADR 0023 §10). `mounted` is
 * false when the route is not there at all (an older server), which counts as `off`. Any
 * other failure, or a mode this UI does not know, is `unavailable`, never a guess (EA-8).
 */
export type FeaturesState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "ready"; conversations: FeatureMode; mounted: boolean }
  | { kind: "unavailable" };

/** The sidebar's conversation list, in the server's order (newest first). */
export type ThreadListState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "ready"; items: ConversationSummary[]; nextAfter: string | null }
  | { kind: "error" };

/**
 * The open conversation in `on`: the server snapshot and the events of its runs other than
 * the active one (the active run stays in `runId` and `view`, its one owner, AG-FE-2).
 */
export interface ThreadState extends ThreadSource {
  status: "idle" | "loading" | "ready" | "error";
}

/** A message the server refused, with its fixed hint as the server wrote it (ADR 0023 §4). */
export interface MessageRefusal {
  code: string;
  message: string;
  /** The server's correlation id for the refusal, when it sent one; shown as a reference. */
  correlationId?: string | null;
}

export type ViewMode =
  | { kind: "thread" }
  | { kind: "per-run"; reason: "loading" | "off" | "shadow" | "features-unavailable" | "thread-unavailable" };

/**
 * Which view a UI shows. Only `on` with readable conversation routes shows the thread;
 * `off` and `shadow` keep today's per-run view, and so does any failed read (ADR 0023).
 */
export function selectViewMode(state: Pick<ControllerState, "features" | "threads" | "thread">): ViewMode {
  const features = state.features;
  if (features.kind === "idle" || features.kind === "loading") return { kind: "per-run", reason: "loading" };
  if (features.kind === "unavailable") return { kind: "per-run", reason: "features-unavailable" };
  if (features.conversations !== "on") return { kind: "per-run", reason: features.conversations };
  if (state.threads.kind === "error" || state.thread.status === "error") return { kind: "per-run", reason: "thread-unavailable" };
  return { kind: "thread" };
}

const emptyThread: ThreadState = { snapshot: null, runs: {}, status: "idle" };

/** A route that is not mounted answers FastAPI's own 404 or a static mount's 405, with no envelope. */
function isNotMounted(err: unknown): boolean {
  return err instanceof ApiError && !err.enveloped && (err.status === 404 || err.status === 405);
}

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
  /** `features.conversations`, read from the server; decides the routes and the view. */
  features: FeaturesState;
  /** The conversation messages go to (`shadow` and `on`); one per "New task". */
  conversationId: string | null;
  /** `on` only: the caller's conversations. */
  threads: ThreadListState;
  /** `on` only: the open conversation. Render it with `selectThread(state.thread, state)`. */
  thread: ThreadState;
  /** The last message the server refused; the draft is kept and the hint shows in the composer. */
  refusal: MessageRefusal | null;
}

export interface TaskHistoryEntry { runId: string; task: string; state: string; reasonCode?: string | null; replyPending?: boolean }

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
  /**
   * A conversation message whose response was lost. Kept in memory only (no thread text is
   * written to browser storage), so the user's own resend reuses its key and the server
   * replays it; the UI itself never re-posts.
   */
  private pendingMessage: { text: string; key: string; conversationId: string; body: PostMessage } | null = null;
  /** False once a conversation route answered "not mounted": an older server. */
  private routesMounted = true;
  /** Thread runs whose events were read after they ended; they do not change any more. */
  private readonly settledRuns = new Set<string>();
  /**
   * The run, and its state, that the shown refusal was about, as read right after the server
   * refused (B-1). The hint describes the refusal only while that holds: once that run changes
   * state, or another run (or none) is attached, it is cleared. The draft is never touched.
   */
  private refusalCause: { runId: string | null; state: string | null } | null = null;
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
      features: { kind: "idle" },
      conversationId: null,
      threads: { kind: "idle" },
      thread: emptyThread,
      refusal: null,
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
    let next = { ...this.state, ...patch };
    if (!next.refusal) this.refusalCause = null;
    else if (this.refusalCause && !this.refusalHolds(next)) {
      next = { ...next, refusal: null };
      this.refusalCause = null;
    }
    this.state = next;
    for (const l of this.listeners) l();
  }

  /** True while the attached run is the one the refusal was about, in the same state (B-1). */
  private refusalHolds(state: ControllerState): boolean {
    const cause = this.refusalCause;
    const run = state.view.run;
    return !!cause && state.runId === cause.runId && (run?.run_id ?? null) === cause.runId && (run?.state ?? null) === cause.state;
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
      await this.loadFeatures();
      try {
        const history: unknown = JSON.parse(this.storage?.getItem(this.storageKey + ".history") ?? "[]");
        if (Array.isArray(history)) this.set({ history: history.filter((h): h is TaskHistoryEntry => !!h && typeof h.runId === "string" && typeof h.task === "string" && typeof h.state === "string").slice(0, 20) });
        const pending: unknown = JSON.parse(this.storage?.getItem(this.storageKey + ".pending") ?? "null");
        if (pending && typeof pending === "object" && "task" in pending && "key" in pending && typeof pending.task === "string" && typeof pending.key === "string") this.pendingSubmission = pending as typeof this.pendingSubmission;
      } catch { /* Ignore corrupt local navigation metadata; server remains authoritative. */ }
      if (this.isOn()) await this.loadConversations();
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

  /**
   * Send the composer's text. `off` (or a server without the conversation routes) uses
   * today's `/v1/runs` and `/inputs`; `shadow` and `on` post to the conversation, and the
   * server routes the message. Returns true when the message was accepted, so the caller
   * clears the draft; on a refusal or an error the draft is kept.
   */
  async start(task: string): Promise<boolean> {
    const text = task.trim();
    if (!text || this.state.busy) return false;
    // The thread view's composer stays open: the server refuses what cannot go now (G-B 4).
    if (!this.isOn() && !canCompose(this.state.view.run?.state)) return false;
    this.set({ busy: true, error: null, refusal: null });
    try {
      await this.ensureSession();
      let features = this.state.features;
      if (features.kind !== "ready") features = await this.loadFeatures();
      if (features.kind !== "ready") {
        // Without a mode the UI may not use /v1/runs, and posts nothing.
        this.set({ error: translate(this.state.locale, "conversation.featuresFailed") });
        return false;
      }
      if (features.conversations === "off" || !this.routesMounted) return await this.startLegacy(text);
      return await this.sendMessage(text, features.conversations);
    } catch (err) {
      this.fail(err);
      return false;
    } finally {
      this.set({ busy: false });
    }
  }

  /** Today's path: `/v1/runs`, or `/inputs` for the run that waits (ADR 0023: `off`). */
  private async startLegacy(text: string): Promise<boolean> {
    const current = this.state.view.run;
    if (!canCompose(current?.state)) return false;
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
  }

  /**
   * Post through `POST /v1/conversations/{id}/messages`. An answer names the waiting run and
   * the revision the user saw with its question. Only a route that is not mounted falls back
   * to today's path, with that path's own fresh key; every other error is shown and nothing
   * is re-posted, because in `shadow` the server already did today's thing (Task 4d.3).
   */
  private async sendMessage(text: string, mode: "shadow" | "on"): Promise<boolean> {
    const run = this.state.view.run;
    const runId = this.state.runId;
    const unresolved = this.pendingMessage;
    if (unresolved && unresolved.text !== text) {
      // The lost message may have been committed: another text waits until it is recovered,
      // as on the legacy path (PR-18). Its draft is kept.
      this.set({ error: translate(this.state.locale, "error.pending") });
      return false;
    }
    const waiting = !!run && !!runId && run.run_id === runId && run.state === "WAITING_INPUT";
    if (!unresolved && waiting && mode === "on" && !run?.conversation_id) {
      // A legacy run, outside every conversation: today's /inputs answers it and starts
      // nothing, so no conversation is made up for it (ADR 0023 §10, D11).
      return this.startLegacy(text);
    }
    let conversationId = unresolved?.conversationId ?? this.state.conversationId;
    let posted: { route: "start" | "answer"; run_id: string };
    try {
      let pending = unresolved;
      if (!pending) {
        if (!conversationId) {
          conversationId = (await this.client.createConversation()).conversation_id;
          this.useConversation(conversationId);
        }
        const replyTo: ReplyTo | null = waiting && run ? { run_id: run.run_id, run_revision: run.revision } : null;
        const body: PostMessage = {
          text,
          reply_to: replyTo,
          host_context: replyTo ? null : (this.hostContext?.() ?? null),
        };
        pending = { text, conversationId, key: newIdempotencyKey(), body };
        this.pendingMessage = pending;
      }
      // A resend of a lost message repeats its exact body, conversation and key.
      conversationId = pending.conversationId;
      posted = await this.client.postMessage(pending.conversationId, pending.body, pending.key);
      this.pendingMessage = null;
    } catch (err) {
      if (isNotMounted(err)) {
        this.routesMounted = false;
        this.pendingMessage = null;
        return this.startLegacy(text);
      }
      await this.messageFailed(err, conversationId);
      return false;
    }
    // The server accepted the message: from here the thread is read back, never echoed.
    if (posted.route === "answer" && posted.run_id === runId) await this.refresh();
    else await this.attachRun(posted.run_id, false, conversationId);
    if (mode === "on") {
      await this.loadThread(conversationId);
      await this.loadConversations();
    }
    return true;
  }

  private async messageFailed(err: unknown, conversationId: string | null): Promise<void> {
    const locale = this.state.locale;
    if (!(err instanceof ApiError)) {
      // A lost response: the outcome is unknown, so the key stays for the user's own resend.
      this.set({ error: translate(locale, "error.network") });
      return;
    }
    // A 4xx is a definitive answer, so a later send is a new message with a new key.
    if (err.status < 500) this.pendingMessage = null;
    if (err.enveloped && err.code === "CONFLICT") {
      // Refused: keep the draft, show the hint, and read the latest state so the user can
      // read the question again. The approval card changes only if the server's did.
      this.set({ refusal: { code: err.code, message: err.message, correlationId: err.correlationId ?? null } });
      await this.refresh();
      // The cause is the state this read showed, so a stale view before it never clears the hint.
      if (this.state.refusal) this.refusalCause = { runId: this.state.runId, state: this.state.view.run?.state ?? null };
      if (this.isOn() && conversationId) await this.loadThread(conversationId);
      return;
    }
    this.set({ error: translate(locale, "conversation.notSent") });
    if (err.enveloped && err.code === "NOT_FOUND") {
      // A missing conversation, or "conversations are off" after a mode change.
      await this.loadFeatures();
      if (this.isOn()) await this.loadConversations();
    }
  }

  newTask(): void {
    // Navigation is explicit and never cancels or rejects server work.
    this.detach();
  }

  private remember(): void {
    const run = this.state.view.run;
    if (!run) return;
    // In `on` a conversation's runs live on the server; the session history keeps only the
    // legacy runs, the "last seen" group, and no thread text goes to browser storage.
    if (this.isOn() && run.conversation_id) return;
    const history = [{ runId: run.run_id, task: run.task, state: run.state, reasonCode: run.reason_code ?? null, replyPending: selectPendingReply(this.state.view) }, ...this.state.history.filter(h => h.runId !== run.run_id)].slice(0, 20);
    this.set({ history });
    this.storage?.setItem(this.storageKey + ".history", JSON.stringify(history));
  }

  async attach(runId: string): Promise<boolean> {
    return this.attachRun(runId, true, null);
  }

  /**
   * Attach a run. Its conversation comes from the server's run record; `keep` is the
   * conversation a message was just posted to, kept when the server answered with an
   * unlinked run (a `shadow` fallback, Task 4d.3).
   */
  private async attachRun(runId: string, withThread: boolean, keep: string | null): Promise<boolean> {
    this.closeStream();
    if (this.expiryTimer) clearTimeout(this.expiryTimer);
    this.storage?.setItem(this.storageKey, runId);
    this.set({ runId, view: emptyRunView, approval: initialApproval, evidence: null, error: null });
    await this.refresh();
    if (this.state.runId !== runId || this.state.view.run?.run_id !== runId) return false;
    this.openStream(runId);
    const conversationId = this.state.view.run?.conversation_id ?? keep;
    this.useConversation(conversationId);
    if (withThread && conversationId && this.isOn()) await this.loadThread(conversationId);
    return true;
  }

  /** Forget the current run and conversation locally (never cancels anything on the server). */
  detach(): void {
    this.release();
    this.useConversation(null);
  }

  private release(): void {
    this.closeStream();
    if (this.expiryTimer) clearTimeout(this.expiryTimer);
    this.storage?.removeItem(this.storageKey);
    this.set({ runId: null, view: emptyRunView, approval: initialApproval, evidence: null, connection: "idle" });
  }

  // -- conversations (ADR 0023) ------------------------------------------------
  private isOn(): boolean {
    const features = this.state.features;
    return features.kind === "ready" && features.conversations === "on";
  }

  private useConversation(conversationId: string | null): void {
    if (conversationId === this.state.conversationId) return;
    this.settledRuns.clear();
    // A pending message is kept: it may have been committed, and only its resend recovers it.
    this.set({ conversationId, thread: emptyThread, refusal: null });
  }

  /** Read `GET /v1/me/features`. Safe to call at any time; the UI reads the mode only here. */
  async loadFeatures(): Promise<FeaturesState> {
    if (this.state.features.kind !== "ready") this.set({ features: { kind: "loading" } });
    let next: FeaturesState;
    try {
      await this.ensureSession();
      const mode: unknown = (await this.client.myFeatures())?.conversations;
      next =
        mode === "off" || mode === "shadow" || mode === "on"
          ? { kind: "ready", conversations: mode, mounted: true }
          : { kind: "unavailable" };
    } catch (err) {
      next = isNotMounted(err) ? { kind: "ready", conversations: "off", mounted: false } : { kind: "unavailable" };
    }
    this.set({ features: next });
    return next;
  }

  /** `on`: the caller's conversations, as the server lists them (newest first). */
  async loadConversations(): Promise<void> {
    if (this.state.threads.kind !== "ready") this.set({ threads: { kind: "loading" } });
    try {
      await this.ensureSession();
      const list = await this.client.listConversations();
      this.set({ threads: { kind: "ready", items: [...list.items], nextAfter: list.next_after ?? null } });
    } catch (err) {
      this.set({ threads: { kind: "error" } });
      if (err instanceof ApiError && err.enveloped && err.code === "NOT_FOUND") await this.loadFeatures();
    }
  }

  /**
   * `on`: open a conversation. Its latest run becomes the active run (streamed); the others
   * are read once from their events. Nothing here is local: the server snapshot is the thread.
   */
  async openConversation(conversationId: string): Promise<void> {
    if (conversationId !== this.state.conversationId) {
      this.release();
      this.useConversation(conversationId);
    }
    const snapshot = await this.loadThread(conversationId);
    if (!snapshot || this.state.conversationId !== conversationId) return;
    const latest = snapshot.runs.at(-1);
    if (!latest) {
      if (this.state.runId) this.release();
      return;
    }
    if (this.state.runId !== latest.run_id) {
      await this.attachRun(latest.run_id, false, conversationId);
      await this.loadThreadRuns(snapshot);
    }
  }

  private async loadThread(conversationId: string): Promise<ConversationSnapshot | null> {
    if (this.state.conversationId !== conversationId) return null;
    this.set({ thread: { ...this.state.thread, status: "loading" } });
    try {
      const snapshot = await this.client.getConversation(conversationId);
      if (this.state.conversationId !== conversationId) return null;
      this.set({ thread: { ...this.state.thread, snapshot, status: "ready" } });
      await this.loadThreadRuns(snapshot);
      return snapshot;
    } catch (err) {
      if (this.state.conversationId !== conversationId) return null;
      this.set({ thread: { ...this.state.thread, status: "error" } });
      if (err instanceof ApiError && err.enveloped && err.code === "NOT_FOUND") await this.loadFeatures();
      return null;
    }
  }

  /** Read the events of the thread's other runs; an ended run is read once more, then kept. */
  private async loadThreadRuns(snapshot: ConversationSnapshot): Promise<void> {
    const conversationId = snapshot.conversation.conversation_id;
    const reads = snapshot.runs
      .filter(run => run.run_id !== this.state.runId && !this.settledRuns.has(run.run_id))
      .map(async run => {
        const before = this.state.thread.runs[run.run_id] ?? emptyRunView;
        try {
          const events = await this.client.listEvents(run.run_id, before.lastSequence);
          if (this.state.conversationId !== conversationId) return;
          const view = reduceRunView(this.state.thread.runs[run.run_id] ?? emptyRunView, { type: "events", events });
          this.set({ thread: { ...this.state.thread, runs: { ...this.state.thread.runs, [run.run_id]: view } } });
          if (TERMINAL_STATES.has(run.state)) this.settledRuns.add(run.run_id);
        } catch {
          // Left unread: selectThread marks the run as not loaded, never as empty (EA-8).
        }
      });
    await Promise.all(reads);
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

  /**
   * Read the run's evidence bundle. The user's explicit reads (Load, the explanation) report a
   * failure in the shared error. A `quiet` read, one a view makes on its own to show an
   * optional detail (the earlier runs used as hints, GD-1), never does: its failure leaves the
   * bundle unread, and that view shows nothing, so no alert asks the user to redo something
   * they never did (EA-16).
   */
  async loadEvidence(options: { quiet?: boolean } = {}): Promise<void> {
    const runId = this.state.runId;
    if (!runId) return;
    const read = async () => {
      const evidence = await this.client.evidence(runId);
      if (this.state.runId === runId) this.set({ evidence });
    };
    if (!options.quiet) return this.guard(read);
    try {
      await read();
    } catch {
      // Left unread: the view that asked shows nothing (PR-21: unread is not empty).
    }
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
