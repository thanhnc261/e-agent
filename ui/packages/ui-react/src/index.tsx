/**
 * L5 React bindings. Holds no state of its own: everything comes from the ui-core
 * RunController through useSyncExternalStore, so every React UI sees the same run.
 */
import { createContext, useContext, useSyncExternalStore, type ComponentType, type ReactNode } from "react";
import {
  canRequestApprove,
  selectTimeline,
  translate,
  type ControllerState,
  type Locale,
  type RunController,
  type TimelineItem,
} from "@e-agent/ui-core";

const ControllerContext = createContext<RunController | null>(null);

export function RunProvider({ controller, children }: { controller: RunController; children: ReactNode }) {
  return <ControllerContext.Provider value={controller}>{children}</ControllerContext.Provider>;
}

export function useController(): RunController {
  const c = useContext(ControllerContext);
  if (!c) throw new Error("RunProvider is missing");
  return c;
}

export function useRunState(): ControllerState {
  const c = useController();
  return useSyncExternalStore(c.subscribe, c.getState, c.getState);
}

export function useRun() {
  const s = useRunState();
  return { runId: s.runId, run: s.view.run, actions: s.view.actions, finalMessage: s.view.finalMessage, error: s.error };
}

export function useTimeline(): TimelineItem[] {
  return selectTimeline(useRunState().view);
}

export function usePendingApproval() {
  const c = useController();
  const s = useRunState();
  return {
    ...s.approval,
    canRequestApprove: canRequestApprove(s.approval),
    canConfirm: s.approval.phase === "confirming" && canRequestApprove(s.approval),
    requestConfirm: () => c.requestConfirm(),
    back: () => c.back(),
    reviewAgain: () => c.reviewAgain(),
    approve: () => c.approve(),
    reject: () => c.reject(),
  };
}

export function useComposer() {
  const c = useController();
  const s = useRunState();
  return { busy: s.busy, submit: (task: string) => c.start(task) };
}

export function useI18n(): { locale: Locale; t: (key: string) => string } {
  const locale = useRunState().locale;
  return { locale, t: (key: string) => translate(locale, key) };
}

// -- slot registry (UI architecture §4.4) ----------------------------------------
export const SLOT_NAMES = [
  "header",
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
