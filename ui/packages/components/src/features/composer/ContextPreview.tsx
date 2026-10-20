/**
 * "What will be sent with this message": the exact host context the next submission
 * carries, read from the controller's own source. Nothing is inferred or invented —
 * a host that sends no context is shown as sending only the message text, with what
 * e-agent uses kept apart from what is sent. The server resolves or drops every hint
 * (ADR 0011), which the panel says when hints are sent.
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
        {context ? (
          <>
            <p className="ea-small ea-muted">{t("context.message")}</p>
            <dl className="ea-context-list">
              {rows.map(([key, value]) => (
                <div key={key}>
                  <dt>{t(key)}</dt>
                  <dd>{value}</dd>
                </div>
              ))}
            </dl>
            <p className="ea-small ea-muted">{t("context.server")}</p>
          </>
        ) : (
          // Owner G-0 (2026-10-20): what this message sends, then what e-agent uses.
          // No hints are sent, so the hints line is left out.
          <>
            <p className="ea-small" data-testid="context-sent">
              {t("context.sentNoHost")}
            </p>
            <div className="ea-context-uses">
              <p className="ea-small" data-testid="context-none">
                {t("context.noHost")}
              </p>
            </div>
          </>
        )}
      </div>
    </details>
  );
}
