/**
 * The earlier runs whose checked values and record refs this run received as hints (ADR 0023
 * §6, brief item 8, G-D 4.U1, AG-EXPL-2), shown in the workspace's Sources tab as mockup A1
 * placed them. Read from the run's evidence bundle through `selectCarriedRuns` only, so
 * nothing shows in `shadow` (nothing reached the model), in `off`, or for an empty list. Each
 * run is named as the thread names it ("Run 1" and its task), or by its id when the loaded
 * thread does not hold it; selecting one opens it in the workspace, as its run card does.
 * Hints only: never presented as evidence or as verified, and never as something the agent
 * knows (EA-5).
 *
 * Showing it reads the bundle when this session has not read it yet: when the user opens the
 * Sources tab, and when a workspace opens on a run with no decision or result yet (Sources is
 * then its first tab). The read is quiet (GD-1): nothing is shown while it is read or when it
 * fails, and a failure never reaches the shared error, since the user asked for nothing.
 */
import { useEffect, useId, useRef } from "react";
import { selectCarriedRuns, selectThread } from "@e-agent/ui-core";
import { useController, useI18n, useRunState } from "@e-agent/ui-react";
import { ActionButton } from "../../primitives/ActionButton.tsx";
import { useArtifactWorkspace } from "./workspace.ts";

export function CarriedRuns() {
  const { t } = useI18n();
  const state = useRunState();
  const controller = useController();
  const workspace = useArtifactWorkspace();
  const headingId = useId();
  // One read per attached run, even across re-renders and a failed read.
  const readFor = useRef<string | null>(null);
  const { evidence, runId } = state;
  useEffect(() => {
    if (evidence || !runId || readFor.current === runId) return;
    readFor.current = runId;
    void controller.loadEvidence({ quiet: true });
  }, [evidence, runId, controller]);
  const runs = selectCarriedRuns(evidence, selectThread(state.thread, state));
  if (runs.length === 0) return null;
  return (
    <section className="ea-carried" aria-labelledby={headingId} data-testid="carried-runs">
      <h3 className="ea-subtitle" id={headingId}>
        {t("carried.title")}
      </h3>
      <ul className="ea-carried-list">
        {runs.map(run => {
          const name = run.ordinal === null ? run.runId : `${t("thread.run")} ${run.ordinal} · ${run.task}`;
          return (
            <li key={run.runId}>
              {workspace ? (
                <ActionButton
                  variant="quiet"
                  className="ea-carried-run"
                  data-testid="carried-run"
                  data-run-id={run.runId}
                  onPress={event => workspace.open(run.runId, event.target as HTMLElement)}
                >
                  {name}
                </ActionButton>
              ) : (
                <span data-testid="carried-run" data-run-id={run.runId}>
                  {name}
                </span>
              )}
            </li>
          );
        })}
      </ul>
      <p className="ea-muted ea-small">{t("carried.note")}</p>
    </section>
  );
}
