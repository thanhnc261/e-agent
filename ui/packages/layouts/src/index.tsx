/**
 * L7 layouts: presets that arrange named slots. A layout config can hide slots or
 * reorder columns but cannot remove the approval surface while one is pending.
 * This entry file is the public surface; each placement lives in its own module.
 */
export {
  LAYOUTS,
  LayoutConfigError,
  parseLayoutConfig,
  type LayoutConfig,
  type LayoutName,
} from "./config.ts";
export { FullPageLayout } from "./full-page/FullPageLayout.tsx";
export { OverlayLayout } from "./overlay/OverlayLayout.tsx";
export { SidebarLayout } from "./sidebar/SidebarLayout.tsx";
export { Layout, type HostPresentation } from "./presentation/Layout.tsx";
export {
  PRESENTATION_DEFAULTS,
  PRESENTATION_OPTIONS,
  resolvePresentation,
  type PresentationConfig,
  type PresentationValues,
} from "./presentation/preferences.ts";
