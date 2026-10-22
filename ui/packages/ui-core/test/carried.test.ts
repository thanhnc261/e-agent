/**
 * `selectCarriedRuns` at the bundle boundary (G-D 4.U1, brief item 8, ADR 0023 §6): the earlier
 * runs a run used as hints, read only from the bundle's `conversation` key, and only in a run
 * pinned `conversations: on`. In `shadow` nothing reached the model, so nothing is listed.
 */
import { describe, expect, it } from "vitest";
import { selectCarriedRuns } from "../src/selectors/explanation.ts";

function bundle(mode: string | null, carried: unknown, extra: Record<string, unknown> = {}) {
  return {
    schema: "e-agent-evidence-v1",
    ...(mode === null ? {} : { modes: { conversations: mode } }),
    conversation: {
      conversation_id: "conv-1",
      mode: mode ?? "off",
      carried_run_ids: carried,
      compared: { start: 0, refuse: 0 },
    },
    ...extra,
  };
}

const entries = [
  { runId: "run-a", task: "which products are short?" },
  { runId: "run-b", task: "draft a PO for it" },
];

describe("selectCarriedRuns", () => {
  it("lists the carried runs of a run pinned on, named by their place in the thread", () => {
    expect(selectCarriedRuns(bundle("on", ["run-a"]), entries)).toEqual([
      { runId: "run-a", ordinal: 1, task: "which products are short?" },
    ]);
  });

  it("keeps the server's order, drops repeats, and falls back to the id outside the thread", () => {
    expect(selectCarriedRuns(bundle("on", ["run-x", "run-a", "run-x", 7, ""]), entries)).toEqual([
      { runId: "run-x", ordinal: null, task: null },
      { runId: "run-a", ordinal: 1, task: "which products are short?" },
    ]);
    expect(selectCarriedRuns(bundle("on", ["run-a"]))).toEqual([
      { runId: "run-a", ordinal: null, task: null },
    ]);
  });

  it("lists nothing in shadow, where nothing reached the model", () => {
    expect(selectCarriedRuns(bundle("shadow", ["run-a"]), entries)).toEqual([]);
  });

  it("lists nothing in off, without pinned modes, or when the key disagrees with the pin", () => {
    expect(selectCarriedRuns(bundle("off", ["run-a"]), entries)).toEqual([]);
    expect(selectCarriedRuns(bundle(null, ["run-a"]), entries)).toEqual([]);
    const disagree = bundle("on", ["run-a"]);
    (disagree.conversation as Record<string, unknown>)["mode"] = "shadow";
    expect(selectCarriedRuns(disagree, entries)).toEqual([]);
  });

  it("lists nothing for an empty or missing list, an absent bundle or another schema", () => {
    expect(selectCarriedRuns(bundle("on", []), entries)).toEqual([]);
    expect(selectCarriedRuns(bundle("on", "run-a"), entries)).toEqual([]);
    expect(
      selectCarriedRuns({ schema: "e-agent-evidence-v1", modes: { conversations: "on" } }, entries),
    ).toEqual([]);
    expect(selectCarriedRuns(null, entries)).toEqual([]);
    expect(selectCarriedRuns(undefined, entries)).toEqual([]);
    expect(selectCarriedRuns(bundle("on", ["run-a"], { schema: "e-agent-evidence-v2" }), entries)).toEqual(
      [],
    );
  });
});
