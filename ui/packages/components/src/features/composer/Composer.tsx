/** Task entry and clarifying answers. Enter sends text; it can never approve. */
import { type FormEvent } from "react";
import { canCompose } from "@e-agent/ui-core";
import { useComposer, useI18n, useRun } from "@e-agent/ui-react";
import { ActionButton } from "../../primitives/ActionButton.tsx";
import { TextAreaField } from "../../primitives/TextAreaField.tsx";
import { ContextPreview } from "./ContextPreview.tsx";
import { RunStatus } from "./RunStatus.tsx";

export function Composer() {
  const { t } = useI18n();
  const { busy, submit, draft: task, setDraft: setTask } = useComposer();
  const { run } = useRun();
  const canSend = canCompose(run?.state);
  const answer = run?.state === "WAITING_INPUT";
  const onSubmit = (e?: FormEvent) => {
    e?.preventDefault();
    if (!task.trim() || busy || !canSend) return;
    void submit(task).then(ok => {
      if (ok) setTask("");
    });
  };
  return (
    <form className="ea-composer" onSubmit={onSubmit} data-testid="composer">
      <RunStatus />
      <TextAreaField
        label={t("composer.label")}
        value={task}
        onChange={setTask}
        isDisabled={busy || !canSend}
        placeholder={t(
          answer ? "composer.answerPlaceholder" : canSend ? "composer.placeholder" : "composer.locked",
        )}
        testId="composer-input"
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
          {t(answer ? "composer.answer" : "composer.submit")}
          <span aria-hidden="true"> ↑</span>
        </ActionButton>
      </div>
    </form>
  );
}
