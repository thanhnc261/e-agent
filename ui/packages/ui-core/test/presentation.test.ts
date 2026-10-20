import { describe, expect, it } from "vitest";
import { catalogKeys } from "../src/i18n.ts";
import {
  actionStatusKey,
  presentationMatchesCanonical,
  resultStatusKey,
  runStatusKey,
} from "../src/presentation.ts";
import { presentation } from "./fixtures.ts";

describe("human-visible approval integrity", () => {
  it("requires every exact canonical value, even when the digest is intact", async () => {
    const p = await presentation();
    expect(presentationMatchesCanonical(p)).toBe(true);
    expect(presentationMatchesCanonical({ ...p, material_fields: [] })).toBe(false);
    expect(presentationMatchesCanonical({ ...p, material_fields: [{ ...p.material_fields[0]!, value: "4" }] })).toBe(false);
    expect(presentationMatchesCanonical({ ...p, material_fields: [...p.material_fields, p.material_fields[0]!] })).toBe(false);
  });
  it("rejects substituted scope and flattened path collisions", async () => {
    const p = await presentation();
    expect(presentationMatchesCanonical({ ...p, canonical_proposal: { ...p.canonical_proposal, connection_id: "other" } })).toBe(false);
    expect(presentationMatchesCanonical({ ...p, canonical_proposal: { arguments: { "a.b": "1", a: { b: "2" } } } })).toBe(false);
  });
});

describe("run status keeps working, sending, recorded and unconfirmed apart", () => {
  it("names an in-flight external change from the server's action state only", () => {
    expect(runStatusKey("RUNNING", [])).toBe("status.RUNNING");
    expect(runStatusKey("RUNNING", [{ state: "APPROVED" }])).toBe("status.RUNNING");
    expect(runStatusKey("RUNNING", [{ state: "DISPATCHING" }])).toBe("status.phase.DISPATCHING");
    expect(runStatusKey("RUNNING", [{ state: "COMMITTED" }])).toBe("status.phase.COMMITTED");
    expect(runStatusKey("VERIFYING", [{ state: "COMMITTED" }])).toBe("status.VERIFYING");
    expect(runStatusKey("VERIFYING", [{ state: "COMMITTED" }, { state: "UNKNOWN" }])).toBe(
      "status.phase.UNKNOWN",
    );
  });

  it("never relabels a waiting or terminal run", () => {
    for (const state of ["WAITING_APPROVAL", "NEEDS_RECONCILIATION", "SUCCEEDED", "FAILED", "CANCELLED"]) {
      expect(runStatusKey(state, [{ state: "UNKNOWN" }, { state: "DISPATCHING" }])).toBe(`status.${state}`);
    }
    expect(runStatusKey(undefined)).toBe("status.idle");
  });

  it("never labels a grounded run verified (PR-19)", () => {
    expect(runStatusKey("SUCCEEDED", [], false, "grounded")).toBe("status.SUCCEEDED.grounded");
    expect(runStatusKey("SUCCEEDED", [], false, "verified")).toBe("status.SUCCEEDED");
    expect(runStatusKey("FAILED", [], false, "grounded")).toBe("status.FAILED");
  });

  it("names a waiting reply as the user's turn, never as a needed answer", () => {
    expect(runStatusKey("WAITING_INPUT", [], true)).toBe("status.WAITING_INPUT.reply");
    expect(runStatusKey("WAITING_INPUT", [], false)).toBe("status.WAITING_INPUT");
    expect(runStatusKey("RUNNING", [], true)).toBe("status.RUNNING");
  });

  it("has a label in every locale for every action state", () => {
    const states = [
      "PROPOSED",
      "VALIDATED",
      "BLOCKED",
      "AWAITING_APPROVAL",
      "APPROVED",
      "RESERVED",
      "DISPATCHING",
      "COMMITTED",
      "FAILED",
      "UNKNOWN",
      "VERIFIED",
      "VERIFICATION_FAILED",
    ];
    for (const locale of ["en", "vi"] as const) {
      for (const state of states) expect(catalogKeys(locale)).toContain(actionStatusKey(state));
      for (const phase of ["DISPATCHING", "COMMITTED", "UNKNOWN"])
        expect(catalogKeys(locale)).toContain(`status.phase.${phase}`);
    }
  });
});

describe("resultStatusKey", () => {
  it("labels a grounded run apart from a verified one (PR-19, ADR 0033)", () => {
    expect(resultStatusKey("SUCCEEDED", "grounded")).toBe("status.SUCCEEDED.grounded");
    expect(resultStatusKey("SUCCEEDED", "verified")).toBe("status.SUCCEEDED");
    expect(resultStatusKey("SUCCEEDED", "answered")).toBe("status.SUCCEEDED");
    expect(resultStatusKey("SUCCEEDED", null)).toBe("status.SUCCEEDED");
    expect(resultStatusKey("SUCCEEDED")).toBe("status.SUCCEEDED");
    expect(resultStatusKey("FAILED", "grounded")).toBe("status.FAILED");
    expect(resultStatusKey(undefined, "grounded")).toBe("status.idle");
    for (const locale of ["en", "vi"] as const) {
      expect(catalogKeys(locale)).toContain("status.SUCCEEDED.grounded");
    }
  });
});
