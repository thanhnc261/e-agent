/**
 * Presentation settings supplied by L7. This context carries placement and
 * appearance only; it never holds run, approval or capability state.
 */
import { createContext, useContext, type ReactNode } from "react";

export const SURFACE_MODES = ["overlay", "workbench", "sidebar", "full-page"] as const;
export type SurfaceMode = (typeof SURFACE_MODES)[number];

export interface SurfaceControls {
  mode: SurfaceMode;
  available: readonly SurfaceMode[];
  change: (mode: SurfaceMode) => void;
  focusOnMount: boolean;
  /**
   * Semantic width of the surface's own container, measured and owned by L7. A
   * docked column is compact on a wide monitor, so components must read this
   * instead of querying the window or walking up the DOM.
   */
  compact: boolean;
}

const SurfaceContext = createContext<SurfaceControls | null>(null);

export function SurfaceProvider({ value, children }: { value: SurfaceControls; children: ReactNode }) {
  return <SurfaceContext.Provider value={value}>{children}</SurfaceContext.Provider>;
}

export function useSurface(): SurfaceControls | null {
  return useContext(SurfaceContext);
}
