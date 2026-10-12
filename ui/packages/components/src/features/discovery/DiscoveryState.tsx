/**
 * Shared rendering of the non-ready discovery states. Loading, denied, unsupported
 * and error each read differently on purpose: none of them may be mistaken for
 * "there is nothing here".
 */
import type { DiscoveryState } from "@e-agent/ui-core";
import { useI18n } from "@e-agent/ui-react";

export function DiscoveryStatus<T>({ state, testId }: { state: DiscoveryState<T>; testId: string }) {
  const { t } = useI18n();
  if (state.kind === "ready") return null;
  const key =
    state.kind === "loading"
      ? "discovery.loading"
      : state.kind === "denied"
        ? "discovery.denied"
        : state.kind === "unsupported"
          ? "discovery.unsupported"
          : state.kind === "malformed"
            ? "discovery.malformed"
            : state.kind === "error"
              ? "discovery.error"
              : "discovery.idle";
  const faulted = state.kind === "error" || state.kind === "malformed";
  return (
    <p
      className={`ea-small ${faulted ? "ea-alert ea-error" : "ea-muted"}`}
      role={state.kind === "loading" ? "status" : faulted ? "alert" : undefined}
      data-testid={testId}
      data-state={state.kind}
    >
      {t(key)}
    </p>
  );
}
