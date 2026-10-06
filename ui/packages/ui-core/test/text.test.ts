import { describe, expect, it } from "vitest";
import { formatDecimal, formatFieldValue } from "../src/format.ts";
import { catalogKeys, translate } from "../src/i18n.ts";
import { segmentText } from "../src/sanitize.ts";

describe("model text policy", () => {
  it("never yields loadable images and always shows full link URLs", () => {
    const segs = segmentText("See ![chart](https://evil.example/x.png) and [docs](https://ok.example/a?b=1) <b>x</b>");
    expect(segs).toEqual([
      { kind: "text", text: "See " },
      { kind: "image", alt: "chart", url: "https://evil.example/x.png" },
      { kind: "text", text: " and " },
      { kind: "link", text: "docs (https://ok.example/a?b=1)", href: "https://ok.example/a?b=1" },
      { kind: "text", text: " <b>x</b>" },
    ]);
  });

  it("does not turn javascript: links into links", () => {
    expect(segmentText("[x](javascript:alert(1))").every((s) => s.kind !== "link")).toBe(true);
  });
});

describe("i18n and formatting", () => {
  it("vi and en catalogs have the same keys", () => {
    expect(catalogKeys("vi").sort()).toEqual(catalogKeys("en").sort());
    expect(translate("vi", "approval.title")).toBe("Phê duyệt");
  });

  it("formats decimals without floats", () => {
    expect(formatDecimal("1234567.890000000000000001", "en")).toBe("1,234,567.890000000000000001");
    expect(formatDecimal("1234.5", "vi")).toBe("1.234,5");
    expect(formatFieldValue("supplier_ref", "1234", "en")).toBe("1234");
  });
});
