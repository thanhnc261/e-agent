/**
 * <e-agent-overlay server="" theme="light|dark|high-contrast" appearance="calm"
 *                   density="comfortable|compact" lang="vi|en"
 *                   layout="overlay|workbench|sidebar">
 *
 * Shadow DOM isolates the UI from host-page CSS; the public styling API is the
 * token custom properties plus ::part(launcher|panel). Attributes never carry
 * secrets: the session is the server's HttpOnly cookie.
 */
import tokensCss from "@e-agent/tokens/tokens.css?inline";
import componentsCss from "@e-agent/components/components.css?inline";
import layoutsCss from "@e-agent/layouts/layouts.css?inline";
import { createRoot, type Root } from "react-dom/client";
import { EAgentClient } from "@e-agent/client";
import { Layout, parseLayoutConfig, type HostPresentation, type LayoutConfig } from "@e-agent/layouts";
import { resolveLocale, RunController } from "@e-agent/ui-core";
import { RunProvider, SlotProvider } from "@e-agent/ui-react";
// React Aria resolves press/focus targets across shadow roots only with this flag
// (an unstable export of react-stately; re-check on every React Aria upgrade).
import { enableShadowDOM } from "react-stately/private/flags/flags";

enableShadowDOM();

const HOST_RESET = ":host { all: initial; display: contents; }";

export class EAgentOverlay extends HTMLElement {
  static observedAttributes = ["theme", "appearance", "density", "lang", "layout"];
  private root: Root | null = null;
  private controller: RunController | null = null;
  private mount: HTMLDivElement | null = null;

  connectedCallback(): void {
    if (this.root) return;
    const shadow = this.shadowRoot ?? this.attachShadow({ mode: "open" });
    const style = document.createElement("style");
    style.textContent = `${HOST_RESET}\n${tokensCss}\n${componentsCss}\n${layoutsCss}`;
    this.mount = document.createElement("div");
    this.mount.setAttribute("part", "panel");
    shadow.replaceChildren(style, this.mount);
    const server = this.getAttribute("server") ?? "";
    this.controller = new RunController({
      client: new EAgentClient({ baseUrl: server }),
      locale: resolveLocale(this.getAttribute("lang") ?? navigator.language),
      storageKey: "e-agent.overlay.run",
      hostContext: () => ({
        host_kind: "embedded",
        page_url_origin: location.origin,
        locale: this.getAttribute("lang") ?? navigator.language,
        resource_hints: [],
      }),
    });
    this.root = createRoot(this.mount);
    this.render();
    void this.controller.init();
  }

  disconnectedCallback(): void {
    this.root?.unmount();
    this.controller?.dispose();
    this.root = null;
    this.controller = null;
  }

  attributeChangedCallback(name: string): void {
    if (!this.controller) return;
    if (name === "lang") this.controller.setLocale(resolveLocale(this.getAttribute("lang")));
    else this.render();
  }

  /** The element is the shadow host, so presentation is reflected on itself. */
  private applyPresentation = (presentation: HostPresentation): void => {
    this.dataset["theme"] = presentation.theme;
    this.dataset["appearance"] = presentation.appearance;
    this.dataset["density"] = presentation.density;
    this.lang = presentation.locale;
  };

  private config(): LayoutConfig {
    try {
      return parseLayoutConfig({ layout: this.getAttribute("layout") ?? "overlay" });
    } catch {
      return { layout: "overlay" };
    }
  }

  private render(): void {
    if (!this.root || !this.controller) return;
    this.root.render(
      <RunProvider controller={this.controller}>
        <SlotProvider overrides={{}}>
          <Layout
            config={this.config()}
            embedded
            restorePreference={!this.hasAttribute("layout")}
            preferenceKey={`e-agent.surface.embedded.${this.id || "default"}`}
            presentation={{
              theme: this.getAttribute("theme"),
              appearance: this.getAttribute("appearance"),
              density: this.getAttribute("density"),
            }}
            onPresentation={this.applyPresentation}
          />
        </SlotProvider>
      </RunProvider>,
    );
  }
}

if (!customElements.get("e-agent-overlay")) customElements.define("e-agent-overlay", EAgentOverlay);
