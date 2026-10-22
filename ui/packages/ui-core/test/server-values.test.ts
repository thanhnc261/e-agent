/**
 * Server enum values shown in the user's language (G-D 4.U6, AG-SOC-1). The value lists are
 * the server's, copied from `src/e_agent/contracts/` (validation.py ValidationStatus,
 * approval.py ApprovalDecision, receipt.py ReceiptStatus, progress.py StageStatus,
 * outcome.py OutcomeStatus) and the generated `ValidationStatus` and approval `decision` types.
 * A value the UI does not know is shown exactly as the server wrote it.
 */
import { describe, expect, it } from "vitest";
import { emptyRunView, reduceRunView, selectTimeline } from "../src/store.ts";
import { translateServerValue, type ServerValueField } from "../src/i18n.ts";
import type { RunEvent } from "@e-agent/client";

const SERVER_VALUES: Record<ServerValueField, string[]> = {
  validation: ["PASS", "FAIL", "UNKNOWN", "ERROR"],
  decision: ["approved", "rejected"],
  receipt: ["COMMITTED", "FAILED", "UNKNOWN"],
  stage: ["succeeded", "failed", "blocked", "unknown", "skipped", "started", "waiting"],
  outcome: ["VERIFIED", "FAILED", "UNKNOWN"],
};

describe("translateServerValue", () => {
  it("names every known server value in both languages, never verbatim", () => {
    let checked = 0;
    for (const locale of ["en", "vi"] as const)
      for (const [field, values] of Object.entries(SERVER_VALUES) as [ServerValueField, string[]][])
        for (const value of values) {
          const text = translateServerValue(locale, field, value);
          expect(text, `${locale} ${field} ${value}`).not.toBe(value);
          expect(text.length).toBeGreaterThan(0);
          checked += 1;
        }
    expect(checked).toBe(38);
  });

  it("shows an unknown or missing value exactly as the server wrote it", () => {
    expect(translateServerValue("vi", "validation", "WARN")).toBe("WARN");
    expect(translateServerValue("en", "stage", "SUCCEEDED")).toBe("SUCCEEDED");
    expect(translateServerValue("vi", "decision", "constructor")).toBe("constructor");
    expect(translateServerValue("en", "outcome", "")).toBe("");
  });

  it("calls only the server's VERIFIED outcome verified", () => {
    const verified = /verif|xác minh/i;
    for (const locale of ["en", "vi"] as const)
      for (const [field, values] of Object.entries(SERVER_VALUES) as [ServerValueField, string[]][])
        for (const value of values) {
          const text = translateServerValue(locale, field, value);
          const claims = verified.test(text) && !/not verified|chưa xác minh/i.test(text);
          expect(claims, `${locale} ${field} ${value}: ${text}`).toBe(field === "outcome" && value === "VERIFIED");
        }
    // A grounded end or a verification stage that "succeeded" is never named verified.
    expect(translateServerValue("en", "stage", "succeeded")).toBe("Succeeded");
    expect(translateServerValue("vi", "stage", "succeeded")).toBe("Thành công");
  });
});

describe("timeline details", () => {
  const event = (sequence: number, type: string, payload: Record<string, unknown>): RunEvent =>
    ({
      event_id: `e${sequence}`,
      run_id: "run-1",
      sequence,
      type,
      occurred_at: "2026-10-22T00:00:00Z",
      payload,
      schema_version: "1",
    }) as RunEvent;

  it("say which server enum a detail holds, and keep the raw value", () => {
    const view = reduceRunView(emptyRunView, {
      type: "events",
      events: [
        event(1, "validation.completed", { status: "PASS" }),
        event(2, "approval.decided", { decision: "approved" }),
        event(3, "outcome.reported", { status: "VERIFIED" }),
        event(4, "read.recorded", { contract_id: "procurement.demand.read.v1" }),
      ],
    });
    const items = selectTimeline(view);
    expect(items.map(item => [item.detail, item.detailField ?? null])).toEqual([
      ["PASS", "validation"],
      ["approved", "decision"],
      ["VERIFIED", "outcome"],
      ["procurement.demand.read.v1", null],
    ]);
    expect(translateServerValue("vi", "outcome", "VERIFIED")).toBe("Đã xác minh");
  });
});
