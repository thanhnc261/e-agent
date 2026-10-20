/** Recorded host events in order. Unsupported events stay visible and labelled. */
import { formatDateTime, formatTime, readableLabel, runStatusKey } from "@e-agent/ui-core";
import { useI18n, useRun, useTimeline } from "@e-agent/ui-react";
import { Disclosure } from "../../primitives/Disclosure.tsx";

export function Timeline() {
  const { t, locale } = useI18n();
  const items = useTimeline();
  // SUCCEEDED is terminal, so its one transition ends with the run's own reason code.
  // A wait on a reply reads "Your turn", as in the composer and the sidebar (runStatusKey).
  const { run } = useRun();
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
                {t(runStatusKey(item.transition.from, [], item.transition.fromReply === true))} →{" "}
                {t(runStatusKey(item.transition.to, [], item.transition.toReply === true, run?.reason_code))}
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
