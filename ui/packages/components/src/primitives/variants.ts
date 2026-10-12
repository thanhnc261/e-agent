/**
 * Small typed variant contracts shared by the primitives. A variant selects a
 * token-driven visual role; it never changes behavior, wording or authority.
 */
export const BUTTON_VARIANTS = ["primary", "default", "quiet"] as const;
export type ButtonVariant = (typeof BUTTON_VARIANTS)[number];

export const STATUS_TONES = ["neutral", "progress", "attention", "verified", "failed", "unknown"] as const;
export type StatusTone = (typeof STATUS_TONES)[number];

export const SURFACE_TONES = ["card", "sunken", "accent", "attention", "failed", "verified"] as const;
export type SurfaceTone = (typeof SURFACE_TONES)[number];
