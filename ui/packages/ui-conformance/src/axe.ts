/**
 * Automated WCAG check for one rendered state (AG-A11Y-1, gap audit F-12). The engine is the
 * pinned `axe-core` dev dependency; `AXE_CORE_PATH` may override it with another build. A
 * missing engine fails the check rather than skipping it, and a run that executed no rule
 * fails too: zero cases is not a pass (PR-31).
 */
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import type { Page } from "@playwright/test";

/** The axe-core build that runs: the override when given, else the pinned dependency. */
export function axeEnginePath(): string {
  const override = process.env["AXE_CORE_PATH"];
  if (override) return override;
  return createRequire(import.meta.url).resolve("axe-core/axe.min.js");
}

/** The WCAG 2.2 AA rule tags; best-practice rules are left out. */
const TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];

export interface AxeResult {
  /** Rules that ran on the page: passed, violated or incomplete. */
  rules: number;
  /** One line per violation: rule id, impact and the first offending targets. */
  violations: string[];
}

export async function runAxe(page: Page): Promise<AxeResult> {
  const engine = readFileSync(axeEnginePath(), "utf8");
  // Evaluated through the browser protocol, so the page's own CSP (script-src 'self') stays
  // as shipped instead of being loosened for the check.
  await page.evaluate(engine);
  return page.evaluate(async tags => {
    type Node = { target: unknown[] };
    type Rule = { id: string; impact?: string | null; nodes: Node[] };
    type Result = { passes: Rule[]; violations: Rule[]; incomplete: Rule[] };
    const axe = (globalThis as unknown as { axe: { run: (c: Document, o: unknown) => Promise<Result> } }).axe;
    const result = await axe.run(document, { runOnly: { type: "tag", values: tags }, resultTypes: ["violations"] });
    return {
      rules: result.passes.length + result.violations.length + result.incomplete.length,
      violations: result.violations.map(
        v => `${v.id} (${v.impact ?? "unknown"}): ${v.nodes.slice(0, 3).map(n => JSON.stringify(n.target)).join(", ")}`,
      ),
    };
  }, TAGS);
}
