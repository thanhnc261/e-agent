import { describe, expect, it } from "vitest";
import type { FeaturesState } from "../src/controller.ts";
import { translate } from "../src/i18n.ts";
import { emptyRunView, HIDDEN_EVENT_TYPES, reduceRunView, selectConversation, selectTimeline } from "../src/store.ts";
import {
  isConversationsOn,
  selectReadConnections,
  selectRunLine,
  selectStopControl,
  selectThreadShown,
} from "../src/selectors/thread.ts";
import { ev, snapshot } from "./fixtures.ts";

// Phase 3 events (ADR 0031 §5, ADR 0032 §7, §11, §13, ADR 0033 §5), ruled in Task 4e.4.
const PHASE3_HIDDEN = [
  ["context.assembled", { pack_digest: "jcs-sha256-v1:a", counts: {} }],
  ["context.compared", { pack_digest: "jcs-sha256-v1:b", counts: {} }],
  ["context.shadow_failed", { stage: "assemble", message: "The context pack could not be assembled.", turn: 1, acknowledgement: false }],
  ["repeat.compared", { would_short_circuit: false }],
  ["repeat.shadow_failed", { stage: "compare", message: "x" }],
  ["grounding.compared", { citations: { total: 1 } }],
  ["grounding.shadow_failed", { stage: "check", message: "x" }],
] as const;

describe("Phase 3 events in the timeline", () => {
  const base = reduceRunView(emptyRunView, { type: "snapshot", snapshot: snapshot("RUNNING", null) });

  it("hides the Phase 3 records, needs no snapshot and still advances lastSequence", () => {
    for (const [type] of PHASE3_HIDDEN) expect(HIDDEN_EVENT_TYPES.has(type)).toBe(true);
    const events = [
      ev(1, "read.recorded", { contract_id: "procurement.demand.read.v1" }),
      ...PHASE3_HIDDEN.map(([type, payload], i) => ev(i + 2, type, { ...payload })),
    ];
    const v = reduceRunView(base, { type: "events", events });
    expect(v.unsupportedEvents).toBe(0);
    expect(v.needsSnapshot).toBe(false);
    expect(v.lastSequence).toBe(events.length);
    expect(v.events).toHaveLength(events.length);
    expect(selectTimeline(v).map(item => item.type)).toEqual(["read.recorded"]);
    // The next event applies without a gap.
    const next = reduceRunView(v, { type: "events", events: [ev(events.length + 1, "message.final", { text: "ok" })] });
    expect(next.lastSequence).toBe(events.length + 1);
    expect(next.needsSnapshot).toBe(false);
  });

  it("labels context.failed like a fallback, with its reason code as the detail", () => {
    const v = reduceRunView(base, {
      type: "events",
      events: [ev(1, "context.failed", { reason_code: "context_unavailable", message: "m", turn: "acknowledgement" })],
    });
    expect(v.unsupportedEvents).toBe(0);
    expect(v.needsSnapshot).toBe(false);
    const [item] = selectTimeline(v);
    expect(item?.supported).toBe(true);
    expect(item?.labelKey).toBe("event.context.failed");
    expect(item?.detail).toBe("context_unavailable");
    expect(translate("en", "event.context.failed")).toBe("Context could not be prepared");
    expect(translate("vi", "event.context.failed")).toBe("Không chuẩn bị được ngữ cảnh");
  });
});

describe("thread helpers", () => {
  it("leaves the composer unlocked only when conversations are on", () => {
    expect(isConversationsOn({ kind: "ready", conversations: "on", mounted: true })).toBe(true);
    expect(isConversationsOn({ kind: "ready", conversations: "shadow", mounted: true })).toBe(false);
    expect(isConversationsOn({ kind: "ready", conversations: "off", mounted: false })).toBe(false);
    expect(isConversationsOn({ kind: "unavailable" })).toBe(false);
    expect(isConversationsOn({ kind: "loading" })).toBe(false);
  });

  it("shows the thread only in on with readable routes, and never for a legacy run", () => {
    const on: FeaturesState = { kind: "ready", conversations: "on", mounted: true };
    const base: Parameters<typeof selectThreadShown>[0] = {
      features: on,
      threads: { kind: "ready", items: [], nextAfter: null },
      thread: { snapshot: null, runs: {}, status: "idle" },
      runId: null,
      conversationId: null,
    };
    expect(selectThreadShown(base)).toBe(true);
    expect(selectThreadShown({ ...base, runId: "run-1", conversationId: "conv-1" })).toBe(true);
    expect(selectThreadShown({ ...base, conversationId: "conv-1" })).toBe(true);
    // A run outside every conversation keeps the per-run view (G-B 2).
    expect(selectThreadShown({ ...base, runId: "legacy-1" })).toBe(false);
    expect(selectThreadShown({ ...base, features: { kind: "ready", conversations: "shadow", mounted: true } })).toBe(false);
    expect(selectThreadShown({ ...base, threads: { kind: "error" } })).toBe(false);
  });

  it("keeps Stop in place: active, idle with a reason, or unconfirmed with the safe check", () => {
    for (const state of ["CREATED", "RUNNING", "WAITING_INPUT", "WAITING_APPROVAL", "VERIFYING"])
      expect(selectStopControl(state)).toEqual({ kind: "active" });
    for (const state of [null, undefined, "SUCCEEDED", "FAILED", "CANCELLED"])
      expect(selectStopControl(state)).toEqual({ kind: "idle" });
    expect(selectStopControl("NEEDS_RECONCILIATION")).toEqual({ kind: "unconfirmed" });
  });

  it("takes the card's one line from recorded events only, preferring the reported outcome", () => {
    expect(selectRunLine(null, "RUNNING")).toBeNull();
    expect(selectRunLine(emptyRunView, "RUNNING")).toBeNull();
    const running = reduceRunView(emptyRunView, {
      type: "events",
      events: [
        ev(1, "run.created", { task: "t" }),
        ev(2, "read.recorded", { contract_id: "procurement.demand.read.v1" }),
        ev(3, "run.state_changed", { from: "CREATED", to: "RUNNING" }),
      ],
    });
    expect(selectRunLine(running, "RUNNING")?.labelKey).toBe("event.read.recorded");
    const ended = reduceRunView(running, {
      type: "events",
      events: [
        ev(4, "outcome.reported", { status: "VERIFIED" }),
        ev(5, "message.final", { text: "done" }),
        ev(6, "run.terminal", { state: "SUCCEEDED" }),
      ],
    });
    expect(selectRunLine(ended, "SUCCEEDED")?.labelKey).toBe("outcome.VERIFIED");
    // An unknown event never becomes the line.
    const odd = reduceRunView(emptyRunView, { type: "events", events: [ev(1, "made.up", {})] });
    expect(selectRunLine(odd, "SUCCEEDED")).toBeNull();
  });

  // B-2: run 2 of the browser run answered with a verified recommendation, then proposed a PO.
  const answeredThenProposed = reduceRunView(emptyRunView, {
    type: "events",
    events: [
      ev(1, "run.created", { task: "draft a PO for it" }),
      ev(2, "proposal.created", { contract_id: "procurement.offer.recommend.v1" }),
      ev(3, "outcome.reported", { status: "VERIFIED" }),
      ev(4, "ir.step_verified", { step: 1 }),
      ev(5, "proposal.created", { contract_id: "procurement.purchase_order.draft.v1" }),
      ev(6, "validation.completed", { status: "PASS" }),
      ev(7, "approval.requested", { digest: "d" }),
      ev(8, "run.state_changed", { from: "RUNNING", to: "WAITING_APPROVAL" }),
    ],
  });
  const VERIFIED_LABELS = ["outcome.VERIFIED", "outcome.reported", "outcome.FAILED", "outcome.UNKNOWN", "event.outcome.reported", "event.ir.step_verified"];

  it("never shows an outcome or verified line while the run has not ended (B-2)", () => {
    for (const state of ["CREATED", "RUNNING", "WAITING_INPUT", "WAITING_APPROVAL", "VERIFYING", "NEEDS_RECONCILIATION", null, undefined]) {
      const line = selectRunLine(answeredThenProposed, state);
      expect(VERIFIED_LABELS).not.toContain(line?.labelKey);
    }
    // The line matches the state the badge shows: the approval that waits.
    expect(selectRunLine(answeredThenProposed, "WAITING_APPROVAL")?.labelKey).toBe("event.approval.requested");
    // Even when the inner outcome is the latest event, it is not the line.
    const outcomeLast = reduceRunView(emptyRunView, {
      type: "events",
      events: [ev(1, "read.recorded", { contract_id: "c" }), ev(2, "outcome.reported", { status: "VERIFIED" }), ev(3, "ir.step_verified", {})],
    });
    expect(selectRunLine(outcomeLast, "RUNNING")?.labelKey).toBe("event.read.recorded");
  });

  it("shows 'Outcome verified' at the end only when the run ended verified (B-2)", () => {
    const failed = reduceRunView(answeredThenProposed, {
      type: "events",
      events: [ev(9, "run.terminal", { state: "FAILED" }), ev(10, "run.state_changed", { from: "WAITING_APPROVAL", to: "FAILED" })],
    });
    for (const [state, reasonCode] of [["FAILED", null], ["CANCELLED", null], ["SUCCEEDED", "grounded"]] as const) {
      const line = selectRunLine(failed, state, reasonCode);
      expect(line?.labelKey).not.toBe("outcome.VERIFIED");
      expect(line?.labelKey).not.toBe("event.ir.step_verified");
    }
    expect(selectRunLine(failed, "FAILED")?.labelKey).toBe("event.approval.requested");
    // A failed outcome check is not a verified label: an ended run still shows it.
    const checkFailed = reduceRunView(answeredThenProposed, {
      type: "events",
      events: [ev(9, "outcome.reported", { status: "FAILED" }), ev(10, "run.terminal", { state: "FAILED" })],
    });
    expect(selectRunLine(checkFailed, "FAILED")?.labelKey).toBe("outcome.FAILED");
    // A run that ended verified shows its outcome.
    const succeeded = reduceRunView(answeredThenProposed, {
      type: "events",
      events: [ev(9, "outcome.reported", { status: "VERIFIED" }), ev(10, "run.terminal", { state: "SUCCEEDED" })],
    });
    expect(selectRunLine(succeeded, "SUCCEEDED")?.labelKey).toBe("outcome.VERIFIED");
  });

  it("lists the connections the server recorded on reads, once each", () => {
    const v = reduceRunView(emptyRunView, {
      type: "events",
      events: [
        ev(1, "read.recorded", { contract_id: "a", connection_id: "conn-1" }),
        ev(2, "read.recorded", { contract_id: "b", connection_id: "conn-1" }),
        ev(3, "read.recorded", { contract_id: "c", connection_id: "conn-2" }),
        ev(4, "read.recorded", { contract_id: "d" }),
      ],
    });
    expect(selectReadConnections(v)).toEqual(["conn-1", "conn-2"]);
    expect(selectReadConnections(null)).toEqual([]);
  });

  it("marks the final message as the agent's words", () => {
    const v = reduceRunView(emptyRunView, {
      type: "events",
      events: [ev(1, "input.requested", { question: "How many?" }), ev(2, "message.final", { text: "Done." })],
    });
    expect(selectConversation(v).map(m => m.final)).toEqual([false, true]);
  });
});
