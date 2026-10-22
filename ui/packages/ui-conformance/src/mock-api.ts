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
  RunState,
  RunSnapshot,
  TextFrame,
} from "@e-agent/client";
import { canonicalize } from "@e-agent/ui-core";
import { createHash } from "node:crypto";

export const RUN_ID = "run-conformance-1";
export const CONVERSATION_ID = "conv-conformance-1";
/** The earlier run of `twoRunThread()`, and the answer it ended with. */
export const EARLIER_RUN_ID = "run-conformance-earlier";
export const EARLIER_ANSWER = "Bracket B-12 is short by 40 (sample).";
/** The server's fixed refusal hints (ADR 0023 §4). */
export const HINT_BUSY = "wait, decide the approval, or stop the run";
export const HINT_QUESTION_CHANGED = "the question changed; read it again";

/** A grounded answer's summary (fictional), its one named citation and one digest-only one. */
export const GROUNDED_ANSWER = "grounded.answer.v1";
export const GROUNDED_SUMMARY = "Two orders are late: SO-SAMPLE-7 and SO-SAMPLE-9 (sample).";
export const GROUNDED_EVIDENCE_ID = "ev-orders-sample-1";
export const UNRESOLVED_CITATION_DIGEST = `jcs-sha256-v1:${"a1".repeat(32)}`;
const GROUNDED_CITATIONS = [
  {
    evidence_id: GROUNDED_EVIDENCE_ID,
    pointer: "/orders/0/ref",
    value_digest: `jcs-sha256-v1:${"c3".repeat(32)}`,
  },
  {
    evidence_id_digest: UNRESOLVED_CITATION_DIGEST,
    pointer_digest: `jcs-sha256-v1:${"b2".repeat(32)}`,
    value_digest: `jcs-sha256-v1:${"d4".repeat(32)}`,
  },
];

/**
 * The evidence bundle of a `GROUNDED` run as `kernel/evidence.py` builds it: no action, the
 * `grounded_answer` key (summary `unverified`, each citation `grounded`) and the `explanation`
 * key (ADR 0033 §6) with the read's source and the grounded outcome.
 */
export function groundedEvidence(
  run: RunSnapshot["run"],
  summary: string,
  events: RunEvent[],
): Record<string, unknown> {
  return {
    schema: "e-agent-evidence-v1",
    generated_at: "2026-10-22T00:00:00Z",
    environment: "fixture",
    run,
    modes: { grounded_answers: "on", conversations: "on" },
    actions: [],
    approvals: [],
    receipts: [],
    outcomes: [],
    events,
    grounded_answer: {
      contract_id: GROUNDED_ANSWER,
      summary: { text: summary, label: "unverified" },
      citations: GROUNDED_CITATIONS.map(c => ({ ...c, label: "grounded" })),
    },
    explanation: {
      completeness: "known",
      run: {
        run_id: run.run_id,
        goal: run.task,
        task_ref: null,
        task_ref_state: "none",
        requester_id: run.requester_id,
        driver_id: "fixture",
        state: "SUCCEEDED",
        reason_code: "grounded",
      },
      sources: [
        {
          evidence_id: GROUNDED_EVIDENCE_ID,
          contract_id: "sales.order.read.v1",
          revision: "rev-17",
          label: "provider_read",
        },
      ],
      validation: { stages: [], open_findings: [], rules_evaluated: [], input_requests: [] },
      proposals: [],
      approvals: [],
      receipts: [],
      outcomes: [
        { action_id: null, status: "succeeded", event_id: null, step_id: null, label: "grounded_answer" },
      ],
    },
  };
}

/**
 * The evidence bundle of a conversation run pinned `mode`, with the `conversation` section as
 * `kernel/evidence.py` builds it (ADR 0023 §12): ids, the pinned mode and counts, never text.
 * Its `carried_run_ids` are those of the run's `conversation.context_carried` events.
 */
export function conversationEvidence(
  run: RunSnapshot["run"],
  mode: "off" | "shadow" | "on",
  events: RunEvent[],
): Record<string, unknown> {
  const carried = events.flatMap(e => {
    const ids = e.type === "conversation.context_carried" ? e.payload?.["carried_run_ids"] : null;
    return Array.isArray(ids) ? ids.filter((id): id is string => typeof id === "string") : [];
  });
  return {
    schema: "e-agent-evidence-v1",
    generated_at: "2026-10-22T00:00:00Z",
    environment: "fixture",
    run,
    modes: { conversations: mode },
    actions: [],
    approvals: [],
    receipts: [],
    outcomes: [],
    events,
    conversation: {
      conversation_id: run.conversation_id ?? null,
      mode,
      carried_run_ids: carried,
      compared: { start: 0, refuse: 0 },
    },
  };
}

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

/**
 * A proposal with ten material fields, as tall as the fixture server's card (G-D 4.U4).
 * The arguments and the shown terms match, so the digest check passes and Approve is enabled.
 */
export function tenFieldPresentation(): ApprovalPresentation {
  const args: Record<string, string> = {
    quantity: "40",
    supplier_ref: "supplier:approved-co",
    unit_price: "100",
    currency: "USD",
    delivery_date: "2026-11-02",
    warehouse_ref: "warehouse:main",
    payment_terms: "net-30",
    incoterm: "FCA",
    buyer_ref: "buyer:sample",
    note: "Sample restock (sample)",
  };
  const canonical = { contract_id: "procurement.purchase-order.create-draft.v1", arguments: args };
  return presentation({
    canonical_proposal: canonical,
    digest: digestOf(canonical),
    material_fields: Object.entries(args).map(([path, value]) => ({
      path,
      value,
      previous_value: value,
      changed: false,
    })),
  });
}

/**
 * One run the mock serves. The primary run (`RUN_ID`) is the one every per-run spec
 * scripts; a conversation can hold more (Task 4e.4: several runs per thread).
 */
export interface MockRun {
  runId: string;
  task: string;
  state: RunState;
  events: RunEvent[];
  pending: ApprovalPresentation | null;
  /** The run's conversation; null is an unlinked (legacy) run. */
  conversationId: string | null;
  createdAt: string;
  reasonCode: string | null;
}

export class MockApi {
  /** Every run, by id. The primary run is always present. */
  readonly runs = new Map<string, MockRun>([
    [
      RUN_ID,
      {
        runId: RUN_ID,
        task: "restock",
        state: "RUNNING",
        events: [],
        pending: null,
        conversationId: null,
        createdAt: "2026-10-06T00:00:00Z",
        reasonCode: null,
      },
    ],
  ]);
  /** The run `emit`, `events`, `state` and `pending` act on; a message start moves it. */
  current = RUN_ID;

  run(runId: string = this.current): MockRun {
    const run = this.runs.get(runId);
    if (!run) throw new Error(`mock has no run ${runId}`);
    return run;
  }

  get events(): RunEvent[] {
    return this.run().events;
  }
  set events(events: RunEvent[]) {
    this.run().events = events;
  }
  get state(): RunState {
    return this.run().state;
  }
  set state(state: RunState) {
    this.run().state = state;
  }
  get pending(): ApprovalPresentation | null {
    return this.run().pending;
  }
  set pending(pending: ApprovalPresentation | null) {
    this.run().pending = pending;
  }
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
  /** `GET /v1/runs/{id}/evidence` calls. */
  evidenceReads = 0;
  /** `POST /v1/runs` calls only (today's path). Message starts are counted apart. */
  createRuns = 0;
  /** Messages the conversation route answered with `route: start` (a new run in a thread). */
  messageStarts = 0;
  /**
   * `GET /v1/me/features` (ADR 0023 §10). `off` by default, so every per-run spec runs
   * today's path; `null` makes the route answer FastAPI's own 404 (an older server).
   */
  features: FeatureMode | null = "off";
  /** False makes every conversation route "not mounted": a plain 404, or 405 for a POST. */
  conversationRoutesMounted = true;
  /** The current run's conversation, once a message started it there; null is unlinked. */
  get runConversation(): string | null {
    return this.run().conversationId;
  }
  set runConversation(conversationId: string | null) {
    this.run().conversationId = conversationId;
  }
  /**
   * Rows of `GET /v1/conversations`, newest first. `null` (the default) derives them from
   * the conversations and their runs, as the server would; a list pins them.
   */
  conversationList: ConversationSummary[] | null = null;
  /** Set to a hint to refuse the next messages with `CONFLICT` (ADR 0023 §4). */
  refuseMessages: string | null = null;
  readonly conversations = new Set<string>();
  readonly messages: { conversationId: string; body: Record<string, unknown>; key: string | undefined }[] =
    [];
  /** Scripts a run a message started, after its `run.created` and `RUNNING` events. */
  onStart: ((run: MockRun) => void) | null = null;
  snapshotReads = 0;
  streamOpens = 0;
  /** Max events per stream response; the response then ends (a dropped stream). */
  chunk = 3;
  /** Re-send this many already-delivered events at the start of each response. */
  overlap = 1;

  emit(type: string, payload: Record<string, unknown> = {}, runId: string = this.current): void {
    const run = this.run(runId);
    const sequence = run.events.length + 1;
    run.events.push({
      event_id: `${runId}-evt-${sequence}`,
      tenant_id: "tenant",
      run_id: runId,
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

  /**
   * Add a run to the mock, for example an earlier run of a conversation. It does not
   * become the current run.
   */
  addRun(run: Partial<MockRun> & { runId: string; task: string }): MockRun {
    const added: MockRun = {
      state: "RUNNING",
      events: [],
      pending: null,
      conversationId: null,
      createdAt: "2026-10-05T00:00:00Z",
      reasonCode: null,
      ...run,
    };
    this.runs.set(added.runId, added);
    if (added.conversationId) this.conversations.add(added.conversationId);
    return added;
  }

  /** Record a run's end with its final message, a verified outcome and the terminal state. */
  finish(runId: string = this.current, text = "Done.", state: RunState = "SUCCEEDED"): this {
    const run = this.run(runId);
    const from = run.state;
    this.emit("message.final", { text }, runId);
    if (state === "SUCCEEDED") this.emit("outcome.reported", { status: "VERIFIED", checks: [] }, runId);
    this.emit("run.terminal", { state }, runId);
    this.emit("run.state_changed", { from, to: state }, runId);
    run.state = state;
    run.pending = null;
    return this;
  }

  /**
   * A conversation of two runs: an earlier run that ended verified, then the primary run,
   * which the caller scripts (for example with `waitingForApproval`). Returns the earlier run.
   */
  twoRunThread(conversationId = CONVERSATION_ID): MockRun {
    const earlier = this.addRun({
      runId: EARLIER_RUN_ID,
      task: "which products are short?",
      conversationId,
      createdAt: "2026-10-05T00:00:00Z",
    });
    this.emit("run.created", { task: earlier.task }, earlier.runId);
    this.emit("run.state_changed", { from: "CREATED", to: "RUNNING" }, earlier.runId);
    this.emit(
      "read.recorded",
      { contract_id: "procurement.demand.read.v1", connection_id: "conn-1" },
      earlier.runId,
    );
    this.finish(earlier.runId, EARLIER_ANSWER);
    const primary = this.run(RUN_ID);
    primary.task = "draft a PO for it";
    primary.conversationId = conversationId;
    this.conversations.add(conversationId);
    return earlier;
  }

  /**
   * Pin `runId` to `conversations: mode` and record that it received `carriedRunIds` as hints:
   * the kernel's `conversation.context_carried` event, recorded only in `on` (ADR 0023 §6, §9),
   * and the evidence bundle's `conversation` section built from it (`conversationEvidence`).
   */
  carryContext(
    carriedRunIds: string[],
    mode: "off" | "shadow" | "on" = "on",
    runId: string = this.current,
  ): this {
    const run = this.run(runId);
    if (mode === "on" && carriedRunIds.length > 0)
      this.emit(
        "conversation.context_carried",
        {
          conversation_id: run.conversationId,
          carried_run_ids: carriedRunIds,
          carried_digest: digestOf(carriedRunIds),
        },
        runId,
      );
    this.evidence = conversationEvidence(this.snapshot(runId).run, mode, run.events);
    return this;
  }

  /**
   * Record a run's `GROUNDED` end (ADR 0033 §3): one read, then the kernel's `message.final`
   * with the answer contract and the at-rest citations, and the terminal state with reason
   * code `grounded`. No outcome report: a grounded answer is never verified. The evidence
   * bundle is set to the server's shape for that run (`groundedEvidence`).
   */
  groundedEnd(runId: string = this.current, text = GROUNDED_SUMMARY): this {
    const run = this.run(runId);
    const from = run.state;
    this.emit("read.recorded", { contract_id: "sales.order.read.v1", connection_id: "conn-1" }, runId);
    this.emit("message.final", { text, contract_id: GROUNDED_ANSWER, citations: GROUNDED_CITATIONS }, runId);
    this.emit("run.terminal", { state: "SUCCEEDED", reason_code: "grounded" }, runId);
    this.emit("run.state_changed", { from, to: "SUCCEEDED", reason_code: "grounded" }, runId);
    run.state = "SUCCEEDED";
    run.reasonCode = "grounded";
    run.pending = null;
    this.evidence = groundedEvidence(this.snapshot(runId).run, text, this.run(runId).events);
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

  snapshot(runId: string = this.current): RunSnapshot {
    const run = this.run(runId);
    return {
      run: {
        run_id: run.runId,
        tenant_id: "tenant",
        requester_id: "operator",
        task: run.task,
        state: run.state,
        revision: run.pending?.run_revision ?? 1,
        logical_operation_id: `op-${run.runId}`,
        created_at: run.createdAt,
        reason: null,
        reason_code: run.reasonCode as RunSnapshot["run"]["reason_code"],
        conversation_id: run.conversationId,
      },
      latest_sequence: run.events.length,
      actions: [],
      pending_approval: run.state === "WAITING_APPROVAL" ? run.pending : null,
    };
  }

  /** A conversation's runs, oldest first, as `GET /v1/conversations/{id}` lists them. */
  threadRuns(conversationId: string): MockRun[] {
    return [...this.runs.values()]
      .filter(run => run.conversationId === conversationId)
      .sort((a, b) => a.createdAt.localeCompare(b.createdAt));
  }

  conversationSnapshot(conversationId: string): ConversationSnapshot {
    const runs = this.threadRuns(conversationId).map(run => ({
      run_id: run.runId,
      task: run.task,
      state: run.state,
      reason_code: run.reasonCode as ConversationSnapshot["runs"][number]["reason_code"],
      revision: run.pending?.run_revision ?? 1,
      created_at: run.createdAt,
    }));
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

  /** The derived list: one row per conversation, newest first, titled by its first run. */
  listConversations(): ConversationSummary[] {
    return [...this.conversations]
      .map(conversationId => {
        const runs = this.threadRuns(conversationId);
        const latest = runs.at(-1);
        return {
          conversation_id: conversationId,
          title: runs[0]?.task ?? "",
          latest_state: latest?.state ?? null,
          reply_pending: false,
          updated_at: latest?.createdAt ?? "2026-10-06T00:00:00Z",
        };
      })
      .sort((a, b) => b.updated_at.localeCompare(a.updated_at));
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
    const run = m?.[1] ? this.runs.get(decodeURIComponent(m[1])) : undefined;
    if (!m || !run) return this.json(route, { code: "NOT_FOUND", message: "not found" }, 404);
    const sub = m[2] ?? "";
    if (method === "GET" && sub === "") {
      this.snapshotReads += 1;
      return this.json(route, this.snapshot(run.runId));
    }
    if (method === "GET" && sub === "/events") {
      const after = Number(url.searchParams.get("after_sequence") ?? "0");
      return this.json(
        route,
        run.events.filter(e => e.sequence > after),
      );
    }
    if (method === "GET" && sub === "/stream") {
      this.streamOpens += 1;
      const header = Number(req.headers()["last-event-id"] ?? "0");
      const after = Math.max(header, Number(url.searchParams.get("after_sequence") ?? "0"));
      const from = Math.max(0, after - this.overlap);
      const batch = run.events.filter(e => e.sequence > from).slice(0, this.chunk + this.overlap);
      let body = "retry: 150\n\n";
      for (const e of batch) body += `event: run_event\nid: ${e.sequence}\ndata: ${JSON.stringify(e)}\n\n`;
      if (run.runId === RUN_ID)
        for (const frame of this.textFrames) body += `event: text_delta\ndata: ${JSON.stringify(frame)}\n\n`;
      const delivered = batch.at(-1)?.sequence ?? after;
      if (["SUCCEEDED", "FAILED", "CANCELLED"].includes(run.state) && delivered >= run.events.length) {
        body += `event: end\ndata: ${JSON.stringify({ state: run.state })}\n\n`;
      }
      return route.fulfill({ status: 200, contentType: "text/event-stream", body });
    }
    if (method === "POST" && sub === "/inputs") {
      this.inputs.push(req.postDataJSON() as Record<string, unknown>);
      run.state = "RUNNING";
      this.emit("input.received", { text: "customer:acme" }, run.runId);
      this.emit("run.state_changed", { from: "WAITING_INPUT", to: "RUNNING" }, run.runId);
      return this.json(route, { status: "accepted" }, 202);
    }
    if (method === "POST" && sub === "/approvals") {
      this.decisions.push(req.postDataJSON() as Record<string, unknown>);
      return this.json(route, { status: "accepted" }, 202);
    }
    if (method === "GET" && sub === "/approvals/pending") {
      return run.pending
        ? this.json(route, run.pending)
        : this.json(route, { code: "NOT_FOUND", message: "none" }, 404);
    }
    if (method === "GET" && sub === "/evidence") {
      this.evidenceReads += 1;
      return this.json(route, this.evidence);
    }
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
      return this.json(route, { items: this.conversationList ?? this.listConversations(), next_after: null });
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
    const replyTo = body["reply_to"] as { run_id?: unknown } | null | undefined;
    if (replyTo) {
      const answered = this.runs.get(String(replyTo.run_id)) ?? this.run();
      answered.state = "RUNNING";
      this.emit("input.received", { input: String(body["text"] ?? "") }, answered.runId);
      this.emit("run.state_changed", { from: "WAITING_INPUT", to: "RUNNING" }, answered.runId);
      return this.json(route, { route: "answer", run_id: answered.runId }, 202);
    }
    this.messageStarts += 1;
    const primary = this.run(RUN_ID);
    const linked = [...this.runs.values()].some(r => r.conversationId !== null);
    if (!linked && primary.conversationId === null) {
      // The first start of the session lands on the primary run, as it was scripted.
      primary.conversationId = conversationId;
      if (primary.task === "restock") primary.task = String(body["text"] ?? primary.task);
      this.current = RUN_ID;
      return this.json(route, { route: "start", run_id: RUN_ID }, 202);
    }
    const started = this.addRun({
      runId: `run-conformance-${this.runs.size + 1}`,
      task: String(body["text"] ?? ""),
      conversationId,
      createdAt: `2026-10-07T00:00:${String(this.runs.size).padStart(2, "0")}Z`,
    });
    this.current = started.runId;
    this.emit("run.created", { task: started.task });
    this.emit("run.state_changed", { from: "CREATED", to: "RUNNING" });
    this.onStart?.(started);
    return this.json(route, { route: "start", run_id: started.runId }, 202);
  }
}
