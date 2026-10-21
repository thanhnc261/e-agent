/**
 * Headless core surface inventory (enterprise overlay adoption plan FE-00). The
 * vanilla reference host and any replacement UI bind to these names.
 */
import { describe, expect, it } from "vitest";
import * as core from "../src/index.ts";

describe("public ui-core exports", () => {
  it("keeps every name a non-React host binds to", () => {
    expect(Object.keys(core).sort()).toEqual([
      "COMPLETENESS",
      "CanonicalizationError",
      "DIGEST_PROFILE",
      "DISCOVERY_SCHEMA_VERSION",
      "EVIDENCE_SCHEMA",
      "HIDDEN_EVENT_TYPES",
      "KNOWN_EVENT_TYPES",
      "RESULT_STATES",
      "RunController",
      "TERMINAL_STATES",
      "actionStatusKey",
      "canCompose",
      "canRequestApprove",
      "canonicalFields",
      "canonicalize",
      "catalogKeys",
      "digest",
      "emptyRunView",
      "formatDateTime",
      "formatDecimal",
      "formatFieldValue",
      "formatTime",
      "hasResult",
      "initialApproval",
      "isAwaitingDecision",
      "isExpired",
      "presentationMatchesCanonical",
      "projectConnections",
      "projectTaskCatalog",
      "readableLabel",
      "reduceApproval",
      "reduceRunView",
      "resolveLocale",
      "resultStatusKey",
      "runStatusKey",
      "segmentText",
      "selectConversation",
      "selectEvidence",
      "selectOutcome",
      "selectPendingReply",
      "selectThread",
      "selectTimeline",
      "selectVerifiedResults",
      "selectViewMode",
      "statusKey",
      "translate",
      "translateServerHint",
      "verifyDigest",
    ]);
  });
});
