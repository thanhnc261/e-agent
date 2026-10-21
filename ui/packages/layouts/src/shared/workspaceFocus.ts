/**
 * L7-internal companion of the artifact workspace controls: whether the last open asked for
 * focus (a user's open moves focus to the workspace heading; an automatic one never moves
 * it, EA-16), and a quiet dismissal for a workspace whose run left the thread.
 */
import { createContext, useContext } from "react";

export interface WorkspaceFocus {
  /** True once after a user's open: the workspace then focuses its heading. */
  take(): boolean;
  /** Close without moving focus or touching the decision (the run is no longer shown). */
  dismiss(): void;
}

const WorkspaceFocusContext = createContext<WorkspaceFocus>({ take: () => false, dismiss: () => {} });

export const WorkspaceFocusProvider = WorkspaceFocusContext.Provider;

export function useWorkspaceFocus(): WorkspaceFocus {
  return useContext(WorkspaceFocusContext);
}
