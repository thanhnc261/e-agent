/**
 * Presentation precedence (enterprise overlay adoption plan §4): explicit host
 * configuration, then a scoped session preference, then the validated default.
 */
import { beforeEach, describe, expect, it } from "vitest";
import { PRESENTATION_DEFAULTS, resolvePresentation } from "../src/presentation/preferences.ts";

const KEY = "test.surface";

class MemoryStorage {
  private readonly map = new Map<string, string>();
  getItem = (k: string) => this.map.get(k) ?? null;
  setItem = (k: string, v: string) => void this.map.set(k, v);
  removeItem = (k: string) => void this.map.delete(k);
  clear = () => this.map.clear();
  key = () => null;
  get length() {
    return this.map.size;
  }
}

beforeEach(() => {
  Object.defineProperty(globalThis, "sessionStorage", { value: new MemoryStorage(), configurable: true });
});

describe("presentation preference precedence", () => {
  it("falls back to validated defaults with no config and no preference", () => {
    const { values, locked } = resolvePresentation({}, KEY, true);
    expect(values).toEqual(PRESENTATION_DEFAULTS);
    expect(locked).toEqual({ theme: false, appearance: false, density: false });
  });

  it("uses a stored session preference when the host pins nothing", () => {
    sessionStorage.setItem(`${KEY}.theme`, "dark");
    sessionStorage.setItem(`${KEY}.density`, "compact");
    const { values, locked } = resolvePresentation({}, KEY, true);
    expect(values.theme).toBe("dark");
    expect(values.density).toBe("compact");
    expect(locked.theme).toBe(false);
  });

  it("lets explicit host configuration win and marks the dimension locked", () => {
    sessionStorage.setItem(`${KEY}.theme`, "dark");
    const { values, locked } = resolvePresentation({ theme: "high-contrast" }, KEY, true);
    expect(values.theme).toBe("high-contrast");
    expect(locked.theme).toBe(true);
  });

  it("ignores invalid host values and invalid stored values instead of failing open", () => {
    sessionStorage.setItem(`${KEY}.density`, "roomy");
    const { values, locked } = resolvePresentation({ theme: "neon", appearance: "" }, KEY, true);
    expect(values).toEqual(PRESENTATION_DEFAULTS);
    expect(locked.theme).toBe(false);
  });

  it("skips stored preferences when the host disables restoring them", () => {
    sessionStorage.setItem(`${KEY}.theme`, "dark");
    expect(resolvePresentation({}, KEY, false).values.theme).toBe("light");
  });

  it("keeps preferences scoped to their key", () => {
    sessionStorage.setItem("other.theme", "dark");
    expect(resolvePresentation({}, KEY, true).values.theme).toBe("light");
  });
});
