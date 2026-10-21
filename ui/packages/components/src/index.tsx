/**
 * L6 default host-neutral task UI. Business authority remains in the server/core.
 * This entry file is the public surface; implementations live under `features/`
 * and `primitives/` so a host can replace one view without forking the package.
 */
export { ApprovalPanel } from "./features/approval/ApprovalPanel.tsx";
export { Composer } from "./features/composer/Composer.tsx";
export { ConnectionCard, Connections } from "./features/discovery/Connections.tsx";
export { TaskCatalog, TaskCatalogCard } from "./features/discovery/TaskCatalog.tsx";
export { ConnectionStatus } from "./features/header/ConnectionStatus.tsx";
export { EvidencePanel } from "./features/evidence/EvidencePanel.tsx";
export { Footer } from "./features/footer/Footer.tsx";
export { Header } from "./features/header/Header.tsx";
export { MessageText } from "./features/conversation/MessageText.tsx";
export { Messages } from "./features/conversation/Messages.tsx";
export {
  ARTIFACT_WORKSPACE_ID,
  ArtifactWorkspaceProvider,
  useArtifactWorkspace,
  type ArtifactWorkspaceControls,
} from "./features/conversation/workspace.ts";
export { OutcomePanel } from "./features/outcome/OutcomePanel.tsx";
export { TaskNavigation } from "./features/task-navigation/TaskNavigation.tsx";
export { TaskOverview } from "./features/task-overview/TaskOverview.tsx";
export { Timeline } from "./features/timeline/Timeline.tsx";
export { defaultSlots } from "./defaults.ts";

/** Reusable primitives. A replacement UI composes these instead of forking a feature. */
export { ActionButton, type ActionButtonProps } from "./primitives/ActionButton.tsx";
export { BrandMark } from "./primitives/BrandMark.tsx";
export { Icon } from "./primitives/Icon.tsx";
export { Disclosure } from "./primitives/Disclosure.tsx";
export { Panel } from "./primitives/Panel.tsx";
export { StatusBadge, statusMarker } from "./primitives/StatusBadge.tsx";
export { runStateTone } from "./primitives/runStateTone.ts";
export { Surface } from "./primitives/Surface.tsx";
export { TextAreaField } from "./primitives/TextAreaField.tsx";
export {
  BUTTON_VARIANTS,
  STATUS_TONES,
  SURFACE_TONES,
  type ButtonVariant,
  type StatusTone,
  type SurfaceTone,
} from "./primitives/variants.ts";
