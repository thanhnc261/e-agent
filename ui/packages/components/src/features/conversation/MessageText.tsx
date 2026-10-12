/** Renders model-supplied text as literal text plus audited links; no HTML, no remote images. */
import { segmentText } from "@e-agent/ui-core";
import { useI18n } from "@e-agent/ui-react";

export function MessageText({ text }: { text: string }) {
  const { t } = useI18n();
  return (
    <span className="ea-text">
      {segmentText(text).map((seg, i) =>
        seg.kind === "link" ? (
          <a
            key={i}
            href={seg.href}
            target="_blank"
            rel="noopener noreferrer nofollow"
            referrerPolicy="no-referrer"
            title={t("link.external")}
          >
            {seg.text}
          </a>
        ) : seg.kind === "image" ? (
          <span
            key={i}
            className="ea-muted"
            data-testid="blocked-image"
          >{`[${t("image.blocked")}: ${seg.alt} ${seg.url}]`}</span>
        ) : (
          <span key={i}>{seg.text}</span>
        ),
      )}
    </span>
  );
}
