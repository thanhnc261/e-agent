/**
 * The explanation of the attached run and the citations of its answer (ADR 0033 §6, ADR 0034
 * §3, §4), from the run's evidence bundle through `selectExplanation`. It opens from the
 * result and from the activity (ADR 0034 §4); opening it reads the bundle when this session
 * has not read it yet, so nothing is fetched for a disclosure nobody opens.
 *
 * Order: the cited records, then the server's explanation in its own order (goal, source
 * facts, rules, proposals, rationale refs, approvals, receipts, outcomes), then the agent's
 * own words. Facts come before any model-authored text (AG-EXPL-1, AG-EXPL-3). Each value
 * keeps the server's label; a value that is not recorded says so, never an empty value
 * (EA-8). A citation is never "verified", and one stored only as digests is never a fact.
 */
import { useRef, useState, type ReactNode } from "react";
import {
  actionStatusKey,
  formatFieldValue,
  readableLabel,
  selectExplanation,
  type CitationGroup,
  type CitationView,
  type ExplanationBody,
  type ValueLabel,
} from "@e-agent/ui-core";
import { useController, useI18n, useRunState } from "@e-agent/ui-react";
import { ActionButton } from "../../primitives/ActionButton.tsx";
import { Disclosure } from "../../primitives/Disclosure.tsx";

type Translate = (key: string) => string;
type LoadState = "idle" | "loading" | "failed";

export function Explanation({ testId = "explanation" }: { testId?: string }) {
  const { t } = useI18n();
  const { evidence, view } = useRunState();
  const controller = useController();
  const [load, setLoad] = useState<LoadState>("idle");
  // One read at a time, even when two toggle events arrive before a re-render.
  const reading = useRef(false);
  const explained = selectExplanation(evidence);
  const read = () => {
    if (reading.current) return;
    reading.current = true;
    setLoad("loading");
    void controller.loadEvidence().then(() => {
      reading.current = false;
      setLoad(controller.getState().evidence ? "idle" : "failed");
    });
  };
  const onToggle = (event: { currentTarget: EventTarget }) => {
    if ((event.currentTarget as HTMLDetailsElement).open && !evidence) read();
  };
  const runRevision = view.run?.revision ?? null;
  return (
    <Disclosure
      className="ea-review-details ea-explanation"
      summary={t("explain.open")}
      data-testid={testId}
      onToggle={onToggle}
    >
      {explained.kind === "absent" && (
        <>
          <p
            className={load === "failed" ? "ea-alert ea-warning" : "ea-muted ea-small"}
            role={load === "loading" ? "status" : undefined}
            data-testid="explain-state"
            data-state={load === "idle" ? "absent" : load}
          >
            {t(
              load === "loading"
                ? "explain.loading"
                : load === "failed"
                  ? "explain.failed"
                  : "explain.absent",
            )}
          </p>
          {load === "failed" && (
            <ActionButton variant="quiet" onPress={read}>
              {t("explain.retry")}
            </ActionButton>
          )}
        </>
      )}
      {explained.kind === "unsupported" && (
        <p className="ea-alert ea-warning" data-testid="explain-state" data-state="unsupported">
          {t("evidence.unsupported")}
          {explained.schema ? ` (${explained.schema})` : ""}
        </p>
      )}
      {explained.kind === "ready" && (
        <>
          {explained.revision !== null && runRevision !== null && explained.revision !== runRevision && (
            <p className="ea-muted ea-small" data-testid="explain-stale">
              {t("explain.stale")}{" "}
              <ActionButton variant="quiet" isPending={load === "loading"} onPress={read}>
                {t("explain.refresh")}
              </ActionButton>
            </p>
          )}
          {explained.citations.map((group, i) => (
            <Citations key={i} group={group} t={t} />
          ))}
          {explained.explanation ? (
            <ExplanationList body={explained.explanation} t={t} />
          ) : (
            <p className="ea-muted" data-testid="explain-missing">
              {t("explain.missing")}
            </p>
          )}
          {explained.agentText && (
            // Model-authored text, after every fact, with the server's label (ADR 0034 §4).
            <figure
              className="ea-explain-words"
              data-testid="explain-agent-text"
              data-label={explained.agentText.label}
            >
              <figcaption>
                <strong>{t("outcome.agentText")}</strong>
                <span aria-hidden="true"> · </span>
                {labelText(t, explained.agentText.label)}
              </figcaption>
              <blockquote>
                {/* Inert text: React escapes it; no markup, link or image is made (AG-ID-2). */}
                <p className="ea-explain-words-text">{explained.agentText.text}</p>
              </blockquote>
            </figure>
          )}
        </>
      )}
    </Disclosure>
  );
}

function labelText(t: Translate, label: ValueLabel): string {
  return t(`explain.label.${label}`);
}

function orNot(t: Translate, value: string | null): string {
  return value ?? t("explain.notRecorded");
}

function Citations({ group, t }: { group: CitationGroup; t: Translate }) {
  return (
    <section className="ea-citations" data-testid="citations" data-origin={group.origin}>
      <h4 className="ea-subtitle">{t("citation.title")}</h4>
      <ol className="ea-citation-list">
        {group.citations.map((c, i) => (
          <CitationItem key={i} citation={c} t={t} />
        ))}
      </ol>
    </section>
  );
}

function CitationItem({ citation, t }: { citation: CitationView; t: Translate }) {
  const { locale } = useI18n();
  if (citation.kind === "unresolved") {
    // Named nothing in the run: no id, pointer or digest, never a fact (ADR 0034 §3).
    return (
      <li className="ea-citation ea-citation-unresolved" data-testid="citation-unresolved">
        <span aria-hidden="true">？ </span>
        {t("citation.unresolved")}
      </li>
    );
  }
  const value = citation.value;
  return (
    <li className="ea-citation" data-testid="citation" data-label={citation.label ?? undefined}>
      <dl className="ea-meta">
        <div>
          <dt>{t("citation.record")}</dt>
          <dd data-testid="citation-record">
            {citation.evidenceId} ·{" "}
            {citation.contractId ? readableLabel(citation.contractId) : t("explain.notRecorded")} ·{" "}
            {t("explain.revision")} {orNot(t, citation.revision)}
          </dd>
        </div>
        <div>
          <dt>{t("citation.field")}</dt>
          <dd data-testid="citation-field" className="ea-mono">
            {citation.pointer === "" ? '""' : citation.pointer}
          </dd>
        </div>
        <div>
          <dt>{t("citation.value")}</dt>
          <dd
            data-testid="citation-value"
            data-recorded={String(value.kind === "recorded")}
            className={value.kind === "recorded" ? undefined : "ea-muted"}
          >
            {value.kind === "recorded"
              ? typeof value.value === "string" && value.value !== ""
                ? formatFieldValue(value.key ?? "", value.value, locale)
                : JSON.stringify(value.value)
              : t("citation.valueNotRecorded")}
          </dd>
        </div>
      </dl>
      {citation.label && <small className="ea-muted">{labelText(t, citation.label)}</small>}
    </li>
  );
}

function Section({ name, title, children }: { name: string; title: string; children: ReactNode }) {
  return (
    <div data-testid="explain-section" data-section={name}>
      <dt>{title}</dt>
      <dd>{children}</dd>
    </div>
  );
}

function Items<T>({
  items,
  t,
  render,
}: {
  items: T[];
  t: Translate;
  render: (item: T, i: number) => ReactNode;
}) {
  if (items.length === 0) return <span className="ea-muted">{t("explain.none")}</span>;
  return <ul className="ea-explain-items">{items.map(render)}</ul>;
}

function Label({ t, label }: { t: Translate; label: ValueLabel }) {
  return (
    <small className="ea-muted" data-label={label}>
      {" "}
      · {labelText(t, label)}
    </small>
  );
}

function ExplanationList({ body, t }: { body: ExplanationBody; t: Translate }) {
  const rationales = body.proposals.flatMap(p => p.rationales);
  return (
    <>
      {body.completeness !== "known" && (
        <p className="ea-muted ea-small" data-testid="explain-partial" data-completeness={body.completeness}>
          {t("explain.partial")}
        </p>
      )}
      <dl className="ea-meta ea-explain-list" data-testid="explain-list">
        <Section name="goal" title={t("explain.goal")}>
          {body.goal ?? <span className="ea-muted">{t("explain.notRecorded")}</span>}
        </Section>
        <Section name="facts" title={t("explain.facts")}>
          <Items
            items={body.sources}
            t={t}
            render={s => (
              <li key={s.evidenceId}>
                {s.contractId ? readableLabel(s.contractId) : t("explain.notRecorded")} ·{" "}
                {t("explain.revision")} {orNot(t, s.revision)} ·{" "}
                <span className="ea-mono">{s.evidenceId}</span>
                <Label t={t} label={s.label} />
              </li>
            )}
          />
        </Section>
        <Section name="rules" title={t("explain.rules")}>
          <Items
            items={body.rules}
            t={t}
            render={(r, i) => (
              <li key={`${r.ruleId}-${i}`}>
                <span className="ea-mono">{r.ruleId}</span> · v{orNot(t, r.ruleVersion)} ·{" "}
                {orNot(t, r.status)}
              </li>
            )}
          />
        </Section>
        <Section name="proposal" title={t("explain.proposal")}>
          <Items
            items={body.proposals}
            t={t}
            render={(p, i) => (
              <li key={p.actionId ?? i}>
                {p.contractId ? readableLabel(p.contractId) : t("explain.notRecorded")} ·{" "}
                {p.state ? t(actionStatusKey(p.state)) : t("explain.notRecorded")}
                <Label t={t} label={p.label} />
                {p.digest && <code className="ea-digest">{p.digest}</code>}
              </li>
            )}
          />
        </Section>
        <Section name="rationale" title={t("explain.rationale")}>
          <Items
            items={rationales}
            t={t}
            render={(r, i) => (
              <li key={i}>
                {r.stepId && (
                  <>
                    {t("explain.step")} <span className="ea-mono">{r.stepId}</span> ·{" "}
                  </>
                )}
                {[...r.citedEvidence, ...r.rulesConsidered].map(id => (
                  <span key={id} className="ea-mono">
                    {id}{" "}
                  </span>
                ))}
                {r.unresolvedRefs > 0 && (
                  <span className="ea-muted">
                    · {t("explain.unresolvedRefs")}: {r.unresolvedRefs}{" "}
                  </span>
                )}
                <Label t={t} label={r.label} />
                {r.summaryDigest && <code className="ea-digest">{r.summaryDigest}</code>}
                <small className="ea-muted ea-block">{t("explain.rationaleIds")}</small>
              </li>
            )}
          />
        </Section>
        <Section name="approval" title={t("explain.approval")}>
          <Items
            items={body.approvals}
            t={t}
            render={(a, i) => (
              <li key={i}>
                {orNot(t, a.decision)} · {orNot(t, a.actorId)} · {t("explain.policy")}{" "}
                {orNot(t, a.policyVersion)}
                <Label t={t} label={a.label} />
              </li>
            )}
          />
        </Section>
        <Section name="receipt" title={t("explain.receipt")}>
          <Items
            items={body.receipts}
            t={t}
            render={(r, i) => (
              <li key={i}>
                {orNot(t, r.status)}
                {r.externalRefs && r.externalRefs.length > 0 && <> · {r.externalRefs.join(", ")}</>}
                <Label t={t} label={r.label} />
              </li>
            )}
          />
        </Section>
        <Section name="outcome" title={t("explain.outcome")}>
          <Items
            items={body.outcomes}
            t={t}
            render={(o, i) => (
              <li key={o.actionId ?? i} data-testid="explain-outcome" data-label={o.label}>
                <strong>{labelText(t, o.label)}</strong> · {orNot(t, o.status)}
              </li>
            )}
          />
        </Section>
      </dl>
    </>
  );
}
