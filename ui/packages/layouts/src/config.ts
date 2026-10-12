/**
 * Validated public layout configuration. Input may come from an element attribute
 * or a host JSON file, so every field is checked and unknown keys are rejected.
 */
import { SLOT_NAMES, SURFACE_MODES, type SlotName } from "@e-agent/ui-react";

export const LAYOUTS = SURFACE_MODES;
export type LayoutName = (typeof LAYOUTS)[number];

export interface LayoutConfig {
  layout: LayoutName;
  slots?: Partial<Record<SlotName, { hidden?: boolean }>>;
  /** sidebar only */
  side?: "left" | "right";
  order?: SlotName[];
}

export class LayoutConfigError extends Error {}

/** Validate untrusted layout config (e.g. from an element attribute or JSON file). */
export function parseLayoutConfig(input: unknown): LayoutConfig {
  if (typeof input !== "object" || input === null)
    throw new LayoutConfigError("layout config must be an object");
  const raw = input as Record<string, unknown>;
  const allowed = new Set(["layout", "slots", "side", "order"]);
  for (const key of Object.keys(raw))
    if (!allowed.has(key)) throw new LayoutConfigError(`unknown key ${key}`);
  if (!LAYOUTS.includes(raw["layout"] as LayoutName)) throw new LayoutConfigError("unknown layout");
  const config: LayoutConfig = { layout: raw["layout"] as LayoutName };
  if (raw["side"] !== undefined) {
    if (raw["side"] !== "left" && raw["side"] !== "right")
      throw new LayoutConfigError("side must be left or right");
    config.side = raw["side"];
  }
  if (raw["slots"] !== undefined) {
    if (typeof raw["slots"] !== "object" || raw["slots"] === null)
      throw new LayoutConfigError("slots must be an object");
    const slots: LayoutConfig["slots"] = {};
    for (const [name, value] of Object.entries(raw["slots"] as Record<string, unknown>)) {
      if (!(SLOT_NAMES as readonly string[]).includes(name))
        throw new LayoutConfigError(`unknown slot ${name}`);
      const v = value as Record<string, unknown>;
      if (
        typeof v !== "object" ||
        v === null ||
        (v["hidden"] !== undefined && typeof v["hidden"] !== "boolean")
      ) {
        throw new LayoutConfigError(`invalid slot config for ${name}`);
      }
      slots[name as SlotName] = { hidden: v["hidden"] === true };
    }
    config.slots = slots;
  }
  if (raw["order"] !== undefined) {
    if (
      !Array.isArray(raw["order"]) ||
      raw["order"].some(n => !SLOT_NAMES.includes(n as SlotName)) ||
      new Set(raw["order"]).size !== raw["order"].length
    )
      throw new LayoutConfigError("invalid slot order");
    config.order = raw["order"] as SlotName[];
  }
  return config;
}
