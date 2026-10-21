/**
 * The thread composition every placement uses in `conversations: on` (ADR 0034 §2, mockup A1):
 * the conversation with one composer, and beside it the closable artifact workspace.
 *
 * Geometry is decided on the thread's own width, in rem, so it holds at 200 % text:
 * - at 60 rem and wider the workspace sits beside the thread at about 40 % (22–34 rem), and
 *   opens by itself for a new decision or a result (G-B 6), without moving focus;
 * - narrower, an open workspace replaces the thread as a full view with "Back to
 *   conversation", and opens only from a run card.
 * The CSS container query and `useContainerWidth` use the same 60 rem threshold.
 */
import { useEffect, useRef } from "react";
import { ConnectionStatus, useArtifactWorkspace } from "@e-agent/components";
import { hasResult, isAwaitingDecision, selectThread } from "@e-agent/ui-core";
import { useI18n, usePendingApproval, useRunState } from "@e-agent/ui-react";
import type { LayoutConfig } from "../config.ts";
import { useContainerWidth } from "../presentation/useContainerWidth.ts";
import { ArtifactWorkspace } from "./ArtifactWorkspace.tsx";
import { ConfiguredSlot } from "./ConfiguredSlot.tsx";
import { useWorkspaceFocus } from "./workspaceFocus.ts";

/** The thread's width, in rem, from which the workspace sits beside it. */
export const SIDE_BY_SIDE_REM = 60;

/** One rem in px: the root's font size, which is what the container query's `60rem` means. */
function rootRem(element: HTMLElement | null): number {
  const root = element?.ownerDocument.documentElement;
  const size = root ? parseFloat(getComputedStyle(root).fontSize) : NaN;
  return Number.isFinite(size) && size > 0 ? size : 16;
}

export function ThreadSurface({ config, navigation }: { config: LayoutConfig; navigation: boolean }) {
  const { t } = useI18n();
  const state = useRunState();
  const approval = usePendingApproval();
  const workspace = useArtifactWorkspace();
  const focus = useWorkspaceFocus();
  const shellRef = useRef<HTMLDivElement>(null);
  const width = useContainerWidth(shellRef);
  const wide = width !== null && width >= SIDE_BY_SIDE_REM * rootRem(shellRef.current);
  const entries = selectThread(state.thread, state);
  const runId = state.view.run?.run_id === state.runId ? state.runId : null;
  const runState = state.view.run?.state;

  // Opens by itself, once each, for a new decision or a result of the active run; never for
  // a reply, and never on a narrow surface, where it would hide the conversation.
  const auto = !runId
    ? null
    : isAwaitingDecision(approval.phase)
      ? `decision:${approval.presentation?.action_id ?? ""}`
      : runState && hasResult(runState) && !["VERIFYING", "CANCELLED"].includes(runState)
        ? `result:${runId}:${runState}`
        : null;
  useEffect(() => {
    if (!auto || !runId || !wide || !workspace || !focus.claimAutoOpen(auto)) return;
    if (workspace.runId !== runId) workspace.open(runId);
  }, [auto, runId, wide, workspace, focus]);

  // A run that left the thread (New conversation, another conversation) closes its workspace.
  const open = workspace?.runId ?? null;
  const shown = open !== null && entries.some(entry => entry.runId === open);
  useEffect(() => {
    if (open !== null && !shown && state.thread.status !== "loading") focus.dismiss();
  }, [open, shown, state.thread.status, focus]);

  const title =
    state.threads.kind === "ready"
      ? state.threads.items.find(row => row.conversation_id === state.conversationId)?.title
      : undefined;
  return (
    <div className="ea-thread-shell" ref={shellRef}>
      <div className="ea-thread-grid" data-workspace-open={shown}>
        <div className="ea-thread-main">
          {navigation && <ConfiguredSlot name="navigation" config={config} />}
          <div className="ea-thread-head" data-testid="thread-head">
            <p className="ea-thread-title">{title || t("nav.new")}</p>
            {/* The stream status, at every width (S-2). Rendered directly, as the header did,
                so no layout config can hide a lost or stale connection (AG-STAT-3). */}
            <ConnectionStatus />
          </div>
          <ConfiguredSlot name="messages" config={config} />
          <ConfiguredSlot name="composer" config={config} />
        </div>
        {shown && open && <ArtifactWorkspace config={config} runId={open} />}
      </div>
    </div>
  );
}
