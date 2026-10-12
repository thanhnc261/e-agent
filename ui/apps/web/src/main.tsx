/**
 * Standalone host (L8). It creates the services and the controller once, owns the
 * host document attributes and the routes, and composes the pages. The controller
 * is never remounted, so the active run, the submission identity and the draft
 * survive every navigation and every surface change.
 */
import "@e-agent/tokens/tokens.css";
import "@e-agent/components/components.css";
import "@e-agent/layouts/layouts.css";
import "./app/standalone.css";
import { StrictMode, useCallback } from "react";
import { createRoot } from "react-dom/client";
import { EAgentClient } from "@e-agent/client";
import { Layout, parseLayoutConfig, type HostPresentation, type LayoutConfig } from "@e-agent/layouts";
import { resolveLocale, RunController } from "@e-agent/ui-core";
import { RunProvider, SlotProvider, useController, useRunState } from "@e-agent/ui-react";
import { WorkspaceNavigation } from "./app/WorkspaceNavigation.tsx";
import { useFollowSubmission, useRouter, useTaskRoute } from "./app/useRouter.ts";
import { ConnectionsPage } from "./pages/Connections.tsx";
import { Overview } from "./pages/Overview.tsx";
import { TaskUnavailable } from "./pages/TaskUnavailable.tsx";

const params = new URLSearchParams(location.search);
const locale = resolveLocale(params.get("lang") ?? navigator.language);
let config: LayoutConfig = { layout: "full-page" };
try {
  config = parseLayoutConfig({ layout: params.get("layout") ?? "full-page" });
} catch {
  // Unknown layout names fall back to the default; never fail open on config.
}

// L8 owns the host document. Invalid query values pin nothing, so the user's
// session preference and then the validated default apply.
const pinned = {
  theme: params.get("theme"),
  appearance: params.get("appearance"),
  density: params.get("density"),
};
const applyPresentation = (presentation: HostPresentation) => {
  const root = document.documentElement;
  root.lang = presentation.locale;
  root.dataset["theme"] = presentation.theme;
  root.dataset["appearance"] = presentation.appearance;
  root.dataset["density"] = presentation.density;
};
document.documentElement.lang = locale;
document.body.className = "ea-root";

const controller = new RunController({ client: new EAgentClient(), locale });
void controller.init();

function App() {
  const { route, navigate } = useRouter();
  const { busy, runId } = useRunState();
  const controller = useController();
  // A submission made anywhere in the app lands on the task surface, so the work the
  // user just started — and any decision it raises — is where they are looking.
  useFollowSubmission(busy, runId, navigate);

  // A run id in the route is a navigation request only: the controller attaches,
  // re-reads the run and applies its safeguards. It is acted on once per navigation
  // and the route then follows the controller, so a failed or superseded address can
  // neither retry forever nor undo a deliberate change the user just made.
  const attach = useCallback((id: string) => controller.attach(id), [controller]);
  const taskRoute = useTaskRoute(route.name === "task" ? route.runId : null, runId, attach, navigate);

  const workspace =
    route.name === "overview" ? (
      <Overview />
    ) : route.name === "connections" ? (
      <ConnectionsPage />
    ) : taskRoute.kind === "unavailable" ? (
      <TaskUnavailable runId={taskRoute.runId} navigate={navigate} />
    ) : undefined;

  return (
    <SlotProvider overrides={{ navigation: () => <WorkspaceNavigation route={route} navigate={navigate} /> }}>
      <Layout
        config={config}
        restorePreference={!params.has("layout")}
        presentation={pinned}
        onPresentation={applyPresentation}
        workspace={workspace}
      />
    </SlotProvider>
  );
}

createRoot(document.getElementById("root") as HTMLElement).render(
  <StrictMode>
    <RunProvider controller={controller}>
      <App />
    </RunProvider>
  </StrictMode>,
);
