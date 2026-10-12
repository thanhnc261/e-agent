import { canRequestApprove } from "@e-agent/ui-core";
import { useController } from "../providers/RunProvider.tsx";
import { useRunState } from "./useRunState.ts";

/**
 * The approval machine lives in ui-core. This hook only binds its phase and the
 * commands; it never decides whether a proposal may be approved.
 */
export function usePendingApproval() {
  const c = useController();
  const s = useRunState();
  return {
    ...s.approval,
    canRequestApprove: canRequestApprove(s.approval),
    canConfirm: s.approval.phase === "confirming" && canRequestApprove(s.approval),
    requestConfirm: () => c.requestConfirm(),
    back: () => c.back(),
    reviewAgain: () => c.reviewAgain(),
    approve: () => c.approve(),
    reject: () => c.reject(),
  };
}
