/**
 * A message the server refused (ADR 0023 §4), inside the composer above the kept draft
 * (mockup A1). The text is the server's fixed hint in the user's language, or exactly as the
 * server wrote it when the UI does not know it. Nothing was sent and the approval card does
 * not change (G-B 4).
 */
import { translateServerHint, type MessageRefusal } from "@e-agent/ui-core";
import { useI18n } from "@e-agent/ui-react";
import { Disclosure } from "../../primitives/Disclosure.tsx";

export function RefusalHint({ refusal, id }: { refusal: MessageRefusal; id: string }) {
  const { t, locale } = useI18n();
  return (
    <div className="ea-refusal" role="alert" data-testid="refusal">
      <p className="ea-refusal-hint" id={id} data-testid="refusal-hint">
        <span className="ea-badge-marker" aria-hidden="true">
          ◆
        </span>
        {translateServerHint(locale, refusal.message)}
      </p>
      <p className="ea-small ea-muted">{t("refused.kept")}</p>
      {refusal.correlationId && (
        <Disclosure className="ea-refusal-details" summary={t("refused.details")}>
          <dl className="ea-meta">
            <div>
              <dt>{t("refused.reference")}</dt>
              <dd className="ea-mono">{refusal.correlationId}</dd>
            </div>
          </dl>
        </Disclosure>
      )}
    </div>
  );
}
