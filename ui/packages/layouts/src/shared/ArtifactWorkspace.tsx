/**
 * The closable artifact workspace (EA-10, ADR 0034 §1, mockup A1): a run's decision, result,
 * sources and activity, in tabs beside the thread. It holds today's slots unchanged, so the
 * approval card keeps its fields, gates and confirm step (ADR 0034 §5 deferred). An earlier
 * run of the thread shows only its recorded events, the one thing read for it.
 *
 * Escape backs out of an open confirmation first, then closes; closing returns focus to the
 * control that opened it. Tabs follow the APG tabs pattern through React Aria (AG-A11Y-2).
 */
import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";
import { Tab, TabList, TabPanel, Tabs } from "react-aria-components";
import {
  ARTIFACT_WORKSPACE_ID,
  ActionButton,
  CarriedRuns,
  MessageText,
  StatusBadge,
  Timeline,
  runStateTone,
  useArtifactWorkspace,
} from "@e-agent/components";
import {
  hasResult,
  isAwaitingDecision,
  isLiveEntry,
  selectReadConnections,
  selectThread,
  selectTimeline,
  threadRunStatusKey,
} from "@e-agent/ui-core";
import { useConnections, useController, useI18n, usePendingApproval, useRunState } from "@e-agent/ui-react";
import type { LayoutConfig } from "../config.ts";
import { ConfiguredSlot } from "./ConfiguredSlot.tsx";
import { useWorkspaceFocus } from "./workspaceFocus.ts";

type TabKey = "decision" | "result" | "sources" | "activity";

export function ArtifactWorkspace({ config, runId }: { config: LayoutConfig; runId: string }) {
  const { t } = useI18n();
  const state = useRunState();
  const approval = usePendingApproval();
  const controller = useController();
  const workspace = useArtifactWorkspace();
  const focus = useWorkspaceFocus();
  const headingId = useId();
  const asideRef = useRef<HTMLElement>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const entries = selectThread(state.thread, state);
  const index = entries.findIndex(entry => entry.runId === runId);
  const entry = entries[index];
  const live = entry ? isLiveEntry(entry, state) : false;
  const run = live ? state.view.run : null;
  const decision = live && isAwaitingDecision(approval.phase);
  const result = live && hasResult(run?.state);
  const tabs: TabKey[] = live
    ? [
        ...(decision ? ["decision" as const] : []),
        ...(result ? ["result" as const] : []),
        "sources",
        "activity",
      ]
    : ["activity"];
  const [selected, setSelected] = useState<TabKey>(tabs[0] ?? "activity");
  const current = tabs.includes(selected) ? selected : (tabs[0] ?? "activity");
  // A new decision or result is brought forward in an open workspace.
  const forward = decision
    ? `decision:${approval.presentation?.action_id ?? ""}`
    : result
      ? `result:${run?.state}`
      : "";
  useEffect(() => {
    if (forward) setSelected(forward.startsWith("decision") ? "decision" : "result");
  }, [forward]);
  useEffect(() => {
    if (focus.take()) headingRef.current?.focus();
  }, [runId, focus]);
  if (!entry) return null;
  const view = live ? state.view : (state.thread.runs[runId] ?? null);
  const status = threadRunStatusKey(entry, state);
  const close = () => workspace?.close();
  const onKeyDown = (event: KeyboardEvent) => {
    if (event.key !== "Escape") return;
    event.stopPropagation();
    if (approval.phase === "confirming") {
      controller.back();
      requestAnimationFrame(() =>
        asideRef.current?.querySelector<HTMLElement>('[data-testid="approval-approve"]')?.focus(),
      );
    } else close();
  };
  return (
    <aside
      id={ARTIFACT_WORKSPACE_ID}
      className="ea-artifact-workspace"
      aria-labelledby={headingId}
      data-testid="artifact-workspace"
      data-run-id={runId}
      ref={asideRef}
      onKeyDown={onKeyDown}
    >
      <div className="ea-ws-head">
        <ActionButton variant="quiet" className="ea-ws-back" onPress={close} data-testid="workspace-back">
          <span aria-hidden="true">← </span>
          {t("ws.back")}
        </ActionButton>
        <p className="ea-eyebrow ea-ws-kicker">
          {t("ws.label")} · {t("thread.run")} {index + 1}
        </p>
        <h2
          className="ea-ws-title"
          id={headingId}
          tabIndex={-1}
          ref={headingRef}
          data-testid="workspace-heading"
        >
          {entry.task}
        </h2>
        <StatusBadge
          tone={
            status === "status.phase.UNKNOWN"
              ? "unknown"
              : runStateTone(run?.state ?? entry.state, run ? run.reason_code : entry.reasonCode)
          }
          className="ea-ws-status"
          data-testid="workspace-status"
        >
          {t(status)}
        </StatusBadge>
        <ActionButton
          variant="quiet"
          className="ea-ws-close"
          aria-label={t("ws.close")}
          onPress={close}
          data-testid="workspace-close"
        >
          <span aria-hidden="true">✕</span>
        </ActionButton>
      </div>
      <Tabs
        className="ea-ws-tabs"
        selectedKey={current}
        onSelectionChange={key => setSelected(String(key) as TabKey)}
      >
        <TabList className="ea-tab-list" aria-label={t("ws.label")}>
          {tabs.map(key => (
            <Tab key={key} id={key} className="ea-tab" data-testid={`workspace-tab-${key}`}>
              {t(`tab.${key}`)}
            </Tab>
          ))}
        </TabList>
        {tabs.map(key => (
          <TabPanel key={key} id={key} className="ea-tab-panel">
            {key === "decision" && <ConfiguredSlot name="approval" config={config} />}
            {key === "result" && (
              <>
                <ConfiguredSlot name="outcome" config={config} />
                {state.view.finalMessage && (
                  // The agent's words, apart from what the result shows was checked (G-B 5).
                  <figure className="ea-agent-words" data-testid="agent-words-result">
                    <figcaption>
                      <strong>{t("outcome.agentText")}</strong>
                      <span aria-hidden="true"> · </span>
                      {t("messages.agentWords")}
                    </figcaption>
                    <blockquote>
                      <MessageText text={state.view.finalMessage} />
                    </blockquote>
                  </figure>
                )}
              </>
            )}
            {key === "sources" && (
              <>
                {/* The earlier runs used as hints, above the sources (mockup A1, G-D 4.U1). */}
                <CarriedRuns />
                <ReadThrough connectionIds={selectReadConnections(view)} />
                <ConfiguredSlot name="evidence" config={config} />
              </>
            )}
            {key === "activity" &&
              (live ? (
                <ConfiguredSlot name="timeline" config={config} />
              ) : (
                <>
                  <p className="ea-muted ea-small">{t("ws.earlierRun")}</p>
                  <Timeline items={view ? selectTimeline(view) : []} reasonCode={entry.reasonCode} />
                  {!view && <p className="ea-muted ea-small">{t("thread.notLoaded")}</p>}
                </>
              ))}
          </TabPanel>
        ))}
      </Tabs>
    </aside>
  );
}

/**
 * The connections the server recorded on this run's reads, with the identity each acts as
 * when the member's connections projection discloses it (gap audit F-11, AG-ID-5). Ids and
 * identities come from the server only; an undisclosed identity says so.
 */
function ReadThrough({ connectionIds }: { connectionIds: string[] }) {
  const { t } = useI18n();
  const connections = useConnections(connectionIds.length > 0);
  if (connectionIds.length === 0) return null;
  const known = connections.kind === "ready" ? connections.items : [];
  return (
    <dl className="ea-meta ea-read-through" data-testid="read-through">
      {connectionIds.map(id => {
        const connection = known.find(c => c.connectionId === id);
        return (
          <div key={id}>
            <dt>{t("thread.readThrough")}</dt>
            <dd>
              {id}
              {connection && (
                <span className="ea-muted">
                  {" · "}
                  {t("connections.actingIdentity")}{" "}
                  {connection.actingIdentity ?? t("connections.identityUndisclosed")}
                </span>
              )}
            </dd>
          </div>
        );
      })}
    </dl>
  );
}
