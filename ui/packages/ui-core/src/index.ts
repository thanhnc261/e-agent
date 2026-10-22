export * from "./approval.ts";
export * from "./controller.ts";
export * from "./digest.ts";
export * from "./format.ts";
export * from "./i18n.ts";
export * from "./sanitize.ts";
export * from "./store.ts";
export * from "./presentation.ts";
export * from "./selectors/discovery.ts";
export * from "./selectors/evidence.ts";
export * from "./selectors/explanation.ts";
export * from "./selectors/outcome.ts";
export * from "./selectors/thread.ts";

/**
 * Wire contracts upper layers render. L3 owns the projection boundary, so L6/L7
 * type their props from here instead of importing the L2 client directly.
 */
export type {
  ActionState,
  ActionSummary,
  ApprovalPresentation,
  ConversationSummary,
  Finding,
  MaterialField,
  RunEvent,
  RunRecord,
  RunState,
} from "@e-agent/client";
