/**
 * Progressive detail. Native `details`/`summary` keeps keyboard operation, the
 * accessible name and find-in-page behavior that a custom widget would lose.
 */
import type { ReactNode, Ref } from "react";

export function Disclosure({
  summary,
  children,
  count,
  badge,
  defaultOpen = false,
  className = "",
  ref,
  ...rest
}: {
  summary: ReactNode;
  children: ReactNode;
  /** Shown after the summary; a count of zero still renders, unknown does not. */
  count?: number | string;
  badge?: ReactNode;
  defaultOpen?: boolean;
  className?: string;
  ref?: Ref<HTMLDetailsElement>;
} & Record<string, unknown>) {
  return (
    <details
      {...rest}
      ref={ref}
      open={defaultOpen || undefined}
      className={`ea-disclosure ${className}`.trim()}
    >
      <summary>
        <span className="ea-disclosure-label">{summary}</span>
        {count !== undefined && <span className="ea-count">{count}</span>}
        {badge}
      </summary>
      {children}
    </details>
  );
}
