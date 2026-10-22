/**
 * The default activity slot: the attached run's recorded events, then, once the run has a
 * result, its explanation (ADR 0034 §4: the explanation opens from the outcome and from the
 * timeline). Features compose here, never through each other. A layout that shows another
 * run's events renders `Timeline` with that run's items; it has no bundle for that run in
 * this view, so it offers no explanation.
 */
import { hasResult } from "@e-agent/ui-core";
import { useRun } from "@e-agent/ui-react";
import { Explanation } from "../features/outcome/Explanation.tsx";
import { Timeline } from "../features/timeline/Timeline.tsx";

export function Activity() {
  const { run } = useRun();
  return (
    <>
      <Timeline />
      {hasResult(run?.state) && <Explanation testId="timeline-explanation" />}
    </>
  );
}
