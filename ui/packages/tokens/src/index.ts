import resolved from "./generated/tokens.json";

export const THEMES = ["light", "dark", "high-contrast"] as const;
export type ThemeName = (typeof THEMES)[number];

/** Resolved token values per theme (for checks and non-CSS consumers). */
export const tokenValues: Record<ThemeName, Record<string, string>> = resolved;

export function cssVar(token: string): string {
  return `var(--ea-${token.replaceAll(".", "-")})`;
}

export function isThemeName(value: string | null | undefined): value is ThemeName {
  return (THEMES as readonly string[]).includes(value ?? "");
}
