/** Formatting that never converts decimal strings to binary floats. */

export function formatDecimal(value: string, locale: string): string {
  const m = /^(-?)(\d+)(?:\.(\d+))?$/.exec(value.trim());
  if (!m) return value;
  const [, sign, int = "0", frac] = m;
  const vi = locale.startsWith("vi");
  const group = vi ? "." : ",";
  const point = vi ? "," : ".";
  const grouped = int.replace(/\B(?=(\d{3})+(?!\d))/g, group);
  return `${sign}${grouped}${frac ? point + frac : ""}`;
}

export function formatDateTime(iso: string, locale: string): string {
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return iso;
  return new Intl.DateTimeFormat(locale, { dateStyle: "short", timeStyle: "medium" }).format(t);
}

const DECIMAL_FIELD = /(quantity|price|subtotal|amount|total|available|inbound|shortage)$/;

/** Values in approval tables: decimals by field name, everything else verbatim. */
export function formatFieldValue(path: string, value: string, locale: string): string {
  return DECIMAL_FIELD.test(path) ? formatDecimal(value, locale) : value;
}
