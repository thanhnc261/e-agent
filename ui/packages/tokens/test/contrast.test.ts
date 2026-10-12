import { describe, expect, it } from "vitest";
import { APPEARANCES, DENSITIES, THEMES, tokenValues } from "../src/index.ts";

function luminance(hex: string): number {
  const [r, g, b] = [1, 3, 5].map(i => {
    const c = parseInt(hex.slice(i, i + 2), 16) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  }) as [number, number, number];
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

export function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x) as [number, number];
  return (hi + 0.05) / (lo + 0.05);
}

const SAFETY = [
  "color.status.verified",
  "color.status.failed",
  "color.status.unknown",
  "color.status.blocked",
  "approval.material-change",
];
const SURFACES = ["color.surface", "color.surface-raised", "color.canvas", "color.accent-soft"];
const rem = (value: string): number => Number.parseFloat(value) * (value.endsWith("rem") ? 16 : 1);

describe("theme safety tokens (UI architecture §4.5)", () => {
  for (const theme of THEMES) {
    it(`${theme}: text and safety signals meet 4.5:1 on every surface role`, () => {
      const t = tokenValues[theme]!;
      for (const surface of SURFACES) {
        for (const token of ["color.text", "color.text-muted", "color.text-subtle", ...SAFETY]) {
          expect(
            contrast(t[token] as string, t[surface] as string),
            `${token} on ${surface}`,
          ).toBeGreaterThanOrEqual(4.5);
        }
      }
      expect(contrast(t["color.accent-text"] as string, t["color.accent"] as string)).toBeGreaterThanOrEqual(
        4.5,
      );
      expect(
        contrast(t["color.accent-text"] as string, t["color.accent-strong"] as string),
      ).toBeGreaterThanOrEqual(4.5);
    });

    it(`${theme}: focus and borders stay visible against their background`, () => {
      const t = tokenValues[theme]!;
      expect(contrast(t["color.focus"] as string, t["color.canvas"] as string)).toBeGreaterThanOrEqual(3);
      expect(
        contrast(t["color.border-strong"] as string, t["color.surface"] as string),
      ).toBeGreaterThanOrEqual(3);
    });

    it(`${theme}: status colors stay distinguishable from each other`, () => {
      const t = tokenValues[theme]!;
      const values = SAFETY.slice(0, 4).map(k => t[k]);
      expect(new Set(values).size).toBe(4);
    });
  }
});

describe("an appearance never weakens a theme's guarantees", () => {
  for (const appearance of APPEARANCES) {
    for (const theme of THEMES) {
      const key = appearance === "calm" ? theme : `${theme}+${appearance}`;
      it(`${theme} + ${appearance}: text and safety signals still meet 4.5:1`, () => {
        const t = tokenValues[key]!;
        for (const surface of SURFACES) {
          for (const token of ["color.text", "color.text-muted", "color.text-subtle", ...SAFETY]) {
            expect(
              contrast(t[token] as string, t[surface] as string),
              `${token} on ${surface}`,
            ).toBeGreaterThanOrEqual(4.5);
          }
        }
        expect(
          contrast(t["color.accent-text"] as string, t["color.accent"] as string),
        ).toBeGreaterThanOrEqual(4.5);
      });

      it(`${theme} + ${appearance}: changes no colour role the theme defined`, () => {
        const base = tokenValues[theme]!;
        const variant = tokenValues[key]!;
        const changed = Object.keys(base).filter(
          name => name.startsWith("color.") && base[name] !== variant[name],
        );
        // A colour role may only be re-pointed at another role of the same theme,
        // whose contrast this suite already checks; a new colour is not allowed.
        const palette = new Set(Object.values(base));
        expect(
          changed.every(name => palette.has(variant[name] as string)),
          changed.join(","),
        ).toBe(true);
      });

      it(`${theme} + ${appearance}: keeps controls at an operable size`, () => {
        expect(rem(tokenValues[key]!["control.min-height"] as string)).toBeGreaterThanOrEqual(24);
      });
    }
  }
});

describe("density stays within accessible target sizes", () => {
  for (const density of DENSITIES) {
    it(`${density}: controls keep at least the 24px WCAG 2.2 AA minimum`, () => {
      const key = density === "comfortable" ? "light" : `light+${density}`;
      const t = tokenValues[key]!;
      expect(rem(t["control.min-height"] as string)).toBeGreaterThanOrEqual(24);
      expect(rem(t["control.min-target"] as string)).toBeGreaterThanOrEqual(24);
    });
  }
  it("comfortable aims at the 44px recommendation", () => {
    expect(rem(tokenValues["light"]!["control.min-height"] as string)).toBeGreaterThanOrEqual(44);
  });
});
