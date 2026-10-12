/**
 * "What will be sent with this message": the exact host context the next submission
 * carries, read from the controller's own source. Nothing is inferred or invented —
 * a host that sends no context is shown as sending none. The server resolves or drops
 * every hint (ADR 0011), which the panel says.
 */
import { useRef } from "react";
import { useController, useI18n } from "@e-agent/ui-react";

export function ContextPreview() {
  const { t } = useI18n();
  const controller = useController();
  const disclosure = useRef<HTMLDetailsElement>(null);
  const context = controller.hostContextPreview();
  const rows: [string, string][] = context
    ? [
        ["context.host", t(`context.host.${context.host_kind}`)],
        ["context.origin", context.page_url_origin ?? t("context.none")],
        ["context.locale", context.locale ?? t("context.none")],
        ["context.selection", context.selection_text ? context.selection_text : t("context.none")],
        [
          "context.resources",
          context.resource_hints.length ? String(context.resource_hints.length) : t("context.none"),
        ],
      ]
    : [];
  return (
    <details
      className="ea-context"
      ref={disclosure}
      onKeyDown={event => {
        if (event.key === "Escape" && disclosure.current?.open) {
          event.stopPropagation();
          disclosure.current.open = false;
          disclosure.current.querySelector("summary")?.focus();
        }
      }}
      onBlur={event => {
        if (!event.currentTarget.contains(event.relatedTarget)) event.currentTarget.open = false;
      }}
    >
      <summary data-testid="context-toggle">{t("context.button")}</summary>
      <div className="ea-context-panel" data-testid="context-panel" tabIndex={-1}>
        <h2 className="ea-panel-title">{t("context.title")}</h2>
        <p className="ea-small ea-muted">{t("context.message")}</p>
        {context ? (
          <dl className="ea-context-list">
            {rows.map(([key, value]) => (
              <div key={key}>
                <dt>{t(key)}</dt>
                <dd>{value}</dd>
              </div>
            ))}
          </dl>
        ) : (
          <p className="ea-small" data-testid="context-none">
            {t("context.noHost")}
          </p>
        )}
        <p className="ea-small ea-muted">{t("context.server")}</p>
      </div>
    </details>
  );
}
