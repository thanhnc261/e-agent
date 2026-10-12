/**
 * Conversation-first entry (owner decision EA-10, owner review 2026-10-12): the
 * composer and the user's recent prompts, nothing competing with them. The AI
 * disclosure stays at first interaction as one line with its detail on demand
 * (AG-DISC-1, AG-DISC-2). The installed task types live on the Capabilities page.
 *
 * A recent prompt only puts its text back into the composer; opening a previous
 * task is the sidebar's job, so the two lists never do the same thing.
 */
import { useMemo } from "react";
import { ActionButton, BrandMark, Composer, Disclosure } from "@e-agent/components";
import { useComposer, useI18n, useRunState } from "@e-agent/ui-react";

const RECENT_LIMIT = 5;

export function Overview() {
  const { t } = useI18n();
  const { error, history } = useRunState();
  const { setDraft, busy } = useComposer();
  const recent = useMemo(() => {
    const seen = new Set<string>();
    return history
      .map(entry => entry.task.trim())
      .filter(task => task && !seen.has(task) && seen.add(task))
      .slice(0, RECENT_LIMIT);
  }, [history]);
  const reuse = (task: string) => {
    setDraft(task);
    document.querySelector<HTMLTextAreaElement>('[data-testid="composer-input"]')?.focus();
  };
  return (
    <main className="ea-workarea ea-overview" data-testid="page-overview">
      <div className="ea-overview-content">
        <section className="ea-messages ea-welcome">
          <BrandMark className="ea-welcome-mark" />
          <h1>{t("overview.heading")}</h1>
        </section>
        <Composer />
        {/* A failed submission is reported next to the control that caused it; the
            draft stays in the composer so the same text can be resent. */}
        {error && (
          <p className="ea-alert ea-error" role="alert" data-testid="error">
            {error}
          </p>
        )}
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
        {recent.length > 0 && (
          <section
            className="ea-recent-prompts"
            aria-labelledby="ea-recent-title"
            data-testid="recent-prompts"
          >
            <h2 id="ea-recent-title">{t("overview.recent")}</h2>
            <p className="ea-small ea-muted">{t("overview.recentHint")}</p>
            <ul>
              {recent.map(task => (
                <li key={task}>
                  <ActionButton
                    variant="quiet"
                    className="ea-recent-prompt"
                    isDisabled={busy}
                    onPress={() => reuse(task)}
                    data-testid="recent-prompt"
                  >
                    {task}
                  </ActionButton>
                </li>
              ))}
            </ul>
          </section>
        )}
      </div>
    </main>
  );
}
