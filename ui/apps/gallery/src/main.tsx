/**
 * Development-only component gallery (frontend development guide §7). Each entry
 * documents a primitive's purpose, props, states, focus behavior and one reuse
 * example, against neutral fixture data. It reuses the production components; it
 * never re-implements them and never drives a real run.
 */
import "@e-agent/tokens/tokens.css";
import "@e-agent/components/components.css";
import "@e-agent/layouts/layouts.css";
import "./gallery.css";
import { StrictMode, useState, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import { EAgentClient } from "@e-agent/client";
import { PRESENTATION_OPTIONS } from "@e-agent/layouts";
import { RunController, translate, type Locale } from "@e-agent/ui-core";
import { RunProvider, useI18n } from "@e-agent/ui-react";
import {
  ActionButton,
  BrandMark,
  BUTTON_VARIANTS,
  Disclosure,
  STATUS_TONES,
  SURFACE_TONES,
  StatusBadge,
  Surface,
  TextAreaField,
} from "@e-agent/components";
import { LONG_VALUE } from "./fixtures.ts";

// A controller is required for the i18n context only. `init()` is never called, so
// the gallery performs no session, run or approval request.
const controller = new RunController({ client: new EAgentClient(), storage: null });

function Entry({
  name,
  purpose,
  props,
  states,
  focus,
  example,
  children,
}: {
  name: string;
  purpose: string;
  props: string;
  states: string;
  focus: string;
  example: string;
  children: ReactNode;
}) {
  return (
    <section className="gal-entry">
      <h2>{name}</h2>
      <p className="gal-purpose">{purpose}</p>
      <dl className="gal-spec">
        <dt>Props</dt>
        <dd>{props}</dd>
        <dt>States</dt>
        <dd>{states}</dd>
        <dt>Focus</dt>
        <dd>{focus}</dd>
      </dl>
      <div className="gal-demo">{children}</div>
      <pre className="gal-example">{example}</pre>
    </section>
  );
}

function Gallery() {
  const { t } = useI18n();
  return (
    <>
      <Entry
        name="ActionButton"
        purpose="The one button contract. Forwards every React Aria prop, ref and data attribute; adds a token-driven variant and a consistent pending state."
        props="variant: primary | default | quiet · isDisabled · isPending · plus all React Aria Button props"
        states="rest, hovered, pressed, focus-visible, disabled, pending (disabled but still named)"
        focus="Native button focus with a 3px token outline. Pending does not move or remove focus."
        example={'<ActionButton variant="primary" onPress={submit}>Send task</ActionButton>'}
      >
        {BUTTON_VARIANTS.map(variant => (
          <div className="gal-row" key={variant}>
            <ActionButton variant={variant}>{variant}</ActionButton>
            <ActionButton variant={variant} isDisabled>
              {variant} disabled
            </ActionButton>
            <ActionButton variant={variant} isPending>
              {variant} pending
            </ActionButton>
          </div>
        ))}
      </Entry>

      <Entry
        name="BrandMark"
        purpose="The owner-approved product mark (Sage Lagoon, 15° clockwise, 35° backward tilt, subtle depth, no shadow, glossy). Shipped as one SVG; never recoloured, redrawn or tinted per theme."
        props="className · size comes from the caller's CSS (default 2rem)"
        states="One. The mark stays the same in light, dark and high contrast; the product name beside it carries meaning."
        focus="Not interactive and decorative (aria-hidden). Always pair it with visible text such as the product name."
        example={"<BrandMark /> <span>e-agent</span>"}
      >
        <div className="gal-row">
          <BrandMark />
          <BrandMark className="gal-brand-large" />
          <span>e-agent</span>
        </div>
      </Entry>

      <Entry
        name="StatusBadge"
        purpose="Status that never depends on color alone: each tone pairs a token color with a shape marker and the caller's own text."
        props="tone: neutral | progress | attention | verified | failed | unknown · children"
        states="One per tone. Unknown is distinct from failed and from verified."
        focus="Not interactive. Callers add role=status when the value changes during a task."
        example={'<StatusBadge tone="unknown">Result not confirmed</StatusBadge>'}
      >
        <div className="gal-row">
          {STATUS_TONES.map(tone => (
            <StatusBadge key={tone} tone={tone}>
              {tone}
            </StatusBadge>
          ))}
        </div>
      </Entry>

      <Entry
        name="Surface"
        purpose="Token-driven container role. Geometry belongs to the layout; the surface only carries background, border and optional elevation."
        props="as · tone: card | sunken | accent | attention | failed | verified · elevated"
        states="Flat and elevated. High contrast removes the shadow through the token, not a conditional."
        focus="Not interactive. It must not trap or outline focus of its contents."
        example={'<Surface as="section" tone="attention">Result not confirmed…</Surface>'}
      >
        <div className="gal-grid">
          {SURFACE_TONES.map(tone => (
            <Surface key={tone} tone={tone} className="gal-surface">
              <strong>{tone}</strong>
              <p className="ea-small ea-muted">{LONG_VALUE}</p>
            </Surface>
          ))}
        </div>
      </Entry>

      <Entry
        name="Disclosure"
        purpose="Progressive detail on native details/summary, so keyboard operation, the accessible name and find-in-page keep working."
        props="summary · count · badge · defaultOpen · children"
        states="Closed, open, open-by-default (used when a check did not pass), with count, with badge."
        focus="Summary is the focus target and toggles with Enter or Space."
        example={'<Disclosure summary="Validation checks" defaultOpen={!allPassed}>…</Disclosure>'}
      >
        <Surface className="gal-surface">
          <Disclosure summary="Closed by default" count={3}>
            <p className="ea-small">Detail revealed on request.</p>
          </Disclosure>
          <Disclosure
            summary="Open by default"
            defaultOpen
            badge={<span className="ea-check-pass">✓ passed</span>}
          >
            <p className="ea-small">A failing check opens itself so nothing is hidden behind a click.</p>
          </Disclosure>
          <Disclosure summary={LONG_VALUE}>
            <p className="ea-small">Long summaries wrap instead of overflowing.</p>
          </Disclosure>
        </Surface>
      </Entry>

      <Entry
        name="TextAreaField"
        purpose="Multi-line input with a required accessible label and explicit description and error slots, so a hint is never carried by placeholder text alone."
        props="label · value · onChange · placeholder · description · errorMessage · isDisabled · rows · onKeyDown"
        states="Empty, filled, long value, disabled, invalid with a message."
        focus="The textarea is the focus target; the label is programmatic and may be visually hidden."
        example={'<TextAreaField label={t("composer.label")} value={draft} onChange={setDraft} />'}
      >
        <Surface className="gal-surface">
          <FieldExamples />
        </Surface>
      </Entry>

      <Entry
        name="Localized labels"
        purpose="Every visible string resolves through the shared catalogs. The gallery switches locale with the same translate() the product uses."
        props="useI18n(): { locale, t }"
        states="EN and VI, including the longer Vietnamese labels."
        focus="Not applicable."
        example={'const { t } = useI18n();  t("approval.approve")'}
      >
        <dl className="gal-spec">
          {["approval.approve", "outcome.effectUnknown", "composer.locked"].map(key => (
            <div key={key}>
              <dt>{key}</dt>
              <dd>{t(key)}</dd>
            </div>
          ))}
        </dl>
      </Entry>
    </>
  );
}

function FieldExamples() {
  const [value, setValue] = useState("");
  return (
    <>
      <TextAreaField label="Empty" value={value} onChange={setValue} placeholder="Describe what you need…" />
      <TextAreaField
        label="Long value"
        value={LONG_VALUE}
        onChange={() => {}}
        description="Values wrap; they are never truncated."
      />
      <TextAreaField
        label="Disabled"
        value=""
        onChange={() => {}}
        isDisabled
        placeholder="Unavailable right now"
      />
      <TextAreaField
        label="Invalid"
        value="x"
        onChange={() => {}}
        errorMessage="This value is not accepted."
      />
    </>
  );
}

function Shell() {
  const [locale, setLocale] = useState<Locale>("en");
  const [values, setValues] = useState({ theme: "light", appearance: "calm", density: "comfortable" });
  const apply = (dimension: "theme" | "appearance" | "density", value: string) => {
    setValues(current => ({ ...current, [dimension]: value }));
    document.documentElement.dataset[dimension] = value;
  };
  const setGalleryLocale = (next: Locale) => {
    setLocale(next);
    controller.setLocale(next);
    document.documentElement.lang = next;
  };
  return (
    <div className="gal-root">
      <header className="gal-header">
        <h1>Component gallery</h1>
        <p className="ea-small ea-muted">
          Development only · neutral fixture data · no server, run or approval is reachable from this page.
        </p>
        <div className="gal-row">
          {(Object.keys(PRESENTATION_OPTIONS) as ("theme" | "appearance" | "density")[]).map(dimension => (
            <label key={dimension}>
              {dimension}
              <select value={values[dimension]} onChange={e => apply(dimension, e.target.value)}>
                {PRESENTATION_OPTIONS[dimension].map(option => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            </label>
          ))}
          <label>
            locale
            <select value={locale} onChange={e => setGalleryLocale(e.target.value as Locale)}>
              <option value="en">en</option>
              <option value="vi">vi</option>
            </select>
          </label>
        </div>
        <p className="ea-small ea-muted">{translate(locale, "workspace.safe")}</p>
      </header>
      <Gallery />
    </div>
  );
}

createRoot(document.getElementById("root") as HTMLElement).render(
  <StrictMode>
    <RunProvider controller={controller}>
      <Shell />
    </RunProvider>
  </StrictMode>,
);
