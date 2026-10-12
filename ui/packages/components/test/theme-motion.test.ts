/**
 * A theme change must apply text and background together. Animating background or
 * colour lets one side lag behind the other, so text briefly sits on a background of
 * the previous theme (a contrast failure mid-transition). Only non-colour properties
 * may transition.
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, resolve } from "node:path";
import { describe, expect, it } from "vitest";

const roots = ["packages/components/src", "packages/layouts/src", "apps/web/src"].map(p =>
  resolve(process.cwd(), p),
);
function cssFiles(dir: string): string[] {
  return readdirSync(dir).flatMap(name => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return cssFiles(path);
    return path.endsWith(".css") ? [path] : [];
  });
}

describe("theme-safe motion", () => {
  it("never transitions background or colour", () => {
    const offenders: string[] = [];
    for (const file of roots.flatMap(cssFiles)) {
      const css = readFileSync(file, "utf8");
      for (const match of css.matchAll(/transition(?:-property)?\s*:([^;]+);/g)) {
        const value = match[1]!.toLowerCase();
        if (/\b(all|background(?:-color)?|color)\b/.test(value)) offenders.push(`${file}: ${value.trim()}`);
      }
    }
    expect(offenders).toEqual([]);
  });
});
