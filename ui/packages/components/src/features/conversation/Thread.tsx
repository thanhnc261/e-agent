/**
 * The conversation thread (ADR 0034 §2, owner-selected mockup A1): the conversation's runs,
 * oldest first, each with its messages and a compact run card. Everything comes from the
 * server's conversation snapshot and the runs' recorded events (`selectThread`); a sent
 * message appears only once the server lists it. Run-state changes and a new run are
 * announced in one polite region, and focus never moves (EA-16).
 */
import {
  isLiveEntry,
  selectThread,
  threadRunStatusKey,
  type ConversationItem,
  type ThreadRunEntry,
} from "@e-agent/ui-core";
import { useI18n, useRunState } from "@e-agent/ui-react";
import { BrandMark } from "../../primitives/BrandMark.tsx";
import { Disclosure } from "../../primitives/Disclosure.tsx";
import { MessageText } from "./MessageText.tsx";
import { RunCard } from "./RunCard.tsx";

export function Thread() {
  const { t } = useI18n();
  const state = useRunState();
  const statusOf = (entry: ThreadRunEntry) => threadRunStatusKey(entry, state);
  const entries = selectThread(state.thread, state);
  const latest = entries.at(-1);
  const announcement = latest ? `${t("thread.run")} ${entries.length}: ${t(statusOf(latest))}` : "";
  return (
    <section className="ea-messages ea-thread-view" aria-label={t("messages.title")} data-testid="messages">
      {/* One polite region for run states; streamed text is never in it (EA-16). */}
      <p className="ea-visually-hidden" role="status" data-testid="thread-announcer">
        {announcement}
      </p>
      {entries.length === 0 ? (
        state.conversationId && state.thread.status === "loading" ? (
          <p className="ea-muted">{t("discovery.loading")}</p>
        ) : (
          <ThreadEmpty />
        )
      ) : (
        <ol className="ea-thread" aria-label={t("messages.title")} data-testid="thread">
          {entries.map((entry, index) => (
            <ThreadRun key={entry.runId} entry={entry} ordinal={index + 1} status={statusOf(entry)} />
          ))}
        </ol>
      )}
    </section>
  );
}

/** Ready: the AI disclosure and what it can and cannot do, in the thread itself (F-1). */
function ThreadEmpty() {
  const { t } = useI18n();
  return (
    <div className="ea-welcome ea-thread-empty" data-testid="thread-empty">
      <BrandMark className="ea-welcome-mark" />
      <h1>{t("workspace.welcome")}</h1>
      <div className="ea-ai-disclosure" data-testid="ai-disclosure">
        <p>{t("overview.aiTitle")}</p>
        <Disclosure summary={t("overview.aiMore")}>
          <p className="ea-muted">{t("overview.aiBody")}</p>
          <ul>
            <li>{t("overview.aiCan")}</li>
            <li>{t("overview.aiCannot")}</li>
            <li>{t("overview.aiAlways")}</li>
          </ul>
        </Disclosure>
      </div>
    </div>
  );
}

function ThreadRun({ entry, ordinal, status }: { entry: ThreadRunEntry; ordinal: number; status: string }) {
  const { t } = useI18n();
  const active = useRunState();
  const { view } = active;
  const live = isLiveEntry(entry, active);
  const streaming = live && view.streamingText && view.run?.state !== "SUCCEEDED" ? view.streamingText : "";
  const titleId = `ea-run-${ordinal}-title`;
  return (
    <li
      className="ea-thread-run"
      data-testid="thread-run"
      data-run-id={entry.runId}
      aria-labelledby={titleId}
    >
      <p className="ea-run-gutter" aria-hidden="true">
        {t("thread.run")} {ordinal}
      </p>
      <ol className="ea-thread-messages">
        <li className="ea-message ea-message-user" data-testid="thread-message" data-role="user">
          <span className="ea-message-avatar" aria-hidden="true">
            ↑
          </span>
          <div>
            <p className="ea-message-author">{t("messages.you")}</p>
            <p className="ea-message-body">{entry.task}</p>
          </div>
        </li>
        {entry.loaded ? (
          entry.messages.map(message => <ThreadMessage key={message.id} message={message} />)
        ) : (
          // Unread is not empty: the messages are unknown, and the UI says so (EA-8).
          <li className="ea-muted ea-small" data-testid="thread-not-loaded">
            {t("thread.notLoaded")}
          </li>
        )}
        {streaming && (
          <li className="ea-message ea-message-agent">
            <BrandMark className="ea-message-avatar ea-message-avatar-agent" />
            <div>
              <p className="ea-message-author">{t("messages.agent")}</p>
              <div className="ea-message-body" data-testid="streaming-message">
                <MessageText text={streaming} />
              </div>
            </div>
          </li>
        )}
      </ol>
      <RunCard entry={entry} ordinal={ordinal} status={status} titleId={titleId} live={live} />
    </li>
  );
}

function ThreadMessage({ message }: { message: ConversationItem }) {
  const { t } = useI18n();
  const user = message.role === "user";
  return (
    <li
      className={`ea-message ea-message-${message.role}`}
      data-testid="thread-message"
      data-role={message.role}
    >
      {user ? (
        <span className="ea-message-avatar" aria-hidden="true">
          ↑
        </span>
      ) : (
        <BrandMark className="ea-message-avatar ea-message-avatar-agent" />
      )}
      <div>
        <p className="ea-message-author">
          {t(user ? "messages.you" : "messages.agent")}
          {message.kind === "reply" && !message.firstReply && (
            // Owner G-0 (2026-10-20): every later reply stays visibly unverified.
            <small className="ea-muted ea-reply-note" data-testid="reply-note">
              {" "}
              <span aria-hidden="true">· </span>
              {t("conversation.replyNote")}
            </small>
          )}
        </p>
        {message.kind === "reply" && message.firstReply && (
          <p className="ea-origin-label" data-testid="reply-label">
            {t("conversation.reply")}
          </p>
        )}
        {message.final && (
          // The agent's words, apart from what was checked (G-B 5, AG-ID-1).
          <p className="ea-origin-label" data-testid="agent-words-message">
            {t("messages.agentWords")}
          </p>
        )}
        {!user && message.kind === "message" && !message.final && (
          <p className="ea-origin-label">{t("messages.question")}</p>
        )}
        <div
          className="ea-message-body"
          data-testid={
            message.pending
              ? message.kind === "reply"
                ? "pending-reply"
                : "clarification-question"
              : undefined
          }
        >
          <MessageText text={message.text} />
        </div>
      </div>
    </li>
  );
}
