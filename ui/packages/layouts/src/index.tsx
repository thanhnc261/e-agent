/**
 * L7 layouts: presets that arrange named slots. A layout config can hide slots or
 * reorder columns but cannot remove the approval surface while one is pending.
 */
import { useEffect, useState, type ComponentType } from "react";
import { Button } from "react-aria-components";
import { defaultSlots } from "@e-agent/components";
import { Slot, SLOT_NAMES, useI18n, usePendingApproval, type SlotName } from "@e-agent/ui-react";

export const LAYOUTS = ["overlay", "sidebar", "full-page"] as const;
export type LayoutName = (typeof LAYOUTS)[number];

export interface LayoutConfig {
  layout: LayoutName;
  slots?: Partial<Record<SlotName, { hidden?: boolean }>>;
  /** sidebar only */
  side?: "left" | "right";
}

export class LayoutConfigError extends Error {}

/** Validate untrusted layout config (e.g. from an element attribute or JSON file). */
export function parseLayoutConfig(input: unknown): LayoutConfig {
  if (typeof input !== "object" || input === null) throw new LayoutConfigError("layout config must be an object");
  const raw = input as Record<string, unknown>;
  const allowed = new Set(["layout", "slots", "side"]);
  for (const key of Object.keys(raw)) if (!allowed.has(key)) throw new LayoutConfigError(`unknown key ${key}`);
  if (!LAYOUTS.includes(raw["layout"] as LayoutName)) throw new LayoutConfigError("unknown layout");
  const config: LayoutConfig = { layout: raw["layout"] as LayoutName };
  if (raw["side"] !== undefined) {
    if (raw["side"] !== "left" && raw["side"] !== "right") throw new LayoutConfigError("side must be left or right");
    config.side = raw["side"];
  }
  if (raw["slots"] !== undefined) {
    if (typeof raw["slots"] !== "object" || raw["slots"] === null) throw new LayoutConfigError("slots must be an object");
    const slots: LayoutConfig["slots"] = {};
    for (const [name, value] of Object.entries(raw["slots"] as Record<string, unknown>)) {
      if (!(SLOT_NAMES as readonly string[]).includes(name)) throw new LayoutConfigError(`unknown slot ${name}`);
      const v = value as Record<string, unknown>;
      if (typeof v !== "object" || v === null || (v["hidden"] !== undefined && typeof v["hidden"] !== "boolean")) {
        throw new LayoutConfigError(`invalid slot config for ${name}`);
      }
      slots[name as SlotName] = { hidden: v["hidden"] === true };
    }
    config.slots = slots;
  }
  return config;
}

function S({ name, config }: { name: SlotName; config: LayoutConfig }) {
  const approval = usePendingApproval();
  const hidden = config.slots?.[name]?.hidden === true;
  // Hiding the approval slot is honored only while nothing awaits a decision.
  if (hidden && !(name === "approval" && approval.phase !== "idle")) return null;
  return <Slot name={name} fallback={defaultSlots[name] as ComponentType} />;
}

export function FullPageLayout({ config }: { config: LayoutConfig }) {
  return (
    <div className="ea-root ea-layout ea-layout-full" data-layout="full-page">
      <S name="header" config={config} />
      <main className="ea-columns">
        <div className="ea-column">
          <S name="messages" config={config} />
          <S name="composer" config={config} />
        </div>
        <div className="ea-column">
          <S name="approval" config={config} />
          <S name="timeline" config={config} />
        </div>
        <div className="ea-column">
          <S name="outcome" config={config} />
          <S name="evidence" config={config} />
        </div>
      </main>
      <S name="footer" config={config} />
    </div>
  );
}

function Stack({ config }: { config: LayoutConfig }) {
  return (
    <div className="ea-stack">
      <S name="messages" config={config} />
      <S name="approval" config={config} />
      <S name="composer" config={config} />
      <S name="outcome" config={config} />
      <S name="timeline" config={config} />
      <S name="evidence" config={config} />
    </div>
  );
}

export function SidebarLayout({ config }: { config: LayoutConfig }) {
  return (
    <aside className={`ea-root ea-layout ea-layout-sidebar ea-side-${config.side ?? "right"}`} data-layout="sidebar">
      <S name="header" config={config} />
      <Stack config={config} />
      <S name="footer" config={config} />
    </aside>
  );
}

export function OverlayLayout({ config, initiallyOpen = false }: { config: LayoutConfig; initiallyOpen?: boolean }) {
  const { t } = useI18n();
  const approval = usePendingApproval();
  const [open, setOpen] = useState(initiallyOpen);
  const pendingId = approval.phase === "idle" ? null : approval.presentation?.action_id;
  useEffect(() => {
    if (pendingId) setOpen(true); // surface each new approval once; the user may close it
  }, [pendingId]);
  const expanded = open;
  return (
    <div className="ea-root ea-layout ea-layout-overlay" data-layout="overlay" data-open={expanded}>
      {expanded && (
        <div className="ea-overlay-panel" role="dialog" aria-label={t("app.title")} data-testid="overlay-panel">
          <S name="header" config={config} />
          <Stack config={config} />
        </div>
      )}
      <Button
        className="ea-button ea-button-primary ea-launcher"
        onPress={() => setOpen(!expanded)}
        aria-expanded={expanded}
        data-testid="overlay-launcher"
      >
        {expanded ? t("overlay.close") : t("overlay.open")}
      </Button>
    </div>
  );
}

export function Layout({ config }: { config: LayoutConfig }) {
  if (config.layout === "overlay") return <OverlayLayout config={config} />;
  if (config.layout === "sidebar") return <SidebarLayout config={config} />;
  return <FullPageLayout config={config} />;
}
