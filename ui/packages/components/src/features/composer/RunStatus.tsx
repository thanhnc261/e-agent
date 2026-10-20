/**
 * The task's live status, shown where the user is working: directly above the
 * composer, with Stop beside it. Labels come from the server's run and action states
 * only (runStatusKey), and the badge is the polite live region for state changes.
 */
import { runStatusKey, selectPendingReply, TERMINAL_STATES } from "@e-agent/ui-core";
import { useController, useI18n, useRun, useRunState } from "@e-agent/ui-react";
import { ActionButton } from "../../primitives/ActionButton.tsx";
import { StatusBadge } from "../../primitives/StatusBadge.tsx";
import { runStateTone } from "../../primitives/runStateTone.ts";

export function RunStatus() {
  const { t } = useI18n();
  const { run, actions } = useRun();
  const controller = useController();
  const { view } = useRunState();
  if (!run) return null;
  const status = runStatusKey(run.state, actions, selectPendingReply(view), run.reason_code);
  // Stopping cannot change an effect that may already have happened, so an
  // unresolved outcome offers a check (in the result) instead of Stop.
  const stoppable = !TERMINAL_STATES.has(run.state) && run.state !== "NEEDS_RECONCILIATION";
  return (
    <div className="ea-run-status" data-testid="run-status">
      <StatusBadge
        tone={status === "status.phase.UNKNOWN" ? "unknown" : runStateTone(run.state, run.reason_code)}
        className={`ea-state-pill ea-state-${run.state.toLowerCase()}`}
        data-testid="run-state"
        data-state={run.state}
        data-phase={status.startsWith("status.phase.") ? status.slice(13) : undefined}
        role="status"
      >
        {t(status)}
      </StatusBadge>
      {stoppable && (
        <ActionButton variant="quiet" onPress={() => void controller.cancel()} data-testid="run-cancel">
          {t("run.cancel")}
        </ActionButton>
      )}
    </div>
  );
}
