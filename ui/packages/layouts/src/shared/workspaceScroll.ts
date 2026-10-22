/**
 * The side workspace's own scroll region (G-D 4.U4, AG-APPR-3, AG-STAT-1). Beside a wide
 * thread the workspace scrolls inside itself, under a sticky head. This hook:
 * - reports whether more content is below, for a visible cue that is shown only while
 *   `scrollTop + clientHeight < scrollHeight`;
 * - writes the head's height (`--ea-ws-head-h`) and the tab list's (`--ea-ws-tabs-h`) to the
 *   region, so a bring-into-view and keyboard focus land below the sticky head, never under it;
 * - writes the height of the surface's own scroll container (`--ea-ws-room`), when the thread
 *   scrolls inside one (Docked, Compact, Workbench), so the region fits in it and stays sticky
 *   with its head in view at the end of a long thread.
 * Without `ResizeObserver` (a test DOM), it measures once and on scroll.
 */
import { useLayoutEffect, useState, type RefObject } from "react";

export function useWorkspaceScroll(region: RefObject<HTMLElement | null>, mounted: boolean): boolean {
  const [more, setMore] = useState(false);
  // A layout effect, so the sizes are written before a child's bring-into-view (a passive
  // effect, as ApprovalPanel's) scrolls the region.
  useLayoutEffect(() => {
    const el = region.current;
    if (!mounted || !el) return;
    const scroller = scrollContainer(el.parentElement);
    const update = () => {
      if (scroller) el.style.setProperty("--ea-ws-room", `${scroller.clientHeight}px`);
      const head = el.querySelector<HTMLElement>(".ea-ws-head");
      const tabs = el.querySelector<HTMLElement>(".ea-tab-list");
      if (head) el.style.setProperty("--ea-ws-head-h", `${head.offsetHeight}px`);
      if (tabs) el.style.setProperty("--ea-ws-tabs-h", `${tabs.offsetHeight}px`);
      setMore(el.scrollTop + el.clientHeight < el.scrollHeight - 1);
    };
    update();
    el.addEventListener("scroll", update, { passive: true });
    let observer: ResizeObserver | null = null;
    if (typeof ResizeObserver === "function") {
      observer = new ResizeObserver(update);
      observer.observe(el);
      if (scroller) observer.observe(scroller);
      // The region keeps its size while its content grows; observe what it holds.
      for (const child of Array.from(el.children)) observer.observe(child);
    }
    return () => {
      el.removeEventListener("scroll", update);
      observer?.disconnect();
    };
  }, [region, mounted]);
  return more;
}

/** The nearest ancestor that scrolls vertically; null when the page itself scrolls. */
function scrollContainer(from: HTMLElement | null): HTMLElement | null {
  for (let node = from; node; node = node.parentElement) {
    const overflow = getComputedStyle(node).overflowY;
    if (overflow === "auto" || overflow === "scroll") return node;
  }
  return null;
}
