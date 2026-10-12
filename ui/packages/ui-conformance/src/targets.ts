import type { Page } from "@playwright/test";

export interface UiTarget {
  name: string;
  /** Path for a locale; the UI must honor ?lang=vi|en (or an equivalent attribute). */
  url(lang?: "vi" | "en"): string;
  /** Bring the agent UI on screen (e.g. open an overlay launcher). */
  open(page: Page): Promise<void>;
}

async function noop(): Promise<void> {}

export const TARGETS: UiTarget[] = [
  { name: "default", url: (lang = "en") => `/?lang=${lang}`, open: noop },
  {
    name: "overlay",
    url: (lang = "en") => `/host.html?lang=${lang}`,
    open: async page => {
      const launcher = page.getByTestId("overlay-launcher");
      await launcher.waitFor();
      if ((await launcher.getAttribute("aria-expanded")) !== "true") await launcher.click();
    },
  },
  {
    name: "workbench",
    url: (lang = "en") => `/?layout=workbench&lang=${lang}`,
    open: async page => {
      const launcher = page.getByTestId("overlay-launcher");
      if ((await launcher.getAttribute("aria-expanded")) !== "true") await launcher.click();
    },
  },
  // Docked is approval-capable too, so it carries the same shared contract.
  { name: "sidebar", url: (lang = "en") => `/?layout=sidebar&lang=${lang}`, open: noop },
  { name: "reference", url: (lang = "en") => `/reference/?lang=${lang}`, open: noop },
];
