/**
 * The app shell: one shared layout plus the three SPEC routes.
 *
 * The page bodies are filled by their feature slices: T11 `/` (Library), T12
 * `/chat` (Chat) and T18 `/evals` (EvalDashboard); the layout and URLs stay
 * untouched.
 */

import { NavLink, Outlet, Route, Routes } from "react-router-dom";

import { Chat } from "./pages/Chat";
import { EvalDashboard } from "./pages/EvalDashboard";
import { Library } from "./pages/Library";

/** Shared chrome: product heading, the promise, and primary navigation. */
function AppLayout() {
  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="app-header__identity">
          <h1 className="app-title">Khaleev</h1>
          <p className="app-tagline">
            Local-first document Q&amp;A with page-cited answers and evaluation metrics.
          </p>
        </div>
        <nav className="app-nav" aria-label="Primary">
          <NavLink className="app-nav__link" to="/" end>
            Library
          </NavLink>
          <NavLink className="app-nav__link" to="/chat">
            Chat
          </NavLink>
          <NavLink className="app-nav__link" to="/evals">
            Eval dashboard
          </NavLink>
        </nav>
      </header>
      <main className="app-main">
        <Outlet />
      </main>
    </div>
  );
}

/** The catch-all for unknown addresses. */
function NotFound() {
  return (
    <section className="page page--not-found" aria-labelledby="not-found-heading">
      <h2 className="page__title" id="not-found-heading">
        Page not found
      </h2>
      <p className="page__lede">That address does not exist. Use the navigation above.</p>
    </section>
  );
}

/** The route table; `App` mounts it inside a `BrowserRouter`. */
export function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<AppLayout />}>
        <Route index element={<Library />} />
        <Route path="chat" element={<Chat />} />
        <Route path="evals" element={<EvalDashboard />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}
