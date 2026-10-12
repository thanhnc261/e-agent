/**
 * Exact material terms. This view arranges the values the server sent; it never
 * reinterprets, rounds, truncates or substitutes one.
 */
import type { MaterialField } from "@e-agent/ui-core";
import { formatFieldValue, readableLabel } from "@e-agent/ui-core";
import { useI18n } from "@e-agent/ui-react";

export function MaterialFields({ fields }: { fields: readonly MaterialField[] }) {
  const { t, locale } = useI18n();
  const actualDiff = fields.some(f => f.comparison === "current");
  const previous = fields.some(f => f.changed && f.previous_value !== null && f.previous_value !== undefined);
  return (
    <div className="ea-decision-fields">
      {fields.map(f => (
        <div
          className={`ea-term ${f.changed ? "ea-changed" : ""}`}
          key={f.path}
          data-testid="material-field"
          data-path={f.path}
          data-changed={f.changed}
        >
          <span className="ea-term-label">{f.label ?? readableLabel(f.path)}</span>
          <span className="ea-term-value">
            {formatFieldValue(f.path, f.value, locale)}
            {f.changed && <small className="ea-badge-change">{t("approval.changed")}</small>}
          </span>
          {(actualDiff || previous) && (
            <small className="ea-term-before">
              {t(actualDiff ? "approval.current" : "approval.previous")}:{" "}
              {f.previous_value == null
                ? t("approval.unknown")
                : formatFieldValue(f.path, f.previous_value, locale)}
            </small>
          )}
        </div>
      ))}
    </div>
  );
}
