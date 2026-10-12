import { useEffect } from "react";
import type { ConnectionView, DiscoveryState, TaskTemplateView } from "@e-agent/ui-core";
import { useController } from "../providers/RunProvider.tsx";
import { useRunState } from "./useRunState.ts";

/**
 * Member discovery projections. Loading is requested once per mount and only for
 * the projection a view actually renders, so opening a page never causes provider
 * traffic or speculative requests.
 */
export function useConnections(load = true): DiscoveryState<ConnectionView> {
  const controller = useController();
  const state = useRunState().connections;
  useEffect(() => {
    if (load && state.kind === "idle") void controller.loadConnections();
  }, [load, state.kind, controller]);
  return state;
}

export function useTaskCatalog(load = true): DiscoveryState<TaskTemplateView> {
  const controller = useController();
  const state = useRunState().catalog;
  useEffect(() => {
    if (load && state.kind === "idle") void controller.loadTaskCatalog();
  }, [load, state.kind, controller]);
  return state;
}
