/**
 * Read-only connection inventory for this member.
 *
 * Configuration status and observed health are shown as the separate facts they
 * are: the server performs no provider probe to render this, so health is always
 * unknown and is labelled as such. There is no connect, re-authorize, disable or
 * repair control, because no API implements one — offering one would represent a
 * request as access granted.
 */
import type { ConnectionView } from "@e-agent/ui-core";
import { useConnections, useI18n } from "@e-agent/ui-react";
import { Disclosure } from "../../primitives/Disclosure.tsx";
import { StatusBadge } from "../../primitives/StatusBadge.tsx";
import { Surface } from "../../primitives/Surface.tsx";
import { DiscoveryStatus } from "./DiscoveryState.tsx";

const STATUSES = new Set([
  "active",
  "draft",
  "verifying",
  "degraded",
  "reauth_required",
  "disabled",
  "revoked",
]);
const OWNERSHIP = new Set(["tenant_shared", "user_delegated"]);

function label(prefix: string, value: string, known: Set<string>): string {
  return known.has(value) ? `${prefix}.${value}` : `${prefix}.unknown`;
}

export function ConnectionCard({ connection }: { connection: ConnectionView }) {
  const { t } = useI18n();
  return (
    <Surface
      as="li"
      tone={connection.unusable ? "attention" : "card"}
      className="ea-connection-card"
      data-testid="connection"
      data-connection={connection.connectionId}
      data-status={connection.configurationStatus}
    >
      <div className="ea-catalog-head">
        <h3 className="ea-catalog-title">{connection.integrationId}</h3>
        <StatusBadge tone={connection.unusable ? "unknown" : "neutral"} data-testid="connection-status">
          {t(label("connection.status", connection.configurationStatus, STATUSES))}
        </StatusBadge>
      </div>
      <dl className="ea-meta">
        <div>
          <dt>{t("connections.ownership")}</dt>
          <dd>{t(label("connections.ownership", connection.ownership, OWNERSHIP))}</dd>
        </div>
        <div>
          <dt>{t("connections.actingIdentity")}</dt>
          <dd data-testid="connection-identity">
            {connection.actingIdentity ?? t("connections.identityUndisclosed")}
          </dd>
        </div>
        <div>
          <dt>{t("connections.health")}</dt>
          {/* No probe was made, so this is unknown rather than "connected". */}
          <dd data-testid="connection-health">{t("connections.healthUnknown")}</dd>
        </div>
        <div>
          <dt>{t("connections.revision")}</dt>
          <dd>{connection.revision}</dd>
        </div>
      </dl>
      <Disclosure
        className="ea-review-details"
        summary={t("connections.capabilities")}
        count={connection.capabilities.length}
      >
        {connection.capabilities.length === 0 ? (
          <p className="ea-small ea-muted">{t("connections.noCapabilities")}</p>
        ) : (
          <ul className="ea-actions-list">
            {connection.capabilities.map(capability => (
              <li key={capability} data-testid="connection-capability">
                {capability}
              </li>
            ))}
          </ul>
        )}
        {connection.allowedResources.length > 0 && (
          <p className="ea-small ea-muted">
            {t("connections.scope")}: {connection.allowedResources.join(", ")}
          </p>
        )}
      </Disclosure>
    </Surface>
  );
}

export function Connections() {
  const { t } = useI18n();
  const state = useConnections();
  return (
    <section className="ea-connections" data-testid="connections" aria-label={t("connections.title")}>
      <h2 className="ea-panel-title">{t("connections.title")}</h2>
      <p className="ea-small ea-muted">{t("connections.intro")}</p>
      <DiscoveryStatus state={state} testId="connections-status" />
      {state.kind === "ready" &&
        (state.items.length === 0 ? (
          <p className="ea-small ea-muted" data-testid="connections-empty">
            {t("connections.empty")}
          </p>
        ) : (
          <ul className="ea-catalog-list">
            {state.items.map(connection => (
              <ConnectionCard key={connection.connectionId} connection={connection} />
            ))}
          </ul>
        ))}
      <p className="ea-small ea-muted">{t("connections.adminNote")}</p>
    </section>
  );
}
