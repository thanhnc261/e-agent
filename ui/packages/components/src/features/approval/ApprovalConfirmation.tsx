/**
 * The explicit second step. Focus moves here on entry, Escape returns to review and
 * no keystroke in the composer or a layout change can reach Confirm.
 */
import { useEffect, useRef } from "react";
import { ActionButton } from "../../primitives/ActionButton.tsx";
import { useI18n } from "@e-agent/ui-react";

export function ApprovalConfirmation({
  canConfirm,
  onConfirm,
  onBack,
  onReject,
}: {
  canConfirm: boolean;
  onConfirm: () => void;
  onBack: () => void;
  onReject: () => void;
}) {
  const { t } = useI18n();
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    ref.current?.focus();
  }, []);
  return (
    <div
      className="ea-decision-footer ea-confirm"
      ref={ref}
      tabIndex={-1}
      data-testid="approval-confirm-prompt"
    >
      <p>{t("approval.confirmPrompt")}</p>
      <div className="ea-actions">
        <ActionButton
          variant="primary"
          isDisabled={!canConfirm}
          onPress={onConfirm}
          data-testid="approval-confirm"
        >
          {t("approval.confirm")}
        </ActionButton>
        <ActionButton onPress={onBack} data-testid="approval-back">
          {t("approval.back")}
        </ActionButton>
        <ActionButton variant="quiet" onPress={onReject} data-testid="approval-reject">
          {t("approval.reject")}
        </ActionButton>
      </div>
    </div>
  );
}
