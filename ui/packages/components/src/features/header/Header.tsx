/**
 * Product identity, stream status and the presentation/locale controls. The task's
 * own status lives with the task, above the composer (RunStatus), not up here. The header
 * reads and sets presentation through the L7-owned context; applying it to the host
 * document is L8's job, so this component never inspects its own root node.
 */
import { useEffect, useRef } from "react";
import { selectThreadShown } from "@e-agent/ui-core";
import { useI18n, useRunState, useSurface, type SurfaceMode } from "@e-agent/ui-react";
import { BrandMark } from "../../primitives/BrandMark.tsx";
import { Preferences } from "./Preferences.tsx";
import { ConnectionStatus } from "./ConnectionStatus.tsx";

export function Header() {
  const { t } = useI18n();
  const surface = useSurface();
  const state = useRunState();
  const { busy } = state;
  const viewRef = useRef<HTMLSelectElement>(null);
  useEffect(() => {
    if (surface?.focusOnMount) viewRef.current?.focus();
  }, []);
  return (
    <header className="ea-header">
      <div className="ea-brand">
        <BrandMark />
        <span>e-agent</span>
      </div>
      <div className="ea-header-tools">
        {/* In the thread the stream status sits in the thread head, at every width (S-2). */}
        {!selectThreadShown(state) && <ConnectionStatus />}
        {surface && (
          <select
            ref={viewRef}
            className="ea-view-switch"
            aria-label={t("controls.view")}
            title={t("controls.view")}
            value={surface.mode}
            disabled={busy}
            onChange={e => surface.change(e.target.value as SurfaceMode)}
            data-testid="view-switch"
          >
            {surface.available.map(mode => (
              <option key={mode} value={mode}>
                {t(`view.${mode}`)}
              </option>
            ))}
          </select>
        )}
        <Preferences />
      </div>
    </header>
  );
}
