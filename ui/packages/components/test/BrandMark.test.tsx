// @vitest-environment happy-dom
/**
 * The product mark is the owner-approved logo
 * (e-agent-sage-lagoon-15-35-depth-1-none-shadow-glossy-multicolor.svg, 2026-10-12),
 * regenerated from the v4 brand.js with identical parameters and spot-verified
 * against the owner file. The hash pins this shipped file against edits.
 * It is decorative: the accessible name stays on the adjacent text or control.
 */
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render } from "@testing-library/react";
import { BrandMark, brandMarkSvg } from "../src/primitives/BrandMark.tsx";

afterEach(cleanup);

const SHIPPED_MARK_SHA256 = "da745b62bab11542048da52468661bf1bf18a924582afd6fcc44ede1922f0613";

describe("BrandMark", () => {
  it("ships the pinned mark unchanged", () => {
    const file = readFileSync(
      resolve(process.cwd(), "packages/components/src/primitives/brand/e-agent-mark.svg"),
      "utf8",
    );
    expect(createHash("sha256").update(file).digest("hex")).toBe(SHIPPED_MARK_SHA256);
    expect(brandMarkSvg).toBe(file);
  });

  it("is decorative, shadowless, glossy and multicolour", () => {
    const { container } = render(<BrandMark />);
    const mark = container.querySelector(".ea-brand-mark");
    expect(mark?.getAttribute("aria-hidden")).toBe("true");
    const svg = mark?.querySelector("svg");
    expect(svg?.getAttribute("color")).toBe("#839675");
    expect(svg?.querySelector("[data-shadow]")).toBeNull();
    expect(svg?.querySelector('[data-face="multicolor"]')).not.toBeNull();
    expect(svg?.querySelector('[data-finish="glossy"]')).not.toBeNull();
  });

  it("accepts a size class without changing the artwork", () => {
    const { container } = render(<BrandMark className="ea-brand-mark-lg" />);
    const mark = container.querySelector(".ea-brand-mark");
    expect(mark?.classList.contains("ea-brand-mark-lg")).toBe(true);
    expect(mark?.innerHTML.length).toBeGreaterThan(9000);
  });
});
