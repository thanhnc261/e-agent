/**
 * Narrow presentation context. L7 owns the values and their validation, L8 applies
 * them to its host document; L5 only carries them to the views. Nothing here is
 * business state: an appearance or density never changes rules or capabilities.
 */
import { createContext, useContext, type ReactNode } from "react";

export const PRESENTATION_DIMENSIONS = ["theme", "appearance", "density"] as const;
export type PresentationDimension = (typeof PRESENTATION_DIMENSIONS)[number];

export interface PresentationControls {
  /** Current value per dimension. Vocabularies are defined and validated by L7. */
  value: Record<PresentationDimension, string>;
  options: Record<PresentationDimension, readonly string[]>;
  /** A host-pinned dimension stays authoritative and is not offered as a choice. */
  locked: Record<PresentationDimension, boolean>;
  set: (dimension: PresentationDimension, value: string) => void;
}

const PresentationContext = createContext<PresentationControls | null>(null);

export function PresentationProvider({
  value,
  children,
}: {
  value: PresentationControls;
  children: ReactNode;
}) {
  return <PresentationContext.Provider value={value}>{children}</PresentationContext.Provider>;
}

export function usePresentation(): PresentationControls | null {
  return useContext(PresentationContext);
}
