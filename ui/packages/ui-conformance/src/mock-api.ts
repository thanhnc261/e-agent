/**
 * Scriptable stand-in for the e-agent API v1, installed with page.route. Every
 * stream response ends after a few events, so UIs must resume via Last-Event-ID or
 * after_sequence, and some responses overlap on purpose to exercise dedup.
 */
import type { Page, Route } from "@playwright/test";
import type {
  ApprovalPresentation,
  ConversationSnapshot,
  ConversationSummary,
  FeatureMode,
  RunEvent,
  RunSnapshot,
  TextFrame,
} from "@e-agent/client";
import { canonicalize } from "@e-agent/ui-core";
import { createHash } from "node:crypto";

export const RUN_ID = "run-conformance-1";
export const CONVERSATION_ID = "conv-conformance-1";
/** The server's fixed refusal hints (ADR 0023 §4). */
export const HINT_BUSY = "wait, decide the approval, or stop the run";
export const HINT_QUESTION_CHANGED = "the question changed; read it again";

export function digestOf(value: unknown): string {
  return `jcs-sha256-v1:${createHash("sha256").update(canonicalize(value), "utf8").digest("hex")}`;
}

export function presentation(
  overrides: Partial<ApprovalPresentation> = {},
  quantity = "40",
): ApprovalPresentation {
  const canonical = {
    contract_id: "procurement.purchase-order.create-draft.v1",
    arguments: { quantity, supplier_ref: "supplier:approved-co", unit_price: "100" },
  };
  return {
    run_id: RUN_ID,
    action_id: "act-1",
    run_revision: 6,
    digest: digestOf(canonical),
    expires_at: new Date(Date.now() + 10 * 60_000).toISOString(),
    contract_id: "procurement.purchase-order.create-draft.v1",
    binding_id: "binding-1",
    connection_id: "conn-1",
    credential_subject: "conn-1@1/integration-user",
    canonical_proposal: canonical,
    expected_effects: [],
    material_fields: [
      { path: "quantity", value: quantity, previous_value: "7", changed: true },
      {
        path: "supplier_ref",
        value: "supplier:approved-co",
        previous_value: "supplier:approved-co",
        changed: false,
      },
      { path: "unit_price", value: "100", previous_value: "100", changed: false },
    ],
    findings: [
      { rule_id: "PR-001", rule_version: "1", status: "PASS", message: "satisfied", evidence_ids: [] },
      { rule_id: "PR-004", rule_version: "1", status: "PASS", message: "satisfied", evidence_ids: [] },
    ],
    plan_steps: [],
    irreversible_steps: [],
    ...overrides,
  };
}

export class MockApi {
  events: RunEvent[] = [];
  state: RunSnapshot["run"]["state"] = "RUNNING";
  pending: ApprovalPresentation | null = null;
  readonly decisions: Record<string, unknown>[] = [];
  readonly inputs: Record<string, unknown>[] = [];
  readonly textFrames: TextFrame[] = [];
  /**
   * Member discovery responses (ADR 0017). `null` makes the route 404, which is how
   * a workspace without these read models behaves.
   */
  connections: Record<string, unknown> | null = {
    schema_version: "1",
    observed_at: "2026-10-09T00:00:00Z",
    connections: [
      {
        connection_id: "conn-1",
        integration_id: "fixture-erp",
        ownership: "tenant_shared",
        acting_identity: "integration-user",
        allowed_resources: ["purchase-order"],
        capabilities: ["procurement.purchase-order.create-draft.v1"],
        configuration_status: "active",
        observed_health: "unknown",
        revision: 1,
      },
      {
        connection_id: "conn-2",
        integration_id: "fixture-archive",
        ownership: "user_delegated",
        acting_identity: null,
        allowed_resources: [],
        capabilities: [],
        configuration_status: "revoked",
        observed_health: "unknown",
        revision: 4,
      },
    ],
  };
  catalog: Record<string, unknown> | null = {
    schema_version: "1",
    observed_at: "2026-10-09T00:00:00Z",
    templates: [
      {
        template_id: "procurement.purchase-order.create-draft.v1",
        title: "purchase-order create-draft (procurement)",
        description: "Draft a purchase order for review.",
        input_intent: "free_text",
        availability: "available",
        unavailable_reason: null,
        required_capabilities: ["procurement.purchase-order.create-draft.v1"],
        bounded_context: "procurement",
      },
      {
        template_id: "procurement.purchase-order.amend.v1",
        title: "purchase-order amend (procurement)",
        description: "Amend an existing purchase order.",
        input_intent: "free_text",
        availability: "unavailable",
        unavailable_reason: "no_usable_connection",
        required_capabilities: ["procurement.purchase-order.amend.v1"],
        bounded_context: "procurement",
      },
    ],
  };
  /** Status used when a discovery response is null; 404 means "not provided". */
  discoveryStatus = 404;
  /** Evidence bundle served by GET /evidence; override to script missing provenance. */
  evidence: Record<string, unknown> = { schema: "e-agent-evidence-v1" };
  createRuns = 0;
  /**
   * `GET /v1/me/features` (ADR 0023 §10). `off` by default, so every per-run spec runs
   * today's path; `null` makes the route answer FastAPI's own 404 (an older server).
   */
  features: FeatureMode | null = "off";
  /** False makes every conversation route "not mounted": a plain 404, or 405 for a POST. */
  conversationRoutesMounted = true;
  /** The run's conversation, once a message started it there; null is an unlinked run. */
  runConversation: string | null = null;
  /** Rows of `GET /v1/conversations`, newest first, as the server orders them. */
  conversationList: ConversationSummary[] = [];
  /** Set to a hint to refuse the next messages with `CONFLICT` (ADR 0023 §4). */
  refuseMessages: string | null = null;
  readonly conversations = new Set<string>();
  readonly messages: { conversationId: string; body: Record<string, unknown>; key: string | undefined }[] =
    [];
  snapshotReads = 0;
  streamOpens = 0;
  /** Max events per stream response; the response then ends (a dropped stream). */
  chunk = 3;
  /** Re-send this many already-delivered events at the start of each response. */
  overlap = 1;

  emit(type: string, payload: Record<string, unknown> = {}): void {
    const sequence = this.events.length + 1;
    this.events.push({
      event_id: `evt-${sequence}`,
      tenant_id: "tenant",
      run_id: RUN_ID,
      sequence,
      type: type as RunEvent["type"],
      occurred_at: new Date().toISOString(),
      payload,
      schema_version: "1",
    });
  }

  /** A run waiting for approval, with the standard preceding events. */
  waitingForApproval(p: ApprovalPresentation = presentation()): this {
    this.emit("run.created", { task: "restock" });
    this.emit("run.state_changed", { from: "CREATED", to: "RUNNING" });
    this.emit("read.recorded", { contract_id: "procurement.demand.read.v1" });
    this.emit("proposal.created", { contract_id: p.contract_id });
    this.emit("validation.completed", { status: "PASS" });
    this.emit("approval.requested", { digest: p.digest });
    this.emit("run.state_changed", { from: "RUNNING", to: "WAITING_APPROVAL" });
    this.state = "WAITING_APPROVAL";
    this.pending = p;
    return this;
  }

  emitText(text: string, reset = false): void {
    this.textFrames.push({
      stream_id: "public-stream",
      message_id: "public-message",
      offset: this.textFrames.length + 1,
      text,
      reset,
    });
  }

  snapshot(): RunSnapshot {
    return {
      run: {
        run_id: RUN_ID,
        tenant_id: "tenant",
        requester_id: "operator",
        task: "restock",
        state: this.state,
        revision: this.pending?.run_revision ?? 1,
        logical_operation_id: "op-1",
        created_at: "2026-10-06T00:00:00Z",
        reason: null,
        conversation_id: this.runConversation,
      },
      latest_sequence: this.events.length,
      actions: [],
      pending_approval: this.state === "WAITING_APPROVAL" ? this.pending : null,
    };
  }

  conversationSnapshot(conversationId: string): ConversationSnapshot {
    const runs =
      this.runConversation === conversationId
        ? [
            {
              run_id: RUN_ID,
              task: "restock",
              state: this.state,
              reason_code: null,
              revision: this.pending?.run_revision ?? 1,
              created_at: "2026-10-06T00:00:00Z",
            },
          ]
        : [];
    return {
      conversation: {
        conversation_id: conversationId,
        tenant_id: "tenant",
        owner_id: "operator",
        revision: runs.length,
        created_at: "2026-10-06T00:00:00Z",
        updated_at: "2026-10-06T00:00:00Z",
      },
      runs,
    };
  }

  async install(page: Page): Promise<void> {
    await page.route("**/v1/**", route => this.handle(route));
  }

  private json(route: Route, body: unknown, status = 200): Promise<void> {
    return route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
  }

  private async handle(route: Route): Promise<void> {
    const req = route.request();
    const url = new URL(req.url());
    const path = url.pathname;
    const method = req.method();
    if (method === "POST" && path === "/v1/local/session") {
      return this.json(route, { csrf_token: "csrf-test", principal: "operator", tenant: "tenant" });
    }
    if (method === "POST" && path === "/v1/runs") {
      this.createRuns += 1;
      return this.json(route, { run_id: RUN_ID, created: this.createRuns === 1 }, 202);
    }
    if (method === "GET" && path === "/v1/me/features") {
      return this.features
        ? this.json(route, { conversations: this.features })
        : this.json(route, { detail: "Not Found" }, 404);
    }
    if (path === "/v1/conversations" || path.startsWith("/v1/conversations/")) {
      return this.handleConversation(route, method, path);
    }
    if (method === "GET" && path === "/v1/me/connections") {
      return this.connections
        ? this.json(route, this.connections)
        : this.json(route, { code: "NOT_FOUND", message: "not found" }, this.discoveryStatus);
    }
    if (method === "GET" && path === "/v1/me/task-catalog") {
      return this.catalog
        ? this.json(route, this.catalog)
        : this.json(route, { code: "NOT_FOUND", message: "not found" }, this.discoveryStatus);
    }
    const m = /^\/v1\/runs\/([^/]+)(\/.*)?$/.exec(path);
    if (!m || m[1] !== RUN_ID) return this.json(route, { code: "NOT_FOUND", message: "not found" }, 404);
    const sub = m[2] ?? "";
    if (method === "GET" && sub === "") {
      this.snapshotReads += 1;
      return this.json(route, this.snapshot());
    }
    if (method === "GET" && sub === "/events") {
      const after = Number(url.searchParams.get("after_sequence") ?? "0");
      return this.json(
        route,
        this.events.filter(e => e.sequence > after),
      );
    }
    if (method === "GET" && sub === "/stream") {
      this.streamOpens += 1;
      const header = Number(req.headers()["last-event-id"] ?? "0");
      const after = Math.max(header, Number(url.searchParams.get("after_sequence") ?? "0"));
      const from = Math.max(0, after - this.overlap);
      const batch = this.events.filter(e => e.sequence > from).slice(0, this.chunk + this.overlap);
      let body = "retry: 150\n\n";
      for (const e of batch) body += `event: run_event\nid: ${e.sequence}\ndata: ${JSON.stringify(e)}\n\n`;
      for (const frame of this.textFrames) body += `event: text_delta\ndata: ${JSON.stringify(frame)}\n\n`;
      const delivered = batch.at(-1)?.sequence ?? after;
      if (["SUCCEEDED", "FAILED", "CANCELLED"].includes(this.state) && delivered >= this.events.length) {
        body += `event: end\ndata: ${JSON.stringify({ state: this.state })}\n\n`;
      }
      return route.fulfill({ status: 200, contentType: "text/event-stream", body });
    }
    if (method === "POST" && sub === "/inputs") {
      this.inputs.push(req.postDataJSON() as Record<string, unknown>);
      this.state = "RUNNING";
      this.emit("input.received", { text: "customer:acme" });
      this.emit("run.state_changed", { from: "WAITING_INPUT", to: "RUNNING" });
      return this.json(route, { status: "accepted" }, 202);
    }
    if (method === "POST" && sub === "/approvals") {
      this.decisions.push(req.postDataJSON() as Record<string, unknown>);
      return this.json(route, { status: "accepted" }, 202);
    }
    if (method === "GET" && sub === "/approvals/pending") {
      return this.pending
        ? this.json(route, this.pending)
        : this.json(route, { code: "NOT_FOUND", message: "none" }, 404);
    }
    if (method === "GET" && sub === "/evidence") return this.json(route, this.evidence);
    return this.json(route, { code: "NOT_FOUND", message: "not found" }, 404);
  }

  /** The conversation routes of 4d.4, with the server's envelope on every e-agent error. */
  private async handleConversation(route: Route, method: string, path: string): Promise<void> {
    const req = route.request();
    if (!this.conversationRoutesMounted) {
      // An older server: FastAPI's own 404, or the static mount's plain-text 405 for a POST.
      return method === "POST"
        ? route.fulfill({ status: 405, contentType: "text/plain", body: "Method Not Allowed" })
        : this.json(route, { detail: "Not Found" }, 404);
    }
    const envelope = (status: number, code: string, message: string) =>
      this.json(route, { code, message, correlation_id: "corr-conformance" }, status);
    if (this.features === "off") return envelope(404, "NOT_FOUND", "conversations are off");
    if (method === "POST" && path === "/v1/conversations") {
      this.conversations.add(CONVERSATION_ID);
      return this.json(route, { conversation_id: CONVERSATION_ID }, 201);
    }
    if (method === "GET" && path === "/v1/conversations") {
      return this.json(route, { items: this.conversationList, next_after: null });
    }
    const m = /^\/v1\/conversations\/([^/]+)(\/messages)?$/.exec(path);
    const conversationId = m?.[1] ? decodeURIComponent(m[1]) : null;
    if (!m || !conversationId || !this.conversations.has(conversationId))
      return envelope(404, "NOT_FOUND", "not found");
    if (method === "GET" && !m[2]) return this.json(route, this.conversationSnapshot(conversationId));
    if (method !== "POST" || !m[2]) return envelope(404, "NOT_FOUND", "not found");
    const body = req.postDataJSON() as Record<string, unknown>;
    this.messages.push({ conversationId, body, key: req.headers()["idempotency-key"] });
    if (this.refuseMessages) return envelope(409, "CONFLICT", this.refuseMessages);
    if (body["reply_to"]) {
      this.state = "RUNNING";
      this.emit("input.received", { input: String(body["text"] ?? "") });
      this.emit("run.state_changed", { from: "WAITING_INPUT", to: "RUNNING" });
      return this.json(route, { route: "answer", run_id: RUN_ID }, 202);
    }
    this.createRuns += 1;
    this.runConversation = conversationId;
    return this.json(route, { route: "start", run_id: RUN_ID }, 202);
  }
}
