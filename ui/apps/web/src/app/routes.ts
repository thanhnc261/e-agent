/**
 * Standalone routes (L8). Hash routes avoid a server history-fallback requirement
 * and keep the existing layout/lang/theme query parameters untouched.
 *
 * A route is a navigation request and nothing more: it carries no secret and no
 * task text, and a run id in it is only a request to attach through the authorized
 * controller, which re-reads the run and applies its own safeguards.
 */
export type Route = { name: "overview" } | { name: "connections" } | { name: "task"; runId: string | null };

export const DEFAULT_ROUTE: Route = { name: "overview" };

/** Run ids are opaque; accept only a conservative, URL-safe shape. */
const RUN_ID = /^[A-Za-z0-9_:.-]{1,128}$/;

export function parseRoute(hash: string): Route {
  const path = hash.replace(/^#/, "").replace(/^\/+/, "");
  const [head = "", tail = ""] = path.split("/", 2);
  if (head === "" || head === "overview") return { name: "overview" };
  if (head === "connections") return { name: "connections" };
  if (head === "task") return { name: "task", runId: decodeRunId(tail) };
  return DEFAULT_ROUTE; // Unknown routes fall back; never fail open on navigation.
}

/**
 * A run id arrives from the address bar, so it may be malformed percent-encoding
 * (`%`), a traversal attempt or simply too long. Every one of those is "no run id",
 * never an exception: a URL a user can type must not be able to stop the app.
 */
function decodeRunId(tail: string): string | null {
  if (tail === "") return null;
  let decoded: string;
  try {
    decoded = decodeURIComponent(tail);
  } catch {
    return null; // URIError: malformed encoding is not a navigation request.
  }
  return RUN_ID.test(decoded) ? decoded : null;
}

export function formatRoute(route: Route): string {
  if (route.name === "task") return route.runId ? `#/task/${encodeURIComponent(route.runId)}` : "#/task";
  return `#/${route.name}`;
}

export function sameRoute(a: Route, b: Route): boolean {
  return formatRoute(a) === formatRoute(b);
}
