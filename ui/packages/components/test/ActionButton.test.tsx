// @vitest-environment happy-dom
/**
 * The pending contract this primitive documents: a request in flight must not take
 * the control out of the tab order, drop its accessible name or let a second
 * submission through. Disabled is the different, stronger state.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { ActionButton } from "../src/primitives/ActionButton.tsx";

afterEach(cleanup);

describe("ActionButton states", () => {
  it("keeps a pending control focusable, named and non-activating", async () => {
    const onPress = vi.fn();
    render(
      <ActionButton isPending onPress={onPress} data-testid="send">
        Send task
      </ActionButton>,
    );
    const button = screen.getByTestId("send");
    expect(button.hasAttribute("disabled")).toBe(false);
    expect(button.getAttribute("aria-disabled")).toBe("true");
    expect(button.hasAttribute("data-pending")).toBe(true);
    expect(button.textContent).toContain("Send task");

    button.focus();
    expect(document.activeElement).toBe(button);
    button.click();
    expect(onPress).not.toHaveBeenCalled();
  });

  it("removes a disabled control from the tab order and from activation", () => {
    const onPress = vi.fn();
    render(
      <ActionButton isDisabled onPress={onPress} data-testid="approve">
        Confirm
      </ActionButton>,
    );
    const button = screen.getByTestId("approve");
    expect(button.hasAttribute("disabled")).toBe(true);
    button.click();
    expect(onPress).not.toHaveBeenCalled();
  });

  it("applies the requested variant and keeps consumer class names", () => {
    render(
      <ActionButton variant="primary" className="ea-launcher" data-testid="launcher">
        Open
      </ActionButton>,
    );
    expect(screen.getByTestId("launcher").className).toBe("ea-button ea-button-primary ea-launcher");
  });
});
