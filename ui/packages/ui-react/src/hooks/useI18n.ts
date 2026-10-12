import { translate, type Locale } from "@e-agent/ui-core";
import { useRunState } from "./useRunState.ts";

export function useI18n(): { locale: Locale; t: (key: string) => string } {
  const locale = useRunState().locale;
  return { locale, t: (key: string) => translate(locale, key) };
}
