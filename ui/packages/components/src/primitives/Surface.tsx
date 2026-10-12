/** Token-driven container. Geometry belongs to the layout, not to this primitive. */
import type { ElementType, ReactNode } from "react";
import type { SurfaceTone } from "./variants.ts";

export function Surface({
  as: Tag = "div",
  tone = "card",
  elevated = false,
  className = "",
  children,
  ...rest
}: {
  as?: ElementType;
  tone?: SurfaceTone;
  elevated?: boolean;
  className?: string;
  children: ReactNode;
} & Record<string, unknown>) {
  return (
    <Tag
      {...rest}
      className={`ea-surface ea-surface-${tone} ${elevated ? "ea-surface-raised" : ""} ${className}`.trim()}
    >
      {children}
    </Tag>
  );
}
