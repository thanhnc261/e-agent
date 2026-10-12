/** The complete reviewable body of one proposal: terms, revisions, checks and scope. */
import type { ApprovalPresentation } from "@e-agent/ui-core";
import { formatDateTime, formatFieldValue, readableLabel } from "@e-agent/ui-core";
import { useI18n } from "@e-agent/ui-react";
import { Disclosure } from "../../primitives/Disclosure.tsx";
import { MaterialFields } from "./MaterialFields.tsx";
import { RuleFindings } from "./RuleFindings.tsx";

export function ApprovalReview({ presentation: p }: { presentation: ApprovalPresentation }) {
  const { t, locale } = useI18n();
  const revised = p.material_fields.filter(f => f.proposal_previous_value != null);
  return (
    <>
      <MaterialFields fields={p.material_fields} />
      {p.material_fields.some(f => f.proposal_previous_value != null && f.comparison === "current") && (
        <Disclosure className="ea-review-details" summary={t("approval.proposalChanges")}>
          <dl className="ea-meta">
            {revised.map(f => (
              <div key={f.path}>
                <dt>{f.label ?? readableLabel(f.path)}</dt>
                <dd>
                  {formatFieldValue(f.path, f.proposal_previous_value!, locale)} →{" "}
                  {formatFieldValue(f.path, f.value, locale)}
                </dd>
              </div>
            ))}
          </dl>
        </Disclosure>
      )}
      <RuleFindings findings={p.findings} />
      <Disclosure className="ea-review-details" summary={t("approval.details")}>
        <dl className="ea-meta">
          <dt>{t("approval.capability")}</dt>
          <dd data-testid="approval-capability">{p.contract_id}</dd>
          <dt>{t("approval.connection")}</dt>
          <dd>{p.connection_id}</dd>
          <dt>{t("approval.credential")}</dt>
          <dd>{p.credential_subject}</dd>
          <dt>{t("approval.expires")}</dt>
          <dd>
            <time dateTime={p.expires_at}>{formatDateTime(p.expires_at, locale)}</time>
          </dd>
        </dl>
      </Disclosure>
    </>
  );
}
