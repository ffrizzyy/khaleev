/**
 * The R1 app shell: tinted canvas, one inset rounded panel, the icon rail and
 * the content area.
 *
 * The top bar (pill search, the two circular icon links and the avatar) is
 * deliberately absent: locked intent 17 and the "Deviation from R1" note in
 * `SPEC.md` removed it, and no later task may restore it "for fidelity".
 *
 * Layout only — the product's own destinations fill the rail:
 *
 * * the rail is the `Primary` navigation landmark with the three real routes,
 *   icon-only (`aria-label`) so it stays keyboard-reachable and announced as
 *   links, and `NavLink` supplies `aria-current="page"` on the active route;
 * * the product name survives as a visually hidden `<h1>` because R1 forbids
 *   visible rail labels but the document still needs exactly one top heading.
 */

import type { ReactElement } from "react";
import { NavLink, Outlet } from "react-router-dom";

import { BrandMark, ChatIcon, EvalIcon, LibraryIcon } from "./Icons";

export function AppShell(): ReactElement {
  return (
    <div className="app-frame">
      <h1 className="visually-hidden">Khaleev</h1>

      <nav className="rail" aria-label="Primary">
        <span className="rail__brand">
          <BrandMark className="rail__brand-glyph" />
        </span>
        <div className="rail__links">
          <NavLink className="rail__link" to="/" end aria-label="Library" title="Library">
            <LibraryIcon />
          </NavLink>
          <NavLink className="rail__link" to="/chat" aria-label="Chat" title="Chat">
            <ChatIcon />
          </NavLink>
          <NavLink
            className="rail__link"
            to="/evals"
            aria-label="Eval dashboard"
            title="Eval dashboard"
          >
            <EvalIcon />
          </NavLink>
        </div>
      </nav>

      <main className="app-main">
        <Outlet />
      </main>
    </div>
  );
}
