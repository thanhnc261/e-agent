import resolved from "./generated/tokens.json";

export const THEMES = ["light", "dark", "high-contrast"] as const;
export type ThemeName = (typeof THEMES)[number];

/** Emphasis and decoration only. An appearance never changes capabilities or rules. */
export const APPEARANCES = ["calm", "presence", "operator"] as const;
export type AppearanceName = (typeof APPEARANCES)[number];

/** Spacing scale. Both values stay within the accessibility target sizes. */
export const DENSITIES = ["comfortable", "compact"] as const;
export type DensityName = (typeof DENSITIES)[number];

/**
 * Resolved token values per variant (for checks and non-CSS consumers). Keys are a
 * theme name, or `"<theme>+<variant>"` for a density/appearance override.
 */
export const tokenValues: Record<string, Record<string, string>> = resolved;

export function cssVar(token: string): string {
  return `var(--ea-${token.replaceAll(".", "-")})`;
}

export function isThemeName(value: string | null | undefined): value is ThemeName {
  return (THEMES as readonly string[]).includes(value ?? "");
}

export function isAppearanceName(value: string | null | undefined): value is AppearanceName {
  return (APPEARANCES as readonly string[]).includes(value ?? "");
}

export function isDensityName(value: string | null | undefined): value is DensityName {
  return (DENSITIES as readonly string[]).includes(value ?? "");
}
