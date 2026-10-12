/**
 * Standalone navigation (L8). It replaces the default `navigation` slot on the
 * full-page surface only, adding the route sections above the existing session task
 * controls. Selecting a section is local navigation: it starts no run and sends no
 * command.
 */
import { Icon, TaskNavigation } from "@e-agent/components";
import { useConnections, useI18n, useRun, useTaskCatalog } from "@e-agent/ui-react";
import { formatRoute, type Route } from "./routes.ts";
import type { Navigate } from "./useRouter.ts";

export function WorkspaceNavigation({ route, navigate }: { route: Route; navigate: (route: Route) => void }) {
  const { t } = useI18n();
  const { run } = useRun();
  // Delivery B navigation is hidden when the workspace does not provide the view;
  // an unsupported or failed response must not advertise a section that cannot load.
  const connections = useConnections();
  const catalog = useTaskCatalog();
  const sections: { route: Route; key: string }[] = [{ route: { name: "overview" }, key: "nav.overview" }];
  // Shown when the workspace demonstrably offers the view, even if this particular
  // response could not be read: hiding a broken view would leave the user with no
  // way to see that it is broken. An absent endpoint still shows no section.
  const offered = (kind: string) => ["ready", "denied", "malformed"].includes(kind);
  if (offered(connections.kind) || offered(catalog.kind)) {
    sections.push({ route: { name: "connections" }, key: "nav.connections" });
  }
  if (run) sections.push({ route: { name: "task", runId: run.run_id }, key: "nav.task" });
  return (
    <div className="ea-workspace-nav">
      <nav className="ea-sections" aria-label={t("nav.sections")} data-testid="sections">
        <p className="ea-eyebrow">{t("nav.sections")}</p>
        <ul>
          {sections.map(section => (
            <li key={section.key}>
              {/* A real link, so Back, copy-link and middle-click keep working. */}
              <a
                className="ea-section-link"
                href={formatRoute(section.route)}
                aria-current={section.route.name === route.name ? "page" : undefined}
                data-testid={`section-${section.route.name}`}
                onClick={event => {
                  if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;
                  event.preventDefault();
                  navigate(section.route);
                }}
              >
                <Icon
                  name={
                    section.route.name === "overview"
                      ? "home"
                      : section.route.name === "connections"
                        ? "connections"
                        : "task"
                  }
                />
                {t(section.key)}
              </a>
            </li>
          ))}
        </ul>
      </nav>
      <TaskNavigation onOpen={runId => navigate({ name: "task", runId })} />
    </div>
  );
}
