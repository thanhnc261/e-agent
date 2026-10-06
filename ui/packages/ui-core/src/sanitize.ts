/**
 * Model text policy (threat model T1, conformance §6.4): text is never parsed as
 * HTML or markdown. Images are never loaded; links are shown with their full URL
 * and only http(s) URLs become links. Renderers must use text nodes only.
 */
export type TextSegment =
  | { kind: "text"; text: string }
  | { kind: "link"; text: string; href: string }
  | { kind: "image"; alt: string; url: string };

const TOKEN = /!\[([^\]]*)\]\(([^)\s]+)\)|\[([^\]]+)\]\(([^)\s]+)\)|(https?:\/\/[^\s<>()]+)/g;

function safeHref(url: string): string | null {
  try {
    const parsed = new URL(url);
    return parsed.protocol === "https:" || parsed.protocol === "http:" ? parsed.href : null;
  } catch {
    return null;
  }
}

export function segmentText(input: string, maxLength = 20_000): TextSegment[] {
  const text = input.length > maxLength ? `${input.slice(0, maxLength)}…` : input;
  const out: TextSegment[] = [];
  let last = 0;
  for (const m of text.matchAll(TOKEN)) {
    const start = m.index ?? 0;
    if (start > last) out.push({ kind: "text", text: text.slice(last, start) });
    if (m[2] !== undefined) {
      out.push({ kind: "image", alt: m[1] ?? "", url: m[2] });
    } else {
      const raw = m[4] ?? m[5] ?? "";
      const label = m[3];
      const href = safeHref(raw);
      if (href) {
        // Always show the full URL so the label cannot disguise the destination.
        out.push({ kind: "link", text: label ? `${label} (${href})` : href, href });
      } else {
        out.push({ kind: "text", text: m[0] });
      }
    }
    last = start + m[0].length;
  }
  if (last < text.length) out.push({ kind: "text", text: text.slice(last) });
  return out;
}
