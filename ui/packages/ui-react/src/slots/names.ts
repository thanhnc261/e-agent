/** Slot registry names (UI architecture §4.4). These IDs are a public contract. */
import type { ComponentType } from "react";

export const SLOT_NAMES = [
  "header",
  "navigation",
  "task-overview",
  "composer",
  "messages",
  "timeline",
  "approval",
  "evidence",
  "outcome",
  "connection-status",
  "footer",
] as const;
export type SlotName = (typeof SLOT_NAMES)[number];
export type SlotOverrides = Partial<Record<SlotName, ComponentType>>;
