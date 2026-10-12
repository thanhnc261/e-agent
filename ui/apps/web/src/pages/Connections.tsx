/**
 * Capabilities (ADR 0017 member projections): what e-agent can do in this workspace
 * and the connections it may use. Read-only by design: this workspace exposes no API
 * to connect, re-authorize, disable or repair a connection, so the page offers no
 * control that would imply one. An older server without the catalog keeps the honest,
 * non-specific statement instead of an empty list.
 */
import { Connections as ConnectionInventory, Surface, TaskCatalog } from "@e-agent/components";
import { useI18n, useTaskCatalog } from "@e-agent/ui-react";

export function ConnectionsPage() {
  const { t } = useI18n();
  const catalog = useTaskCatalog();
  return (
    <main className="ea-workarea" data-testid="page-connections">
      <div className="ea-inventory">
        {catalog.kind === "ready" ? (
          <TaskCatalog />
        ) : (
          <Surface as="section" tone="accent" className="ea-scope-card" data-testid="installed-scope">
            <h2 className="ea-panel-title">{t("overview.scope")}</h2>
            <p className="ea-small">{t("overview.scopeBody")}</p>
          </Surface>
        )}
        <ConnectionInventory />
      </div>
    </main>
  );
}
