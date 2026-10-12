/** Rule findings exactly as recorded. An empty set is not "all checks passed". */
import type { Finding } from "@e-agent/ui-core";
import { useI18n } from "@e-agent/ui-react";
import { Disclosure } from "../../primitives/Disclosure.tsx";

export function RuleFindings({ findings }: { findings: readonly Finding[] }) {
  const { t } = useI18n();
  const checksPass = findings.length > 0 && findings.every(f => f.status === "PASS");
  return (
    <Disclosure
      className="ea-review-details"
      defaultOpen={!checksPass}
      summary={t("approval.checks")}
      badge={checksPass ? <span className="ea-check-pass">✓ {t("approval.allChecks")}</span> : undefined}
    >
      <ul className="ea-findings">
        {findings.map(f => (
          <li
            key={`${f.rule_id}-${f.status}`}
            data-testid="finding"
            data-status={f.status}
            className={`ea-status-${f.status.toLowerCase()}`}
          >
            <strong>{f.status}</strong>
            <span>{f.message}</span>
            <small>
              {f.rule_id} · {f.rule_version}
            </small>
          </li>
        ))}
      </ul>
    </Disclosure>
  );
}
