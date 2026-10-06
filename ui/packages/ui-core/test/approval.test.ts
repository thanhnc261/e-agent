import { describe, expect, it } from "vitest";
import { canRequestApprove, initialApproval, reduceApproval, type ApprovalState } from "../src/approval.ts";
import { presentation } from "./fixtures.ts";

async function reviewing(digestOk = true): Promise<ApprovalState> {
  return reduceApproval(initialApproval, { type: "PRESENTED", presentation: await presentation(), digestOk });
}

describe("approval state machine", () => {
  it("requires reviewing -> confirming -> submitting", async () => {
    let s = await reviewing();
    expect(s.phase).toBe("reviewing");
    expect(reduceApproval(s, { type: "SUBMIT", decision: "approved" })).toBe(s); // no shortcut
    s = reduceApproval(s, { type: "REQUEST_CONFIRM" });
    expect(s.phase).toBe("confirming");
    s = reduceApproval(s, { type: "SUBMIT", decision: "approved" });
    expect(s.phase).toBe("submitting");
    expect(reduceApproval(s, { type: "SUBMIT", decision: "approved" })).toBe(s); // no double submit
    expect(reduceApproval(s, { type: "SUBMITTED", decision: "approved" }).phase).toBe("approved");
  });

  it("never offers approve on a digest mismatch", async () => {
    const s = await reviewing(false);
    expect(canRequestApprove(s)).toBe(false);
    expect(reduceApproval(s, { type: "REQUEST_CONFIRM" }).phase).toBe("reviewing");
    expect(reduceApproval(s, { type: "SUBMIT", decision: "rejected" }).phase).toBe("submitting");
  });

  it("never offers approve after expiry", async () => {
    const p = await presentation({ expires_at: new Date(Date.now() - 1000).toISOString() });
    const s = reduceApproval(initialApproval, { type: "PRESENTED", presentation: p, digestOk: true });
    expect(canRequestApprove(s)).toBe(false);
    expect(reduceApproval(s, { type: "EXPIRED" }).phase).toBe("expired");
  });

  it("goes stale when a new revision arrives while confirming and forces re-review", async () => {
    let s = reduceApproval(await reviewing(), { type: "REQUEST_CONFIRM" });
    const next = await presentation({ run_revision: 7, action_id: "act-2" }, "41");
    s = reduceApproval(s, { type: "PRESENTED", presentation: next, digestOk: true });
    expect(s.phase).toBe("stale");
    expect(canRequestApprove(s)).toBe(false);
    expect(reduceApproval(s, { type: "SUBMIT", decision: "approved" }).phase).toBe("stale");
    s = reduceApproval(s, { type: "REVIEW_AGAIN" });
    expect(s.phase).toBe("reviewing");
    expect(s.presentation?.action_id).toBe("act-2");
  });

  it("server conflict marks stale; other errors are errors", async () => {
    const s = reduceApproval(await reviewing(), { type: "REQUEST_CONFIRM" });
    expect(reduceApproval(s, { type: "FAILED", error: "x", stale: true }).phase).toBe("stale");
    expect(reduceApproval(s, { type: "FAILED", error: "x", stale: false }).phase).toBe("error");
  });
});
