/**
 * Presentation owner (L7): validates and remembers the selected surface, theme,
 * appearance and density, and keeps the controller above the swap so the draft and
 * the active run survive it. A new surface always requires a fresh explicit
 * confirmation. Host document attributes are applied by L8 through `onPresentation`;
 * no component below reads or mutates its host document.
 */
import { useEffect, useRef, useState, type ReactNode, type Ref } from "react";
import {
  PresentationProvider,
  SURFACE_MODES,
  SurfaceProvider,
  useController,
  useRunState,
  type PresentationDimension,
  type SurfaceMode,
} from "@e-agent/ui-react";
import type { LayoutConfig } from "../config.ts";
import { FullPageLayout } from "../full-page/FullPageLayout.tsx";
import { OverlayLayout } from "../overlay/OverlayLayout.tsx";
import { SidebarLayout } from "../sidebar/SidebarLayout.tsx";
import {
  PRESENTATION_OPTIONS,
  resolvePresentation,
  storePreference,
  type PresentationConfig,
  type PresentationValues,
} from "./preferences.ts";
import { isCompact, useContainerWidth } from "./useContainerWidth.ts";

/** What L8 needs to reflect on its document or shadow host. */
export interface HostPresentation extends PresentationValues {
  locale: string;
}

export function Layout({
  config,
  embedded = false,
  restorePreference = true,
  preferenceKey = "e-agent.surface.web",
  presentation = {},
  onPresentation,
  workspace,
}: {
  config: LayoutConfig;
  embedded?: boolean;
  restorePreference?: boolean;
  preferenceKey?: string;
  /** Host-pinned presentation values. A pinned dimension is not user-selectable. */
  presentation?: PresentationConfig;
  onPresentation?: (presentation: HostPresentation) => void;
  /**
   * Page body for the standalone (full-page) surface only. Every other placement is
   * the task surface, so a host page composition can never displace the decision.
   */
  workspace?: ReactNode;
}) {
  const controller = useController();
  const { locale } = useRunState();
  // One measured element per surface. Components read the derived `compact` value
  // instead of querying the window or inspecting their ancestors.
  const surfaceRef = useRef<HTMLElement | null>(null);
  const compact = isCompact(useContainerWidth(surfaceRef));
  const available: readonly SurfaceMode[] = embedded
    ? SURFACE_MODES.filter(mode => mode !== "full-page")
    : SURFACE_MODES;
  const [mode, setMode] = useState<SurfaceMode>(() => {
    if (restorePreference) {
      try {
        const saved = sessionStorage.getItem(preferenceKey);
        if (available.includes(saved as SurfaceMode)) return saved as SurfaceMode;
      } catch {
        /* Storage is optional. */
      }
    }
    return available.includes(config.layout) ? config.layout : "overlay";
  });
  const [switched, setSwitched] = useState(false);
  const initialConfig = useRef(config.layout);

  const pinned = JSON.stringify(presentation);
  const [resolved, setResolved] = useState(() =>
    resolvePresentation(presentation, preferenceKey, restorePreference),
  );
  const lastPinned = useRef(pinned);
  useEffect(() => {
    if (lastPinned.current === pinned) return;
    lastPinned.current = pinned;
    setResolved(resolvePresentation(presentation, preferenceKey, restorePreference));
  }, [pinned, preferenceKey, restorePreference]);

  useEffect(() => {
    onPresentation?.({ ...resolved.values, locale });
  }, [resolved.values, locale, onPresentation]);

  const setPresentation = (dimension: PresentationDimension, value: string) => {
    if (resolved.locked[dimension] || !PRESENTATION_OPTIONS[dimension].includes(value)) return;
    setResolved(current => ({ ...current, values: { ...current.values, [dimension]: value } }));
    storePreference(preferenceKey, dimension, value);
  };

  useEffect(() => {
    if (initialConfig.current === config.layout) return;
    initialConfig.current = config.layout;
    controller.back();
    setMode(available.includes(config.layout) ? config.layout : "overlay");
    setSwitched(true);
  }, [config.layout, controller]);
  const change = (next: SurfaceMode) => {
    if (!available.includes(next) || next === mode) return;
    controller.back(); // A new review surface always requires a fresh explicit confirmation.
    setMode(next);
    setSwitched(true);
    try {
      sessionStorage.setItem(preferenceKey, next);
    } catch {
      /* Storage is optional. */
    }
  };
  const selected = { ...config, layout: mode };
  const surface =
    mode === "overlay" || mode === "workbench" ? (
      <OverlayLayout
        key={mode}
        config={selected}
        initiallyOpen={switched}
        surfaceRef={surfaceRef as Ref<HTMLDivElement>}
      />
    ) : mode === "sidebar" ? (
      <SidebarLayout config={selected} surfaceRef={surfaceRef} />
    ) : (
      <FullPageLayout
        config={selected}
        surfaceRef={surfaceRef as Ref<HTMLDivElement>}
        workspace={workspace}
      />
    );
  return (
    <PresentationProvider
      value={{
        value: resolved.values,
        options: PRESENTATION_OPTIONS,
        locked: resolved.locked,
        set: setPresentation,
      }}
    >
      <SurfaceProvider value={{ mode, available, change, focusOnMount: switched, compact }}>
        {surface}
      </SurfaceProvider>
    </PresentationProvider>
  );
}
