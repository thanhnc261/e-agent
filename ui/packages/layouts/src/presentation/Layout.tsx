/**
 * Presentation owner (L7): validates and remembers the selected surface, theme,
 * appearance and density, and keeps the controller above the swap so the draft and
 * the active run survive it. A new surface always requires a fresh explicit
 * confirmation. Host document attributes are applied by L8 through `onPresentation`;
 * no component below reads or mutates its host document.
 */
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode, type Ref } from "react";
import { ArtifactWorkspaceProvider, type ArtifactWorkspaceControls } from "@e-agent/components";
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
import { WorkspaceFocusProvider } from "../shared/workspaceFocus.ts";

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
  // The closable artifact workspace (EA-10, ADR 0034 §1): one owner, above the surface swap,
  // so a surface change keeps it. Closing resets an open confirmation to review (EA-9) and
  // gives focus back to the control that opened it, or to its run card's Open.
  const [workspaceRun, setWorkspaceRun] = useState<string | null>(null);
  // Each user's open, counted, so opening the run already shown still focuses its workspace.
  const [requests, setRequests] = useState(0);
  const opener = useRef<HTMLElement | null>(null);
  const focusRequested = useRef(false);
  // What already opened by itself: kept here, not in the surface, so remounting a surface
  // cannot reopen a workspace the user closed.
  const autoOpened = useRef(new Set<string>());
  const openRun = useRef<string | null>(null);
  openRun.current = workspaceRun;
  const close = useCallback(() => {
    controller.back();
    const current = openRun.current;
    setWorkspaceRun(null);
    if (!current) return;
    requestAnimationFrame(() => {
      const card = surfaceRef.current?.querySelector<HTMLElement>(`[data-open-run="${CSS.escape(current)}"]`);
      (opener.current?.isConnected ? opener.current : card)?.focus();
    });
  }, [controller]);
  const artifactWorkspace = useMemo<ArtifactWorkspaceControls>(
    () => ({
      runId: workspaceRun,
      open: (runId, from) => {
        opener.current = from ?? null;
        focusRequested.current = !!from;
        if (from) setRequests(n => n + 1);
        setWorkspaceRun(runId);
      },
      close,
    }),
    [workspaceRun, close],
  );
  const focus = useMemo(
    () => ({
      requests,
      take: () => {
        const requested = focusRequested.current;
        focusRequested.current = false;
        return requested;
      },
      dismiss: () => setWorkspaceRun(null),
      claimAutoOpen: (key: string) => {
        if (autoOpened.current.has(key)) return false;
        autoOpened.current.add(key);
        return true;
      },
    }),
    [requests],
  );
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
        <ArtifactWorkspaceProvider value={artifactWorkspace}>
          <WorkspaceFocusProvider value={focus}>{surface}</WorkspaceFocusProvider>
        </ArtifactWorkspaceProvider>
      </SurfaceProvider>
    </PresentationProvider>
  );
}
