/**
 * The one task composition every placement uses: what the task is, the
 * conversation and composer, the exact decision, the result and the evidence.
 *
 * Region membership and order are decided here, once, so a placement chooses only
 * the geometry variant. It arranges slots: task, approval and evidence authority
 * stay in the core and the server, so no variant can drop the decision, separate it
 * from the terms it belongs to, or hide the result.
 */
import type { SlotName } from "@e-agent/ui-react";
import { useRun } from "@e-agent/ui-react";
import type { LayoutConfig } from "../config.ts";
import { ConfiguredSlot } from "./ConfiguredSlot.tsx";

/** Decision and result always travel with the conversation they belong to. */
const TASK_ORDER: SlotName[] = ["messages", "outcome", "approval", "composer"];
/** Secondary inspection. `task-overview` summarises the task shown beside it. */
const INSPECTOR_ORDER: SlotName[] = ["task-overview", "evidence", "timeline"];

/**
 * `page` is a wide workspace column with an inspector aside, `split` a two-column
 * panel, `stack` a single scrolling column with the inspector inline.
 */
export type SurfaceVariant = "page" | "split" | "stack";

function ordered(config: LayoutConfig, defaults: SlotName[]): SlotName[] {
  const requested = (config.order ?? []).filter(name => defaults.includes(name));
  return [...requested, ...defaults.filter(name => !requested.includes(name))];
}

export function TaskContent({ config }: { config: LayoutConfig }) {
  return (
    <>
      {ordered(config, TASK_ORDER).map(name => (
        <ConfiguredSlot key={name} name={name} config={config} />
      ))}
    </>
  );
}

function InspectorRegions({ config, withOverview }: { config: LayoutConfig; withOverview: boolean }) {
  return (
    <>
      {INSPECTOR_ORDER.filter(name => withOverview || name !== "task-overview").map(name => (
        <ConfiguredSlot key={name} name={name} config={config} />
      ))}
    </>
  );
}

export function TaskSurface({
  config,
  variant,
  navigation = true,
}: {
  config: LayoutConfig;
  variant: SurfaceVariant;
  /** Placements with their own navigation rail render it themselves. */
  navigation?: boolean;
}) {
  const { run } = useRun();
  const nav = navigation ? <ConfiguredSlot name="navigation" config={config} /> : null;

  if (variant === "page") {
    return (
      <main className={`ea-workarea ${run ? "ea-workarea-active" : ""}`}>
        <div className="ea-conversation">
          {nav}
          <TaskContent config={config} />
        </div>
        {run && (
          <aside className="ea-inspector">
            <InspectorRegions config={config} withOverview={false} />
          </aside>
        )}
      </main>
    );
  }

  if (variant === "split") {
    return (
      <div className="ea-workbench-body">
        <div className="ea-stack ea-workbench-main">
          {nav}
          <TaskContent config={config} />
        </div>
        <aside className="ea-workbench-inspector">
          <InspectorRegions config={config} withOverview />
        </aside>
      </div>
    );
  }

  return (
    <div className="ea-stack">
      {nav}
      <TaskContent config={config} />
      <InspectorRegions config={config} withOverview={false} />
    </div>
  );
}
