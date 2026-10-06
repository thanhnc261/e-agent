/**
 * L6 default components. They read state only through L5 hooks, render model and
 * provider text as text nodes, and use semantic tokens for every color/spacing.
 * The data-testid/role contract is what ui-conformance checks in any UI.
 */
import { useEffect, useRef, useState, type FormEvent } from "react";
import { Button, Input, Label, TextField } from "react-aria-components";
import { formatDateTime, formatFieldValue, segmentText, TERMINAL_STATES } from "@e-agent/ui-core";
import { useComposer, useController, useI18n, usePendingApproval, useRun, useRunState, useTimeline } from "@e-agent/ui-react";

export function MessageText({ text }: { text: string }) {
  const { t } = useI18n();
  return (
    <span className="ea-text">
      {segmentText(text).map((seg, i) => {
        if (seg.kind === "link") {
          return (
            <a key={i} href={seg.href} target="_blank" rel="noopener noreferrer nofollow" referrerPolicy="no-referrer" title={t("link.external")}>
              {seg.text}
            </a>
          );
        }
        if (seg.kind === "image") {
          // Never load remote images from model text (threat model T1).
          return <span key={i} className="ea-blocked-image" data-testid="blocked-image">{`[${t("image.blocked")}: ${seg.alt} ${seg.url}]`}</span>;
        }
        return <span key={i}>{seg.text}</span>;
      })}
    </span>
  );
}

export function ConnectionStatus() {
  const { connection } = useRunState();
  const { t } = useI18n();
  return (
    <span className="ea-connection" data-testid="connection-status" data-status={connection} role="status">
      {t(`connection.${connection}`)}
    </span>
  );
}

export function Header() {
  const { t } = useI18n();
  const { run } = useRun();
  const controller = useController();
  const active = run && !TERMINAL_STATES.has(run.state) && run.state !== "NEEDS_RECONCILIATION";
  return (
    <header className="ea-header">
      <h1 className="ea-title">{t("app.title")}</h1>
      <ConnectionStatus />
      {run && (
        <span className="ea-run-state" data-testid="run-state" data-state={run.state}>
          {t("run.state")}: {run.state}
        </span>
      )}
      {active && (
        <Button className="ea-button ea-button-quiet" onPress={() => void controller.cancel()} data-testid="run-cancel">
          {t("run.cancel")}
        </Button>
      )}
    </header>
  );
}

export function Composer() {
  const { t } = useI18n();
  const { busy, submit } = useComposer();
  const [task, setTask] = useState("");
  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!task.trim()) return;
    void submit(task).then(() => setTask(""));
  };
  // Enter in this form only ever starts a run; it can never approve anything.
  return (
    <form className="ea-composer" onSubmit={onSubmit} data-testid="composer">
      <TextField className="ea-field" value={task} onChange={setTask} isDisabled={busy} aria-label={t("composer.label")}>
        <Label className="ea-visually-hidden">{t("composer.label")}</Label>
        <Input className="ea-input" placeholder={t("composer.placeholder")} data-testid="composer-input" />
      </TextField>
      <Button type="submit" className="ea-button ea-button-primary" isDisabled={busy || !task.trim()} data-testid="composer-submit">
        {t("composer.submit")}
      </Button>
    </form>
  );
}

export function Messages() {
  const { t } = useI18n();
  const { run, finalMessage, error } = useRun();
  return (
    <section className="ea-panel" aria-labelledby="ea-messages-title" data-testid="messages">
      <h2 id="ea-messages-title" className="ea-panel-title">{t("messages.title")}</h2>
      {!run && <p className="ea-muted">{t("messages.empty")}</p>}
      {run && (
        <p className="ea-user-task" data-testid="run-task">
          {run.task}
        </p>
      )}
      {finalMessage && (
        <div className="ea-agent-message" data-testid="final-message">
          <strong>{t("messages.final")}: </strong>
          <MessageText text={finalMessage} />
        </div>
      )}
      {error && (
        <p className="ea-error" role="alert" data-testid="error">
          {error}
        </p>
      )}
    </section>
  );
}

export function Timeline() {
  const { t, locale } = useI18n();
  const items = useTimeline();
  return (
    <section className="ea-panel" aria-labelledby="ea-timeline-title" data-testid="timeline">
      <h2 id="ea-timeline-title" className="ea-panel-title">{t("timeline.title")}</h2>
      {items.length === 0 && <p className="ea-muted">{t("timeline.empty")}</p>}
      <ol className="ea-timeline">
        {items.map((item) => (
          <li key={item.sequence} data-testid="timeline-item" data-type={item.type} data-supported={item.supported}>
            <span className="ea-timeline-label">{t(item.labelKey)}</span>
            {item.detail && <span className="ea-timeline-detail"> · {item.detail}</span>}
            <time className="ea-muted" dateTime={item.occurredAt}> {formatDateTime(item.occurredAt, locale)}</time>
          </li>
        ))}
      </ol>
    </section>
  );
}

export function ApprovalPanel() {
  const { t, locale } = useI18n();
  const a = usePendingApproval();
  const confirmRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    // Move focus to the prompt, not the confirm button: confirming needs its own action.
    if (a.phase === "confirming") confirmRef.current?.focus();
  }, [a.phase]);
  const p = a.presentation;
  if (!p || a.phase === "idle") {
    return (
      <section className="ea-panel ea-approval" aria-labelledby="ea-approval-title" data-testid="approval" data-phase="idle">
        <h2 id="ea-approval-title" className="ea-panel-title">{t("approval.title")}</h2>
        <p className="ea-muted">{t("approval.none")}</p>
      </section>
    );
  }
  return (
    <section className="ea-panel ea-approval" aria-labelledby="ea-approval-title" data-testid="approval" data-phase={a.phase}>
      <h2 id="ea-approval-title" className="ea-panel-title">{t("approval.title")}</h2>
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
      <table className="ea-fields">
        <thead>
          <tr>
            <th scope="col">{t("approval.field")}</th>
            <th scope="col">{t("approval.value")}</th>
            <th scope="col">{t("approval.previous")}</th>
          </tr>
        </thead>
        <tbody>
          {p.material_fields.map((f) => (
            <tr key={f.path} data-testid="material-field" data-path={f.path} data-changed={f.changed} className={f.changed ? "ea-changed" : undefined}>
              <th scope="row">{f.path}</th>
              <td>
                {formatFieldValue(f.path, f.value, locale)}
                {f.changed && <span className="ea-badge ea-badge-change"> {t("approval.changed")}</span>}
              </td>
              <td className="ea-muted">{f.changed ? (f.previous_value ?? "—") : ""}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <h3 className="ea-subtitle">{t("approval.findings")}</h3>
      {p.findings.length === 0 && <p className="ea-muted">{t("approval.noFindings")}</p>}
      <ul className="ea-findings">
        {p.findings.map((f) => (
          <li key={`${f.rule_id}-${f.status}`} data-testid="finding" data-status={f.status} className={`ea-status-${f.status.toLowerCase()}`}>
            <strong>{f.status}</strong> {f.rule_id}: {f.message}
          </li>
        ))}
      </ul>
      {a.digestOk === false && (
        <p className="ea-error" role="alert" data-testid="approval-digest-mismatch">
          {t("approval.digestMismatch")}
        </p>
      )}
      {a.phase === "expired" && (
        <p className="ea-error" role="alert" data-testid="approval-expired">
          {t("approval.expired")}
        </p>
      )}
      {a.phase === "stale" && (
        <div className="ea-warning" role="alert" data-testid="approval-stale">
          <p>{t("approval.stale")}</p>
          <Button className="ea-button" onPress={a.reviewAgain} data-testid="approval-review-again">
            {t("approval.reviewAgain")}
          </Button>
        </div>
      )}
      {a.phase === "error" && (
        <p className="ea-error" role="alert">
          {t("approval.error")} {a.error}
        </p>
      )}
      {a.phase === "submitting" && <p role="status">{t("approval.submitting")}</p>}
      {a.phase === "approved" && <p role="status" data-testid="approval-approved">{t("approval.approved")}</p>}
      {a.phase === "rejected" && <p role="status" data-testid="approval-rejected">{t("approval.rejected")}</p>}
      {a.phase === "reviewing" && (
        <div className="ea-actions">
          <Button className="ea-button ea-button-primary" isDisabled={!a.canRequestApprove} onPress={a.requestConfirm} data-testid="approval-approve">
            {t("approval.approve")}
          </Button>
          <Button className="ea-button" onPress={() => void a.reject()} data-testid="approval-reject">
            {t("approval.reject")}
          </Button>
        </div>
      )}
      {a.phase === "confirming" && (
        <div className="ea-confirm" ref={confirmRef} tabIndex={-1} data-testid="approval-confirm-prompt">
          <p>{t("approval.confirmPrompt")}</p>
          <div className="ea-actions">
            <Button className="ea-button ea-button-primary" isDisabled={!a.canConfirm} onPress={() => void a.approve()} data-testid="approval-confirm">
              {t("approval.confirm")}
            </Button>
            <Button className="ea-button" onPress={a.back} data-testid="approval-back">
              {t("approval.back")}
            </Button>
            <Button className="ea-button" onPress={() => void a.reject()} data-testid="approval-reject">
              {t("approval.reject")}
            </Button>
          </div>
        </div>
      )}
    </section>
  );
}

export function OutcomePanel() {
  const { t } = useI18n();
  const { run, actions } = useRun();
  const controller = useController();
  if (!run) return null;
  return (
    <section className="ea-panel" aria-labelledby="ea-outcome-title" data-testid="outcome">
      <h2 id="ea-outcome-title" className="ea-panel-title">{t("outcome.title")}</h2>
      <p className={`ea-run-outcome ea-state-${run.state.toLowerCase()}`} data-testid="outcome-state" data-state={run.state}>
        {run.state}
        {run.reason ? ` — ${run.reason}` : ""}
      </p>
      <ul className="ea-actions-list">
        {actions.map((a) => (
          <li key={a.action_id} data-testid="action" data-state={a.state} className={`ea-action-${a.state.toLowerCase()}`}>
            {a.contract_id}: <strong>{a.state}</strong>
          </li>
        ))}
      </ul>
      {run.state === "NEEDS_RECONCILIATION" && (
        <div className="ea-warning" role="alert" data-testid="outcome-unresolved">
          <p>{t("outcome.unresolved")}</p>
          <Button className="ea-button" onPress={() => void controller.reconcile()} data-testid="outcome-reconcile">
            {t("outcome.reconcile")}
          </Button>
        </div>
      )}
    </section>
  );
}

export function EvidencePanel() {
  const { t } = useI18n();
  const { run } = useRun();
  const { evidence } = useRunState();
  const controller = useController();
  const done = run && (TERMINAL_STATES.has(run.state) || run.state === "NEEDS_RECONCILIATION");
  return (
    <section className="ea-panel" aria-labelledby="ea-evidence-title" data-testid="evidence">
      <h2 id="ea-evidence-title" className="ea-panel-title">{t("evidence.title")}</h2>
      {!done && <p className="ea-muted">{t("evidence.empty")}</p>}
      {done && !evidence && (
        <Button className="ea-button" onPress={() => void controller.loadEvidence()} data-testid="evidence-load">
          {t("evidence.load")}
        </Button>
      )}
      {evidence && (
        <pre className="ea-evidence" data-testid="evidence-bundle">
          {JSON.stringify(evidence, null, 2)}
        </pre>
      )}
    </section>
  );
}

export function Footer() {
  return null;
}

export const defaultSlots = {
  header: Header,
  composer: Composer,
  messages: Messages,
  timeline: Timeline,
  approval: ApprovalPanel,
  evidence: EvidencePanel,
  outcome: OutcomePanel,
  "connection-status": ConnectionStatus,
  footer: Footer,
} as const;
