/**
 * Container measurement owned by L7. CSS handles everything that can be expressed
 * as a style; this exists only for the few behaviors that cannot be — such as
 * whether the task navigation history starts expanded. It observes the layout's own
 * element, so a narrow docked column on a wide monitor is compact.
 */
import { useEffect, useState, type RefObject } from "react";

/** Below this, the surface shows one column and sticky controls take more room. */
export const COMPACT_WIDTH = 760;

export function useContainerWidth(ref: RefObject<HTMLElement | null>): number | null {
  const [width, setWidth] = useState<number | null>(null);
  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    if (typeof ResizeObserver === "undefined") {
      setWidth(element.getBoundingClientRect().width);
      return;
    }
    const observer = new ResizeObserver(entries => {
      const entry = entries[0];
      if (entry) setWidth(entry.contentRect.width);
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, [ref]);
  return width;
}

/** Unmeasured surfaces are treated as wide; the compact rules are the exception. */
export function isCompact(width: number | null): boolean {
  return width !== null && width < COMPACT_WIDTH;
}
