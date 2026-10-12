/** Small, decorative navigation glyphs. Meaning stays in the adjacent label. */
const paths = {
  home: "M3 10 12 3l9 7v10a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1Z",
  work: "M8 5V3h8v2M3 9h18M4 5h16a1 1 0 0 1 1 1v14H3V6a1 1 0 0 1 1-1ZM9 13h6",
  connections:
    "M8 8h8v8H8ZM3 3h3v3H3ZM18 3h3v3h-3ZM3 18h3v3H3ZM18 18h3v3h-3ZM6 6l2 2m8 0 2-2M6 18l2-2m8 0 2 2",
  settings: "M4 7h16M4 17h16M8 4v6m8 4v6",
  task: "M7 3h10l3 3v15H4V3h3Zm1 5h5m-5 5h8m-8 4h5",
  shield: "M12 3 4 6v6c0 5 8 9 8 9s8-4 8-9V6ZM8 12l3 3 5-6",
} as const;
export function Icon({ name, className = "" }: { name: keyof typeof paths; className?: string }) {
  return (
    <svg
      className={`ea-icon ${className}`}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      <path d={paths[name]} />
    </svg>
  );
}
