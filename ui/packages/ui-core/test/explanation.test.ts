/**
 * `selectExplanation` at the bundle boundary (Task 4e.5, ADR 0034 §3): pointer lookup into the
 * run's approved facts, and shapes the UI must never guess at.
 */
import { describe, expect, it } from "vitest";
import { selectExplanation } from "../src/selectors/explanation.ts";

const fact = (evidenceId: string, data: unknown) => ({ contract_id: "c.read.v1", data, evidence: { evidence_id: evidenceId } });

function typed(pointer: string, data: unknown, extra: Record<string, unknown> = {}) {
  return {
    schema: "e-agent-evidence-v1",
    modes: { grounded_answers: "on" },
    actions: [{ approved_facts: [fact("ev-1", data)] }],
    events: [
      {
        type: "proposal.created",
        schema_version: "1",
        payload: { contract_id: "a.answer.v1", citations: [{ evidence_id: "ev-1", pointer, value_digest: "x" }] },
      },
    ],
    ...extra,
  };
}

function firstValue(bundle: Record<string, unknown>) {
  const view = selectExplanation(bundle);
  if (view.kind !== "ready") throw new Error(view.kind);
  const c = view.citations[0]?.citations[0];
  if (!c || c.kind !== "named") throw new Error("no named citation");
  return c.value;
}

describe("selectExplanation", () => {
  it("tells a recorded null apart from a pointer that names nothing", () => {
    expect(firstValue(typed("/a", { a: null }))).toEqual({ kind: "recorded", value: null, key: "a" });
    expect(firstValue(typed("/b", { a: null }))).toEqual({ kind: "not_recorded" });
  });

  it("follows RFC 6901: escapes, array indices and malformed pointers", () => {
    expect(firstValue(typed("/x~1y/~0z", { "x/y": { "~z": "v" } }))).toMatchObject({ kind: "recorded", value: "v" });
    expect(firstValue(typed("/rows/1", { rows: ["a", "b"] }))).toMatchObject({ kind: "recorded", value: "b" });
    expect(firstValue(typed("/rows/01", { rows: ["a", "b"] }))).toEqual({ kind: "not_recorded" });
    expect(firstValue(typed("/rows/2", { rows: ["a", "b"] }))).toEqual({ kind: "not_recorded" });
    expect(firstValue(typed("rows", { rows: ["a"] }))).toEqual({ kind: "not_recorded" });
  });

  it("shows typed-answer citations only in a run pinned on, from schema 1 events", () => {
    const off = selectExplanation(typed("/a", { a: 1 }, { modes: { grounded_answers: "shadow" } }));
    expect(off.kind === "ready" && off.citations).toEqual([]);
    const noModes = typed("/a", { a: 1 });
    delete (noModes as Record<string, unknown>)["modes"];
    const none = selectExplanation(noModes);
    expect(none.kind === "ready" && none.citations).toEqual([]);
    const v2 = typed("/a", { a: 1 });
    (v2.events[0] as Record<string, unknown>)["schema_version"] = "2";
    const unknown = selectExplanation(v2);
    expect(unknown.kind === "ready" && unknown.citations).toEqual([]);
  });

  it("keeps a digest-only citation unresolved, with nothing of it carried", () => {
    const view = selectExplanation({
      schema: "e-agent-evidence-v1",
      grounded_answer: {
        summary: { text: "s", label: "unverified" },
        citations: [{ evidence_id_digest: "d1", pointer_digest: "d2", value_digest: "d3", label: "grounded" }],
      },
    });
    expect(view.kind === "ready" && view.citations[0]?.citations).toEqual([{ kind: "unresolved" }]);
  });

  it("reports an unknown completeness and label as unknown and unsupported", () => {
    const view = selectExplanation({
      schema: "e-agent-evidence-v1",
      explanation: {
        completeness: "fine",
        run: {},
        sources: [{ evidence_id: "ev-1", contract_id: null, revision: null, label: "trusted" }],
        validation: {},
        outcomes: [{ status: "succeeded", label: "verified_outcome" }],
      },
    });
    if (view.kind !== "ready" || !view.explanation) throw new Error("not ready");
    expect(view.explanation.completeness).toBe("unknown");
    expect(view.explanation.goal).toBeNull();
    expect(view.explanation.sources[0]?.label).toBe("unsupported");
    expect(view.explanation.outcomes[0]?.label).toBe("verified_outcome");
    expect(selectExplanation({ schema: "e-agent-evidence-v9" })).toEqual({ kind: "unsupported", schema: "e-agent-evidence-v9" });
    expect(selectExplanation(null)).toEqual({ kind: "absent" });
  });
});
