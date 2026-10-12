/** Local disclosure state only; preferences remain owned by the presentation context. */
import { useRef } from "react";
import { useController, useI18n, usePresentation, type PresentationDimension } from "@e-agent/ui-react";
import { Icon } from "../../primitives/Icon.tsx";

export function Preferences() {
  const { t, locale } = useI18n();
  const controller = useController();
  const presentation = usePresentation();
  const disclosure = useRef<HTMLDetailsElement>(null);
  const dimensions: PresentationDimension[] = ["theme", "appearance", "density"];
  return (
    <details
      className="ea-preferences"
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
      <summary
        data-testid="preferences-toggle"
        aria-label={t("controls.settings")}
        title={t("controls.settings")}
      >
        <Icon name="settings" />
      </summary>
      <div className="ea-preferences-panel" data-testid="preferences-panel">
        <h2 className="ea-panel-title">{t("controls.settings")}</h2>
        <label>
          <span>{t("controls.language")}</span>
          <select
            aria-label={t("controls.language")}
            value={locale}
            onChange={event => controller.setLocale(event.target.value === "vi" ? "vi" : "en")}
          >
            <option value="en">English</option>
            <option value="vi">Tiếng Việt</option>
          </select>
        </label>
        {presentation &&
          dimensions
            .filter(d => !presentation.locked[d] && presentation.options[d].length > 1)
            .map(dimension => (
              <label key={dimension}>
                <span>{t(`controls.${dimension}`)}</span>
                <select
                  aria-label={t(`controls.${dimension}`)}
                  value={presentation.value[dimension]}
                  data-testid={`${dimension}-switch`}
                  onChange={event => presentation.set(dimension, event.target.value)}
                >
                  {presentation.options[dimension].map(option => (
                    <option key={option} value={option}>
                      {t(`${dimension}.${option}`)}
                    </option>
                  ))}
                </select>
              </label>
            ))}
      </div>
    </details>
  );
}
