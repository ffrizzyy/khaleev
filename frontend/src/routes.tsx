/**
 * The route table and the shared R1 shell (T23).
 *
 * `AppShell` owns the frame, the icon rail, the top bar and the content area;
 * each route fills that content area. URLs and page components are unchanged.
 */

import { Route, Routes } from "react-router-dom";

import { AppShell } from "./components/AppShell";
import { Chat } from "./pages/Chat";
import { EvalDashboard } from "./pages/EvalDashboard";
import { Library } from "./pages/Library";

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
      <Route path="/" element={<AppShell />}>
        <Route index element={<Library />} />
        <Route path="chat" element={<Chat />} />
        <Route path="evals" element={<EvalDashboard />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}
