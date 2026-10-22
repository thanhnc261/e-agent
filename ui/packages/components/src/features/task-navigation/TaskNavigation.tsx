/**
 * Session task switcher. Switching is local navigation and never stops server work.
 *
 * In `conversations: on` it lists the server's conversations, newest first, as the server
 * orders them (ADR 0034 §2), and keeps this session's runs that belong to no conversation in
 * their own "last seen" group (G-B 2, ADR 0023 §10). `off` and `shadow` keep today's list.
 */
import { useId } from "react";
import {
  isConversationsOn,
  runStatusKey,
  selectThread,
  threadRunStatusKey,
  type ConversationSummary,
  type TaskHistoryEntry,
} from "@e-agent/ui-core";
import { useController, useI18n, useRunState, useSurface } from "@e-agent/ui-react";
import { ActionButton } from "../../primitives/ActionButton.tsx";
import { statusMarker } from "../../primitives/StatusBadge.tsx";
import { runStateTone } from "../../primitives/runStateTone.ts";
import type { StatusTone } from "../../primitives/variants.ts";

export function TaskNavigation({
  onOpen,
}: {
  /**
   * How a host opens a previous task. A routed host passes a navigation request so
   * its route stays the one place that attaches; without it the controller attaches.
   */
  onOpen?: (runId: string) => void;
} = {}) {
  const { features } = useRunState();
  return isConversationsOn(features) ? (
    <ConversationNavigation onOpen={onOpen} />
  ) : (
    <RunNavigation onOpen={onOpen} />
  );
}

/** Expand recent work only in the workspace rail; embedded surfaces keep the task in view. */
function useExpanded(): boolean {
  const surface = useSurface();
  return surface?.mode === "full-page" && !surface.compact;
}

function RunNavigation({ onOpen }: { onOpen?: ((runId: string) => void) | undefined }) {
  const { t } = useI18n();
  const { history, busy } = useRunState();
  const controller = useController();
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
      <details className="ea-task-history" open={useExpanded() || undefined}>
        <summary>{t("workspace.recent")}</summary>
        {history.length === 0 ? (
          <p className="ea-muted ea-small">{t("workspace.noHistory")}</p>
        ) : (
          <HistoryList history={history} onOpen={onOpen} />
        )}
        <p className="ea-muted ea-nav-hint">{t("workspace.historyHint")}</p>
      </details>
    </nav>
  );
}

function HistoryList({
  history,
  onOpen,
  lastSeen = false,
}: {
  history: TaskHistoryEntry[];
  onOpen?: ((runId: string) => void) | undefined;
  /** Legacy runs in `on`: the status is the one this session last saw (G-B 2). */
  lastSeen?: boolean;
}) {
  const { t } = useI18n();
  const { runId, busy } = useRunState();
  const controller = useController();
  return (
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
            <small>
              {lastSeen && (
                <span className="ea-last-seen">
                  {t("nav.lastSeen")}
                  <span aria-hidden="true"> · </span>
                </span>
              )}
              {/* The same marker as the composer's status pill (EA-15). */}
              <span className="ea-task-status-marker" aria-hidden="true" data-testid="history-status-marker">
                {statusMarker(runStateTone(h.state, h.reasonCode))}
              </span>
              {t(runStatusKey(h.state, [], h.replyPending === true, h.reasonCode))}
            </small>
          </ActionButton>
        </li>
      ))}
    </ul>
  );
}

function ConversationNavigation({ onOpen }: { onOpen?: ((runId: string) => void) | undefined }) {
  const { t } = useI18n();
  const state = useRunState();
  const { threads, history, busy } = state;
  const controller = useController();
  const legacyId = useId();
  const open = (conversationId: string) =>
    void controller.openConversation(conversationId).then(() => {
      // A routed host shows the thread on its task route; the route only follows the run.
      const runId = controller.getState().runId;
      if (onOpen && runId && controller.getState().conversationId === conversationId) onOpen(runId);
    });
  return (
    <nav className="ea-task-nav ea-thread-nav" aria-label={t("nav.conversations")}>
      <ActionButton
        className="ea-button-new"
        isDisabled={busy}
        onPress={() => controller.newTask()}
        data-testid="new-task"
      >
        <span aria-hidden="true">＋</span>
        {t("nav.new")}
      </ActionButton>
      <details className="ea-task-history" open={useExpanded() || undefined}>
        <summary data-testid="thread-list-toggle">{t("nav.conversations")}</summary>
        <div data-testid="thread-list">
          {threads.kind === "ready" ? (
            threads.items.length === 0 ? (
              <p className="ea-muted ea-small">{t("nav.noConversations")}</p>
            ) : (
              <ul>
                {threads.items.map(row => (
                  <li key={row.conversation_id}>
                    <ActionButton
                      variant="quiet"
                      className="ea-task-link"
                      aria-current={row.conversation_id === state.conversationId ? "page" : undefined}
                      isDisabled={busy}
                      onPress={() => open(row.conversation_id)}
                      data-testid="thread-row"
                    >
                      <span>{row.title || t("nav.untitled")}</span>
                      <RowStatus row={row} />
                    </ActionButton>
                  </li>
                ))}
              </ul>
            )
          ) : threads.kind === "error" ? (
            <p className="ea-muted ea-small" role="status">
              {t("nav.conversationsFailed")}
            </p>
          ) : (
            <p className="ea-muted ea-small">{t("discovery.loading")}</p>
          )}
        </div>
        {history.length > 0 && (
          <section className="ea-legacy-group" aria-labelledby={legacyId} data-testid="legacy-group">
            <h2 className="ea-nav-heading" id={legacyId}>
              {t("nav.legacy")}
            </h2>
            <p className="ea-muted ea-small">{t("nav.legacyNote")}</p>
            <HistoryList history={history} onOpen={onOpen} lastSeen />
          </section>
        )}
      </details>
    </nav>
  );
}

/**
 * A row's status. The open conversation's latest run is read live; any other row has only
 * the list's `latest_state`, which carries no reason code, so a completed run there is shown
 * as "Completed" and never claimed verified (PR-19, EA-3).
 */
function RowStatus({ row }: { row: ConversationSummary }) {
  const { t } = useI18n();
  const state = useRunState();
  const latest =
    row.conversation_id === state.conversationId ? selectThread(state.thread, state).at(-1) : undefined;
  let key: string | null;
  let tone: StatusTone;
  if (latest) {
    key = threadRunStatusKey(latest, state);
    const live = state.view.run?.run_id === latest.runId ? state.view.run : null;
    tone = runStateTone(live?.state ?? latest.state, live ? live.reason_code : latest.reasonCode);
  } else if (row.latest_state === "SUCCEEDED") {
    key = "nav.completed";
    tone = "neutral";
  } else if (row.latest_state) {
    key = runStatusKey(row.latest_state, [], row.reply_pending);
    tone = runStateTone(row.latest_state);
  } else {
    key = null;
    tone = "neutral";
  }
  if (!key) return null;
  return (
    <small>
      <span className="ea-task-status-marker" aria-hidden="true">
        {statusMarker(tone)}
      </span>
      {t(key)}
    </small>
  );
}
