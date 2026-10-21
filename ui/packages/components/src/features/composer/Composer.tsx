/**
 * Task entry and clarifying answers. Enter sends text; it can never approve.
 *
 * In `conversations: on` the composer keeps no local lock (G-B 4): a message that cannot go
 * now is refused by the server, whose hint shows inside the composer above the kept draft,
 * and the approval card does not change. `off` and `shadow` keep today's lock. In the thread
 * view, the stop slot under the composer names the latest run and its status (mockup A1);
 * the per-run view keeps today's status line above the input.
 */
import { useId, type FormEvent } from "react";
import {
  canCompose,
  isConversationsOn,
  isLiveEntry,
  selectPendingReply,
  selectThread,
  selectThreadShown,
  threadRunStatusKey,
} from "@e-agent/ui-core";
import { useComposer, useController, useI18n, useRun, useRunState } from "@e-agent/ui-react";
import { ActionButton } from "../../primitives/ActionButton.tsx";
import { StatusBadge } from "../../primitives/StatusBadge.tsx";
import { TextAreaField } from "../../primitives/TextAreaField.tsx";
import { ContextPreview } from "./ContextPreview.tsx";
import { RefusalHint } from "./RefusalHint.tsx";
import { RunStatus } from "./RunStatus.tsx";
import { StopSlot } from "./StopSlot.tsx";

export function Composer() {
  const { t } = useI18n();
  const { busy, submit, draft: task, setDraft: setTask } = useComposer();
  const { run, error } = useRun();
  const state = useRunState();
  const { view, refusal } = state;
  const hintId = useId();
  const controller = useController();
  const thread = selectThreadShown(state);
  const canSend = isConversationsOn(state.features) || canCompose(run?.state);
  const reply = selectPendingReply(view);
  const answer = run?.state === "WAITING_INPUT" && !reply;
  const entries = thread ? selectThread(state.thread, state) : [];
  const latest = entries.at(-1);
  const answering = latest && isLiveEntry(latest, state) && run?.state === "WAITING_INPUT" ? latest : null;
  const onSubmit = (e?: FormEvent) => {
    e?.preventDefault();
    if (!task.trim() || busy || !canSend) return;
    const sent = task;
    void submit(sent).then(ok => {
      if (!ok) return;
      // Clear only what was sent: text typed while the send was in flight is kept.
      const now = controller.getState().draft;
      setTask(now.startsWith(sent) ? now.slice(sent.length).trimStart() : now);
    });
  };
  const placeholder = answer
    ? "composer.answerPlaceholder"
    : reply || (thread && entries.length > 0)
      ? "composer.replyPlaceholder"
      : canSend
        ? "composer.placeholder"
        : "composer.locked";
  const label = answer
    ? "composer.answer"
    : reply || (thread && entries.length > 0)
      ? "composer.reply"
      : "composer.submit";
  return (
    <form
      className={`ea-composer ${thread ? "ea-composer-thread" : ""}`}
      onSubmit={onSubmit}
      data-testid="composer"
    >
      {!thread && <RunStatus />}
      {refusal && <RefusalHint refusal={refusal} id={hintId} />}
      {thread && error && (
        // In the thread a failed send is reported where it was made; the draft is kept.
        <p className="ea-alert ea-error" role="alert" data-testid="error">
          {error}
        </p>
      )}
      {answering && (
        <p className="ea-answering ea-small" data-testid="answering">
          {t("composer.answering")} {entries.length}
          <span aria-hidden="true"> · </span>
          <StatusBadge tone="attention">{t(threadRunStatusKey(answering, state))}</StatusBadge>
        </p>
      )}
      <TextAreaField
        label={t("composer.label")}
        value={task}
        onChange={setTask}
        // The thread keeps the input enabled while a message is sent, so focus stays in it
        // (EA-16); a second send waits for the first (onSubmit).
        isDisabled={(busy && !thread) || !canSend}
        placeholder={t(placeholder)}
        testId="composer-input"
        describedBy={refusal ? hintId : undefined}
        onKeyDown={e => {
          if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
            e.preventDefault();
            onSubmit();
          }
        }}
      />
      <div className="ea-composer-footer">
        <div className="ea-composer-tools">
          <ContextPreview />
        </div>
        <span className="ea-muted ea-small ea-composer-help">{t("composer.help")}</span>
        <ActionButton
          type="submit"
          variant="primary"
          isDisabled={!canSend || !task.trim()}
          isPending={busy}
          data-testid="composer-submit"
        >
          {t(label)}
          <span aria-hidden="true"> ↑</span>
        </ActionButton>
      </div>
      {thread && <StopSlot latest={latest} ordinal={entries.length} />}
    </form>
  );
}
