/**
 * A task route that could not be opened. The run may not exist, may have been
 * deleted, or may simply not be visible to this principal — the server does not
 * distinguish those, and neither does this page.
 *
 * It is a terminal state on purpose: retrying automatically would hammer the API
 * for a run that is not coming back. Recovery is a deliberate act by the user.
 */
import { ActionButton, Surface } from "@e-agent/components";
import { useI18n } from "@e-agent/ui-react";
import type { Navigate } from "../app/useRouter.ts";

export function TaskUnavailable({ runId, navigate }: { runId: string; navigate: Navigate }) {
  const { t } = useI18n();
  return (
    <main className="ea-workarea" data-testid="page-task-unavailable">
      <div className="ea-conversation">
        <Surface as="section" tone="attention" className="ea-scope-card" data-testid="task-unavailable">
          <h2 className="ea-panel-title">{t("task.unavailable")}</h2>
          <p className="ea-small">{t("task.unavailableBody")}</p>
          <p className="ea-small ea-muted ea-catalog-id">{runId}</p>
          <div className="ea-actions">
            <ActionButton
              variant="primary"
              data-testid="task-unavailable-overview"
              onPress={() => navigate({ name: "overview" })}
            >
              {t("nav.back")}
            </ActionButton>
          </div>
        </Surface>
      </div>
    </main>
  );
}
