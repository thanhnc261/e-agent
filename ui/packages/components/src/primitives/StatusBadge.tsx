/**
 * Status is never carried by color alone: every tone pairs a token color with a
 * shape marker and the caller's text.
 */
import type { ReactNode } from "react";
import type { StatusTone } from "./variants.ts";

const MARKER: Record<StatusTone, string> = {
  neutral: "·",
  progress: "◍",
  attention: "◆",
  verified: "✓",
  failed: "✕",
  unknown: "？",
};

export function StatusBadge({
  tone = "neutral",
  children,
  className = "",
  ...rest
}: {
  tone?: StatusTone;
  children: ReactNode;
  className?: string;
} & Omit<React.HTMLAttributes<HTMLSpanElement>, "className" | "children">) {
  return (
    <span {...rest} className={`ea-badge ea-badge-${tone} ${className}`.trim()} data-tone={tone}>
      <span className="ea-badge-marker" aria-hidden="true">
        {MARKER[tone]}
      </span>
      {children}
    </span>
  );
}
