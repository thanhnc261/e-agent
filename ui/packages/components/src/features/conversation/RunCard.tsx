/**
 * A run's compact card in the thread (mockup A1): its status, one line from its recorded
 * events, Open, and Stop while it is the active run. With the workspace closed, the card
 * and the stop slot carry the run's status. The label of Open names what waits there: the
 * decision, the result, or the run's recorded activity. Open never closes the workspace.
 */
import {
  formatTime,
  hasResult,
  isAwaitingDecision,
  readableLabel,
  selectRunLine,
  selectStopControl,
  translateServerValue,
  type ThreadRunEntry,
} from "@e-agent/ui-core";
import { useController, useI18n, usePendingApproval, useRunState } from "@e-agent/ui-react";
import { ActionButton } from "../../primitives/ActionButton.tsx";
import { StatusBadge } from "../../primitives/StatusBadge.tsx";
import { runStateTone } from "../../primitives/runStateTone.ts";
import { ARTIFACT_WORKSPACE_ID, useArtifactWorkspace } from "./workspace.ts";

export function RunCard({
  entry,
  ordinal,
  status,
  titleId,
  live,
}: {
  entry: ThreadRunEntry;
  ordinal: number;
  status: string;
  titleId: string;
  /** The active run: the controller's attached run, with its approval and result. */
  live: boolean;
}) {
  const { t, locale } = useI18n();
  const state = useRunState();
  const approval = usePendingApproval();
  const controller = useController();
  const workspace = useArtifactWorkspace();
  const view = live ? state.view : (state.thread.runs[entry.runId] ?? null);
  const runState = live ? (state.view.run?.state ?? entry.state) : entry.state;
  const reasonCode = live ? (state.view.run?.reason_code ?? null) : entry.reasonCode;
  // No outcome or verified line before the run ends, nor one the run's end does not bear out (B-2).
  const line = selectRunLine(view, runState, reasonCode);
  const decision = live && isAwaitingDecision(approval.phase);
  const result = live && hasResult(runState);
  const open = workspace?.runId === entry.runId;
  const stoppable = live && entry.latest && selectStopControl(runState).kind === "active";
  const tone = status === "status.phase.UNKNOWN" ? "unknown" : runStateTone(runState, reasonCode);
  return (
    <article
      className={`ea-run-card ea-run-card-${tone}`}
      data-testid="run-card"
      data-run-id={entry.runId}
      aria-labelledby={titleId}
    >
      <header className="ea-run-card-head">
        <span className="ea-run-num">
          {t("thread.run")} {ordinal}
        </span>
        <h2 className="ea-run-title" id={titleId}>
          {entry.task}
        </h2>
        <StatusBadge tone={tone} data-testid="run-card-status" data-state={runState}>
          {t(status)}
        </StatusBadge>
      </header>
      {line && (
        <p className="ea-run-line" data-testid="run-card-line">
          {t(line.labelKey)}
          {line.detail && (
            <span className="ea-muted">
              {" · "}
              {line.detailField
                ? translateServerValue(locale, line.detailField, line.detail)
                : line.type.endsWith(".recorded") || line.type === "proposal.created"
                  ? readableLabel(line.detail)
                  : line.detail}
            </span>
          )}
          <time className="ea-muted" dateTime={line.occurredAt}>
            {" · "}
            {formatTime(line.occurredAt, locale)}
          </time>
        </p>
      )}
      {workspace && (
        <div className="ea-run-card-foot">
          <ActionButton
            variant={decision ? "primary" : "default"}
            data-testid="run-card-open"
            data-open-run={entry.runId}
            aria-controls={open ? ARTIFACT_WORKSPACE_ID : undefined}
            // Open only (G-D 4.U5): while this run's workspace is open, a press brings it forward
            // with focus on its heading. Closing stays with the workspace's Close and Back.
            onPress={event => workspace.open(entry.runId, event.target as HTMLElement)}
          >
            {t(decision ? "thread.openDecision" : result ? "thread.openResult" : "thread.open")}
          </ActionButton>
          {stoppable && (
            <ActionButton
              className="ea-button-stop"
              data-testid="run-card-stop"
              onPress={() => void controller.cancel()}
            >
              <span className="ea-stop-square" aria-hidden="true" />
              {t("run.cancel")}
            </ActionButton>
          )}
        </div>
      )}
    </article>
  );
}
