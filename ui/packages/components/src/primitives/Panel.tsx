/** Labelled region primitive. Props only: no run hooks, no transport. */
import { useId, type ReactNode } from "react";

export function Panel({
  title,
  children,
  className = "",
  testId,
}: {
  title: string;
  children: ReactNode;
  className?: string;
  testId?: string;
}) {
  const id = useId();
  return (
    <section className={`ea-panel ${className}`} aria-labelledby={id} data-testid={testId}>
      <h2 id={id} className="ea-panel-title">
        {title}
      </h2>
      {children}
    </section>
  );
}
