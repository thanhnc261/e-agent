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

  it("records the final message as data", () => {
    const v = reduceRunView(base, { type: "events", events: [ev(1, "message.final", { text: "done" })] });
    expect(v.finalMessage).toBe("done");
  });
});
