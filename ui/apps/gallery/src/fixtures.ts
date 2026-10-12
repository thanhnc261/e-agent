/**
 * Neutral gallery data. It never touches a controller, a server or a provider, so
 * nothing here can start a run, approve anything or name a real integration.
 */
export const LONG_VALUE =
  "a-very-long-identifier-that-must-stay-readable-00000000-1111-2222-3333-444444444444";

export const SAMPLE_TERMS = [
  { label: "Quantity", value: "40", changed: true, previous: "7" },
  { label: "Unit price", value: "100", changed: false, previous: "100" },
  { label: "Reference", value: LONG_VALUE, changed: false, previous: null },
];
