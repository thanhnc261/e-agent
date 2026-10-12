/**
 * Presentation preference resolution (L7). Precedence is explicit host
 * configuration, then a scoped session preference, then the validated default. A
 * host-controlled value stays authoritative until that configuration changes, so a
 * pinned dimension is never offered as a user choice.
 */
import { APPEARANCES, DENSITIES, THEMES } from "@e-agent/tokens";
import type { PresentationDimension } from "@e-agent/ui-react";

export const PRESENTATION_OPTIONS: Record<PresentationDimension, readonly string[]> = {
  theme: THEMES,
  appearance: APPEARANCES,
  density: DENSITIES,
};

export const PRESENTATION_DEFAULTS: Record<PresentationDimension, string> = {
  theme: "light",
  appearance: "calm",
  density: "comfortable",
};

export type PresentationValues = Record<PresentationDimension, string>;

/** Host configuration; an absent or invalid value simply does not pin anything. */
export type PresentationConfig = Partial<Record<PresentationDimension, string | null | undefined>>;

export function isValid(dimension: PresentationDimension, value: string | null | undefined): boolean {
  return value != null && PRESENTATION_OPTIONS[dimension].includes(value);
}

function readStored(key: string, dimension: PresentationDimension): string | null {
  try {
    const saved = sessionStorage.getItem(`${key}.${dimension}`);
    return isValid(dimension, saved) ? saved : null;
  } catch {
    return null; // Storage is optional.
  }
}

export function storePreference(key: string, dimension: PresentationDimension, value: string): void {
  try {
    sessionStorage.setItem(`${key}.${dimension}`, value);
  } catch {
    /* Storage is optional. */
  }
}

export function resolvePresentation(
  config: PresentationConfig,
  preferenceKey: string,
  restorePreference: boolean,
): { values: PresentationValues; locked: Record<PresentationDimension, boolean> } {
  const values = { ...PRESENTATION_DEFAULTS };
  const locked = { theme: false, appearance: false, density: false };
  for (const dimension of Object.keys(values) as PresentationDimension[]) {
    const pinned = config[dimension];
    if (isValid(dimension, pinned)) {
      values[dimension] = pinned as string;
      locked[dimension] = true;
      continue;
    }
    const saved = restorePreference ? readStored(preferenceKey, dimension) : null;
    if (saved) values[dimension] = saved;
  }
  return { values, locked };
}
