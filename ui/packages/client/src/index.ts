/**
 * L2 client (UI architecture §3): typed HTTP + SSE for the e-agent API v1.
 * Types come only from the generated OpenAPI schema; nothing here renders UI.
 */
import type { components } from "./schema.ts";

type S = components["schemas"];
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
export type { components, paths } from "./schema.ts";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export interface StreamHandlers {
  onEvent(event: RunEvent): void;
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

  listEvents(runId: string, afterSequence = 0): Promise<RunEvent[]> {
    return this.request("GET", `/v1/runs/${encodeURIComponent(runId)}/events?after_sequence=${afterSequence}`);
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
    const data: unknown = text ? JSON.parse(text) : null;
    if (!response.ok) {
      const err = (data ?? {}) as { code?: string; message?: string };
      throw new ApiError(response.status, err.code ?? "HTTP_ERROR", err.message ?? response.statusText);
    }
    return data as T;
  }
}
