/**
 * Source observations and the full audit record, from the typed bundle projection.
 * Provenance the server did not record is shown as unknown; an unrecognised bundle
 * schema is reported as unsupported instead of being rendered on a best effort.
 */
import { useState } from "react";
import { formatDateTime, readableLabel, selectEvidence } from "@e-agent/ui-core";
import { useController, useI18n, useRun, useRunState } from "@e-agent/ui-react";
import { ActionButton } from "../../primitives/ActionButton.tsx";
import { Disclosure } from "../../primitives/Disclosure.tsx";

export function EvidencePanel() {
  const { t, locale } = useI18n();
  const { run } = useRun();
  const { evidence } = useRunState();
  const controller = useController();
  const [loading, setLoading] = useState(false);
  if (!run) return null;
  const bundle = selectEvidence(evidence);
  const reload = () => {
    setLoading(true);
    void controller.loadEvidence().finally(() => setLoading(false));
  };
  return (
    <Disclosure
      className="ea-inspector-card"
      data-testid="evidence"
      summary={t("evidence.title")}
      badge={<span aria-hidden="true">↗</span>}
    >
      <p className="ea-muted ea-small">{t("evidence.summary")}</p>
      {bundle.kind === "absent" && (
        <ActionButton isPending={loading} onPress={reload} data-testid="evidence-load">
          {t("evidence.load")}
        </ActionButton>
      )}
      {bundle.kind === "unsupported" && (
        <p className="ea-alert ea-warning" role="status" data-testid="evidence-unsupported">
          {t("evidence.unsupported")}
          {bundle.schema ? ` (${bundle.schema})` : ""}
        </p>
      )}
      {bundle.kind !== "absent" && (
        <>
          <div className="ea-evidence-actions">
            <ActionButton variant="quiet" isPending={loading} onPress={reload}>
              {t("evidence.refresh")}
            </ActionButton>
            <ActionButton
              variant="quiet"
              onPress={() => {
                const blob = new Blob([JSON.stringify(evidence, null, 2)], { type: "application/json" });
                const url = URL.createObjectURL(blob);
                const a = document.createElement("a");
                a.href = url;
                a.download = "task-audit.json";
                a.click();
                URL.revokeObjectURL(url);
              }}
            >
              {t("evidence.download")}
            </ActionButton>
          </div>
          <Disclosure className="ea-review-details" summary={t("evidence.audit")}>
            <pre className="ea-evidence" data-testid="evidence-bundle">
              {JSON.stringify(evidence, null, 2)}
            </pre>
          </Disclosure>
        </>
      )}
      {bundle.kind === "ready" && (
        <>
          <h3 className="ea-subtitle">{t("evidence.sources")}</h3>
          {bundle.sources.length === 0 && <p className="ea-muted">{t("evidence.noSources")}</p>}
          {bundle.sources.map(source => (
            <div className="ea-source" key={source.evidenceId} data-testid="evidence-source">
              <strong>{source.source ?? t("approval.unknown")}</strong>
              <p>{source.locator ?? t("approval.unknown")}</p>
              <small data-completeness={source.completeness}>
                {t("evidence.observed")}:{" "}
                {source.observedAt ? formatDateTime(source.observedAt, locale) : t("approval.unknown")} ·{" "}
                {t(`evidence.completeness.${source.completeness}`)}
              </small>
              <Disclosure summary={t("evidence.sourceValues")}>
                <dl className="ea-meta">
                  {source.data.map(datum => (
                    <div key={datum.path}>
                      <dt>{readableLabel(datum.path)}</dt>
                      <dd>{datum.value}</dd>
                    </div>
                  ))}
                </dl>
              </Disclosure>
            </div>
          ))}
        </>
      )}
    </Disclosure>
  );
}
