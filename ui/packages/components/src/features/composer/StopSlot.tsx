/**
 * The stop slot under the thread's composer (4e.2 stop ruling, AG-CTRL-1). It names the
 * latest run and its status, and keeps Stop in one place: enabled while that run is active;
 * otherwise disabled with its visible reason, so it is never enabled and then failing
 * (AG-ENT-1). While a result is unconfirmed, Stop cannot change what may already have
 * happened, so the safe status check is offered instead (EA-4).
 */
import { useId } from "react";
import { isLiveEntry, selectStopControl, threadRunStatusKey, type ThreadRunEntry } from "@e-agent/ui-core";
import { useController, useI18n, useRunState } from "@e-agent/ui-react";
import { ActionButton } from "../../primitives/ActionButton.tsx";
import { StatusBadge } from "../../primitives/StatusBadge.tsx";
import { runStateTone } from "../../primitives/runStateTone.ts";

export function StopSlot({ latest, ordinal }: { latest: ThreadRunEntry | undefined; ordinal: number }) {
  const { t } = useI18n();
  const state = useRunState();
  const controller = useController();
  const reasonId = useId();
  const live = latest ? isLiveEntry(latest, state) : false;
  const runState = live ? state.view.run?.state : latest?.state;
  const reasonCode = live ? state.view.run?.reason_code : latest?.reasonCode;
  const control = live ? selectStopControl(runState) : { kind: "idle" as const };
  const status = latest ? threadRunStatusKey(latest, state) : null;
  return (
    <div className="ea-stop-slot" data-testid="stop-slot" data-control={control.kind}>
      {latest && status && (
        <span className="ea-stop-run">
          <span>
            {t("thread.run")} {ordinal}
          </span>
          <StatusBadge
            tone={status === "status.phase.UNKNOWN" ? "unknown" : runStateTone(runState, reasonCode)}
            data-testid="stop-slot-status"
          >
            {t(status)}
          </StatusBadge>
        </span>
      )}
      {control.kind === "active" ? (
        <ActionButton
          className="ea-button-stop"
          data-testid="stop"
          isDisabled={state.busy}
          onPress={() => void controller.cancel()}
        >
          <span className="ea-stop-square" aria-hidden="true" />
          {t("run.cancel")}
        </ActionButton>
      ) : (
        <span className="ea-stop-off">
          <ActionButton className="ea-button-stop" isDisabled data-testid="stop" aria-describedby={reasonId}>
            <span className="ea-stop-square" aria-hidden="true" />
            {t("run.cancel")}
          </ActionButton>
          <span className="ea-muted ea-small" id={reasonId} data-testid="stop-reason">
            {t(control.kind === "unconfirmed" ? "run.noStopReconcile" : "run.nothingRunning")}
          </span>
          {control.kind === "unconfirmed" && (
            <ActionButton data-testid="stop-reconcile" onPress={() => void controller.reconcile()}>
              {t("outcome.reconcile")}
            </ActionButton>
          )}
        </span>
      )}
    </div>
  );
}
