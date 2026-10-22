/**
 * Projection safety: a missing value stays unknown, an unrecognised bundle is
 * unsupported rather than best-effort, and no check or result is promoted.
 */
import { describe, expect, it } from "vitest";
import { EVIDENCE_SCHEMA, selectEvidence } from "../src/selectors/evidence.ts";
import { translate } from "../src/i18n.ts";
import { hasResult, selectOutcome } from "../src/selectors/outcome.ts";
import {
  emptyRunView,
  reduceRunView,
  selectConversation,
  selectPendingReply,
  selectTimeline,
  type RunView,
} from "../src/store.ts";
import type { RunEvent, RunRecord } from "@e-agent/client";

function run(state: RunRecord["state"], reason: string | null = null): RunRecord {
  return {
    run_id: "run-1",
    tenant_id: "t",
    requester_id: "u",
    task: "restock",
    state,
    revision: 1,
    logical_operation_id: "op-1",
    created_at: "2026-10-09T00:00:00Z",
    reason,
  };
}

function event(sequence: number, type: string, payload: Record<string, unknown>): RunEvent {
  return {
    event_id: `e${sequence}`,
    tenant_id: "t",
    run_id: "run-1",
    sequence,
    type: type as RunEvent["type"],
    occurred_at: "2026-10-09T00:00:00Z",
    payload,
    schema_version: "1",
  };
}

function viewWith(state: RunRecord["state"], events: RunEvent[] = []): RunView {
  const base = reduceRunView(emptyRunView, {
    type: "snapshot",
    snapshot: { run: run(state), latest_sequence: events.length, actions: [], pending_approval: null },
  });
  return reduceRunView(base, { type: "events", events });
}

describe("evidence projection", () => {
  it("reports an absent bundle and an unrecognised schema distinctly", () => {
    expect(selectEvidence(null)).toEqual({ kind: "absent" });
    expect(selectEvidence({ schema: "something-else" })).toEqual({
      kind: "unsupported",
      schema: "something-else",
    });
    expect(selectEvidence({})).toEqual({ kind: "unsupported", schema: null });
  });

  it("keeps missing provenance unknown instead of inventing it", () => {
    const view = selectEvidence({
      schema: EVIDENCE_SCHEMA,
      actions: [
        { approved_facts: [{ contract_id: "c.read.v1", data: { a: 1 }, evidence: { evidence_id: "ev-1" } }] },
      ],
    });
    expect(view.kind).toBe("ready");
    if (view.kind !== "ready") return;
    const source = view.sources[0]!;
    expect(source).toMatchObject({
      evidenceId: "ev-1",
      source: null,
      locator: null,
      observedAt: null,
      revision: null,
      completeness: "unknown",
    });
    expect(source.data).toEqual([{ path: "a", value: "1" }]);
  });

  it("rejects an unknown completeness value rather than trusting it", () => {
    const view = selectEvidence({
      schema: EVIDENCE_SCHEMA,
      actions: [{ approved_facts: [{ evidence: { evidence_id: "ev-1", completeness: "totally-fine" } }] }],
    });
    expect(view.kind === "ready" && view.sources[0]!.completeness).toBe("unknown");
  });

  it("drops facts without an evidence id and collapses repeats", () => {
    const view = selectEvidence({
      schema: EVIDENCE_SCHEMA,
      actions: [
        { approved_facts: [{ evidence: {} }, { evidence: { evidence_id: "ev-1", source: "first" } }] },
        { approved_facts: [{ evidence: { evidence_id: "ev-1", source: "second" } }] },
      ],
    });
    expect(view.kind === "ready" && view.sources.map(s => s.source)).toEqual(["first"]);
  });

  it("tolerates malformed containers without throwing", () => {
    expect(selectEvidence({ schema: EVIDENCE_SCHEMA, actions: "nope" })).toEqual({
      kind: "ready",
      schema: EVIDENCE_SCHEMA,
      generatedAt: null,
      environment: null,
      classification: null,
      rulesEvaluated: [],
      sources: [],
    });
  });
});

describe("outcome projection", () => {
  it("separates checking, unresolved, verified, failed and cancelled", () => {
    expect(selectOutcome(viewWith("VERIFYING")).status).toBe("checking");
    expect(selectOutcome(viewWith("NEEDS_RECONCILIATION")).status).toBe("unresolved");
    expect(selectOutcome(viewWith("SUCCEEDED")).status).toBe("verified");
    expect(selectOutcome(viewWith("FAILED")).status).toBe("failed");
    expect(selectOutcome(viewWith("CANCELLED")).status).toBe("cancelled");
    expect(selectOutcome(viewWith("RUNNING")).status).toBe("none");
    expect(hasResult("RUNNING")).toBe(false);
    expect(hasResult("NEEDS_RECONCILIATION")).toBe(true);
  });

  it("never reports a grounded run as verified (PR-19, ADR 0033)", () => {
    const view = viewWith("SUCCEEDED");
    const grounded = { ...view, run: { ...view.run!, reason_code: "grounded" as const } };
    const outcome = selectOutcome(grounded);
    expect(outcome.status).toBe("grounded");
    expect(outcome.status).not.toBe("verified");
    expect(outcome.reasonCode).toBe("grounded");
    expect(outcome.labelKey).toBe("status.SUCCEEDED.grounded");
    expect(translate("en", outcome.labelKey)).toBe("Completed · grounded, not verified");
    expect(translate("vi", outcome.labelKey)).not.toBe(translate("vi", "status.SUCCEEDED"));
    const verified = { ...view, run: { ...view.run!, reason_code: "verified" as const } };
    expect(selectOutcome(verified).status).toBe("verified");
    expect(selectOutcome(verified).labelKey).toBe("status.SUCCEEDED");
    const failed = viewWith("FAILED");
    const failedGrounded = { ...failed, run: { ...failed.run!, reason_code: "grounded" as const } };
    expect(selectOutcome(failedGrounded).status).toBe("failed");
  });

  it("keeps an unresolved effect unresolved and never verified", () => {
    const outcome = selectOutcome(viewWith("NEEDS_RECONCILIATION"));
    expect(outcome.unresolved).toBe(true);
    expect(outcome.verified).toEqual([]);
  });

  it("marks a check without a recorded verdict unknown, not failed", () => {
    const view = viewWith("SUCCEEDED", [
      event(1, "outcome.reported", {
        status: "VERIFIED",
        checks: [{ name: "quantity" }, { name: "price", passed: false, observed: "99" }, "nonsense"],
      }),
    ]);
    const checks = selectOutcome(view).checks;
    expect(checks.map(c => c.passed)).toEqual([null, false, null]);
    expect(checks[0]!.observed).toBeNull();
    expect(checks[1]!.observed).toBe("99");
  });

  it("uses only the latest outcome report", () => {
    const view = viewWith("SUCCEEDED", [
      event(1, "outcome.reported", { checks: [{ name: "first", passed: true }] }),
      event(2, "outcome.reported", { checks: [{ name: "second", passed: true }] }),
    ]);
    expect(selectOutcome(view).checks.map(c => c.name)).toEqual(["second"]);
  });
});

describe("conversation item kind (ADR 0022)", () => {
  const kindOf = (payload: Record<string, unknown>) =>
    selectConversation(viewWith("WAITING_INPUT", [event(1, "input.requested", payload)]))[0]?.kind;

  it("marks a reply, and treats a clarification or an old row without kind as a message", () => {
    expect(kindOf({ question: "Hello!", kind: "reply" })).toBe("reply");
    expect(kindOf({ question: "Which one?", kind: "clarification" })).toBe("message");
    expect(kindOf({ question: "Which one?" })).toBe("message");
    expect(kindOf({ question: "x", kind: "something-new" })).toBe("message");
  });

  it("marks only the first reply of a thread", () => {
    const view = viewWith("WAITING_INPUT", [
      event(1, "input.requested", { question: "Hello!", kind: "reply" }),
      event(2, "input.received", { input: "hi" }),
      event(3, "input.requested", { question: "Hi again!", kind: "reply" }),
      event(4, "input.requested", { question: "Which one?", kind: "clarification" }),
    ]);
    expect(selectConversation(view).map(m => m.firstReply)).toEqual([true, false, false, false]);
  });

  it("marks only the pending question and flags a pending reply for the status label", () => {
    const view = viewWith("WAITING_INPUT", [
      event(1, "input.requested", { question: "Hello!", kind: "reply" }),
    ]);
    expect(selectConversation(view)[0]).toMatchObject({ kind: "reply", pending: true });
    expect(selectPendingReply(view)).toBe(true);
    const old = viewWith("WAITING_INPUT", [event(1, "input.requested", { question: "Which?" })]);
    expect(selectPendingReply(old)).toBe(false);
  });
});

describe("a recorded question replaces its streamed text (plan Task 5)", () => {
  for (const kind of ["reply", "clarification", undefined]) {
    it(`clears streaming text on input.requested (${kind ?? "old row"})`, () => {
      let view = viewWith("RUNNING");
      view = reduceRunView(view, {
        type: "text",
        frame: { stream_id: "s", message_id: "m", offset: 1, text: "Hello! What next?", reset: true },
      });
      expect(view.streamingText).toBe("Hello! What next?");
      view = reduceRunView(view, {
        type: "events",
        events: [event(1, "input.requested", { question: "Hello! What next?", ...(kind ? { kind } : {}) })],
      });
      expect(view.streamingText).toBe("");
      expect(selectConversation(view).filter(m => m.role === "agent")).toHaveLength(1);
    });
  }

  it("does not restore stream text from a snapshot of a waiting run", () => {
    let view = viewWith("RUNNING");
    view = reduceRunView(view, {
      type: "text",
      frame: { stream_id: "s", message_id: "m", offset: 1, text: "stale", reset: true },
    });
    view = reduceRunView(view, {
      type: "snapshot",
      snapshot: { run: run("WAITING_INPUT"), latest_sequence: 0, actions: [], pending_approval: null },
    });
    expect(view.streamingText).toBe("");
  });
});

describe("timeline transitions", () => {
  it("renders a legacy state row as unknown → RUNNING", () => {
    const [item] = selectTimeline(viewWith("RUNNING", [event(1, "run.state_changed", { state: "RUNNING" })]));
    expect(item?.detail).toBe("unknown → RUNNING");
    expect(item?.transition).toEqual({ from: "unknown", to: "RUNNING" });
  });

  it("never prints undefined in a transition", () => {
    const items = selectTimeline(
      viewWith("RUNNING", [
        event(1, "run.state_changed", {}),
        event(2, "run.state_changed", { state: "RUNNING" }),
        event(3, "run.state_changed", { from: "CREATED", to: "RUNNING" }),
      ]),
    );
    for (const item of items) {
      expect(item.detail).not.toContain("undefined");
      expect(item.transition?.from).not.toBe("undefined");
      expect(item.transition?.to).not.toBe("undefined");
    }
    expect(items[2]?.detail).toBe("CREATED → RUNNING");
    expect(translate("en", "status.unknown")).toBe("Unknown");
    expect(translate("vi", "status.unknown")).not.toBe("status.unknown");
  });
});

describe("F-5 timeline reply turn", () => {
  it("F-5 marks a WAITING_INPUT change after a reply as the user's turn, both ways", () => {
    const items = selectTimeline(
      viewWith("RUNNING", [
        event(1, "input.requested", { question: "Hello! What next?", kind: "reply" }),
        event(2, "run.state_changed", { from: "RUNNING", to: "WAITING_INPUT" }),
        event(3, "input.received", { input: "hi" }),
        event(4, "run.state_changed", { from: "WAITING_INPUT", to: "RUNNING" }),
        event(5, "input.requested", { question: "Which supplier?", kind: "clarification" }),
        event(6, "run.state_changed", { from: "RUNNING", to: "WAITING_INPUT" }),
        event(7, "run.state_changed", { from: "WAITING_INPUT", to: "RUNNING" }),
      ]),
    );
    const transitions = items.flatMap(i => (i.transition ? [i.transition] : []));
    expect(transitions[0]).toMatchObject({ to: "WAITING_INPUT", toReply: true });
    expect(transitions[1]).toMatchObject({ from: "WAITING_INPUT", fromReply: true });
    expect(transitions[2]?.toReply).toBeFalsy();
    expect(transitions[3]?.fromReply).toBeFalsy();
  });
});
