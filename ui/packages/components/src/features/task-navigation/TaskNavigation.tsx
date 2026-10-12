/** Session task switcher. Switching is local navigation and never stops server work. */
import { statusKey } from "@e-agent/ui-core";
import { useController, useI18n, useRunState, useSurface } from "@e-agent/ui-react";
import { ActionButton } from "../../primitives/ActionButton.tsx";

export function TaskNavigation({
  onOpen,
}: {
  /**
   * How a host opens a previous task. A routed host passes a navigation request so
   * its route stays the one place that attaches; without it the controller attaches.
   */
  onOpen?: (runId: string) => void;
} = {}) {
  const { t } = useI18n();
  const { history, runId, busy } = useRunState();
  const controller = useController();
  // Expand recent work only in the workspace rail. Embedded surfaces keep the
  // task in view even when a wide host gives the panel plenty of space.
  const surface = useSurface();
  const expandedHistory = surface?.mode === "full-page" && !surface.compact;
  return (
    <nav className="ea-task-nav" aria-label={t("workspace.recent")}>
      <ActionButton
        className="ea-button-new"
        isDisabled={busy}
        onPress={() => controller.newTask()}
        data-testid="new-task"
      >
        <span aria-hidden="true">＋</span>
        {t("workspace.new")}
      </ActionButton>
      <details className="ea-task-history" open={expandedHistory || undefined}>
        <summary>{t("workspace.recent")}</summary>
        {history.length === 0 ? (
          <p className="ea-muted ea-small">{t("workspace.noHistory")}</p>
        ) : (
          <ul>
            {history.map(h => (
              <li key={h.runId}>
                <ActionButton
                  variant="quiet"
                  className="ea-task-link"
                  aria-current={h.runId === runId ? "page" : undefined}
                  isDisabled={busy}
                  onPress={() => (onOpen ? onOpen(h.runId) : void controller.attach(h.runId))}
                  data-testid="history-task"
                >
                  <span>{h.task}</span>
                  <small>{t(statusKey(h.state))}</small>
                </ActionButton>
              </li>
            ))}
          </ul>
        )}
        <p className="ea-muted ea-nav-hint">{t("workspace.historyHint")}</p>
      </details>
    </nav>
  );
}
