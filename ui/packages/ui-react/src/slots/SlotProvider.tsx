import { createContext, useContext, type ComponentType, type ReactNode } from "react";
import type { SlotName, SlotOverrides } from "./names.ts";

const SlotContext = createContext<SlotOverrides>({});

export function SlotProvider({ overrides, children }: { overrides: SlotOverrides; children: ReactNode }) {
  return <SlotContext.Provider value={overrides}>{children}</SlotContext.Provider>;
}

/** Render the override for ``name`` if one is registered, else the default. */
export function Slot({ name, fallback: Fallback }: { name: SlotName; fallback: ComponentType }) {
  const Override = useContext(SlotContext)[name];
  const Component = Override ?? Fallback;
  return (
    <div className="ea-slot" data-slot={name}>
      <Component />
    </div>
  );
}
