/**
 * L5 controller context. The provider holds no state of its own: every value comes
 * from the ui-core RunController, so React and vanilla hosts observe the same run.
 */
import { createContext, useContext, type ReactNode } from "react";
import type { RunController } from "@e-agent/ui-core";

const ControllerContext = createContext<RunController | null>(null);

export function RunProvider({ controller, children }: { controller: RunController; children: ReactNode }) {
  return <ControllerContext.Provider value={controller}>{children}</ControllerContext.Provider>;
}

export function useController(): RunController {
  const c = useContext(ControllerContext);
  if (!c) throw new Error("RunProvider is missing");
  return c;
}
