import { describe, expect, it } from "vitest";
import { LayoutConfigError, parseLayoutConfig } from "../src/index.tsx";

describe("layout config schema", () => {
  it("accepts presets, side and slot visibility", () => {
    expect(parseLayoutConfig({ layout: "sidebar", side: "left", slots: { evidence: { hidden: true } } })).toEqual({
      layout: "sidebar",
      side: "left",
      slots: { evidence: { hidden: true } },
    });
  });

  it.each([
    [null],
    [{ layout: "floating" }],
    [{ layout: "overlay", extra: 1 }],
    [{ layout: "overlay", slots: { sidebar: {} } }],
    [{ layout: "overlay", slots: { approval: { hidden: "yes" } } }],
    [{ layout: "sidebar", side: "top" }],
  ])("rejects %j", (input) => {
    expect(() => parseLayoutConfig(input)).toThrow(LayoutConfigError);
  });
});
