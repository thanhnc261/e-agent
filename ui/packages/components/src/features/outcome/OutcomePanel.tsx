/**
 * Task result from the typed outcome projection. Committed, verified, failed and
 * unknown stay distinct: an unresolved external effect is never presented as a
 * verified one, a check without a recorded verdict is shown as unknown rather than
 * as a failure, and nothing here retries a possibly committed write.
 */
import { actionStatusKey, formatFieldValue, hasResult, readableLabel, selectOutcome } from "@e-agent/ui-core";
import { useController, useI18n, useRunState } from "@e-agent/ui-react";
import { ActionButton } from "../../primitives/ActionButton.tsx";
import { Disclosure } from "../../primitives/Disclosure.tsx";
import { Panel } from "../../primitives/Panel.tsx";
import { StatusBadge } from "../../primitives/StatusBadge.tsx";
import type { StatusTone } from "../../primitives/variants.ts";

const TONES: Record<string, StatusTone> = {
  checking: "progress",
  unresolved: "unknown",
  verified: "verified",
  failed: "failed",
  cancelled: "neutral",
  none: "neutral",
};

export function OutcomePanel() {
  const { t, locale } = useI18n();
  const { view } = useRunState();
  const controller = useController();
  const outcome = selectOutcome(view);
  if (!hasResult(outcome.state)) return null;
  const decided = outcome.checks.filter(c => c.passed !== null);
  return (
    <Panel
      title={t("outcome.title")}
      testId="outcome"
      className={`ea-result ea-state-${(outcome.state ?? "").toLowerCase()}`}
    >
      <p className="ea-result-heading">
        <StatusBadge
          tone={TONES[outcome.status] ?? "neutral"}
          data-testid="outcome-state"
          data-state={outcome.state}
          data-status={outcome.status}
        >
          {t(outcome.labelKey)}
        </StatusBadge>
      </p>
      {outcome.unresolved && (
        <div className="ea-alert ea-warning" role="alert" data-testid="outcome-unresolved">
          <p>{t("outcome.effectUnknown")}</p>
          <ActionButton onPress={() => void controller.reconcile()} data-testid="outcome-reconcile">
            {t("outcome.reconcile")}
          </ActionButton>
        </div>
      )}
      {outcome.verified.map(result => (
        <div key={result.actionId}>
          {result.externalRefs.length > 0 && (
            <dl className="ea-result-refs">
              <dt>{t("outcome.records")}</dt>
              {result.externalRefs.map(ref => (
                <dd key={ref}>{ref}</dd>
              ))}
            </dl>
          )}
          <Disclosure className="ea-review-details" summary={t("outcome.values")}>
            <dl className="ea-meta">
              {Object.entries(result.fields).map(([key, value]) => (
                <div key={key}>
                  <dt>{readableLabel(key)}</dt>
                  <dd>
                    {typeof value === "string" ? formatFieldValue(key, value, locale) : JSON.stringify(value)}
                  </dd>
                </div>
              ))}
            </dl>
          </Disclosure>
        </div>
      ))}
      {outcome.checks.length > 0 && (
        <Disclosure
          className="ea-review-details"
          summary={t("outcome.checks")}
          count={`${decided.filter(c => c.passed).length}/${outcome.checks.length}`}
        >
          <ul className="ea-findings">
            {outcome.checks.map((check, i) => (
              <li key={`${check.name}-${i}`} data-testid="outcome-check" data-passed={String(check.passed)}>
                <strong aria-hidden="true">
                  {check.passed === true ? "✓" : check.passed === false ? "✕" : "？"}
                </strong>
                <span>{readableLabel(check.name)}</span>
                <small>{check.observed ?? t("outcome.checkUnknown")}</small>
              </li>
            ))}
          </ul>
        </Disclosure>
      )}
      <Disclosure className="ea-review-details" summary={t("workspace.details")}>
        {outcome.reason && <p className="ea-muted">{outcome.reason}</p>}
        <ul className="ea-actions-list">
          {outcome.actions.map(action => (
            <li key={action.actionId} data-testid="action" data-state={action.state}>
              <span>{readableLabel(action.contractId)}</span>
              <strong>{t(actionStatusKey(action.state))}</strong>
            </li>
          ))}
        </ul>
      </Disclosure>
    </Panel>
  );
}
