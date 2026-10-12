import { useSyncExternalStore } from "react";
import { selectTimeline, type ControllerState, type TimelineItem } from "@e-agent/ui-core";
import { useController } from "../providers/RunProvider.tsx";

/** The whole controller snapshot. Stable between notifications. */
export function useRunState(): ControllerState {
  const c = useController();
  return useSyncExternalStore(c.subscribe, c.getState, c.getState);
}

export function useRun() {
  const s = useRunState();
  return {
    runId: s.runId,
    run: s.view.run,
    actions: s.view.actions,
    finalMessage: s.view.finalMessage,
    streamingText: s.view.streamingText,
    question: s.view.question,
    error: s.error,
  };
}

export function useTimeline(): TimelineItem[] {
  return selectTimeline(useRunState().view);
}
