import { describe, expect, it } from "vitest";
import { runStateTone } from "../src/primitives/runStateTone.ts";

describe("run state tone", () => {
  it("never gives a grounded run the verified tone (PR-19)", () => {
    expect(runStateTone("SUCCEEDED")).toBe("verified");
    expect(runStateTone("SUCCEEDED", "grounded")).toBe("neutral");
    expect(runStateTone("FAILED", "grounded")).toBe("failed");
  });
});
