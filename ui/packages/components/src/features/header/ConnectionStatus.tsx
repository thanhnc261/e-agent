/** Stream connectivity only. Never conflate with task state or integration availability. */
import { useI18n, useRunState } from "@e-agent/ui-react";

export function ConnectionStatus() {
  const { connection } = useRunState();
  const { t } = useI18n();
  return (
    <span className="ea-connection" data-testid="connection-status" data-status={connection} role="status">
      <span className="ea-dot" aria-hidden="true" />
      {t(`connection.${connection}`)}
    </span>
  );
}
