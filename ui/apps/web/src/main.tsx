import "@e-agent/tokens/tokens.css";
import "@e-agent/components/components.css";
import "@e-agent/layouts/layouts.css";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { EAgentClient } from "@e-agent/client";
import { Layout, parseLayoutConfig, type LayoutConfig } from "@e-agent/layouts";
import { isThemeName } from "@e-agent/tokens";
import { resolveLocale, RunController } from "@e-agent/ui-core";
import { RunProvider, SlotProvider } from "@e-agent/ui-react";

const params = new URLSearchParams(location.search);
const locale = resolveLocale(params.get("lang") ?? navigator.language);
const theme = params.get("theme");
let config: LayoutConfig = { layout: "full-page" };
try {
  config = parseLayoutConfig({ layout: params.get("layout") ?? "full-page" });
} catch {
  // Unknown layout names fall back to the default; never fail open on config.
}

document.documentElement.lang = locale;
document.documentElement.dataset["theme"] = isThemeName(theme) ? theme : "light";
document.body.className = "ea-root";

const controller = new RunController({ client: new EAgentClient(), locale });
void controller.init();

createRoot(document.getElementById("root") as HTMLElement).render(
  <StrictMode>
    <RunProvider controller={controller}>
      <SlotProvider overrides={{}}>
        <Layout config={config} />
      </SlotProvider>
    </RunProvider>
  </StrictMode>,
);
