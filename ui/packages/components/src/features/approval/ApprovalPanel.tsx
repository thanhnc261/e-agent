/**
 * Approval container. Every gate (digest, completeness, findings, freshness,
 * explicit confirmation) stays in the ui-core machine; this component only renders
 * its phase and forwards the user's commands.
 */
import { useEffect, useRef } from "react";
import { ActionButton } from "../../primitives/ActionButton.tsx";
import { Disclosure } from "../../primitives/Disclosure.tsx";
import { formatDateTime } from "@e-agent/ui-core";
import { useI18n, usePendingApproval, useRun } from "@e-agent/ui-react";
import { ApprovalConfirmation } from "./ApprovalConfirmation.tsx";
import { ApprovalReview } from "./ApprovalReview.tsx";

export function ApprovalPanel() {
  const { t, locale } = useI18n();
  const a = usePendingApproval();
  const { run } = useRun();
  const panelRef = useRef<HTMLElement>(null);
  // A proposal the user has not seen is brought into view once, in every placement
  // and without taking focus. `nearest` leaves an already-visible panel alone, and
  // the motion preference is honored because scrolling is not decoration here.
  const actionId = a.presentation?.action_id;
  useEffect(() => {
    if (!actionId) return;
    const reduced =
      typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;
    panelRef.current?.scrollIntoView({ block: "nearest", behavior: reduced ? "auto" : "smooth" });
  }, [actionId]);
  const p = a.presentation;
  if (!p || a.phase === "idle") return null;
  const decided = a.phase === "approved" || a.phase === "rejected";
  const reviewBody = <ApprovalReview presentation={p} />;
  return (
    <section
      className={`ea-panel ea-approval ${decided ? "ea-decision-recorded" : ""}`}
      ref={panelRef}
      data-testid="approval"
      data-phase={a.phase}
      aria-label={t("approval.title")}
    >
      <div className="ea-decision-heading">
        <span className="ea-decision-icon" aria-hidden="true">
          {decided ? "✓" : "◇"}
        </span>
        <div>
          <p className="ea-eyebrow">{t("approval.kicker")}</p>
          <h2 className="ea-panel-title">
            {decided
              ? t(a.phase === "approved" ? "approval.approved" : "approval.rejected")
              : (p.display_title ?? t("approval.title"))}
          </h2>
        </div>
      </div>
      {decided ? (
        <Disclosure className="ea-review-details" summary={t("approval.viewDecision")}>
          {reviewBody}
        </Disclosure>
      ) : (
        <>
          <p className="ea-muted ea-decision-description">
            {p.expected_effects?.join(" · ") || t("approval.description")}
          </p>
          <div className="ea-decision-body">{reviewBody}</div>
        </>
      )}
      {a.digestOk === false && (
        <p className="ea-alert ea-error" role="alert" data-testid="approval-digest-mismatch">
          {t("approval.digestMismatch")}
        </p>
      )}
      {a.phase === "expired" && (
        <p className="ea-alert ea-error" role="alert" data-testid="approval-expired">
          {t("approval.expired")}
        </p>
      )}
      {a.phase === "stale" && (
        <div className="ea-alert ea-warning" role="alert" data-testid="approval-stale">
          <p>{t("approval.stale")}</p>
          <ActionButton onPress={a.reviewAgain} data-testid="approval-review-again">
            {t("approval.reviewAgain")}
          </ActionButton>
        </div>
      )}
      {a.phase === "error" && (
        <p className="ea-alert ea-error" role="alert">
          {t("approval.error")}
        </p>
      )}
      {a.phase === "submitting" && <p role="status">{t("approval.submitting")}</p>}
      {a.phase === "approved" && (
        <span className="ea-visually-hidden" data-testid="approval-approved">
          {t("approval.approved")}
        </span>
      )}
      {a.phase === "rejected" && (
        <span className="ea-visually-hidden" data-testid="approval-rejected">
          {t("approval.rejected")}
        </span>
      )}
      {a.phase === "reviewing" && (
        <div className="ea-decision-footer">
          <span className="ea-muted ea-small">
            {t("approval.expires")} {formatDateTime(p.expires_at, locale)}
          </span>
          <div className="ea-actions">
            <ActionButton
              variant="primary"
              isDisabled={!a.canRequestApprove}
              onPress={a.requestConfirm}
              data-testid="approval-approve"
            >
              {t("approval.approve")}
            </ActionButton>
            <ActionButton variant="quiet" onPress={() => void a.reject()} data-testid="approval-reject">
              {t("approval.reject")}
            </ActionButton>
          </div>
        </div>
      )}
      {a.phase === "confirming" && (
        <ApprovalConfirmation
          canConfirm={a.canConfirm}
          onConfirm={() => void a.approve()}
          onBack={a.back}
          onReject={() => void a.reject()}
        />
      )}
      {decided && run?.state === "NEEDS_RECONCILIATION" && (
        <p className="ea-warning">{t("outcome.effectUnknown")}</p>
      )}
    </section>
  );
}
