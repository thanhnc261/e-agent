/** Recorded host events in order. Unsupported events stay visible and labelled. */
import { formatDateTime, formatTime, readableLabel, statusKey } from "@e-agent/ui-core";
import { useI18n, useTimeline } from "@e-agent/ui-react";
import { Disclosure } from "../../primitives/Disclosure.tsx";

export function Timeline() {
  const { t, locale } = useI18n();
  const items = useTimeline();
  if (!items.length) return null;
  return (
    <Disclosure
      className="ea-inspector-card"
      data-testid="timeline"
      summary={t("timeline.title")}
      count={items.length}
    >
      <ol className="ea-timeline">
        {items.map(item => (
          <li
            key={item.sequence}
            data-testid="timeline-item"
            data-type={item.type}
            data-supported={item.supported}
          >
            <span>{t(item.labelKey)}</span>
            {item.transition ? (
              <small>
                {t(statusKey(item.transition.from))} → {t(statusKey(item.transition.to))}
              </small>
            ) : (
              item.detail && (
                <small>
                  {item.type.endsWith(".recorded") || item.type === "proposal.created"
                    ? readableLabel(item.detail)
                    : item.detail}
                </small>
              )
            )}
            <time dateTime={item.occurredAt} title={formatDateTime(item.occurredAt, locale)}>
              {formatTime(item.occurredAt, locale)}
            </time>
          </li>
        ))}
      </ol>
    </Disclosure>
  );
}
