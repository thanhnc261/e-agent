/**
 * L2 client (UI architecture §3): typed HTTP + SSE for the e-agent API v1.
 * Types come only from the generated OpenAPI schema; nothing here renders UI.
 */
import type { components } from "./schema.ts";

type S = components["schemas"];
export type TextFrame = S["TextFrame"];
export type RunEvent = S["RunEvent"];
export type RunEventType = S["RunEventType"];
export type RunRecord = S["RunRecord"];
export type RunSnapshot = S["RunSnapshot"];
export type RunState = S["RunState"];
export type ActionState = S["ActionState"];
export type ActionSummary = S["ActionSummary"];
export type ApprovalPresentation = S["ApprovalPresentation"];
export type MaterialField = S["MaterialField"];
export type Finding = S["Finding"];
export type SessionResponse = S["SessionResponse"];
export type CreateRunResponse = S["CreateRunResponse"];
export type StateResponse = S["StateResponse"];
export type Decision = S["Decide"]["decision"];
export type HostContext = S["HostContext"];
export type MemberConnection = S["MemberConnection"];
export type MemberConnections = S["MemberConnections"];
export type TaskTemplate = S["TaskTemplate"];
export type TaskCatalog = S["TaskCatalog"];
export type FeatureMode = S["FeatureMode"];
export type MemberFeatures = S["MemberFeatures"];
export type Conversation = S["Conversation"];
export type ConversationList = S["ConversationList"];
export type ConversationSummary = S["ConversationSummary"];
export type ConversationSnapshot = S["ConversationSnapshot"];
export type ThreadRun = S["ThreadRun"];
export type ReplyTo = S["ReplyTo"];
export type PostMessage = S["PostMessage"];
export type PostedMessage = S["PostedMessage"];
export type CreatedConversation = S["CreatedConversation"];
export type { components, paths } from "./schema.ts";

export class ApiError extends Error {
  /**
   * True when the body was e-agent's error envelope `{code, message, correlation_id}`.
   * A route that is not mounted (an older server) answers without it, so the UI can tell
   * "not there" from "refused" by the envelope and never by the status alone (ADR 0023).
   */
  readonly enveloped: boolean;
  readonly correlationId: string | null;

  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    options: { enveloped?: boolean; correlationId?: string | null } = {},
  ) {
    super(message);
    this.name = "ApiError";
    this.enveloped = options.enveloped ?? true;
    this.correlationId = options.correlationId ?? null;
  }
}

export interface StreamHandlers {
  onEvent(event: RunEvent): void;
  onText?(frame: TextFrame): void;
  onOpen?(): void;
  onEnd?(state: string): void;
  /** ``closed`` is true when the browser gave up and the caller must reopen. */
  onError?(closed: boolean): void;
}

export interface StreamHandle {
  close(): void;
}

type EventSourceCtor = new (url: string, init?: EventSourceInit) => EventSource;

export interface ClientOptions {
  /** API origin; empty means same origin (the default and the MVP deployment). */
  baseUrl?: string;
  fetch?: typeof fetch;
  EventSource?: EventSourceCtor;
}

/** The largest page the events endpoint serves (ADR 0018). */
const EVENT_PAGE_LIMIT = 1000;

export function newIdempotencyKey(): string {
  return `ui-${crypto.randomUUID()}`;
}

export class EAgentClient {
  private csrf: string | null = null;
  private readonly base: string;
  private readonly fetchImpl: typeof fetch;
  private readonly es: EventSourceCtor | undefined;

  constructor(options: ClientOptions = {}) {
    this.base = (options.baseUrl ?? "").replace(/\/$/, "");
    this.fetchImpl = options.fetch ?? globalThis.fetch.bind(globalThis);
    this.es = options.EventSource ?? (globalThis as { EventSource?: EventSourceCtor }).EventSource;
  }

  get storageOrigin(): string { return this.base || "same-origin"; }

  get hasSession(): boolean {
    return this.csrf !== null;
  }

  /** Loopback-only local session: HttpOnly cookie plus a CSRF token kept in memory. */
  async startLocalSession(): Promise<SessionResponse> {
    const body = await this.request<SessionResponse>("POST", "/v1/local/session", undefined, {}, false);
    this.csrf = body.csrf_token;
    return body;
  }

  createRun(
    task: string,
    idempotencyKey: string = newIdempotencyKey(),
    hostContext?: HostContext,
  ): Promise<CreateRunResponse> {
    const body = hostContext ? { task, host_context: hostContext } : { task };
    return this.request("POST", "/v1/runs", body, { "Idempotency-Key": idempotencyKey });
  }

  getRun(runId: string): Promise<RunSnapshot> {
    return this.request("GET", `/v1/runs/${encodeURIComponent(runId)}`);
  }

  /**
   * Every event after ``afterSequence``. The server caps one response (500 by default,
   * 1000 at most), so this pages with ``after_sequence`` until a short page comes back.
   */
  async listEvents(runId: string, afterSequence = 0): Promise<RunEvent[]> {
    const path = `/v1/runs/${encodeURIComponent(runId)}/events`;
    const events: RunEvent[] = [];
    let cursor = afterSequence;
    for (;;) {
      const page = await this.request<RunEvent[]>(
        "GET",
        `${path}?after_sequence=${cursor}&limit=${EVENT_PAGE_LIMIT}`,
      );
      events.push(...page);
      if (page.length < EVENT_PAGE_LIMIT) return events;
      cursor = page[page.length - 1]!.sequence;
    }
  }

  pendingApproval(runId: string): Promise<ApprovalPresentation> {
    return this.request("GET", `/v1/runs/${encodeURIComponent(runId)}/approvals/pending`);
  }

  decide(
    runId: string,
    body: { action_id: string; digest: string; expected_revision: number; decision: Decision },
  ): Promise<{ status: string }> {
    return this.request("POST", `/v1/runs/${encodeURIComponent(runId)}/approvals`, body);
  }

  submitInput(runId: string, input: string, expectedRevision: number): Promise<{ status: string }> {
    return this.request("POST", `/v1/runs/${encodeURIComponent(runId)}/inputs`, {
      input, expected_revision: expectedRevision,
    });
  }

  cancel(runId: string): Promise<StateResponse> {
    return this.request("POST", `/v1/runs/${encodeURIComponent(runId)}/cancel`, {});
  }

  reconcile(runId: string): Promise<StateResponse> {
    return this.request("POST", `/v1/runs/${encodeURIComponent(runId)}/reconcile`, {});
  }

  evidence(runId: string): Promise<Record<string, unknown>> {
    return this.request("GET", `/v1/runs/${encodeURIComponent(runId)}/evidence`);
  }

  /**
   * Member-readable discovery projections (ADR 0017). Both are read-only views of
   * admitted metadata: they never probe a provider and never return credentials.
   */
  myConnections(): Promise<MemberConnections> {
    return this.request("GET", "/v1/me/connections");
  }

  myTaskCatalog(): Promise<TaskCatalog> {
    return this.request("GET", "/v1/me/task-catalog");
  }

  /** The member's view of the server's modes; answers in every conversations mode (ADR 0023 §10). */
  myFeatures(): Promise<MemberFeatures> {
    return this.request("GET", "/v1/me/features");
  }

  createConversation(): Promise<CreatedConversation> {
    return this.request("POST", "/v1/conversations");
  }

  /** The caller's conversations, newest first, as the server orders them. */
  listConversations(options: { after?: string | null; limit?: number } = {}): Promise<ConversationList> {
    const query = new URLSearchParams();
    if (options.after) query.set("after", options.after);
    if (options.limit !== undefined) query.set("limit", String(options.limit));
    const qs = query.toString();
    return this.request("GET", qs ? `/v1/conversations?${qs}` : "/v1/conversations");
  }

  /** The conversation and its runs, oldest first, each with the revision an answer's `reply_to` uses. */
  getConversation(conversationId: string): Promise<ConversationSnapshot> {
    return this.request("GET", `/v1/conversations/${encodeURIComponent(conversationId)}`);
  }

  /**
   * One message into a conversation. The server routes it (start or answer); a refusal is a
   * `CONFLICT` with a fixed hint, never a 202 (ADR 0023 §4).
   */
  postMessage(
    conversationId: string,
    body: PostMessage,
    idempotencyKey: string = newIdempotencyKey(),
  ): Promise<PostedMessage> {
    return this.request("POST", `/v1/conversations/${encodeURIComponent(conversationId)}/messages`, body, {
      "Idempotency-Key": idempotencyKey,
    });
  }

  /**
   * Subscribe to run events after ``afterSequence``. The browser resumes with
   * ``Last-Event-ID`` on transient drops; callers dedupe by ``sequence`` anyway.
   */
  stream(runId: string, afterSequence: number, handlers: StreamHandlers): StreamHandle {
    if (!this.es) throw new Error("EventSource is not available");
    const url = `${this.base}/v1/runs/${encodeURIComponent(runId)}/stream?after_sequence=${afterSequence}`;
    const source = new this.es(url, { withCredentials: this.base !== "" });
    source.addEventListener("run_event", (msg) => {
      handlers.onEvent(JSON.parse((msg as MessageEvent<string>).data) as RunEvent);
    });
    source.addEventListener("text_delta", (msg) => {
      handlers.onText?.(JSON.parse((msg as MessageEvent<string>).data) as TextFrame);
    });
    source.addEventListener("end", (msg) => {
      source.close();
      const data = JSON.parse((msg as MessageEvent<string>).data) as { state: string };
      handlers.onEnd?.(data.state);
    });
    source.onopen = () => handlers.onOpen?.();
    source.onerror = () => handlers.onError?.(source.readyState === 2);
    return { close: () => source.close() };
  }

  private async request<T>(
    method: "GET" | "POST",
    path: string,
    body?: unknown,
    headers: Record<string, string> = {},
    needsCsrf = method !== "GET",
  ): Promise<T> {
    const h: Record<string, string> = { Accept: "application/json", ...headers };
    if (body !== undefined) h["Content-Type"] = "application/json";
    if (needsCsrf && this.csrf) h["X-CSRF-Token"] = this.csrf;
    const response = await this.fetchImpl(`${this.base}${path}`, {
      method,
      headers: h,
      body: body === undefined ? null : JSON.stringify(body),
      credentials: this.base === "" ? "same-origin" : "include",
    });
    const text = await response.text();
    if (!response.ok) {
      // An error body may be plain text (a static mount's 405) or FastAPI's `{"detail": ...}`.
      let err: { code?: unknown; message?: unknown; correlation_id?: unknown } = {};
      try {
        const parsed: unknown = text ? JSON.parse(text) : null;
        if (parsed && typeof parsed === "object") err = parsed as typeof err;
      } catch {
        /* not JSON: no envelope */
      }
      const enveloped = typeof err.code === "string";
      throw new ApiError(
        response.status,
        enveloped ? (err.code as string) : "HTTP_ERROR",
        typeof err.message === "string" ? err.message : response.statusText,
        { enveloped, correlationId: typeof err.correlation_id === "string" ? err.correlation_id : null },
      );
    }
    return (text ? JSON.parse(text) : null) as T;
  }
}
