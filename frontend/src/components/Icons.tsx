/**
 * Hand-written inline SVG glyphs (T23).
 *
 * The redesign may not add an icon package (SPEC `## Boundaries → Ask first`),
 * so every glyph is a small inline SVG drawn from the same 24px grid. They are
 * decorative: `aria-hidden` and `focusable="false"` keep them out of the
 * accessibility tree, and the surrounding link or button carries the name.
 */

import type { ReactElement } from "react";

export interface IconProps {
  className?: string;
}

const base = {
  width: 24,
  height: 24,
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.7,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  "aria-hidden": true,
  focusable: "false" as const,
};

/** The product mark: a compact square with an abstract “K” fold. */
export function BrandMark({ className }: IconProps): ReactElement {
  return (
    <svg {...base} className={className}>
      <rect x="3" y="3" width="18" height="18" rx="5" />
      <path d="M8.5 7.5v9" />
      <path d="M15.5 7.5 9.5 12l6 4.5" />
    </svg>
  );
}

/** Library: a stack of documents. */
export function LibraryIcon({ className }: IconProps): ReactElement {
  return (
    <svg {...base} className={className}>
      <path d="M6 4.5h9.5a2 2 0 0 1 2 2V19H8a2 2 0 0 1-2-2z" />
      <path d="M6 17h11.5" />
      <path d="M9.5 8.5h4" />
    </svg>
  );
}

/** Chat: a speech bubble. */
export function ChatIcon({ className }: IconProps): ReactElement {
  return (
    <svg {...base} className={className}>
      <path d="M20 11.5a7.5 7.5 0 0 1-10.9 6.7L4 20l1.8-5.1A7.5 7.5 0 1 1 20 11.5Z" />
      <path d="M8.5 11.5h7" />
    </svg>
  );
}

/** Eval dashboard: a small bar chart. */
export function EvalIcon({ className }: IconProps): ReactElement {
  return (
    <svg {...base} className={className}>
      <path d="M4 20h16" />
      <path d="M7 20v-5" />
      <path d="M12 20V8" />
      <path d="M17 20v-9" />
    </svg>
  );
}

/** Search: a magnifier. */
export function SearchIcon({ className }: IconProps): ReactElement {
  return (
    <svg {...base} className={className}>
      <circle cx="10.5" cy="10.5" r="6" />
      <path d="m15 15 4.5 4.5" />
    </svg>
  );
}

/** The inert top-bar avatar: a generic person, not a user record. */
export function UserIcon({ className }: IconProps): ReactElement {
  return (
    <svg {...base} className={className}>
      <circle cx="12" cy="9" r="3.5" />
      <path d="M5.5 19a6.5 6.5 0 0 1 13 0" />
    </svg>
  );
}

/** A document page, used by each library card's icon chip. */
export function DocumentIcon({ className }: IconProps): ReactElement {
  return (
    <svg {...base} className={className}>
      <path d="M7 3.5h6.5L18.5 8v12.5H7z" />
      <path d="M13.5 3.5V8h5" />
      <path d="M10 12h5" />
      <path d="M10 15.5h5" />
    </svg>
  );
}

/** Golden set: a checked list. */
export function GoldenIcon({ className }: IconProps): ReactElement {
  return (
    <svg {...base} className={className}>
      <path d="m4.5 7.5 1.5 1.5 3-3" />
      <path d="m4.5 14 1.5 1.5 3-3" />
      <path d="M12.5 7.5H20" />
      <path d="M12.5 14H20" />
      <path d="M12.5 20H20" />
    </svg>
  );
}

/** Document detail: an information mark. */
export function DetailIcon({ className }: IconProps): ReactElement {
  return (
    <svg {...base} className={className}>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 11v5.5" />
      <path d="M12 7.5h.01" />
    </svg>
  );
}

/** Embedder id: a small node lattice. */
export function EmbedderIcon({ className }: IconProps): ReactElement {
  return (
    <svg {...base} className={className}>
      <circle cx="7" cy="7" r="2" />
      <circle cx="17" cy="7" r="2" />
      <circle cx="7" cy="17" r="2" />
      <circle cx="17" cy="17" r="2" />
      <path d="m8.8 8.8 6.4 6.4" />
      <path d="m15.2 8.8-6.4 6.4" />
    </svg>
  );
}

/** Scorer id: a verification check. */
export function ScorerIcon({ className }: IconProps): ReactElement {
  return (
    <svg {...base} className={className}>
      <path d="M12 3.5 19 6v5.5c0 4.2-2.9 7.5-7 9-4.1-1.5-7-4.8-7-9V6z" />
      <path d="m8.5 12 2.5 2.5 4.5-4.5" />
    </svg>
  );
}

/** A small arrow, used by links inside the cards. */
export function ArrowIcon({ className }: IconProps): ReactElement {
  return (
    <svg {...base} width={16} height={16} className={className}>
      <path d="M5 12h14" />
      <path d="m13 6 6 6-6 6" />
    </svg>
  );
}
