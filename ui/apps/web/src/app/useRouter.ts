/**
 * Hash router (L8). The controller is created above the router and never
 * remounted, so navigating preserves the active run, the submission identity and
 * the in-memory draft, and issues no command of its own.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { formatRoute, parseRoute, sameRoute, type Route } from "./routes.ts";

export interface NavigateOptions {
  /**
   * Replace the current entry instead of pushing one. Used when the route is
   * catching up with a deliberate controller change, so Back does not return the
   * user to an address that no longer describes anything.
   */
  replace?: boolean;
}

export type Navigate = (route: Route, options?: NavigateOptions) => void;

export function useRouter(): { route: Route; navigate: Navigate } {
  const [route, setRoute] = useState<Route>(() => parseRoute(location.hash));
  useEffect(() => {
    const onHashChange = () => setRoute(parseRoute(location.hash));
    addEventListener("hashchange", onHashChange);
    return () => removeEventListener("hashchange", onHashChange);
  }, []);
  const navigate = useCallback<Navigate>((next, options) => {
    if (sameRoute(parseRoute(location.hash), next)) {
      setRoute(next);
      return;
    }
    if (options?.replace) {
      // `replaceState` does not fire hashchange, so the state is set directly.
      history.replaceState(history.state, "", `${location.pathname}${location.search}${formatRoute(next)}`);
      setRoute(next);
      return;
    }
    // Pushing the hash keeps Back working; the hashchange listener sets the state.
    location.hash = formatRoute(next);
  }, []);
  return { route, navigate };
}

/**
 * Follow a submission the user made here to the task surface.
 *
 * Only `start` puts the controller in its busy state, so this reacts to an actual
 * submission from this page. A run merely restored from an earlier visit never
 * redirects: resuming is the user's choice, made from session work.
 */
export function useFollowSubmission(busy: boolean, runId: string | null, navigate: Navigate): void {
  const submitting = useRef(false);
  useEffect(() => {
    if (busy) {
      submitting.current = true;
      return;
    }
    if (submitting.current && runId) {
      submitting.current = false;
      navigate({ name: "task", runId });
    }
    if (!runId) submitting.current = false;
  }, [busy, runId, navigate]);
}

/**
 * How a task route and the controller stay in agreement.
 *
 * `requested` is the run id the address bar names. It is a navigation *request*:
 * the controller alone attaches, re-reads the run and applies its safeguards.
 */
export type TaskRouteState =
  | { kind: "none" }
  | { kind: "attaching"; runId: string }
  | { kind: "attached"; runId: string }
  /** The attach was refused or the run is gone. Do not retry; say so instead. */
  | { kind: "unavailable"; runId: string };

/**
 * Act on a task route exactly once per navigation, then let the controller lead.
 *
 * Two rules, and they are deliberately not symmetric:
 *
 * 1. A requested run is attached once. If that attach fails — the run is missing,
 *    deleted or not visible to this principal — the result is an explicit
 *    unavailable state. Re-rendering must never retry it: the controller detaches
 *    on a 404, which would otherwise make "route names X, controller has nothing"
 *    permanently true and drive an unbounded request loop.
 * 2. Once attached, the route follows the controller. New task and picking another
 *    task from history are deliberate controller changes, so the address catches up
 *    (replacing the entry) instead of the stale address undoing the user's action.
 */
export function useTaskRoute(
  requested: string | null,
  runId: string | null,
  attach: (runId: string) => Promise<boolean>,
  navigate: Navigate,
): TaskRouteState {
  const [state, setState] = useState<TaskRouteState>({ kind: "none" });
  const acting = useRef<string | null>(null);

  useEffect(() => {
    if (requested === null) {
      acting.current = null;
      setState(current => (current.kind === "none" ? current : { kind: "none" }));
      return;
    }
    if (acting.current === requested) return; // Already acted on this navigation.
    acting.current = requested;
    if (requested === runId) {
      // Already the current run — a submission that just landed here, or a repeat of
      // the address. Nothing to attach. This is checked only on the first evaluation
      // for this address: `attach` sets the controller's run id optimistically, so
      // after that point an equal id proves nothing about whether the read succeeded.
      setState({ kind: "attached", runId: requested });
      return;
    }
    setState({ kind: "attaching", runId: requested });
    // The outcome is not discarded when this effect re-runs: `attach` sets the
    // controller's run id before the read completes, so a re-run is expected mid
    // attach. Only a newer navigation supersedes this one, which `acting` records.
    void attach(requested).then(ok => {
      if (acting.current !== requested) return;
      setState({ kind: ok ? "attached" : "unavailable", runId: requested });
    });
  }, [requested, runId, attach]);

  // Rule 2. The address follows the controller only once *this* address has settled
  // as attached. While an attach is still in flight the controller's run id is the
  // previous one, so following it would undo the navigation being performed; and a
  // route whose attach failed keeps its unavailable state instead of bouncing away.
  useEffect(() => {
    if (requested === null || requested === runId) return;
    if (state.kind !== "attached" || state.runId !== requested) return;
    navigate(runId === null ? { name: "overview" } : { name: "task", runId }, { replace: true });
  }, [requested, runId, state, navigate]);

  return state;
}
