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
    expect(translate("vi", "approval.title")).toBe("Xem xét thay đổi được đề xuất");
  });

  it("G-D Vietnamese: the flagged strings, and one word for the user's task", () => {
    expect(translate("vi", "citation.valueNotRecorded")).toBe("Giá trị không được ghi lại");
    expect(translate("vi", "nav.lastSeen")).toBe("thấy lần cuối");
    expect(translate("vi", "explain.revision")).toBe("Bản sửa đổi");
    expect(translate("vi", "conversation.refusedBusy")).toBe(
      "Cuộc trò chuyện đang bận. Hãy chờ, quyết định phê duyệt, hoặc dừng yêu cầu.",
    );
    expect(translate("vi", "run.nothingRunning")).toBe("Không có yêu cầu nào đang chạy");
    // GD-6 rulings: the group heading is plural and says "last seen" as nav.lastSeen does;
    // a receipt's commit is named as a commit, apart from verification (PR-19).
    expect(translate("vi", "nav.legacy")).toBe("Các yêu cầu trước · phiên này · trạng thái thấy lần cuối");
    expect(translate("en", "value.receipt.COMMITTED")).toBe("Committed");
    expect(translate("vi", "value.receipt.COMMITTED")).toBe("Đã ghi vào hệ thống");
    // The Stop button says "Dừng yêu cầu"; the task is "yêu cầu" everywhere. context.noHost
    // keeps its owner-confirmed copy, pinned in apps/web/test/routes.test.ts.
    expect(translate("vi", "run.cancel")).toBe("Dừng yêu cầu");
    const split = catalogKeys("vi").filter(key => /tác vụ/i.test(translate("vi", key)));
    expect(split).toEqual(["context.noHost"]);
  });

  it("formats decimals without floats", () => {
    expect(formatDecimal("1234567.890000000000000001", "en")).toBe("1,234,567.890000000000000001");
    expect(formatDecimal("1234.5", "vi")).toBe("1.234,5");
    expect(formatFieldValue("supplier_ref", "1234", "en")).toBe("1234");
  });
});
