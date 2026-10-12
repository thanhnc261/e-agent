/**
 * Floating and expanded placements. Minimizing keeps the run and draft; a pending
 * decision may reveal the surface but never confirms it, and Escape backs out of
 * confirmation before it closes anything.
 */
import { useEffect, useId, useRef, useState, type Ref } from "react";
import { Button } from "react-aria-components";
import { useController, useI18n, usePendingApproval } from "@e-agent/ui-react";
import { BrandMark } from "@e-agent/components";
import type { LayoutConfig } from "../config.ts";
import { ConfiguredSlot } from "../shared/ConfiguredSlot.tsx";
import { TaskSurface } from "../shared/TaskSurface.tsx";

export function OverlayLayout({
  config,
  initiallyOpen = false,
  surfaceRef,
}: {
  config: LayoutConfig;
  initiallyOpen?: boolean;
  /** Attached to the panel: the task surface is only laid out while it is open. */
  surfaceRef?: Ref<HTMLDivElement>;
}) {
  const { t } = useI18n();
  const approval = usePendingApproval();
  const controller = useController();
  const launcherRef = useRef<HTMLButtonElement>(null);
  const panelId = useId();
  const [open, setOpen] = useState(initiallyOpen);
  const pendingId = approval.phase === "idle" ? null : approval.presentation?.action_id;
  useEffect(() => {
    if (pendingId) setOpen(true); // surface each new approval once; the user may close it
  }, [pendingId]);
  const expanded = open;
  const workbench = config.layout === "workbench";
  const close = () => {
    controller.back();
    setOpen(false);
    requestAnimationFrame(() => launcherRef.current?.focus());
  };
  return (
    <div
      className={`ea-root ea-layout ea-layout-overlay ${workbench ? "ea-layout-workbench" : ""}`}
      data-layout={config.layout}
      data-open={expanded}
    >
      {expanded && (
        <div
          className="ea-overlay-panel"
          ref={surfaceRef}
          id={panelId}
          role="dialog"
          aria-label={t("app.title")}
          data-testid="overlay-panel"
          onKeyDown={e => {
            if (e.key === "Escape") {
              e.stopPropagation();
              if (approval.phase === "confirming") controller.back();
              else close();
            }
          }}
        >
          <ConfiguredSlot name="header" config={config} />
          <TaskSurface config={config} variant={workbench ? "split" : "stack"} />
        </div>
      )}
      <Button
        className="ea-button ea-button-primary ea-launcher"
        ref={launcherRef}
        onPress={() => (expanded ? close() : setOpen(true))}
        aria-controls={expanded ? panelId : undefined}
        aria-expanded={expanded}
        data-testid="overlay-launcher"
      >
        <BrandMark />
        {expanded ? t("overlay.close") : t("overlay.open")}
        {!expanded && approval.phase !== "idle" && !["approved", "rejected"].includes(approval.phase) && (
          <span className="ea-launcher-badge">{t("overlay.reviewBadge")}</span>
        )}
      </Button>
    </div>
  );
}
