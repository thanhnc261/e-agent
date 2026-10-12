/** Trusted summary of the current task: its text, state and recorded host milestones. */
import { useI18n, useRun, useTimeline } from "@e-agent/ui-react";
import { statusKey } from "@e-agent/ui-core";

const MILESTONE_TYPES = [
  "read.recorded",
  "approval.requested",
  "action.receipt_recorded",
  "action.unknown",
  "outcome.reported",
];

export function TaskOverview() {
  const { t } = useI18n();
  const { run } = useRun();
  const items = useTimeline();
  const milestones = items.filter(item => item.supported && MILESTONE_TYPES.includes(item.type)).slice(-4);
  return (
    <section
      className="ea-inspector-card ea-task-overview"
      data-testid="task-overview"
      aria-label={t("overview.title")}
    >
      <p className="ea-eyebrow">{t("overview.title")}</p>
      <h2 className="ea-overview-task">{run?.task ?? t("overview.empty")}</h2>
      <p className="ea-muted ea-small">{run ? t(statusKey(run.state)) : t("workspace.safe")}</p>
      {milestones.length > 0 && (
        <ol className="ea-milestones">
          {milestones.map(item => (
            <li key={item.sequence}>
              <span aria-hidden="true">•</span>
              {t(item.labelKey)}
            </li>
          ))}
        </ol>
      )}
      <p className="ea-overview-note">{t("overview.authority")}</p>
    </section>
  );
}
