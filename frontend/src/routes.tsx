/**
 * The app shell: one shared layout plus the three SPEC routes.
 *
 * The page bodies here start as intentional placeholders so the shell is
 * navigable and testable before the feature slices land. T11 filled `/`
 * (Library); T12 fills `/chat` (Chat) and T18 fills `/evals` (EvalDashboard);
 * each swap only replaces the `element` of its route, leaving the layout and
 * URLs untouched.
 */

import { NavLink, Outlet, Route, Routes } from "react-router-dom";

import { Library } from "./pages/Library";

/** Shared chrome: product heading, the promise, and primary navigation. */
function AppLayout() {
  return (
    <div>
      <header>
        <h1>Khaleev</h1>
        <p>Local-first document Q&amp;A with page-cited answers and evaluation metrics.</p>
        <nav aria-label="Primary">
          <NavLink to="/" end>
            Library
          </NavLink>
          <NavLink to="/chat">Chat</NavLink>
          <NavLink to="/evals">Eval dashboard</NavLink>
        </nav>
      </header>
      <main>
        <Outlet />
      </main>
    </div>
  );
}

/** Placeholder for the Chat page (F3), replaced by T12. */
function ChatPlaceholder() {
  return (
    <section aria-labelledby="chat-heading">
      <h2 id="chat-heading">Chat</h2>
      <p>Ask a question about the selected document and read the page-cited answer.</p>
    </section>
  );
}

/** Placeholder for the eval dashboard (F6), replaced by T18. */
function EvalDashboardPlaceholder() {
  return (
    <section aria-labelledby="evals-heading">
      <h2 id="evals-heading">Eval dashboard</h2>
      <p>Retrieval hit rate and answer faithfulness for each eval run, with history.</p>
    </section>
  );
}

function NotFound() {
  return (
    <section aria-labelledby="not-found-heading">
      <h2 id="not-found-heading">Page not found</h2>
      <p>That address does not exist. Use the navigation above.</p>
    </section>
  );
}

/** The route table; `App` mounts it inside a `BrowserRouter`. */
export function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<AppLayout />}>
        <Route index element={<Library />} />
        <Route path="chat" element={<ChatPlaceholder />} />
        <Route path="evals" element={<EvalDashboardPlaceholder />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}
