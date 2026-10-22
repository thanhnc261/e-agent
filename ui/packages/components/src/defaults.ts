/** Built-in slot map. Hosts override any entry through SlotProvider. */
import type { SlotOverrides } from "@e-agent/ui-react";
import { Activity } from "./containers/Activity.tsx";
import { ApprovalPanel } from "./features/approval/ApprovalPanel.tsx";
import { Composer } from "./features/composer/Composer.tsx";
import { ConnectionStatus } from "./features/header/ConnectionStatus.tsx";
import { EvidencePanel } from "./features/evidence/EvidencePanel.tsx";
import { Footer } from "./features/footer/Footer.tsx";
import { Header } from "./features/header/Header.tsx";
import { Messages } from "./features/conversation/Messages.tsx";
import { OutcomePanel } from "./features/outcome/OutcomePanel.tsx";
import { TaskNavigation } from "./features/task-navigation/TaskNavigation.tsx";
import { TaskOverview } from "./features/task-overview/TaskOverview.tsx";

export const defaultSlots = {
  header: Header,
  navigation: TaskNavigation,
  "task-overview": TaskOverview,
  composer: Composer,
  messages: Messages,
  timeline: Activity,
  approval: ApprovalPanel,
  evidence: EvidencePanel,
  outcome: OutcomePanel,
  "connection-status": ConnectionStatus,
  footer: Footer,
} as const satisfies Required<SlotOverrides>;
