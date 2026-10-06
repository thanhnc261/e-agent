/**
 * Scriptable stand-in for the e-agent API v1, installed with page.route. Every
 * stream response ends after a few events, so UIs must resume via Last-Event-ID or
 * after_sequence, and some responses overlap on purpose to exercise dedup.
 */
import type { Page, Route } from "@playwright/test";
import type { ApprovalPresentation, RunEvent, RunSnapshot } from "@e-agent/client";
import { canonicalize } from "@e-agent/ui-core";
import { createHash } from "node:crypto";

export const RUN_ID = "run-conformance-1";

export function digestOf(value: unknown): string {
  return `jcs-sha256-v1:${createHash("sha256").update(canonicalize(value), "utf8").digest("hex")}`;
}

export function presentation(overrides: Partial<ApprovalPresentation> = {}, quantity = "40"): ApprovalPresentation {
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
    material_fields: [
      { path: "quantity", value: quantity, previous_value: "7", changed: true },
      { path: "supplier_ref", value: "supplier:approved-co", previous_value: "supplier:approved-co", changed: false },
      { path: "unit_price", value: "100", previous_value: "100", changed: false },
    ],
    findings: [
      { rule_id: "PR-001", rule_version: "1", status: "PASS", message: "satisfied", evidence_ids: [] },
      { rule_id: "PR-004", rule_version: "1", status: "UNKNOWN", message: "fact missing", evidence_ids: [] },
    ],
    ...overrides,
  };
}

export class MockApi {
  events: RunEvent[] = [];
  state: RunSnapshot["run"]["state"] = "RUNNING";
  pending: ApprovalPresentation | null = null;
  readonly decisions: Record<string, unknown>[] = [];
  createRuns = 0;
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
      },
      latest_sequence: this.events.length,
      actions: [],
      pending_approval: this.state === "WAITING_APPROVAL" ? this.pending : null,
    };
  }

  async install(page: Page): Promise<void> {
    await page.route("**/v1/**", (route) => this.handle(route));
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
    const m = /^\/v1\/runs\/([^/]+)(\/.*)?$/.exec(path);
    if (!m || m[1] !== RUN_ID) return this.json(route, { code: "NOT_FOUND", message: "not found" }, 404);
    const sub = m[2] ?? "";
    if (method === "GET" && sub === "") {
      this.snapshotReads += 1;
      return this.json(route, this.snapshot());
    }
    if (method === "GET" && sub === "/events") {
      const after = Number(url.searchParams.get("after_sequence") ?? "0");
      return this.json(route, this.events.filter((e) => e.sequence > after));
    }
    if (method === "GET" && sub === "/stream") {
      this.streamOpens += 1;
      const header = Number(req.headers()["last-event-id"] ?? "0");
      const after = Math.max(header, Number(url.searchParams.get("after_sequence") ?? "0"));
      const from = Math.max(0, after - this.overlap);
      const batch = this.events.filter((e) => e.sequence > from).slice(0, this.chunk + this.overlap);
      let body = "retry: 150\n\n";
      for (const e of batch) body += `event: run_event\nid: ${e.sequence}\ndata: ${JSON.stringify(e)}\n\n`;
      const delivered = batch.at(-1)?.sequence ?? after;
      if (["SUCCEEDED", "FAILED", "CANCELLED"].includes(this.state) && delivered >= this.events.length) {
        body += `event: end\ndata: ${JSON.stringify({ state: this.state })}\n\n`;
      }
      return route.fulfill({ status: 200, contentType: "text/event-stream", body });
    }
    if (method === "POST" && sub === "/approvals") {
      this.decisions.push(req.postDataJSON() as Record<string, unknown>);
      return this.json(route, { status: "accepted" }, 202);
    }
    if (method === "GET" && sub === "/approvals/pending") {
      return this.pending ? this.json(route, this.pending) : this.json(route, { code: "NOT_FOUND", message: "none" }, 404);
    }
    if (method === "GET" && sub === "/evidence") return this.json(route, { schema: "e-agent-evidence-v1" });
    return this.json(route, { code: "NOT_FOUND", message: "not found" }, 404);
  }
}
