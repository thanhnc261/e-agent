/**
 * The closable artifact workspace's controls (EA-10, ADR 0034 §1). L7 owns the state, above
 * the surface swap, and provides it here; run cards only ask it to open or close a run's
 * artifact. Presentation only: opening or closing never submits, decides or chooses anything.
 */
import { createContext, useContext } from "react";

/** The id of the workspace region, for a run card's `aria-controls` while it is open. */
export const ARTIFACT_WORKSPACE_ID = "ea-artifact-workspace";

export interface ArtifactWorkspaceControls {
  /** The run whose artifact is open, or null while the workspace is closed. */
  runId: string | null;
  /**
   * Open a run's artifact. `opener` is the control that asked: the workspace takes focus to
   * its heading, and gives it back to `opener` when it closes.
   */
  open(runId: string, opener?: HTMLElement | null): void;
  close(): void;
}

const ArtifactWorkspaceContext = createContext<ArtifactWorkspaceControls | null>(null);

export const ArtifactWorkspaceProvider = ArtifactWorkspaceContext.Provider;

/** Null outside a layout that offers the workspace (for example a host's own composition). */
export function useArtifactWorkspace(): ArtifactWorkspaceControls | null {
  return useContext(ArtifactWorkspaceContext);
}
