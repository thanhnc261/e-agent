/**
 * Standalone workspace: a navigation rail beside the page body. The body defaults
 * to the shared task surface; a host (L8) may supply its own page composition for
 * this surface, which is how standalone routes are rendered without the layout
 * knowing anything about routing.
 *
 * A host page is a presentation choice and is honored only while no decision is
 * outstanding: a review the user still owns always keeps the task surface. A
 * recorded decision does not hold them there.
 */
import type { ReactNode, Ref } from "react";
import { isAwaitingDecision } from "@e-agent/ui-core";
import { usePendingApproval } from "@e-agent/ui-react";
import type { LayoutConfig } from "../config.ts";
import { ConfiguredSlot } from "../shared/ConfiguredSlot.tsx";
import { TaskSurface } from "../shared/TaskSurface.tsx";

export function FullPageLayout({
  config,
  surfaceRef,
  workspace,
}: {
  config: LayoutConfig;
  /** L7 measures this element to derive the surface's semantic width. */
  surfaceRef?: Ref<HTMLDivElement>;
  /** Host-supplied page body for this surface; defaults to the task surface. */
  workspace?: ReactNode;
}) {
  const approval = usePendingApproval();
  const body = isAwaitingDecision(approval.phase) ? undefined : workspace;
  return (
    <div className="ea-root ea-layout ea-layout-full" ref={surfaceRef}>
      <ConfiguredSlot name="header" config={config} />
      <div className="ea-workspace">
        <ConfiguredSlot name="navigation" config={config} />
        {body ?? <TaskSurface config={config} variant="page" navigation={false} />}
      </div>
      <ConfiguredSlot name="footer" config={config} />
    </div>
  );
}
