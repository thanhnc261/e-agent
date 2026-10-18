import { describe, expect, it } from "vitest";
import { translate } from "../src/i18n.ts";
import { emptyRunView, reduceRunView, selectTimeline } from "../src/store.ts";
import { ev, snapshot } from "./fixtures.ts";

// Feature-toggle and execution-plan events (ADR 0025, ADR 0027): known, labelled, no refresh.
const FEATURE_EVENTS = [
  ["feature.fallback", { feature: "execution_ir", reason_code: "ir_compile_failed", message: "The proposal could not be compiled into a plan." }],
  ["ir.plan_compiled", { plan_digest: "jcs-sha256-v1:abc", step_count: 1 }],
  ["ir.shadow_failed", { reason_code: "ir_task_unresolved" }],
  ["ir.lineage_resolved", { step_index: 1 }],
  ["ir.step_verified", { step_index: 1 }],
] as const;

describe("feature and execution-plan events", () => {
  const base = reduceRunView(emptyRunView, { type: "snapshot", snapshot: snapshot("RUNNING", null) });

  it("renders feature and IR events without crashing and with a label", () => {
    const events = FEATURE_EVENTS.map(([type, payload], i) => ev(i + 1, type, { ...payload }));
    const v = reduceRunView(base, { type: "events", events });
    expect(v.unsupportedEvents).toBe(0);
    expect(v.needsSnapshot).toBe(false);
    const items = selectTimeline(v);
    expect(items.map((item) => item.type)).toEqual(FEATURE_EVENTS.map(([type]) => type));
    for (const item of items) {
      expect(item.supported).toBe(true);
      expect(item.labelKey).toBe(`event.${item.type}`);
      for (const locale of ["en", "vi"] as const) {
        const label = translate(locale, item.labelKey);
        expect(label).not.toBe(item.labelKey);
        expect(label.trim().length).toBeGreaterThan(0);
      }
    }
  });

  it("shows the typed reason of a fallback or shadow failure as its detail", () => {
    const v = reduceRunView(base, {
      type: "events",
      events: [
        ev(1, "feature.fallback", { feature: "execution_ir", reason_code: "ir_validation_failed", message: "<b>x</b>" }),
        ev(2, "ir.shadow_failed", { reason_code: "ir_task_unresolved" }),
        ev(3, "ir.plan_compiled", { plan_digest: "d" }),
      ],
    });
    expect(selectTimeline(v).map((item) => item.detail)).toEqual(["ir_validation_failed", "ir_task_unresolved", null]);
  });

  it("labels the acceptance_unmet reason code and keeps its terminal events supported", () => {
    // ADR 0028: a run that ends without meeting its task definition's acceptance spec.
    const failed = { from: "VERIFYING", to: "FAILED", reason: "acceptance unmet", reason_code: "acceptance_unmet" };
    const v = reduceRunView(base, {
      type: "events",
      events: [ev(1, "run.state_changed", failed), ev(2, "run.terminal", { state: "FAILED", reason_code: "acceptance_unmet" })],
    });
    expect(v.unsupportedEvents).toBe(0);
    expect(selectTimeline(v).map((item) => item.supported)).toEqual([true, true]);
    for (const locale of ["en", "vi"] as const) {
      const label = translate(locale, "reason.acceptance_unmet");
      expect(label).not.toBe("reason.acceptance_unmet");
      expect(label.trim().length).toBeGreaterThan(0);
    }
  });

  it("labels the plan_lineage_rejected reason code and keeps its terminal events supported", () => {
    // ADR 0025: a plan step's lineage value was not in the earlier step's verified read-back.
    const failed = { from: "RUNNING", to: "FAILED", reason: "lineage rejected", reason_code: "plan_lineage_rejected" };
    const v = reduceRunView(base, {
      type: "events",
      events: [ev(1, "run.state_changed", failed), ev(2, "run.terminal", { state: "FAILED", reason_code: "plan_lineage_rejected" })],
    });
    expect(v.unsupportedEvents).toBe(0);
    expect(selectTimeline(v).map((item) => item.supported)).toEqual([true, true]);
    for (const locale of ["en", "vi"] as const) {
      const label = translate(locale, "reason.plan_lineage_rejected");
      expect(label).not.toBe("reason.plan_lineage_rejected");
      expect(label.trim().length).toBeGreaterThan(0);
    }
  });
});
