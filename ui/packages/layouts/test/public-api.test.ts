/**
 * Public surface inventory (enterprise overlay adoption plan FE-00). Extraction and
 * recomposition must not silently drop or rename an export, a slot name or a surface
 * mode that an existing host or a replacement UI already depends on.
 */
import { describe, expect, it } from "vitest";
import * as components from "@e-agent/components";
import * as layouts from "../src/index.tsx";
import * as uiReact from "@e-agent/ui-react";

const names = (module: object): string[] => Object.keys(module).sort();

describe("public UI exports", () => {
  it("keeps the L6 component surface", () => {
    expect(names(components)).toEqual([
      "ARTIFACT_WORKSPACE_ID",
      "ActionButton",
      "ApprovalPanel",
      "ArtifactWorkspaceProvider",
      "BUTTON_VARIANTS",
      "BrandMark",
      "CarriedRuns",
      "Composer",
      "ConnectionCard",
      "ConnectionStatus",
      "Connections",
      "Disclosure",
      "EvidencePanel",
      "Footer",
      "Header",
      "Icon",
      "MessageText",
      "Messages",
      "OutcomePanel",
      "Panel",
      "STATUS_TONES",
      "SURFACE_TONES",
      "StatusBadge",
      "Surface",
      "TaskCatalog",
      "TaskCatalogCard",
      "TaskNavigation",
      "TaskOverview",
      "TextAreaField",
      "Timeline",
      "defaultSlots",
      "runStateTone",
      "statusMarker",
      "useArtifactWorkspace",
    ]);
  });

  it("keeps the L5 binding surface", () => {
    expect(names(uiReact)).toEqual([
      "PRESENTATION_DIMENSIONS",
      "PresentationProvider",
      "RunProvider",
      "SLOT_NAMES",
      "SURFACE_MODES",
      "Slot",
      "SlotProvider",
      "SurfaceProvider",
      "useComposer",
      "useConnections",
      "useController",
      "useI18n",
      "usePendingApproval",
      "usePresentation",
      "useRun",
      "useRunState",
      "useSurface",
      "useTaskCatalog",
      "useTimeline",
    ]);
  });

  it("keeps the L7 layout surface", () => {
    expect(names(layouts)).toEqual([
      "FullPageLayout",
      "LAYOUTS",
      "Layout",
      "LayoutConfigError",
      "OverlayLayout",
      "PRESENTATION_DEFAULTS",
      "PRESENTATION_OPTIONS",
      "SidebarLayout",
      "parseLayoutConfig",
      "resolvePresentation",
    ]);
  });

  it("keeps every slot name a host may override", () => {
    expect([...uiReact.SLOT_NAMES]).toEqual([
      "header",
      "navigation",
      "task-overview",
      "composer",
      "messages",
      "timeline",
      "approval",
      "evidence",
      "outcome",
      "connection-status",
      "footer",
    ]);
    expect(Object.keys(components.defaultSlots).sort()).toEqual([...uiReact.SLOT_NAMES].sort());
  });

  it("keeps the selectable surface modes", () => {
    expect([...uiReact.SURFACE_MODES]).toEqual(["overlay", "workbench", "sidebar", "full-page"]);
    expect([...layouts.LAYOUTS]).toEqual([...uiReact.SURFACE_MODES]);
  });
});
