/**
 * Slot rendering under a layout config. Hiding a slot is a presentation choice and
 * can never remove the approval surface while a decision is pending.
 */
import type { ComponentType } from "react";
import { defaultSlots } from "@e-agent/components";
import { Slot, usePendingApproval, type SlotName } from "@e-agent/ui-react";
import type { LayoutConfig } from "../config.ts";

export function ConfiguredSlot({ name, config }: { name: SlotName; config: LayoutConfig }) {
  const approval = usePendingApproval();
  const hidden = config.slots?.[name]?.hidden === true;
  // Hiding the approval slot is honored only while nothing awaits a decision.
  if (hidden && !(name === "approval" && approval.phase !== "idle")) return null;
  return <Slot name={name} fallback={defaultSlots[name] as ComponentType} />;
}
