/** Docked column beside host content: the shared task surface, stacked. */
import type { Ref } from "react";
import type { LayoutConfig } from "../config.ts";
import { ConfiguredSlot } from "../shared/ConfiguredSlot.tsx";
import { TaskSurface } from "../shared/TaskSurface.tsx";

export function SidebarLayout({
  config,
  surfaceRef,
}: {
  config: LayoutConfig;
  surfaceRef?: Ref<HTMLElement>;
}) {
  return (
    <aside
      className={`ea-root ea-layout ea-layout-sidebar ea-side-${config.side ?? "right"}`}
      data-layout="sidebar"
      ref={surfaceRef}
    >
      <ConfiguredSlot name="header" config={config} />
      <TaskSurface config={config} variant="stack" />
      <ConfiguredSlot name="footer" config={config} />
    </aside>
  );
}
