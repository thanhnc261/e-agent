/**
 * L7-internal companion of the artifact workspace controls: whether the last open asked for
 * focus (a user's open moves focus to the workspace heading; an automatic one never moves
 * it, EA-16), a quiet dismissal for a workspace whose run left the thread, and the memory
 * of what already opened by itself. Layout owns all of it, above the surface swap, so a
 * surface change never reopens a workspace the user closed (EA-10).
 */
import { createContext, useContext } from "react";

export interface WorkspaceFocus {
  /**
   * Counts the user's opens, so a repeated open of the run already shown still brings the
   * workspace forward (G-D 4.U5): the workspace re-reads `take()` when it changes.
   */
  requests: number;
  /** True once after a user's open: the workspace then focuses its heading. */
  take(): boolean;
  /** Close without moving focus or touching the decision (the run is no longer shown). */
  dismiss(): void;
  /** True the first time `key` (a decision or a result) asks to open by itself; then false. */
  claimAutoOpen(key: string): boolean;
}

const WorkspaceFocusContext = createContext<WorkspaceFocus>({
  requests: 0,
  take: () => false,
  dismiss: () => {},
  claimAutoOpen: () => false,
});

export const WorkspaceFocusProvider = WorkspaceFocusContext.Provider;

export function useWorkspaceFocus(): WorkspaceFocus {
  return useContext(WorkspaceFocusContext);
}
