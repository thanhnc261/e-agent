import { describe, expect, it } from "vitest";
import { THEMES, tokenValues } from "../src/index.ts";

function luminance(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => {
    const c = parseInt(hex.slice(i, i + 2), 16) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  }) as [number, number, number];
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

export function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x) as [number, number];
  return (hi + 0.05) / (lo + 0.05);
}

const SAFETY = ["color.status.verified", "color.status.failed", "color.status.unknown", "color.status.blocked", "approval.material-change"];

describe("theme safety tokens (UI architecture §4.5)", () => {
  for (const theme of THEMES) {
    it(`${theme}: text and safety signals meet 4.5:1 on surfaces`, () => {
      const t = tokenValues[theme];
      for (const surface of ["color.surface", "color.surface-raised"]) {
        for (const token of ["color.text", "color.text-muted", ...SAFETY]) {
          expect(contrast(t[token] as string, t[surface] as string), `${token} on ${surface}`).toBeGreaterThanOrEqual(4.5);
        }
      }
      expect(contrast(t["color.accent-text"] as string, t["color.accent"] as string)).toBeGreaterThanOrEqual(4.5);
    });

    it(`${theme}: status colors stay distinguishable from each other`, () => {
      const t = tokenValues[theme];
      const values = SAFETY.slice(0, 4).map((k) => t[k]);
      expect(new Set(values).size).toBe(4);
    });
  }
});
