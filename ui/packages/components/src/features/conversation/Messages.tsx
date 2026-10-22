/**
 * Conversation transcript and the neutral welcome state. In `conversations: on` it is the
 * thread (ADR 0034 §2); `off`, `shadow` and any failed conversation read keep today's
 * per-run view. A run outside every conversation, opened in `on`, keeps the per-run view
 * and says it is not part of a conversation (G-B 2).
 */
import { selectConversation, selectThreadShown, selectViewMode } from "@e-agent/ui-core";
import { useI18n, useRun, useRunState } from "@e-agent/ui-react";
import { BrandMark } from "../../primitives/BrandMark.tsx";
import { MessageText } from "./MessageText.tsx";
import { Thread } from "./Thread.tsx";

export function Messages() {
  return selectThreadShown(useRunState()) ? <Thread /> : <RunMessages />;
}

function RunMessages() {
  const { t } = useI18n();
  const { run, finalMessage, streamingText, question, error } = useRun();
  const state = useRunState();
  const { view } = state;
  const conversation = selectConversation(view);
  const legacy = selectViewMode(state).kind === "thread" && !!run && !state.conversationId;
  return (
    <section
      className={`ea-messages ${run ? "" : "ea-welcome"}`}
      data-testid="messages"
      aria-label={t("messages.title")}
    >
      {legacy && (
        <p className="ea-eyebrow ea-legacy-note" data-testid="legacy-note">
          {t("thread.legacyNote")}
        </p>
      )}
      {!run && (
        <>
          <p className="ea-eyebrow">{t("workspace.kicker")}</p>
          <h1>{t("workspace.welcome")}</h1>
          <p className="ea-welcome-copy">{t("workspace.intro")}</p>
          <div className="ea-assurance">
            <span aria-hidden="true">◇</span>
            {t("workspace.safe")}
          </div>
        </>
      )}
      {run && (
        <div className="ea-message ea-message-user">
          <span className="ea-message-avatar" aria-hidden="true">
            ↑
          </span>
          <div>
            <p className="ea-message-author">{t("messages.you")}</p>
            <p className="ea-message-body" data-testid="run-task">
              {run.task}
            </p>
          </div>
        </div>
      )}
      {conversation
        .filter(m => m.text !== finalMessage)
        .map(m => (
          <div className={`ea-message ea-message-${m.role}`} key={m.id}>
            {m.role === "user" ? (
              <span className="ea-message-avatar" aria-hidden="true">
                ↑
              </span>
            ) : (
              <BrandMark className="ea-message-avatar ea-message-avatar-agent" />
            )}
            <div>
              <p className="ea-message-author">
                {t(m.role === "user" ? "messages.you" : "messages.agent")}
                {m.kind === "reply" && !m.firstReply && (
                  // Owner G-0 (2026-10-20): every later reply stays visibly unverified.
                  <small className="ea-muted ea-reply-note" data-testid="reply-note">
                    {" "}
                    <span aria-hidden="true">· </span>
                    {t("conversation.replyNote")}
                  </small>
                )}
              </p>
              {m.kind === "reply" && m.firstReply && (
                <p className="ea-muted ea-small" data-testid="reply-label">
                  {t("conversation.reply")}
                </p>
              )}
              <div
                className="ea-message-body"
                data-testid={
                  m.pending ? (m.kind === "reply" ? "pending-reply" : "clarification-question") : undefined
                }
              >
                <MessageText text={m.text} />
              </div>
            </div>
          </div>
        ))}
      {question && !conversation.some(m => m.pending) && (
        <p data-testid="clarification-question">{question}</p>
      )}
      {streamingText && run?.state !== "SUCCEEDED" && (
        <div className="ea-message ea-message-agent">
          <BrandMark className="ea-message-avatar ea-message-avatar-agent" />
          <div>
            <p className="ea-message-author">e-agent</p>
            <div className="ea-message-body" data-testid="streaming-message">
              <MessageText text={streamingText} />
            </div>
          </div>
        </div>
      )}
      {finalMessage && (
        <div className="ea-message ea-message-agent">
          <BrandMark className="ea-message-avatar ea-message-avatar-agent" />
          <div>
            <p className="ea-message-author">e-agent</p>
            <div className="ea-message-body" data-testid="final-message">
              <MessageText text={finalMessage} />
            </div>
          </div>
        </div>
      )}
      {run?.state === "RUNNING" && !streamingText && !finalMessage && (
        <p className="ea-progress" role="status">
          <span className="ea-dot" aria-hidden="true" />
          {t("messages.progress")}
        </p>
      )}
      {error && (
        <p className="ea-alert ea-error" role="alert" data-testid="error">
          {error}
        </p>
      )}
    </section>
  );
}
