import { useController } from "../providers/RunProvider.tsx";
import { useRunState } from "./useRunState.ts";

/** Draft text is controller state so it survives layout and route changes. */
export function useComposer() {
  const c = useController();
  const s = useRunState();
  return {
    busy: s.busy,
    draft: s.draft,
    setDraft: (draft: string) => c.setDraft(draft),
    submit: (task: string) => c.start(task),
  };
}
