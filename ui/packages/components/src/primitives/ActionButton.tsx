/**
 * Product button contract over React Aria. It forwards every consumer prop (ref,
 * press handlers, ARIA attributes, data-testid) so behavior stays the library's;
 * the wrapper only adds the token-driven variant.
 *
 * `isDisabled` and `isPending` are different states and are both forwarded to the
 * library rather than collapsed here. Disabled leaves the tab order. Pending keeps
 * the control focusable and keeps its accessible name, marks it `aria-disabled`,
 * suppresses activation and announces the work; a user who tabbed to Send does not
 * lose their place because a request is in flight.
 */
import { Button, type ButtonProps } from "react-aria-components";
import type { Ref } from "react";
import type { ButtonVariant } from "./variants.ts";

export interface ActionButtonProps extends Omit<ButtonProps, "className"> {
  variant?: ButtonVariant;
  /** Extra class names; the primitive always contributes `ea-button`. */
  className?: string;
  ref?: Ref<HTMLButtonElement>;
}

export function ActionButton({ variant = "default", className = "", ...props }: ActionButtonProps) {
  return <Button {...props} className={`ea-button ea-button-${variant} ${className}`.trim()} />;
}
