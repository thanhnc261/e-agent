/**
 * L5 React bindings. Holds no state of its own: everything comes from the ui-core
 * RunController through useSyncExternalStore, so every React UI sees the same run.
 * This entry file is the public surface; implementations live beside it by concern.
 */
export { RunProvider, useController } from "./providers/RunProvider.tsx";
export { useRun, useRunState, useTimeline } from "./hooks/useRunState.ts";
export { usePendingApproval } from "./hooks/useApproval.ts";
export { useComposer } from "./hooks/useComposer.ts";
export { useConnections, useTaskCatalog } from "./hooks/useDiscovery.ts";
export { useI18n } from "./hooks/useI18n.ts";
export { SLOT_NAMES, type SlotName, type SlotOverrides } from "./slots/names.ts";
export { Slot, SlotProvider } from "./slots/SlotProvider.tsx";
export {
  PRESENTATION_DIMENSIONS,
  PresentationProvider,
  usePresentation,
  type PresentationControls,
  type PresentationDimension,
} from "./presentation/presentation.tsx";
export {
  SURFACE_MODES,
  SurfaceProvider,
  useSurface,
  type SurfaceControls,
  type SurfaceMode,
} from "./presentation/surface.tsx";
