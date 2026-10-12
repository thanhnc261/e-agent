/**
 * Admitted task types for this requester. Cards are driven entirely by server
 * metadata: adding a provider or a capability changes this view without a source
 * edit, and an unavailable template says why instead of disappearing or pretending
 * to work.
 */
import type { TaskTemplateView } from "@e-agent/ui-core";
import { useI18n, useTaskCatalog } from "@e-agent/ui-react";
import { Icon } from "../../primitives/Icon.tsx";
import { Disclosure } from "../../primitives/Disclosure.tsx";
import { StatusBadge } from "../../primitives/StatusBadge.tsx";
import { Surface } from "../../primitives/Surface.tsx";
import { DiscoveryStatus } from "./DiscoveryState.tsx";

const REASONS = new Set(["no_usable_connection", "ambiguous_binding", "no_executor", "no_verifier"]);

function reasonKey(reason: string | null): string {
  return REASONS.has(reason ?? "") ? `catalog.reason.${reason}` : "catalog.reason.unknown";
}

export function TaskCatalogCard({ template }: { template: TaskTemplateView }) {
  const { t } = useI18n();
  return (
    <Surface
      as="li"
      tone={template.available ? "card" : "sunken"}
      className="ea-catalog-card"
      data-testid="catalog-template"
      data-template={template.templateId}
      data-available={template.available}
    >
      <div className="ea-catalog-meta">
        <span className="ea-catalog-glyph">
          <Icon name="task" />
        </span>
        <span>{template.boundedContext}</span>
        <StatusBadge className="ea-catalog-availability" tone={template.available ? "neutral" : "unknown"}>
          {t(template.available ? "catalog.available" : "catalog.unavailable")}
        </StatusBadge>
      </div>
      <div className="ea-catalog-head">
        <h3 className="ea-catalog-title">{template.title}</h3>
      </div>
      {template.description && <p className="ea-small">{template.description}</p>}
      {!template.available && (
        <p className="ea-small ea-muted" data-testid="catalog-reason">
          {t(reasonKey(template.unavailableReason))}
        </p>
      )}
      <Disclosure className="ea-catalog-details" summary={t("catalog.details")}>
        <p className="ea-small ea-muted ea-catalog-id">{template.templateId}</p>
      </Disclosure>
    </Surface>
  );
}

export function TaskCatalog() {
  const { t } = useI18n();
  const state = useTaskCatalog();
  return (
    <section className="ea-catalog" data-testid="task-catalog" aria-label={t("catalog.title")}>
      <h2 className="ea-panel-title">{t("catalog.title")}</h2>
      <p className="ea-small ea-muted">{t("catalog.intro")}</p>
      <DiscoveryStatus state={state} testId="catalog-status" />
      {state.kind === "ready" &&
        (state.items.length === 0 ? (
          <p className="ea-small ea-muted" data-testid="catalog-empty">
            {t("catalog.empty")}
          </p>
        ) : (
          <ul className="ea-catalog-list">
            {state.items.map(template => (
              <TaskCatalogCard key={template.templateId} template={template} />
            ))}
          </ul>
        ))}
    </section>
  );
}
