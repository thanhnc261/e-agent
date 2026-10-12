import { describe, expect, it } from "vitest";
import { emptyRunView, reduceRunView, selectTimeline } from "../src/store.ts";
import { ev, snapshot } from "./fixtures.ts";

describe("run view reducer", () => {
  const base = reduceRunView(emptyRunView, { type: "snapshot", snapshot: snapshot("RUNNING", null) });

  it("applies ordered events and dedupes replays", () => {
    let v = reduceRunView(base, { type: "events", events: [ev(1, "run.created"), ev(2, "run.state_changed", { from: "CREATED", to: "RUNNING" })] });
    v = reduceRunView(v, { type: "events", events: [ev(1, "run.created"), ev(2, "run.state_changed")] });
    expect(v.events.map((e) => e.sequence)).toEqual([1, 2]);
    expect(v.run?.state).toBe("RUNNING");
  });

  it("asks for a snapshot on a gap instead of applying out of order", () => {
    const v = reduceRunView(base, { type: "events", events: [ev(1, "run.created"), ev(3, "read.recorded")] });
    expect(v.lastSequence).toBe(1);
    expect(v.needsSnapshot).toBe(true);
  });

  it("shows unknown event types as unsupported and requests a snapshot", () => {
    const v = reduceRunView(base, { type: "events", events: [ev(1, "future.thing", { x: "<img src=x>" })] });
    expect(v.needsSnapshot).toBe(true);
    expect(v.unsupportedEvents).toBe(1);
    expect(selectTimeline(v)[0]).toMatchObject({ supported: false, labelKey: "event.unsupported", detail: null });
  });

  it("accepts read.rejected as a known event without a snapshot refresh", () => {
    const v = reduceRunView(base, {
      type: "events",
      events: [ev(1, "read.rejected", { request_id: "r1", contract_id: "c", connection_id: "k", code: "E_AGENT_INVALID_REF", message: "Odoo rejected the request" })],
    });
    expect(v.needsSnapshot).toBe(false);
    expect(v.unsupportedEvents).toBe(0);
    expect(selectTimeline(v)[0]).toMatchObject({ supported: true, labelKey: "event.read.rejected" });
  });

  it("records the final message as data", () => {
    const v = reduceRunView(base, { type: "events", events: [ev(1, "message.final", { text: "done" })] });
    expect(v.finalMessage).toBe("done");
  });
});

it("keeps transient text offsets separate from durable event sequence", () => {
  let v = reduceRunView(emptyRunView, { type: "snapshot", snapshot: snapshot("RUNNING", null) });
  v = reduceRunView(v, { type: "text", frame: { message_id: "message-1", stream_id: "text-1", offset: 1, text: "Public ", reset: true } });
  v = reduceRunView(v, { type: "text", frame: { message_id: "message-1", stream_id: "text-1", offset: 2, text: "answer", reset: false } });
  const duplicate = reduceRunView(v, { type: "text", frame: { message_id: "message-1", stream_id: "text-1", offset: 2, text: "answer", reset: false } });
  expect(duplicate.streamingText).toBe("Public answer");
  expect(duplicate.lastSequence).toBe(0);
  expect(duplicate.events).toHaveLength(0);
  v = reduceRunView(v, { type: "text", frame: { message_id: "message-1", stream_id: "new-process", offset: 1, text: "Restored", reset: true } });
  expect(v.streamingText).toBe("Restored");
  expect(v.lastSequence).toBe(0);
});

it("does not interpret a known event with an unsupported schema version", () => {
  const base = reduceRunView(emptyRunView, { type: "snapshot", snapshot: snapshot("RUNNING", null) });
  const event = { ...ev(1, "run.state_changed", { to: "SUCCEEDED" }), schema_version: "999" };
  const view = reduceRunView(base, { type: "events", events: [event] });
  expect(view.run?.state).toBe("RUNNING");
  expect(view.needsSnapshot).toBe(true);
  expect(selectTimeline(view)[0]?.supported).toBe(false);
});

it("distinguishes unknown verification from verified outcome", () => {
  const view = reduceRunView(emptyRunView, { type: "events", events: [ev(1, "outcome.reported", { status: "UNKNOWN" })] });
  expect(selectTimeline(view)[0]?.labelKey).toBe("outcome.UNKNOWN");
});

it("correlates verified result fields and committed references with the same action", async () => {
  const { selectVerifiedResults } = await import("../src/store.ts");
  const snap = snapshot("SUCCEEDED", null);
  snap.actions = [{ action_id: "a", contract_id: "example.answer.v1", state: "VERIFIED", arguments: { quantity: "7" } }];
  let view = reduceRunView(emptyRunView, { type: "snapshot", snapshot: snap });
  view = reduceRunView(view, { type: "events", events: [ev(1, "outcome.reported", { action_id: "other", status: "VERIFIED" })] });
  expect(selectVerifiedResults(view)).toEqual([]);
  view = reduceRunView(view, { type: "events", events: [ev(2, "outcome.reported", { action_id: "a", status: "VERIFIED" }), ev(3, "action.receipt_recorded", { action_id: "a", status: "COMMITTED", external_refs: ["record:1"] })] });
  expect(selectVerifiedResults(view)).toEqual([{ actionId: "a", fields: { quantity: "7" }, externalRefs: ["record:1"] }]);
});
