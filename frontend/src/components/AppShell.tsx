/**
 * The R1 app shell (T23): tinted canvas, one inset rounded panel, an icon rail,
 * the pill-search top bar and the content area.
 *
 * Layout only — the product's own destinations fill the rail and the top bar:
 *
 * * the rail is the `Primary` navigation landmark with the three real routes,
 *   icon-only (`aria-label`) so it stays keyboard-reachable and announced as
 *   links, and `NavLink` supplies `aria-current="page"` on the active route;
 * * the product name survives as a visually hidden `<h1>` because R1 forbids
 *   visible rail labels but the document still needs exactly one top heading;
 * * the top-bar icon buttons are links to real destinations, deliberately named
 *   "Go to Library" / "Go to the Eval dashboard" so they never collide with the
 *   rail's exact names, and the avatar is inert, decorative chrome.
 *
 * The search field is a real labelled `<input type="search">`. SPEC has no
 * search endpoint, so it only writes shared client state; the Library filters
 * its already-loaded list from that value.
 */

import { useId } from "react";
import type { ChangeEvent, ReactElement } from "react";
import { Link, NavLink, Outlet } from "react-router-dom";

import { setSearchQuery, useSearchQuery } from "../state/searchQuery";
import { BrandMark, ChatIcon, EvalIcon, LibraryIcon, SearchIcon, UserIcon } from "./Icons";

export function AppShell(): ReactElement {
  const searchId = useId();
  const query = useSearchQuery();

  function handleSearchChange(event: ChangeEvent<HTMLInputElement>): void {
    setSearchQuery(event.currentTarget.value);
  }

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

      <div className="app-body">
        <header className="topbar">
          <div className="search">
            <SearchIcon className="search__icon" />
            <label className="visually-hidden" htmlFor={searchId}>
              Search documents
            </label>
            <input
              className="search__input"
              id={searchId}
              type="search"
              placeholder="Search documents"
              autoComplete="off"
              value={query}
              onChange={handleSearchChange}
            />
          </div>
          <div className="topbar__actions">
            <Link className="icon-button" to="/" aria-label="Go to Library" title="Go to Library">
              <LibraryIcon />
            </Link>
            <Link
              className="icon-button"
              to="/evals"
              aria-label="Go to the Eval dashboard"
              title="Go to the Eval dashboard"
            >
              <EvalIcon />
            </Link>
            <span className="avatar" aria-hidden="true">
              <UserIcon />
            </span>
          </div>
        </header>

        <main className="app-main">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
