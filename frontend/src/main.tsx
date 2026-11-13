import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";

// The whole UI is styled by hand-written CSS, imported exactly once, here.
// No component imports a stylesheet of its own (T21).
import "./styles/tokens.css";
import "./styles/base.css";
import "./styles/components.css";
import "./styles/responsive.css";

const container = document.getElementById("root");

if (!container) {
  throw new Error("Khaleev: #root element is missing from index.html");
}

createRoot(container).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
